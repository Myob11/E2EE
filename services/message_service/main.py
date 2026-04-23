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
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

app = FastAPI()

# MongoDB connection (will be set via environment variables)
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://mongodb:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "messages_db")
CHAT_SERVICE_URL = os.getenv("CHAT_SERVICE_URL", "http://chat_service:8002")
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")

# In-memory message storage (for testing without MongoDB)
messages_db = {}

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

    message_id = f"msg_{uuid.uuid4().hex[:8]}"
    
    messages_db[message_id] = {
        "id": message_id,
        "chat_id": chat_id,
        "sender_id": message.sender_id,
        "ciphertext": message.ciphertext,
        "message_type": message.message_type,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }
    
    return MessageResponse(**messages_db[message_id])

@app.get("/chats/{chat_id}/messages", response_model=List[MessageResponse])
def get_messages(chat_id: str, limit: int = 50, before: Optional[str] = None, authorization: str = Header(None), current_user_id: str = Depends(parse_bearer_token)):
    """Get messages for a chat with pagination"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    ensure_chat_membership(chat_id, current_user_id, authorization)

    chat_messages = [
        msg for msg in messages_db.values()
        if msg["chat_id"] == chat_id
    ]

    if before:
        before_timestamp = _parse_utc_timestamp(before)
        chat_messages = [
            msg for msg in chat_messages
            if _parse_utc_timestamp(msg["created_at"]) < before_timestamp
        ]

    chat_messages.sort(key=lambda msg: _parse_utc_timestamp(msg["created_at"]), reverse=True)

    return [MessageResponse(**msg) for msg in chat_messages[:limit]]

@app.get("/messages/{message_id}", response_model=MessageResponse)
def get_message(message_id: str, authorization: str = Header(None), current_user_id: str = Depends(parse_bearer_token)):
    """Get a specific message"""
    if message_id not in messages_db:
        raise HTTPException(status_code=404, detail="Message not found")

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    ensure_chat_membership(messages_db[message_id]["chat_id"], current_user_id, authorization)

    return MessageResponse(**messages_db[message_id])

@app.delete("/messages/{message_id}")
def delete_message(message_id: str, authorization: str = Header(None), current_user_id: str = Depends(parse_bearer_token)):
    """Delete a message"""
    if message_id not in messages_db:
        raise HTTPException(status_code=404, detail="Message not found")

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    message = messages_db[message_id]
    ensure_chat_membership(message["chat_id"], current_user_id, authorization)

    if message["sender_id"] != current_user_id:
        raise HTTPException(status_code=403, detail="Only the sender can delete this message")
    
    del messages_db[message_id]
    return {"message": "Message deleted", "message_id": message_id}
