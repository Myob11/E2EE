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
import os

app = FastAPI()

# Database connection (will be set via environment variables)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/auth_db")

# JWT settings
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
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def wait_for_db(max_retries: int = 10, delay_seconds: int = 2):
    last_error = None
    for _ in range(max_retries):
        try:
            with get_db_conn():
                return
        except psycopg2.OperationalError as exc:
            last_error = exc
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


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
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
    prekeys = bundle["one_time_prekeys"] or []
    if prekeys:
        one_time_prekey = prekeys.pop(0)
        with get_db_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE devices SET one_time_prekeys = %s WHERE id = %s",
                    (psycopg2.extras.Json(prekeys), bundle["id"]),
                )

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
