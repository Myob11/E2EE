from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import uuid
import os

app = FastAPI()

# MongoDB connection (will be set via environment variables)
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://mongodb:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "messages_db")

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

@app.get("/health")
def health():
    return {"status": "ok", "service": "message_service"}

@app.post("/chats/{chat_id}/messages", response_model=MessageResponse)
def send_message(chat_id: str, message: MessageCreate):
    """Send an encrypted message to a chat"""
    message_id = f"msg_{uuid.uuid4().hex[:8]}"
    
    messages_db[message_id] = {
        "id": message_id,
        "chat_id": chat_id,
        "sender_id": message.sender_id,
        "ciphertext": message.ciphertext,
        "message_type": message.message_type,
        "created_at": datetime.utcnow().isoformat() + "Z"
    }
    
    return MessageResponse(**messages_db[message_id])

@app.get("/chats/{chat_id}/messages", response_model=List[MessageResponse])
def get_messages(chat_id: str, limit: int = 50, before: Optional[str] = None):
    """Get messages for a chat with pagination"""
    chat_messages = [
        MessageResponse(**msg) for msg in messages_db.values()
        if msg["chat_id"] == chat_id
    ]
    
    # Sort by created_at descending (newest first)
    chat_messages.sort(key=lambda x: x.created_at, reverse=True)
    
    # Apply limit
    return chat_messages[:limit]

@app.get("/messages/{message_id}", response_model=MessageResponse)
def get_message(message_id: str):
    """Get a specific message"""
    if message_id not in messages_db:
        raise HTTPException(status_code=404, detail="Message not found")
    return MessageResponse(**messages_db[message_id])

@app.delete("/messages/{message_id}")
def delete_message(message_id: str):
    """Delete a message"""
    if message_id not in messages_db:
        raise HTTPException(status_code=404, detail="Message not found")
    
    del messages_db[message_id]
    return {"message": "Message deleted", "message_id": message_id}
