from fastapi import FastAPI, HTTPException, Depends, Header
from jose import jwt
from jose.exceptions import JWTError
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import time
import bcrypt
import psycopg2
import psycopg2.extras
from psycopg2 import sql
from urllib.parse import unquote, urlparse, urlunparse
import os
import logging
import time

app = FastAPI()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("auth_service")


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

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/auth_db")

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Pydantic models
class SignalKeyBundle(BaseModel):
    identity_key: str
    signed_prekey: str
    one_time_prekeys: List[str]
    registration_id: Optional[int] = None
    device_id: Optional[str] = None

class UserCreate(BaseModel):
    username: str
    password: str
    public_key: Optional[str] = None
    identity_key: Optional[str] = None
    signed_prekey: Optional[str] = None
    one_time_prekeys: Optional[List[str]] = None
    registration_id: Optional[int] = None
    device_id: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    username: str
    public_key: Optional[str] = None
    registration_id: Optional[int] = None

class FriendCreate(BaseModel):
    friend_id: str

class FriendResponse(BaseModel):
    user_id: str
    friend_id: str
    status: str

class FriendUserResponse(BaseModel):
    id: str
    username: str
    public_key: Optional[str] = None
    registration_id: Optional[int] = None

class Token(BaseModel):
    access_token: str
    token_type: str

class LoginRequest(BaseModel):
    username: str
    password: str

class KeyBundleResponse(BaseModel):
    user_id: str
    identity_key: str
    signed_prekey: str
    one_time_prekey: Optional[str] = None
    registration_id: Optional[int] = None
    device_id: str


def get_db_conn():
    parsed = urlparse(DATABASE_URL)
    return psycopg2.connect(
        host=parsed.hostname or "postgres",
        port=parsed.port or 5432,
        user=unquote(parsed.username or "postgres"),
        password=unquote(parsed.password or ""),
        dbname=parsed.path.lstrip("/") or "auth_db",
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def get_admin_db_url():
    parsed = urlparse(DATABASE_URL)
    admin_path = "/postgres"
    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        admin_path,
        parsed.params,
        parsed.query,
        parsed.fragment,
    ))


def get_target_db_name():
    parsed = urlparse(DATABASE_URL)
    return parsed.path.lstrip("/") or "postgres"


def ensure_database_exists():
    db_name = get_target_db_name()
    if db_name == "postgres":
        return

    admin_db_url = get_admin_db_url()
    conn = psycopg2.connect(admin_db_url, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        conn.autocommit = True
        cur = conn.cursor()
        try:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            if not cur.fetchone():
                cur.execute(sql.SQL("CREATE DATABASE {};").format(sql.Identifier(db_name)))
        finally:
            cur.close()
    finally:
        conn.close()


def wait_for_db(max_retries: int = 10, delay_seconds: int = 2):
    last_error = None
    for _ in range(max_retries):
        try:
            with get_db_conn():
                return
        except psycopg2.OperationalError as exc:
            last_error = exc
            error_text = str(exc).lower()
            if "does not exist" in error_text:
                try:
                    ensure_database_exists()
                    continue
                except Exception as inner_exc:
                    last_error = inner_exc
            time.sleep(delay_seconds)
    raise last_error


def setup_database():
    wait_for_db()
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE SEQUENCE IF NOT EXISTS user_id_seq;")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id text PRIMARY KEY,
                    username text UNIQUE NOT NULL,
                    password text NOT NULL,
                    public_key text,
                    registration_id int
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS devices (
                    id serial PRIMARY KEY,
                    user_id text NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    device_id text NOT NULL,
                    identity_key text NOT NULL,
                    signed_prekey text NOT NULL,
                    one_time_prekeys jsonb NOT NULL,
                    registration_id int,
                    UNIQUE (user_id, device_id)
                )
                """
            )
            # One-time prekeys stored as separate rows for atomic consumption
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS one_time_prekeys (
                    id serial PRIMARY KEY,
                    user_id text NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    device_id text NOT NULL,
                    prekey text NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )

            # Migrate any existing JSONB prekeys from devices into one_time_prekeys
            cur.execute(
                "SELECT id, user_id, device_id, one_time_prekeys FROM devices WHERE jsonb_array_length(one_time_prekeys) > 0"
            )
            rows = cur.fetchall()
            for row in rows:
                dev_id = row["device_id"]
                user_id = row["user_id"]
                prekeys = row["one_time_prekeys"] or []
                for pk in prekeys:
                    cur.execute(
                        "INSERT INTO one_time_prekeys (user_id, device_id, prekey) VALUES (%s, %s, %s)",
                        (user_id, dev_id, pk),
                    )
                # clear JSONB array to avoid duplication
                cur.execute("UPDATE devices SET one_time_prekeys = %s WHERE id = %s", (psycopg2.extras.Json([]), row["id"]))
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS friends (
                    id serial PRIMARY KEY,
                    user_id text NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    friend_id text NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                    status text NOT NULL DEFAULT 'accepted',
                    UNIQUE (user_id, friend_id)
                )
                """
            )


def create_access_token(data: dict):
    to_encode = data.copy()
    now = datetime.utcnow()
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": now})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_user_by_username(username: str):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE username = %s", (username,))
            return cur.fetchone()


def get_user_by_id(user_id: str):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            return cur.fetchone()


def get_device(user_id: str, device_id: str):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM devices WHERE user_id = %s AND device_id = %s",
                (user_id, device_id),
            )
            return cur.fetchone()


def get_friends(user_id: str):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT u.user_id, u.username, u.public_key, u.registration_id "
                "FROM friends f "
                "JOIN users u ON u.user_id = f.friend_id "
                "WHERE f.user_id = %s",
                (user_id,),
            )
            return cur.fetchall()


def friend_exists(user_id: str, friend_id: str):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM friends WHERE user_id = %s AND friend_id = %s",
                (user_id, friend_id),
            )
            return cur.fetchone() is not None


def add_friend_relation(user_id: str, friend_id: str):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO friends (user_id, friend_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (user_id, friend_id),
            )


def remove_friend_relation(user_id: str, friend_id: str):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM friends WHERE user_id = %s AND friend_id = %s",
                (user_id, friend_id),
            )


def get_first_device(user_id: str):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM devices WHERE user_id = %s ORDER BY id LIMIT 1",
                (user_id,),
            )
            return cur.fetchone()


def parse_bearer_token(authorization: Optional[str] = Header(None)) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")


@app.on_event("startup")
def on_startup():
    setup_database()


@app.get("/health")
def health():
    return {"status": "ok", "service": "auth_service"}


@app.post("/register", response_model=UserResponse)
def register(user: UserCreate):
    """Register a new user with optional Signal key bundle."""
    identity_key = user.identity_key or user.public_key
    hashed_password = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt()).decode()

    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO users (user_id, username, password, public_key, registration_id) "
                "VALUES (concat('user_', nextval('user_id_seq')), %s, %s, %s, %s) "
                "RETURNING user_id",
                (user.username, hashed_password, identity_key, user.registration_id),
            )
            user_id = cur.fetchone()["user_id"]

            if identity_key and user.signed_prekey and user.one_time_prekeys:
                device_id = user.device_id or "default"
                cur.execute(
                    "INSERT INTO devices (user_id, device_id, identity_key, signed_prekey, one_time_prekeys, registration_id) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        user_id,
                        device_id,
                        identity_key,
                        user.signed_prekey,
                        psycopg2.extras.Json(user.one_time_prekeys),
                        user.registration_id,
                    ),
                )

    return UserResponse(
        id=user_id,
        username=user.username,
        public_key=identity_key,
        registration_id=user.registration_id,
    )


@app.post("/login", response_model=Token)
def login(login_data: LoginRequest):
    """Login and get access token"""
    user = get_user_by_username(login_data.username)
    if not user or not bcrypt.checkpw(login_data.password.encode(), user["password"].encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token({"sub": user["user_id"], "username": user["username"]})
    return Token(access_token=access_token, token_type="bearer")


@app.get("/users/me", response_model=UserResponse)
def get_current_user(user_id: str = Depends(parse_bearer_token)):
    """Get current user info from JWT token"""
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(
        id=user["user_id"],
        username=user["username"],
        public_key=user.get("public_key"),
        registration_id=user.get("registration_id"),
    )


@app.post("/users/{user_id}/keys")
def register_key_bundle(user_id: str, bundle: SignalKeyBundle, current_user_id: str = Depends(parse_bearer_token)):
    """Register or refresh a Signal key bundle for a device."""
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Cannot register keys for another user")

    if not get_user_by_id(user_id):
        raise HTTPException(status_code=404, detail="User not found")

    device_id = bundle.device_id or "default"
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO devices (user_id, device_id, identity_key, signed_prekey, one_time_prekeys, registration_id) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (user_id, device_id) DO UPDATE SET "
                "identity_key = EXCLUDED.identity_key, "
                "signed_prekey = EXCLUDED.signed_prekey, "
                "one_time_prekeys = EXCLUDED.one_time_prekeys, "
                "registration_id = EXCLUDED.registration_id",
                (
                    user_id,
                    device_id,
                    bundle.identity_key,
                    bundle.signed_prekey,
                    psycopg2.extras.Json(bundle.one_time_prekeys),
                    bundle.registration_id,
                ),
            )
            cur.execute(
                "UPDATE users SET public_key = %s, registration_id = %s WHERE user_id = %s",
                (bundle.identity_key, bundle.registration_id, user_id),
            )
            # Store one-time prekeys into dedicated table for atomic consumption
            if bundle.one_time_prekeys:
                cur.execute(
                    "DELETE FROM one_time_prekeys WHERE user_id = %s AND device_id = %s",
                    (user_id, device_id),
                )
                for pk in bundle.one_time_prekeys:
                    cur.execute(
                        "INSERT INTO one_time_prekeys (user_id, device_id, prekey) VALUES (%s, %s, %s)",
                        (user_id, device_id, pk),
                    )
                # clear JSONB storage to avoid duplication
                cur.execute(
                    "UPDATE devices SET one_time_prekeys = %s WHERE user_id = %s AND device_id = %s",
                    (psycopg2.extras.Json([]), user_id, device_id),
                )

    return {"user_id": user_id, "device_id": device_id, "status": "ok"}


@app.get("/users/{user_id}/bundle", response_model=KeyBundleResponse)
def get_key_bundle(user_id: str, device_id: Optional[str] = None):
    """Retrieve a user's Signal key bundle for session establishment."""
    if not get_user_by_id(user_id):
        raise HTTPException(status_code=404, detail="User not found")

    bundle = get_device(user_id, device_id) if device_id else get_first_device(user_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="No device bundle registered")

    one_time_prekey = None
    # Atomically consume a one-time prekey from the dedicated table to avoid race conditions
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH sel AS (
                    SELECT id, prekey FROM one_time_prekeys
                    WHERE user_id = %s AND device_id = %s
                    ORDER BY id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                DELETE FROM one_time_prekeys WHERE id IN (SELECT id FROM sel) RETURNING prekey
                """,
                (user_id, bundle["device_id"]),
            )
            row = cur.fetchone()
            if row:
                # row may be a dict or tuple depending on cursor; handle both
                try:
                    one_time_prekey = row["prekey"]
                except Exception:
                    one_time_prekey = row[0]

    return KeyBundleResponse(
        user_id=user_id,
        identity_key=bundle["identity_key"],
        signed_prekey=bundle["signed_prekey"],
        one_time_prekey=one_time_prekey,
        registration_id=bundle.get("registration_id"),
        device_id=bundle["device_id"],
    )


@app.get("/users/{user_id}/public-key")
def get_user_public_key(user_id: str, device_id: Optional[str] = None):
    """Get a user's public identity key for E2EE."""
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if device_id:
        device = get_device(user_id, device_id)
        if device:
            return {
                "user_id": user_id,
                "device_id": device["device_id"],
                "public_key": device["identity_key"],
            }

    first_device = get_first_device(user_id)
    if first_device:
        return {
            "user_id": user_id,
            "device_id": first_device["device_id"],
            "public_key": first_device["identity_key"],
        }

    return {"user_id": user_id, "public_key": user.get("public_key")}


@app.get("/users/{user_id}/devices")
def list_devices(user_id: str, current_user_id: str = Depends(parse_bearer_token)):
    """List devices for the current user."""
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Cannot view devices for another user")

    if not get_user_by_id(user_id):
        raise HTTPException(status_code=404, detail="User not found")

    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT device_id, identity_key, signed_prekey, registration_id FROM devices WHERE user_id = %s",
                (user_id,),
            )
            rows = cur.fetchall()

    return [
        {
            "device_id": r["device_id"],
            "identity_key": r["identity_key"],
            "registration_id": r.get("registration_id"),
        }
        for r in rows
    ]


@app.delete("/users/{user_id}/devices/{device_id}")
def delete_device(user_id: str, device_id: str, current_user_id: str = Depends(parse_bearer_token)):
    """Revoke and remove a device for the current user."""
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Cannot delete device for another user")

    if not get_user_by_id(user_id):
        raise HTTPException(status_code=404, detail="User not found")

    with get_db_conn() as conn:
        with conn.cursor() as cur:
            # remove any pending prekeys for that device
            cur.execute(
                "DELETE FROM one_time_prekeys WHERE user_id = %s AND device_id = %s",
                (user_id, device_id),
            )
            cur.execute(
                "DELETE FROM devices WHERE user_id = %s AND device_id = %s RETURNING device_id",
                (user_id, device_id),
            )
            deleted = cur.fetchone()

    if not deleted:
        raise HTTPException(status_code=404, detail="Device not found")

    return {"user_id": user_id, "device_id": device_id, "status": "revoked"}


@app.post("/users/{user_id}/devices/{device_id}/rotate")
def rotate_signed_prekey(user_id: str, device_id: str, body: dict, current_user_id: str = Depends(parse_bearer_token)):
    """Rotate the signed prekey for a device. Expects JSON body with `signed_prekey` and optional `registration_id`."""
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Cannot rotate keys for another user")

    if not get_user_by_id(user_id):
        raise HTTPException(status_code=404, detail="User not found")

    signed_prekey = body.get("signed_prekey")
    registration_id = body.get("registration_id")
    if not signed_prekey:
        raise HTTPException(status_code=400, detail="signed_prekey is required")

    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE devices SET signed_prekey = %s, registration_id = COALESCE(%s, registration_id) WHERE user_id = %s AND device_id = %s RETURNING device_id",
                (signed_prekey, registration_id, user_id, device_id),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Device not found")

    return {"user_id": user_id, "device_id": device_id, "status": "rotated"}


@app.get("/users", response_model=List[FriendUserResponse])
def search_users(query: str, current_user_id: str = Depends(parse_bearer_token)):
    """Search registered users by username prefix."""
    # Require authentication to search users.
    if not current_user_id:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")

    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, username, public_key, registration_id "
                "FROM users "
                "WHERE username ILIKE %s "
                "ORDER BY username ASC "
                "LIMIT 50",
                (query + "%",),
            )
            rows = cur.fetchall()

    return [
        FriendUserResponse(
            id=row["user_id"],
            username=row["username"],
            public_key=row.get("public_key"),
            registration_id=row.get("registration_id"),
        )
        for row in rows
    ]

@app.post("/users/{user_id}/friends", response_model=FriendResponse)
def add_friend(user_id: str, friend: FriendCreate, current_user_id: str = Depends(parse_bearer_token)):
    """Add a friend relationship for the current user."""
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Cannot manage friends for another user")

    if user_id == friend.friend_id:
        raise HTTPException(status_code=400, detail="Cannot add yourself as a friend")

    if not get_user_by_id(user_id) or not get_user_by_id(friend.friend_id):
        raise HTTPException(status_code=404, detail="User or friend not found")

    add_friend_relation(user_id, friend.friend_id)
    add_friend_relation(friend.friend_id, user_id)
    return FriendResponse(user_id=user_id, friend_id=friend.friend_id, status="accepted")


@app.get("/users/{user_id}/friends", response_model=List[FriendUserResponse])
def list_friends(user_id: str, current_user_id: str = Depends(parse_bearer_token)):
    """List friends for the current user."""
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Cannot view friends for another user")

    if not get_user_by_id(user_id):
        raise HTTPException(status_code=404, detail="User not found")

    friends = get_friends(user_id)
    return [
        FriendUserResponse(
            id=friend["user_id"],
            username=friend["username"],
            public_key=friend.get("public_key"),
            registration_id=friend.get("registration_id"),
        )
        for friend in friends
    ]


@app.delete("/users/{user_id}/friends/{friend_id}")
def remove_friend(user_id: str, friend_id: str, current_user_id: str = Depends(parse_bearer_token)):
    """Remove a friend relationship."""
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Cannot remove friends for another user")

    if not get_user_by_id(user_id) or not get_user_by_id(friend_id):
        raise HTTPException(status_code=404, detail="User or friend not found")

    remove_friend_relation(user_id, friend_id)
    remove_friend_relation(friend_id, user_id)
    return {"user_id": user_id, "friend_id": friend_id, "status": "removed"}