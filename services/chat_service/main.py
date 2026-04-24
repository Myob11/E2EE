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
import redis
from redis.exceptions import RedisError

app = FastAPI()

# Redis connection (will be set via environment variables)
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"


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


def _chat_key(chat_id: str) -> str:
    return f"chat:{chat_id}"


def _user_chats_key(user_id: str) -> str:
    return f"user_chats:{user_id}"


def _get_chat_or_404(client: redis.Redis, chat_id: str) -> dict:
    payload = client.get(_chat_key(chat_id))
    if not payload:
        raise HTTPException(status_code=404, detail="Chat not found")
    return json.loads(payload)


def _find_existing_individual_chat(client: redis.Redis, member_ids: List[str]) -> Optional[dict]:
    if len(member_ids) != 2:
        return None

    requested_members = set(member_ids)
    try:
        candidate_chat_ids = client.smembers(_user_chats_key(member_ids[0]))
        for chat_id in candidate_chat_ids:
            payload = client.get(_chat_key(chat_id))
            if not payload:
                continue

            chat = json.loads(payload)
            if chat.get("is_group"):
                continue

            chat_members = chat.get("member_ids", [])
            if len(chat_members) != 2:
                continue

            if set(chat_members) == requested_members:
                return chat
    except RedisError:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    return None

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
    client = get_redis_conn()

    unique_member_ids = list(dict.fromkeys(chat.member_ids))
    if current_user_id not in unique_member_ids:
        unique_member_ids = [current_user_id, *unique_member_ids]

    if not chat.is_group:
        if len(unique_member_ids) != 2:
            raise HTTPException(status_code=400, detail="Individual chat must have exactly 2 members")

        existing_chat = _find_existing_individual_chat(client, unique_member_ids)
        if existing_chat:
            return ChatResponse(**existing_chat)

    chat_id = f"chat_{uuid.uuid4().hex[:8]}"

    chat_payload = {
        "id": chat_id,
        "name": chat.name,
        "is_group": chat.is_group,
        "member_ids": unique_member_ids,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    try:
        pipe = client.pipeline()
        pipe.set(_chat_key(chat_id), json.dumps(chat_payload))
        for member_id in unique_member_ids:
            pipe.sadd(_user_chats_key(member_id), chat_id)
        pipe.execute()
    except RedisError:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    return ChatResponse(**chat_payload)

@app.get("/chats", response_model=List[ChatResponse])
def get_chats(user_id: str, current_user_id: str = Depends(parse_bearer_token)):
    """Get all chats for a user. Only chats where the user is a member are returned."""
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Cannot view chats for another user")

    client = get_redis_conn()
    try:
        chat_ids = sorted(client.smembers(_user_chats_key(user_id)))
        user_chats = []
        for chat_id in chat_ids:
            payload = client.get(_chat_key(chat_id))
            if not payload:
                continue
            user_chats.append(ChatResponse(**json.loads(payload)))
        return user_chats
    except RedisError:
        raise HTTPException(status_code=503, detail="Redis unavailable")

@app.get("/chats/{chat_id}", response_model=ChatResponse)
def get_chat(chat_id: str, current_user_id: str = Depends(parse_bearer_token)):
    """Get a specific chat"""
    client = get_redis_conn()
    try:
        chat = _get_chat_or_404(client, chat_id)
    except RedisError:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    if current_user_id not in chat["member_ids"]:
        raise HTTPException(status_code=403, detail="Cannot access a chat you are not a member of")

    return ChatResponse(**chat)

@app.post("/chats/{chat_id}/members")
def add_member(chat_id: str, request: AddMemberRequest, current_user_id: str = Depends(parse_bearer_token)):
    """Add a member to a chat"""
    client = get_redis_conn()
    try:
        chat = _get_chat_or_404(client, chat_id)
    except RedisError:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    if current_user_id not in chat["member_ids"]:
        raise HTTPException(status_code=403, detail="Cannot add members to a chat you are not part of")

    if request.user_id not in chat["member_ids"]:
        chat["member_ids"].append(request.user_id)
        try:
            pipe = client.pipeline()
            pipe.set(_chat_key(chat_id), json.dumps(chat))
            pipe.sadd(_user_chats_key(request.user_id), chat_id)
            pipe.execute()
        except RedisError:
            raise HTTPException(status_code=503, detail="Redis unavailable")
    
    return {"message": "Member added", "chat_id": chat_id, "user_id": request.user_id}

@app.delete("/chats/{chat_id}/members/{user_id}")
def remove_member(chat_id: str, user_id: str, current_user_id: str = Depends(parse_bearer_token)):
    """Remove a member from a chat"""
    client = get_redis_conn()
    try:
        chat = _get_chat_or_404(client, chat_id)
    except RedisError:
        raise HTTPException(status_code=503, detail="Redis unavailable")

    if current_user_id not in chat["member_ids"]:
        raise HTTPException(status_code=403, detail="Cannot remove members from a chat you are not part of")

    if user_id in chat["member_ids"]:
        chat["member_ids"].remove(user_id)
        try:
            pipe = client.pipeline()
            pipe.set(_chat_key(chat_id), json.dumps(chat))
            pipe.srem(_user_chats_key(user_id), chat_id)
            pipe.execute()
        except RedisError:
            raise HTTPException(status_code=503, detail="Redis unavailable")
    
    return {"message": "Member removed", "chat_id": chat_id, "user_id": user_id}
