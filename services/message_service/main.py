from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
import uuid
import os
import base64
import hashlib
import hmac
import json
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from pymongo import MongoClient
from pymongo.errors import PyMongoError

app = FastAPI()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("message_service")


@app.middleware("http")
async def request_logging_middleware(request, call_next):
    start = time.perf_counter()
    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        status = getattr(response, "status_code", 500)
        duration_ms = (time.perf_counter() - start) * 1000.0
        logger.info(
            "request method=%s path=%s status=%s duration_ms=%.2f client=%s",
            request.method,
            request.url.path,
            status,
            duration_ms,
            request.client.host if request.client else "unknown",
        )

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://mongodb:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "messages_db")
MONGODB_USER = os.getenv("MONGO_USER", "admin")
MONGODB_PASSWORD = os.getenv("MONGO_PASSWORD")
CHAT_SERVICE_URL = os.getenv("CHAT_SERVICE_URL", "http://chat_service:8002")
GATEWAY_URL = os.getenv("API_GATEWAY_URL", "http://e2ee_api_gateway:8000")
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")


def get_mongo_client():
    try:
        if MONGODB_USER and MONGODB_PASSWORD:
            return MongoClient(
                MONGODB_URL,
                username=MONGODB_USER,
                password=MONGODB_PASSWORD,
                authSource="admin",
                serverSelectionTimeoutMS=5000
            )
        return MongoClient(MONGODB_URL, serverSelectionTimeoutMS=5000)
    except PyMongoError:
        raise HTTPException(status_code=503, detail="Database unavailable")


def _messages_collection():
    client = get_mongo_client()
    return client[MONGODB_DB].messages


def _post_event_to_gateway(event: dict):
    try:
        req = Request(
            f"{GATEWAY_URL}/internal/events",
            data=json.dumps(event).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=3) as resp:
            return resp.read()
    except Exception:
        return None


def _get_message_or_404(db, message_id: str) -> dict:
    payload = db.find_one({"id": message_id})
    if not payload:
        raise HTTPException(status_code=404, detail="Message not found")
    return payload


def _serialize_message_for_user(db, message: dict, current_user_id: str) -> dict:
    if message.get("sender_id") == current_user_id:
        is_read = True
    else:
        is_read = current_user_id in message.get("reads", [])

    response = dict(message)
    response["is_read"] = bool(is_read)
    return response

class MessageCreate(BaseModel):
    chat_id: str
    sender_id: str
    ciphertext: str  # Encrypted message content (E2EE)
    message_type: str = "text"  # text, image, file

class MessageResponse(BaseModel):
    id: str
    chat_id: str
    sender_id: str
    ciphertext: str
    message_type: str
    created_at: str
    is_read: bool = False


class ReadStatusResponse(BaseModel):
    message_id: str
    user_id: str
    is_read: bool


def _parse_utc_timestamp(value: str) -> datetime:
    try:
        parsed_value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed_value.tzinfo is None:
            return parsed_value.replace(tzinfo=timezone.utc)
        return parsed_value
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid before timestamp")


def _base64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def parse_bearer_token(authorization: Optional[str] = Header(None)) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.split(" ", 1)[1]
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        signing_input = f"{header_b64}.{payload_b64}".encode()
        expected_signature = hmac.new(
            SECRET_KEY.encode(),
            signing_input,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(_base64url_decode(signature_b64), expected_signature):
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")

        payload = json.loads(_base64url_decode(payload_b64).decode())
        exp = payload.get("exp")
        if exp is not None and datetime.utcnow().timestamp() > float(exp):
            raise HTTPException(status_code=401, detail="Token expired")

        subject = payload.get("sub")
        if not subject:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return subject
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")


def fetch_chat(chat_id: str, authorization: str):
    request = Request(
        f"{CHAT_SERVICE_URL}/chats/{chat_id}",
        headers={"Authorization": authorization},
        method="GET",
    )
    try:
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode())
    except HTTPError as exc:
        body = exc.read().decode() if exc.fp else ""
        message = "Chat service unavailable"
        if body:
            try:
                message = json.loads(body).get("detail", message)
            except json.JSONDecodeError:
                pass
        if exc.code == 404:
            raise HTTPException(status_code=404, detail=message)
        if exc.code == 403:
            raise HTTPException(status_code=403, detail=message)
        raise HTTPException(status_code=503, detail=message)
    except URLError:
        raise HTTPException(status_code=503, detail="Chat service unavailable")


def ensure_chat_membership(chat_id: str, current_user_id: str, authorization: str):
    chat = fetch_chat(chat_id, authorization)
    if current_user_id not in chat.get("member_ids", []):
        raise HTTPException(status_code=403, detail="Cannot access a chat you are not a member of")
    return chat

@app.get("/health")
def health():
    return {"status": "ok", "service": "message_service"}

@app.post("/chats/{chat_id}/messages", response_model=MessageResponse)
def send_message(chat_id: str, message: MessageCreate, authorization: str = Header(None), current_user_id: str = Depends(parse_bearer_token)):
    """Send an encrypted message to a chat"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    if current_user_id != message.sender_id:
        raise HTTPException(status_code=403, detail="Sender must match authenticated user")

    ensure_chat_membership(chat_id, current_user_id, authorization)

    db = _messages_collection()

    message_id = f"msg_{uuid.uuid4().hex[:8]}"
    created_at = datetime.now(timezone.utc)

    message_payload = {
        "id": message_id,
        "chat_id": chat_id,
        "sender_id": message.sender_id,
        "ciphertext": message.ciphertext,
        "message_type": message.message_type,
        "created_at": created_at,
        "reads": [message.sender_id],
    }

    try:
        db.insert_one(message_payload)
    except PyMongoError:
        raise HTTPException(status_code=503, detail="Database unavailable")

    # best-effort notify gateway
    event = {
        "type": "message.new",
        "chat_id": chat_id,
        "message": {
            "id": message_payload["id"],
            "chat_id": message_payload["chat_id"],
            "sender_id": message_payload["sender_id"],
            "ciphertext": message_payload["ciphertext"],
            "message_type": message_payload["message_type"],
            "created_at": message_payload["created_at"].isoformat(),
        }
    }
    _post_event_to_gateway(event)

    resp = message_payload.copy()
    resp["created_at"] = resp["created_at"].isoformat()
    return MessageResponse(**_serialize_message_for_user(db, resp, current_user_id))

@app.get("/chats/{chat_id}/messages", response_model=List[MessageResponse])
def get_messages(chat_id: str, limit: int = 50, before: Optional[str] = None, authorization: str = Header(None), current_user_id: str = Depends(parse_bearer_token)):
    """Get messages for a chat with pagination"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    ensure_chat_membership(chat_id, current_user_id, authorization)
    db = _messages_collection()

    query = {"chat_id": chat_id}
    if before:
        before_dt = _parse_utc_timestamp(before)
        query["created_at"] = {"$lt": before_dt}

    try:
        cursor = db.find(query).sort("created_at", -1).limit(limit)
        chat_messages = []
        for msg in cursor:
            msg_copy = msg.copy()
            msg_copy["created_at"] = msg_copy["created_at"].isoformat()
            chat_messages.append(MessageResponse(**_serialize_message_for_user(db, msg_copy, current_user_id)))
        return chat_messages
    except PyMongoError:
        raise HTTPException(status_code=503, detail="Database unavailable")

@app.get("/messages/{message_id}", response_model=MessageResponse)
def get_message(message_id: str, authorization: str = Header(None), current_user_id: str = Depends(parse_bearer_token)):
    """Get a specific message"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    db = _messages_collection()
    try:
        message = _get_message_or_404(db, message_id)
        message["created_at"] = message["created_at"].isoformat()
    except PyMongoError:
        raise HTTPException(status_code=503, detail="Database unavailable")

    ensure_chat_membership(message["chat_id"], current_user_id, authorization)

    return MessageResponse(**_serialize_message_for_user(db, message, current_user_id))

@app.delete("/messages/{message_id}")
def delete_message(message_id: str, authorization: str = Header(None), current_user_id: str = Depends(parse_bearer_token)):
    """Delete a message"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    db = _messages_collection()
    try:
        message = _get_message_or_404(db, message_id)
    except PyMongoError:
        raise HTTPException(status_code=503, detail="Database unavailable")

    ensure_chat_membership(message["chat_id"], current_user_id, authorization)

    if message["sender_id"] != current_user_id:
        raise HTTPException(status_code=403, detail="Only the sender can delete this message")

    try:
        db.delete_one({"id": message_id})
    except PyMongoError:
        raise HTTPException(status_code=503, detail="Database unavailable")

    return {"message": "Message deleted", "message_id": message_id}


@app.post("/messages/{message_id}/read", response_model=ReadStatusResponse)
def mark_message_as_read(message_id: str, authorization: str = Header(None), current_user_id: str = Depends(parse_bearer_token)):
    """Mark a message as read for the authenticated user"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    db = _messages_collection()
    try:
        message = _get_message_or_404(db, message_id)
    except PyMongoError:
        raise HTTPException(status_code=503, detail="Database unavailable")

    ensure_chat_membership(message["chat_id"], current_user_id, authorization)

    try:
        db.update_one({"id": message_id}, {"$addToSet": {"reads": current_user_id}})
    except PyMongoError:
        raise HTTPException(status_code=503, detail="Database unavailable")

    return ReadStatusResponse(message_id=message_id, user_id=current_user_id, is_read=True)


@app.get("/messages/{message_id}/read", response_model=ReadStatusResponse)
def get_message_read_status(message_id: str, authorization: str = Header(None), current_user_id: str = Depends(parse_bearer_token)):
    """Get read status of a message for the authenticated user"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    db = _messages_collection()
    try:
        message = _get_message_or_404(db, message_id)
    except PyMongoError:
        raise HTTPException(status_code=503, detail="Database unavailable")

    ensure_chat_membership(message["chat_id"], current_user_id, authorization)

    try:
        is_read = message["sender_id"] == current_user_id or (current_user_id in message.get("reads", []))
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable")

    return ReadStatusResponse(message_id=message_id, user_id=current_user_id, is_read=bool(is_read))
