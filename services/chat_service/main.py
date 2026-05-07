from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
from typing import List, Optional
import uuid
import os
import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from pymongo import MongoClient
from pymongo.errors import PyMongoError

app = FastAPI()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("chat_service")


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
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"


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


def _chats_collection():
    client = get_mongo_client()
    return client[MONGODB_DB].chats


def _get_chat_or_404(db, chat_id: str) -> dict:
    chat = db.find_one({"id": chat_id})
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


def _find_existing_individual_chat(db, member_ids: List[str]) -> Optional[dict]:
    if len(member_ids) != 2:
        return None

    try:
        candidates = db.find({"is_group": False, "member_ids": {"$all": member_ids}})
        for chat in candidates:
            members = chat.get("member_ids", [])
            if len(members) == 2 and set(members) == set(member_ids):
                return chat
    except PyMongoError:
        raise HTTPException(status_code=503, detail="Database unavailable")

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
    db = _chats_collection()

    unique_member_ids = list(dict.fromkeys(chat.member_ids))
    if current_user_id not in unique_member_ids:
        unique_member_ids = [current_user_id, *unique_member_ids]

    if not chat.is_group:
        if len(unique_member_ids) != 2:
            raise HTTPException(status_code=400, detail="Individual chat must have exactly 2 members")

        existing_chat = _find_existing_individual_chat(db, unique_member_ids)
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
        db.insert_one(chat_payload)
    except PyMongoError:
        raise HTTPException(status_code=503, detail="Database unavailable")

    return ChatResponse(**chat_payload)

@app.get("/chats", response_model=List[ChatResponse])
def get_chats(user_id: str, current_user_id: str = Depends(parse_bearer_token)):
    """Get all chats for a user. Only chats where the user is a member are returned."""
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Cannot view chats for another user")

    db = _chats_collection()
    try:
        cursor = db.find({"member_ids": user_id})
        user_chats = [ChatResponse(**chat) for chat in cursor]
        return user_chats
    except PyMongoError:
        raise HTTPException(status_code=503, detail="Database unavailable")

@app.get("/chats/{chat_id}", response_model=ChatResponse)
def get_chat(chat_id: str, current_user_id: str = Depends(parse_bearer_token)):
    """Get a specific chat"""
    db = _chats_collection()
    try:
        chat = _get_chat_or_404(db, chat_id)
    except PyMongoError:
        raise HTTPException(status_code=503, detail="Database unavailable")

    if current_user_id not in chat["member_ids"]:
        raise HTTPException(status_code=403, detail="Cannot access a chat you are not a member of")

    return ChatResponse(**chat)

@app.post("/chats/{chat_id}/members")
def add_member(chat_id: str, request: AddMemberRequest, current_user_id: str = Depends(parse_bearer_token)):
    """Add a member to a chat"""
    db = _chats_collection()
    try:
        chat = _get_chat_or_404(db, chat_id)
    except PyMongoError:
        raise HTTPException(status_code=503, detail="Database unavailable")

    if current_user_id not in chat["member_ids"]:
        raise HTTPException(status_code=403, detail="Cannot add members to a chat you are not part of")

    if request.user_id not in chat["member_ids"]:
        chat["member_ids"].append(request.user_id)
        try:
            db.update_one({"id": chat_id}, {"$set": {"member_ids": chat["member_ids"]}})
        except PyMongoError:
            raise HTTPException(status_code=503, detail="Database unavailable")
    
    return {"message": "Member added", "chat_id": chat_id, "user_id": request.user_id}

@app.delete("/chats/{chat_id}/members/{user_id}")
def remove_member(chat_id: str, user_id: str, current_user_id: str = Depends(parse_bearer_token)):
    """Remove a member from a chat"""
    db = _chats_collection()
    try:
        chat = _get_chat_or_404(db, chat_id)
    except PyMongoError:
        raise HTTPException(status_code=503, detail="Database unavailable")

    if current_user_id not in chat["member_ids"]:
        raise HTTPException(status_code=403, detail="Cannot remove members from a chat you are not part of")

    if user_id in chat["member_ids"]:
        chat["member_ids"].remove(user_id)
        try:
            db.update_one({"id": chat_id}, {"$set": {"member_ids": chat["member_ids"]}})
        except PyMongoError:
            raise HTTPException(status_code=503, detail="Database unavailable")
    
    return {"message": "Member removed", "chat_id": chat_id, "user_id": user_id}
