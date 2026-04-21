from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os

app = FastAPI()

# CORS settings for Android app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service URLs (from environment or docker-compose)
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth_service:8001")
CHAT_SERVICE_URL = os.getenv("CHAT_SERVICE_URL", "http://chat_service:8002")
MESSAGE_SERVICE_URL = os.getenv("MESSAGE_SERVICE_URL", "http://message_service:8003")
MEDIA_SERVICE_URL = os.getenv("MEDIA_SERVICE_URL", "http://media_service:8004")
DOMAIN = os.getenv("DOMAIN", "secra.top")


def forward_headers(request: Request):
    headers = {}
    auth = request.headers.get("authorization")
    if auth:
        headers["Authorization"] = auth
    return headers


def forward_query_params(request: Request):
    return dict(request.query_params)


@app.get("/health")
def health():
    return {"status": "ok", "service": "api_gateway", "domain": DOMAIN}


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
async def proxy_get_current_user(request: Request):
    """Proxy to auth service - get current user"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{AUTH_SERVICE_URL}/users/me", headers=headers)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Auth service unavailable: {str(e)}")


@app.get("/api/users/{user_id}/public-key")
async def proxy_get_public_key(user_id: str, request: Request):
    """Proxy to auth service - get user public key"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{AUTH_SERVICE_URL}/users/{user_id}/public-key", headers=headers)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Auth service unavailable: {str(e)}")


@app.post("/api/users/{user_id}/keys")
async def proxy_register_key_bundle(user_id: str, request: Request):
    """Proxy to auth service - register Signal key bundle"""
    body = await request.json()
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{AUTH_SERVICE_URL}/users/{user_id}/keys", json=body, headers=headers)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Auth service unavailable: {str(e)}")


@app.post("/api/users/{user_id}/friends")
async def proxy_add_friend(user_id: str, request: Request):
    """Proxy to auth service - add friend"""
    body = await request.json()
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{AUTH_SERVICE_URL}/users/{user_id}/friends", json=body, headers=headers)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Auth service unavailable: {str(e)}")


@app.get("/api/users/{user_id}/friends")
async def proxy_list_friends(user_id: str, request: Request):
    """Proxy to auth service - list friends"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{AUTH_SERVICE_URL}/users/{user_id}/friends", headers=headers)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Auth service unavailable: {str(e)}")


@app.delete("/api/users/{user_id}/friends/{friend_id}")
async def proxy_remove_friend(user_id: str, friend_id: str, request: Request):
    """Proxy to auth service - remove friend"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.delete(f"{AUTH_SERVICE_URL}/users/{user_id}/friends/{friend_id}", headers=headers)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Auth service unavailable: {str(e)}")


@app.get("/api/users/{user_id}/bundle")
async def proxy_get_key_bundle(user_id: str, request: Request, device_id: str | None = None):
    """Proxy to auth service - get Signal key bundle"""
    headers = forward_headers(request)
    url = f"{AUTH_SERVICE_URL}/users/{user_id}/bundle"
    if device_id:
        url += f"?device_id={device_id}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers)
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
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{CHAT_SERVICE_URL}/chats", json=body, headers=headers)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Chat service unavailable: {str(e)}")


@app.get("/api/chats")
async def proxy_get_chats(request: Request):
    """Proxy to chat service - get all chats"""
    headers = forward_headers(request)
    params = forward_query_params(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{CHAT_SERVICE_URL}/chats", headers=headers, params=params)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Chat service unavailable: {str(e)}")


@app.get("/api/chats/{chat_id}")
async def proxy_get_chat(chat_id: str, request: Request):
    """Proxy to chat service - get specific chat"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{CHAT_SERVICE_URL}/chats/{chat_id}", headers=headers)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Chat service unavailable: {str(e)}")


@app.post("/api/chats/{chat_id}/members")
async def proxy_add_member(chat_id: str, request: Request):
    """Proxy to chat service - add member"""
    body = await request.json()
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{CHAT_SERVICE_URL}/chats/{chat_id}/members", json=body, headers=headers)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Chat service unavailable: {str(e)}")


@app.delete("/api/chats/{chat_id}/members/{user_id}")
async def proxy_remove_member(chat_id: str, user_id: str, request: Request):
    """Proxy to chat service - remove member"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.delete(f"{CHAT_SERVICE_URL}/chats/{chat_id}/members/{user_id}", headers=headers)
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
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{MESSAGE_SERVICE_URL}/chats/{chat_id}/messages", json=body, headers=headers)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Message service unavailable: {str(e)}")


@app.get("/api/chats/{chat_id}/messages")
async def proxy_get_messages(chat_id: str, request: Request, limit: int = 50):
    """Proxy to message service - get messages"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{MESSAGE_SERVICE_URL}/chats/{chat_id}/messages?limit={limit}", headers=headers)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Message service unavailable: {str(e)}")


@app.get("/api/messages/{message_id}")
async def proxy_get_message(message_id: str, request: Request):
    """Proxy to message service - get specific message"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{MESSAGE_SERVICE_URL}/messages/{message_id}", headers=headers)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Message service unavailable: {str(e)}")


@app.delete("/api/messages/{message_id}")
async def proxy_delete_message(message_id: str, request: Request):
    """Proxy to message service - delete message"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.delete(f"{MESSAGE_SERVICE_URL}/messages/{message_id}", headers=headers)
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
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{MEDIA_SERVICE_URL}/media/upload-url", json=body, headers=headers)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Media service unavailable: {str(e)}")


@app.post("/api/media/complete")
async def proxy_complete_upload(request: Request):
    """Proxy to media service - complete upload"""
    body = await request.json()
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{MEDIA_SERVICE_URL}/media/complete", json=body, headers=headers)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Media service unavailable: {str(e)}")


@app.get("/api/media/{media_id}/download-url")
async def proxy_get_download_url(media_id: str, request: Request):
    """Proxy to media service - get download URL"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{MEDIA_SERVICE_URL}/media/{media_id}/download-url", headers=headers)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Media service unavailable: {str(e)}")


@app.get("/api/media/{media_id}")
async def proxy_get_media_metadata(media_id: str, request: Request):
    """Proxy to media service - get media metadata"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{MEDIA_SERVICE_URL}/media/{media_id}", headers=headers)
            return response.json()
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Media service unavailable: {str(e)}")
