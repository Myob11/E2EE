from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, Depends, Header
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os
import asyncio
import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
import redis.asyncio as redis_async

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
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")

MESSAGE_EVENTS_CHANNEL = "chat_messages"


def _base64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def parse_bearer_token(authorization: str | None) -> str:
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


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, chat_id: str, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self._connections.setdefault(chat_id, []).append(websocket)

    async def disconnect(self, chat_id: str, websocket: WebSocket):
        async with self._lock:
            sockets = self._connections.get(chat_id, [])
            if websocket in sockets:
                sockets.remove(websocket)
            if not sockets and chat_id in self._connections:
                self._connections.pop(chat_id, None)

    async def broadcast(self, chat_id: str, payload: dict):
        async with self._lock:
            sockets = list(self._connections.get(chat_id, []))

        dead_sockets = []
        for socket in sockets:
            try:
                await socket.send_json(payload)
            except Exception:
                dead_sockets.append(socket)

        for socket in dead_sockets:
            await self.disconnect(chat_id, socket)


connection_manager = ConnectionManager()
redis_client: redis_async.Redis | None = None
redis_listener_task: asyncio.Task | None = None


def forward_headers(request: Request):
    headers = {}
    auth = request.headers.get("authorization")
    if auth:
        headers["Authorization"] = auth
    return headers


def forward_query_params(request: Request):
    return dict(request.query_params)


def build_proxy_response(response):
    try:
        content = response.json()
    except ValueError:
        content = response.text or {"detail": "Empty upstream response"}
    return JSONResponse(status_code=response.status_code, content=content)


@app.get("/health")
def health():
    return {"status": "ok", "service": "api_gateway", "domain": DOMAIN}


async def get_chat_via_gateway(chat_id: str, authorization: str):
    headers = {"Authorization": authorization}
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{CHAT_SERVICE_URL}/chats/{chat_id}", headers=headers)
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", "Unable to fetch chat")
            except ValueError:
                detail = response.text or "Unable to fetch chat"
            raise HTTPException(status_code=response.status_code, detail=detail)
        return response.json()


async def redis_message_listener():
    global redis_client
    while True:
        try:
            if redis_client is None:
                redis_client = redis_async.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

            pubsub = redis_client.pubsub()
            await pubsub.subscribe(MESSAGE_EVENTS_CHANNEL)
            async for event in pubsub.listen():
                if event.get("type") != "message":
                    continue

                raw_payload = event.get("data")
                if not raw_payload:
                    continue

                try:
                    payload = json.loads(raw_payload)
                except json.JSONDecodeError:
                    continue

                chat_id = payload.get("chat_id")
                if chat_id:
                    await connection_manager.broadcast(chat_id, payload)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(2)


@app.on_event("startup")
async def on_startup():
    global redis_listener_task
    redis_listener_task = asyncio.create_task(redis_message_listener())


@app.on_event("shutdown")
async def on_shutdown():
    global redis_listener_task, redis_client
    if redis_listener_task:
        redis_listener_task.cancel()
        try:
            await redis_listener_task
        except Exception:
            pass
        redis_listener_task = None
    if redis_client:
        await redis_client.close()
        redis_client = None


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
            return build_proxy_response(response)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Auth service unavailable: {str(e)}")


@app.post("/api/auth/login")
async def proxy_login(request: Request):
    """Proxy to auth service - login"""
    body = await request.json()
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{AUTH_SERVICE_URL}/login", json=body)
            return build_proxy_response(response)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Auth service unavailable: {str(e)}")


@app.get("/api/users/me")
async def proxy_get_current_user(request: Request):
    """Proxy to auth service - get current user"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{AUTH_SERVICE_URL}/users/me", headers=headers)
            return build_proxy_response(response)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Auth service unavailable: {str(e)}")


@app.get("/api/users")
async def proxy_search_users(request: Request):
    """Proxy to auth service - search users"""
    headers = forward_headers(request)
    params = forward_query_params(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{AUTH_SERVICE_URL}/users", headers=headers, params=params)
            return build_proxy_response(response)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Auth service unavailable: {str(e)}")


@app.get("/api/users/{user_id}/public-key")
async def proxy_get_public_key(user_id: str, request: Request):
    """Proxy to auth service - get user public key"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{AUTH_SERVICE_URL}/users/{user_id}/public-key", headers=headers)
            return build_proxy_response(response)
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
            return build_proxy_response(response)
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
            return build_proxy_response(response)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Auth service unavailable: {str(e)}")


@app.get("/api/users/{user_id}/friends")
async def proxy_list_friends(user_id: str, request: Request):
    """Proxy to auth service - list friends"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{AUTH_SERVICE_URL}/users/{user_id}/friends", headers=headers)
            return build_proxy_response(response)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Auth service unavailable: {str(e)}")


@app.delete("/api/users/{user_id}/friends/{friend_id}")
async def proxy_remove_friend(user_id: str, friend_id: str, request: Request):
    """Proxy to auth service - remove friend"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.delete(f"{AUTH_SERVICE_URL}/users/{user_id}/friends/{friend_id}", headers=headers)
            return build_proxy_response(response)
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
            return build_proxy_response(response)
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
            return build_proxy_response(response)
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
            return build_proxy_response(response)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Chat service unavailable: {str(e)}")


@app.get("/api/chats/{chat_id}")
async def proxy_get_chat(chat_id: str, request: Request):
    """Proxy to chat service - get specific chat"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{CHAT_SERVICE_URL}/chats/{chat_id}", headers=headers)
            return build_proxy_response(response)
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
            return build_proxy_response(response)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Chat service unavailable: {str(e)}")


@app.delete("/api/chats/{chat_id}/members/{user_id}")
async def proxy_remove_member(chat_id: str, user_id: str, request: Request):
    """Proxy to chat service - remove member"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.delete(f"{CHAT_SERVICE_URL}/chats/{chat_id}/members/{user_id}", headers=headers)
            return build_proxy_response(response)
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
            return build_proxy_response(response)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Message service unavailable: {str(e)}")


@app.get("/api/chats/{chat_id}/messages")
async def proxy_get_messages(chat_id: str, request: Request, limit: int = 50):
    """Proxy to message service - get messages"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{MESSAGE_SERVICE_URL}/chats/{chat_id}/messages?limit={limit}", headers=headers)
            return build_proxy_response(response)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Message service unavailable: {str(e)}")


@app.get("/api/messages/{message_id}")
async def proxy_get_message(message_id: str, request: Request):
    """Proxy to message service - get specific message"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{MESSAGE_SERVICE_URL}/messages/{message_id}", headers=headers)
            return build_proxy_response(response)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Message service unavailable: {str(e)}")


@app.delete("/api/messages/{message_id}")
async def proxy_delete_message(message_id: str, request: Request):
    """Proxy to message service - delete message"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.delete(f"{MESSAGE_SERVICE_URL}/messages/{message_id}", headers=headers)
            return build_proxy_response(response)
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
            return build_proxy_response(response)
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
            return build_proxy_response(response)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Media service unavailable: {str(e)}")


@app.get("/api/media/{media_id}/download-url")
async def proxy_get_download_url(media_id: str, request: Request):
    """Proxy to media service - get download URL"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{MEDIA_SERVICE_URL}/media/{media_id}/download-url", headers=headers)
            return build_proxy_response(response)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Media service unavailable: {str(e)}")


@app.get("/api/media/{media_id}")
async def proxy_get_media_metadata(media_id: str, request: Request):
    """Proxy to media service - get media metadata"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{MEDIA_SERVICE_URL}/media/{media_id}", headers=headers)
            return build_proxy_response(response)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Media service unavailable: {str(e)}")


@app.websocket("/ws/chats/{chat_id}")
async def websocket_chat(chat_id: str, websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not token:
        auth_header = websocket.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]

    if not token:
        await websocket.close(code=4401)
        return

    authorization = f"Bearer {token}"
    try:
        current_user_id = parse_bearer_token(authorization)
        chat = await get_chat_via_gateway(chat_id, authorization)
        if current_user_id not in chat.get("member_ids", []):
            await websocket.close(code=4403)
            return
    except HTTPException:
        await websocket.close(code=4401)
        return

    await connection_manager.connect(chat_id, websocket)
    try:
        await websocket.send_json({"type": "connected", "chat_id": chat_id, "user_id": current_user_id})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await connection_manager.disconnect(chat_id, websocket)
    except Exception:
        await connection_manager.disconnect(chat_id, websocket)
        await websocket.close(code=1011)
