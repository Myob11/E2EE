from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

app = FastAPI()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("api_gateway")

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
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")

MESSAGE_EVENTS_CHANNEL = "chat_messages"

REQUEST_COUNT = Counter(
    "api_gateway_requests_total",
    "Total HTTP requests handled by the API gateway",
    ["method", "path", "status"],
)
REQUEST_LATENCY = Histogram(
    "api_gateway_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
)
WEBSOCKET_CONNECTIONS = Counter(
    "api_gateway_websocket_connections_total",
    "Total websocket connections accepted by the API gateway",
    ["chat_id"],
)


def route_path(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", request.url.path)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        duration = time.perf_counter() - start
        path = route_path(request)
        status = getattr(response, "status_code", 500)
        REQUEST_COUNT.labels(request.method, path, str(status)).inc()
        REQUEST_LATENCY.labels(request.method, path).observe(duration)
        logger.info(
            "request method=%s path=%s status=%s duration_ms=%.2f client=%s",
            request.method,
            path,
            status,
            duration * 1000.0,
            request.client.host if request.client else "unknown",
        )


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
        WEBSOCKET_CONNECTIONS.labels(chat_id).inc()

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


@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


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


@app.post("/internal/events")
async def internal_events(request: Request):
    """Internal endpoint for services to post events (e.g. message.new).
    This replaces Redis pub/sub for event delivery inside the docker network.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    chat_id = payload.get("chat_id")
    if not chat_id:
        raise HTTPException(status_code=400, detail="chat_id required")

    # broadcast to websocket clients
    await connection_manager.broadcast(chat_id, payload)
    return JSONResponse(status_code=200, content={"status": "ok"})


@app.on_event("startup")
async def on_startup():
    # No external pub/sub required; services will POST events to /internal/events
    pass


@app.on_event("shutdown")
async def on_shutdown():
    pass


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


@app.delete("/api/chats/{chat_id}")
async def proxy_delete_chat(chat_id: str, request: Request):
    """Proxy to chat service - delete chat"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.delete(f"{CHAT_SERVICE_URL}/chats/{chat_id}", headers=headers)
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

@app.post("/api/profiles/{username}/picture")
async def proxy_get_profile_picture_upload_url(username: str, request: Request, content_type: str = "image/jpeg"):
    """Proxy to media service - get profile picture upload URL"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{MEDIA_SERVICE_URL}/profiles/{username}/picture?content_type={content_type}", headers=headers)
            return build_proxy_response(response)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Media service unavailable: {str(e)}")


@app.get("/api/profiles/{username}/picture")
async def proxy_get_profile_picture_download_url(username: str, request: Request):
    """Proxy to media service - get profile picture download URL"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{MEDIA_SERVICE_URL}/profiles/{username}/picture", headers=headers)
            return build_proxy_response(response)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Media service unavailable: {str(e)}")


@app.get("/api/profiles/{username}/picture/metadata")
async def proxy_get_profile_picture_metadata(username: str, request: Request):
    """Proxy to media service - get profile picture metadata"""
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{MEDIA_SERVICE_URL}/profiles/{username}/picture/metadata", headers=headers)
            return build_proxy_response(response)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Media service unavailable: {str(e)}")


@app.post("/api/profiles/{username}/picture/complete")
async def proxy_complete_profile_picture_upload(username: str, request: Request):
    """Proxy to media service - complete profile picture upload"""
    body = await request.json()
    headers = forward_headers(request)
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{MEDIA_SERVICE_URL}/profiles/{username}/picture/complete", json=body, headers=headers)
            return build_proxy_response(response)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Media service unavailable: {str(e)}")


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
