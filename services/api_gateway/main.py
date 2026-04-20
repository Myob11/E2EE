from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import httpx
import os

app = FastAPI()

# Service URLs (from environment or docker-compose)
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth_service:8001")
CHAT_SERVICE_URL = os.getenv("CHAT_SERVICE_URL", "http://chat_service:8002")
MESSAGE_SERVICE_URL = os.getenv("MESSAGE_SERVICE_URL", "http://message_service:8003")
MEDIA_SERVICE_URL = os.getenv("MEDIA_SERVICE_URL", "http://media_service:8004")

@app.get("/health")
def health():
    return {"status": "ok", "service": "api_gateway"}

# =====================
# Auth Service Routes
# =====================

@app.post("/api/auth/register")
async def proxy_register(request: Request):
    """Proxy to auth service - register"""
    body = await request.json()
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{AUTH_SERVICE_URL}/register", json=body)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Auth service unavailable: {str(e)}")

@app.post("/api/auth/login")
async def proxy_login(request: Request):
    """Proxy to auth service - login"""
    body = await request.json()
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{AUTH_SERVICE_URL}/login", json=body)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Auth service unavailable: {str(e)}")

@app.get("/api/users/me")
async def proxy_get_current_user():
    """Proxy to auth service - get current user"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{AUTH_SERVICE_URL}/users/me")
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Auth service unavailable: {str(e)}")

@app.get("/api/users/{user_id}/public-key")
async def proxy_get_public_key(user_id: str):
    """Proxy to auth service - get user public key"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{AUTH_SERVICE_URL}/users/{user_id}/public-key")
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Auth service unavailable: {str(e)}")

# =====================
# Chat Service Routes
# =====================

@app.post("/api/chats")
async def proxy_create_chat(request: Request):
    """Proxy to chat service - create chat"""
    body = await request.json()
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{CHAT_SERVICE_URL}/chats", json=body)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Chat service unavailable: {str(e)}")

@app.get("/api/chats")
async def proxy_get_chats():
    """Proxy to chat service - get all chats"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{CHAT_SERVICE_URL}/chats")
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Chat service unavailable: {str(e)}")

@app.get("/api/chats/{chat_id}")
async def proxy_get_chat(chat_id: str):
    """Proxy to chat service - get specific chat"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{CHAT_SERVICE_URL}/chats/{chat_id}")
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Chat service unavailable: {str(e)}")

@app.post("/api/chats/{chat_id}/members")
async def proxy_add_member(chat_id: str, request: Request):
    """Proxy to chat service - add member"""
    body = await request.json()
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{CHAT_SERVICE_URL}/chats/{chat_id}/members", json=body)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Chat service unavailable: {str(e)}")

@app.delete("/api/chats/{chat_id}/members/{user_id}")
async def proxy_remove_member(chat_id: str, user_id: str):
    """Proxy to chat service - remove member"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.delete(f"{CHAT_SERVICE_URL}/chats/{chat_id}/members/{user_id}")
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Chat service unavailable: {str(e)}")

# =====================
# Message Service Routes
# =====================

@app.post("/api/chats/{chat_id}/messages")
async def proxy_send_message(chat_id: str, request: Request):
    """Proxy to message service - send message"""
    body = await request.json()
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{MESSAGE_SERVICE_URL}/chats/{chat_id}/messages", json=body)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Message service unavailable: {str(e)}")

@app.get("/api/chats/{chat_id}/messages")
async def proxy_get_messages(chat_id: str, limit: int = 50):
    """Proxy to message service - get messages"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{MESSAGE_SERVICE_URL}/chats/{chat_id}/messages?limit={limit}")
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Message service unavailable: {str(e)}")

@app.get("/api/messages/{message_id}")
async def proxy_get_message(message_id: str):
    """Proxy to message service - get specific message"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{MESSAGE_SERVICE_URL}/messages/{message_id}")
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Message service unavailable: {str(e)}")

@app.delete("/api/messages/{message_id}")
async def proxy_delete_message(message_id: str):
    """Proxy to message service - delete message"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.delete(f"{MESSAGE_SERVICE_URL}/messages/{message_id}")
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Message service unavailable: {str(e)}")

# =====================
# Media Service Routes
# =====================

@app.post("/api/media/upload-url")
async def proxy_get_upload_url(request: Request):
    """Proxy to media service - get upload URL"""
    body = await request.json()
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{MEDIA_SERVICE_URL}/media/upload-url", json=body)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Media service unavailable: {str(e)}")

@app.post("/api/media/complete")
async def proxy_complete_upload(request: Request):
    """Proxy to media service - complete upload"""
    body = await request.json()
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{MEDIA_SERVICE_URL}/media/complete", json=body)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Media service unavailable: {str(e)}")

@app.get("/api/media/{media_id}/download-url")
async def proxy_get_download_url(media_id: str):
    """Proxy to media service - get download URL"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{MEDIA_SERVICE_URL}/media/{media_id}/download-url")
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Media service unavailable: {str(e)}")

@app.get("/api/media/{media_id}")
async def proxy_get_media_metadata(media_id: str):
    """Proxy to media service - get media metadata"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{MEDIA_SERVICE_URL}/media/{media_id}")
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Media service unavailable: {str(e)}")
