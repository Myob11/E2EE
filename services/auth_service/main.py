from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import psycopg2
import bcrypt
from jose import jwt
from datetime import datetime, timedelta
import os

app = FastAPI()

# Database connection (will be set via environment variables)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/auth_db")

# JWT settings
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# In-memory user storage (for testing without DB)
users_db = {}

# Pydantic models
class UserCreate(BaseModel):
    username: str
    password: str
    public_key: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    username: str
    public_key: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str

class LoginRequest(BaseModel):
    username: str
    password: str

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

@app.get("/health")
def health():
    return {"status": "ok", "service": "auth_service"}

@app.post("/register", response_model=UserResponse)
def register(user: UserCreate):
    """Register a new user with public key for E2EE"""
    user_id = f"user_{len(users_db) + 1}"
    
    # Hash password
    hashed_password = bcrypt.hashpw(user.password.encode(), bcrypt.gensalt()).decode()
    
    users_db[user_id] = {
        "id": user_id,
        "username": user.username,
        "password": hashed_password,
        "public_key": user.public_key
    }
    
    return UserResponse(
        id=user_id,
        username=user.username,
        public_key=user.public_key
    )

@app.post("/login", response_model=Token)
def login(login_data: LoginRequest):
    """Login and get access token"""
    # Find user by username
    user = None
    for u in users_db.values():
        if u["username"] == login_data.username:
            user = u
            break
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Verify password
    if not bcrypt.checkpw(login_data.password.encode(), user["password"].encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Create token
    access_token = create_access_token({"sub": user["id"], "username": user["username"]})
    
    return Token(access_token=access_token, token_type="bearer")

@app.get("/users/me", response_model=UserResponse)
def get_current_user(user_id: str = Depends(lambda: "user_1")):
    """Get current user info"""
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = users_db[user_id]
    return UserResponse(id=user["id"], username=user["username"], public_key=user["public_key"])

@app.get("/users/{user_id}/public-key")
def get_user_public_key(user_id: str):
    """Get a user's public key for E2EE"""
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"user_id": user_id, "public_key": users_db[user_id]["public_key"]}
