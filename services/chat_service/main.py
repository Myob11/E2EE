from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
from typing import List, Optional
import uuid
import os
import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone

app = FastAPI()

# Redis connection (will be set via environment variables)
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"

# In-memory chat storage (for testing without Redis)
chats_db = {}
chat_members_db = {}

# Pydantic models
class ChatCreate(BaseModel):
    name: Optional[str] = None
    member_ids: List[str]
    is_group: bool = False

class ChatResponse(BaseModel):
    id: str
    name: Optional[str]
    is_group: bool
    member_ids: List[str]
    created_at: str

class AddMemberRequest(BaseModel):
    user_id: str


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
        if exp is not None and datetime.now(timezone.utc).timestamp() > float(exp):
            raise HTTPException(status_code=401, detail="Token expired")

        subject = payload.get("sub")
        if not subject:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return subject
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

@app.get("/health")
def health():
    return {"status": "ok", "service": "chat_service"}

@app.post("/chats", response_model=ChatResponse)
def create_chat(chat: ChatCreate, current_user_id: str = Depends(parse_bearer_token)):
    """Create a new chat (1:1 or group)"""
    if current_user_id not in chat.member_ids:
        chat.member_ids = [current_user_id, *chat.member_ids]

    chat_id = f"chat_{uuid.uuid4().hex[:8]}"
    
    chats_db[chat_id] = {
        "id": chat_id,
        "name": chat.name,
        "is_group": chat.is_group,
        "member_ids": chat.member_ids,
        "created_at": "2026-04-20T12:00:00Z"
    }
    
    # Store members
    chat_members_db[chat_id] = chat.member_ids
    
    return ChatResponse(**chats_db[chat_id])

@app.get("/chats", response_model=List[ChatResponse])
def get_chats(user_id: str, current_user_id: str = Depends(parse_bearer_token)):
    """Get all chats for a user. Only chats where the user is a member are returned."""
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Cannot view chats for another user")

    user_chats = []
    for chat in chats_db.values():
        if user_id in chat["member_ids"]:
            user_chats.append(ChatResponse(**chat))
    return user_chats

@app.get("/chats/{chat_id}", response_model=ChatResponse)
def get_chat(chat_id: str, current_user_id: str = Depends(parse_bearer_token)):
    """Get a specific chat"""
    if chat_id not in chats_db:
        raise HTTPException(status_code=404, detail="Chat not found")

    if current_user_id not in chats_db[chat_id]["member_ids"]:
        raise HTTPException(status_code=403, detail="Cannot access a chat you are not a member of")

    return ChatResponse(**chats_db[chat_id])

@app.post("/chats/{chat_id}/members")
def add_member(chat_id: str, request: AddMemberRequest, current_user_id: str = Depends(parse_bearer_token)):
    """Add a member to a chat"""
    if chat_id not in chats_db:
        raise HTTPException(status_code=404, detail="Chat not found")

    if current_user_id not in chats_db[chat_id]["member_ids"]:
        raise HTTPException(status_code=403, detail="Cannot add members to a chat you are not part of")
    
    if request.user_id not in chats_db[chat_id]["member_ids"]:
        chats_db[chat_id]["member_ids"].append(request.user_id)
        chat_members_db[chat_id] = chats_db[chat_id]["member_ids"]
    
    return {"message": "Member added", "chat_id": chat_id, "user_id": request.user_id}

@app.delete("/chats/{chat_id}/members/{user_id}")
def remove_member(chat_id: str, user_id: str, current_user_id: str = Depends(parse_bearer_token)):
    """Remove a member from a chat"""
    if chat_id not in chats_db:
        raise HTTPException(status_code=404, detail="Chat not found")

    if current_user_id not in chats_db[chat_id]["member_ids"]:
        raise HTTPException(status_code=403, detail="Cannot remove members from a chat you are not part of")
    
    if user_id in chats_db[chat_id]["member_ids"]:
        chats_db[chat_id]["member_ids"].remove(user_id)
        chat_members_db[chat_id] = chats_db[chat_id]["member_ids"]
    
    return {"message": "Member removed", "chat_id": chat_id, "user_id": user_id}
