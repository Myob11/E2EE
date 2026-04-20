from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import uuid
import os

app = FastAPI()

# Redis connection (will be set via environment variables)
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

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

@app.get("/health")
def health():
    return {"status": "ok", "service": "chat_service"}

@app.post("/chats", response_model=ChatResponse)
def create_chat(chat: ChatCreate):
    """Create a new chat (1:1 or group)"""
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
def get_chats(user_id: str = "user_1"):
    """Get all chats for a user"""
    user_chats = []
    for chat in chats_db.values():
        if user_id in chat["member_ids"]:
            user_chats.append(ChatResponse(**chat))
    return user_chats

@app.get("/chats/{chat_id}", response_model=ChatResponse)
def get_chat(chat_id: str):
    """Get a specific chat"""
    if chat_id not in chats_db:
        raise HTTPException(status_code=404, detail="Chat not found")
    return ChatResponse(**chats_db[chat_id])

@app.post("/chats/{chat_id}/members")
def add_member(chat_id: str, request: AddMemberRequest):
    """Add a member to a chat"""
    if chat_id not in chats_db:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    if request.user_id not in chats_db[chat_id]["member_ids"]:
        chats_db[chat_id]["member_ids"].append(request.user_id)
        chat_members_db[chat_id] = chats_db[chat_id]["member_ids"]
    
    return {"message": "Member added", "chat_id": chat_id, "user_id": request.user_id}

@app.delete("/chats/{chat_id}/members/{user_id}")
def remove_member(chat_id: str, user_id: str):
    """Remove a member from a chat"""
    if chat_id not in chats_db:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    if user_id in chats_db[chat_id]["member_ids"]:
        chats_db[chat_id]["member_ids"].remove(user_id)
        chat_members_db[chat_id] = chats_db[chat_id]["member_ids"]
    
    return {"message": "Member removed", "chat_id": chat_id, "user_id": user_id}
