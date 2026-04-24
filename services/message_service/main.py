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
import redis
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from redis.exceptions import RedisError

app = FastAPI()

# MongoDB connection (will be set via environment variables)
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://mongodb:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "messages_db")
CHAT_SERVICE_URL = os.getenv("CHAT_SERVICE_URL", "http://chat_service:8002")
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
MESSAGE_EVENTS_CHANNEL = os.getenv("MESSAGE_EVENTS_CHANNEL", "chat_messages")


def get_redis_conn():
    try:
        return redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,
            socket_timeout=3,
        )
    except RedisError:
        raise HTTPException(status_code=503, detail="Redis unavailable")


def _message_key(message_id: str) -> str:
    return f"message:{message_id}"


def _chat_messages_key(chat_id: str) -> str:
    return f"chat_messages:{chat_id}"


def _message_reads_key(message_id: str) -> str:
    return f"message_reads:{message_id}"


def _get_message_or_404(client: redis.Redis, message_id: str) -> dict:
    payload = client.get(_message_key(message_id))
    if not payload:
        raise HTTPException(status_code=404, detail="Message not found")
    return json.loads(payload)


def _serialize_message_for_user(client: redis.Redis, message: dict, current_user_id: str) -> dict:
    if message.get("sender_id") == current_user_id:
        is_read = True
    else:
        is_read = client.sismember(_message_reads_key(message["id"]), current_user_id)

    response = dict(message)
    response["is_read"] = bool(is_read)
    return response

# Pydantic models
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

    client = get_redis_conn()

    message_id = f"msg_{uuid.uuid4().hex[:8]}"
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    score = _parse_utc_timestamp(created_at).timestamp()

    message_payload = {
        "id": message_id,
        "chat_id": chat_id,
        "sender_id": message.sender_id,
        "ciphertext": message.ciphertext,
        "message_type": message.message_type,
        "created_at": created_at,
    }

    try:
        pipe = client.pipeline()
        pipe.set(_message_key(message_id), json.dumps(message_payload))
        pipe.zadd(_chat_messages_key(chat_id), {message_id: score})
        pipe.sadd(_message_reads_key(message_id), message.sender_id)
        pipe.execute()
        client.publish(MESSAGE_EVENTS_CHANNEL, json.dumps({"type": "message.new", **message_payload}))
    except RedisError:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    return MessageResponse(**_serialize_message_for_user(client, message_payload, current_user_id))

@app.get("/chats/{chat_id}/messages", response_model=List[MessageResponse])
def get_messages(chat_id: str, limit: int = 50, before: Optional[str] = None, authorization: str = Header(None), current_user_id: str = Depends(parse_bearer_token)):
    """Get messages for a chat with pagination"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    ensure_chat_membership(chat_id, current_user_id, authorization)
    client = get_redis_conn()

    max_score = "+inf"
    if before:
        max_score = f"({_parse_utc_timestamp(before).timestamp()}"

    try:
        message_ids = client.zrevrangebyscore(
            _chat_messages_key(chat_id),
            max_score,
            "-inf",
            start=0,
            num=limit,
        )
        chat_messages = []
        for message_id in message_ids:
            payload = client.get(_message_key(message_id))
            if not payload:
                continue
            chat_messages.append(
                MessageResponse(**_serialize_message_for_user(client, json.loads(payload), current_user_id))
            )
        return chat_messages
    except RedisError:
        raise HTTPException(status_code=503, detail="Redis unavailable")

@app.get("/messages/{message_id}", response_model=MessageResponse)
def get_message(message_id: str, authorization: str = Header(None), current_user_id: str = Depends(parse_bearer_token)):
    """Get a specific message"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    client = get_redis_conn()
    try:
        message = _get_message_or_404(client, message_id)
    except RedisError:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    ensure_chat_membership(message["chat_id"], current_user_id, authorization)

    try:
        return MessageResponse(**_serialize_message_for_user(client, message, current_user_id))
    except RedisError:
        raise HTTPException(status_code=503, detail="Redis unavailable")

@app.delete("/messages/{message_id}")
def delete_message(message_id: str, authorization: str = Header(None), current_user_id: str = Depends(parse_bearer_token)):
    """Delete a message"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    client = get_redis_conn()
    try:
        message = _get_message_or_404(client, message_id)
    except RedisError:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    ensure_chat_membership(message["chat_id"], current_user_id, authorization)

    if message["sender_id"] != current_user_id:
        raise HTTPException(status_code=403, detail="Only the sender can delete this message")
    
    try:
        pipe = client.pipeline()
        pipe.delete(_message_key(message_id))
        pipe.zrem(_chat_messages_key(message["chat_id"]), message_id)
        pipe.delete(_message_reads_key(message_id))
        pipe.execute()
    except RedisError:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    return {"message": "Message deleted", "message_id": message_id}


@app.post("/messages/{message_id}/read", response_model=ReadStatusResponse)
def mark_message_as_read(message_id: str, authorization: str = Header(None), current_user_id: str = Depends(parse_bearer_token)):
    """Mark a message as read for the authenticated user"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    client = get_redis_conn()
    try:
        message = _get_message_or_404(client, message_id)
    except RedisError:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    ensure_chat_membership(message["chat_id"], current_user_id, authorization)

    try:
        client.sadd(_message_reads_key(message_id), current_user_id)
    except RedisError:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    return ReadStatusResponse(message_id=message_id, user_id=current_user_id, is_read=True)


@app.get("/messages/{message_id}/read", response_model=ReadStatusResponse)
def get_message_read_status(message_id: str, authorization: str = Header(None), current_user_id: str = Depends(parse_bearer_token)):
    """Get read status of a message for the authenticated user"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    client = get_redis_conn()
    try:
        message = _get_message_or_404(client, message_id)
    except RedisError:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    ensure_chat_membership(message["chat_id"], current_user_id, authorization)

    try:
        is_read = message["sender_id"] == current_user_id or client.sismember(_message_reads_key(message_id), current_user_id)
    except RedisError:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    return ReadStatusResponse(message_id=message_id, user_id=current_user_id, is_read=bool(is_read))
