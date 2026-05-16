from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional
import uuid
import boto3
import os
import logging
import time
from datetime import datetime, timedelta

app = FastAPI()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("media_service")


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

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "media")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
DOMAIN = os.getenv("DOMAIN", "secra.top")

# In-memory media storage (for testing without MinIO)
media_db = {}

# Initialize S3 client
s3_client = None

def get_s3_client():
    global s3_client
    if s3_client is None:
        s3_client = boto3.client(
            's3',
            endpoint_url=f"http://{MINIO_ENDPOINT}" if not MINIO_SECURE else f"https://{MINIO_ENDPOINT}",
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
            use_ssl=MINIO_SECURE
        )
    return s3_client

# Pydantic models
class MediaUploadResponse(BaseModel):
    upload_id: str
    upload_url: str
    expires_at: str

class MediaDownloadResponse(BaseModel):
    media_id: str
    download_url: str
    expires_at: str

class MediaMetadata(BaseModel):
    id: str
    filename: str
    content_type: str
    size: int
    uploaded_by: str
    created_at: str

@app.get("/health")
def health():
    return {"status": "ok", "service": "media_service"}

@app.post("/media/upload-url")
def get_upload_url(filename: str, content_type: str, user_id: str):
    """Get a pre-signed URL for uploading media"""
    media_id = f"media_{uuid.uuid4().hex[:8]}"
    
    # Generate pre-signed URL (for MinIO)
    try:
        s3 = get_s3_client()
        upload_url = s3.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': MINIO_BUCKET,
                'Key': media_id,
                'ContentType': content_type
            },
            ExpiresIn=3600  # 1 hour
        )
    except Exception:
        # Fallback for testing without MinIO - use domain
        protocol = "https" if MINIO_SECURE else "http"
        upload_url = f"{protocol}://media.{DOMAIN}/{MINIO_BUCKET}/{media_id}"
    
    media_db[media_id] = {
        "id": media_id,
        "filename": filename,
        "content_type": content_type,
        "size": 0,
        "uploaded_by": user_id,
        "created_at": datetime.utcnow().isoformat() + "Z"
    }
    
    expires_at = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
    
    return MediaUploadResponse(
        upload_id=media_id,
        upload_url=upload_url,
        expires_at=expires_at
    )

@app.post("/media/complete")
def complete_upload(media_id: str, size: int):
    """Mark upload as complete"""
    if media_id not in media_db:
        raise HTTPException(status_code=404, detail="Media not found")
    
    media_db[media_id]["size"] = size
    return {"message": "Upload complete", "media_id": media_id}

@app.get("/media/{media_id}/download-url")
def get_download_url(media_id: str):
    """Get a pre-signed URL for downloading media"""
    if media_id not in media_db:
        raise HTTPException(status_code=404, detail="Media not found")
    
    try:
        s3 = get_s3_client()
        download_url = s3.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': MINIO_BUCKET,
                'Key': media_id
            },
            ExpiresIn=3600  # 1 hour
        )
    except Exception:
        # Fallback for testing without MinIO - use domain
        protocol = "https" if MINIO_SECURE else "http"
        download_url = f"{protocol}://media.{DOMAIN}/{MINIO_BUCKET}/{media_id}"
    
    expires_at = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
    
    return MediaDownloadResponse(
        media_id=media_id,
        download_url=download_url,
        expires_at=expires_at
    )

@app.get("/media/{media_id}", response_model=MediaMetadata)
def get_media_metadata(media_id: str):
    """Get media metadata"""
    if media_id not in media_db:
        raise HTTPException(status_code=404, detail="Media not found")
    
    return MediaMetadata(**media_db[media_id])
# Profile Picture Endpoints
class ProfilePictureUploadResponse(BaseModel):
    username: str
    key: str
    upload_url: str
    expires_at: str


class ProfilePictureDownloadResponse(BaseModel):
    username: str
    key: str
    download_url: str
    expires_at: str
    content_type: str


class ProfilePictureMetadata(BaseModel):
    username: str
    key: str
    content_type: str
    size: int
    uploaded_at: str


class CompletePictureUploadRequest(BaseModel):
    size: int


@app.post("/profiles/{username}/picture", response_model=ProfilePictureUploadResponse)
def get_profile_picture_upload_url(username: str, content_type: str = "image/jpeg"):
    """Get a pre-signed URL for uploading a profile picture"""
    if not username or len(username) < 1:
        raise HTTPException(status_code=400, detail="Invalid username")
    
    if content_type not in ["image/jpeg", "image/png", "image/webp", "image/gif"]:
        raise HTTPException(status_code=400, detail="Invalid image content type")
    
    # S3 key format: profiles/{username}/picture
    s3_key = f"profiles/{username}/picture"
    
    try:
        s3 = get_s3_client()
        # Create bucket if it doesn't exist
        try:
            s3.head_bucket(Bucket=MINIO_BUCKET)
        except:
            s3.create_bucket(Bucket=MINIO_BUCKET)
        
        upload_url = s3.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': MINIO_BUCKET,
                'Key': s3_key,
                'ContentType': content_type
            },
            ExpiresIn=3600  # 1 hour
        )
    except Exception as e:
        logger.error(f"Error generating S3 upload URL: {str(e)}")
        # Fallback for testing without MinIO
        protocol = "https" if MINIO_SECURE else "http"
        upload_url = f"{protocol}://profiles.{DOMAIN}/{username}/picture"
    
    # Store metadata
    media_db[s3_key] = {
        "username": username,
        "content_type": content_type,
        "size": 0,
        "uploaded_at": datetime.utcnow().isoformat() + "Z"
    }
    
    expires_at = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
    
    return ProfilePictureUploadResponse(
        username=username,
        key=s3_key,
        upload_url=upload_url,
        expires_at=expires_at
    )


@app.get("/profiles/{username}/picture", response_model=ProfilePictureDownloadResponse)
def get_profile_picture_download_url(username: str):
    """Get a pre-signed URL for downloading a profile picture"""
    if not username or len(username) < 1:
        raise HTTPException(status_code=400, detail="Invalid username")
    
    s3_key = f"profiles/{username}/picture"
    
    if s3_key not in media_db:
        raise HTTPException(status_code=404, detail="Profile picture not found")
    
    metadata = media_db[s3_key]
    
    try:
        s3 = get_s3_client()
        download_url = s3.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': MINIO_BUCKET,
                'Key': s3_key
            },
            ExpiresIn=3600  # 1 hour
        )
    except Exception as e:
        logger.error(f"Error generating S3 download URL: {str(e)}")
        # Fallback for testing without MinIO
        protocol = "https" if MINIO_SECURE else "http"
        download_url = f"{protocol}://profiles.{DOMAIN}/{username}/picture"
    
    expires_at = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"
    
    return ProfilePictureDownloadResponse(
        username=username,
        key=s3_key,
        download_url=download_url,
        expires_at=expires_at,
        content_type=metadata.get("content_type", "image/jpeg")
    )


@app.get("/profiles/{username}/picture/metadata", response_model=ProfilePictureMetadata)
def get_profile_picture_metadata(username: str):
    """Get profile picture metadata"""
    if not username or len(username) < 1:
        raise HTTPException(status_code=400, detail="Invalid username")
    
    s3_key = f"profiles/{username}/picture"
    
    if s3_key not in media_db:
        raise HTTPException(status_code=404, detail="Profile picture not found")
    
    metadata = media_db[s3_key]
    
    return ProfilePictureMetadata(
        username=username,
        key=s3_key,
        content_type=metadata.get("content_type", "image/jpeg"),
        size=metadata.get("size", 0),
        uploaded_at=metadata.get("uploaded_at", "")
    )


@app.post("/profiles/{username}/picture/complete")
def complete_profile_picture_upload(username: str, request: CompletePictureUploadRequest):
    """Mark profile picture upload as complete"""
    if not username or len(username) < 1:
        raise HTTPException(status_code=400, detail="Invalid username")
    
    s3_key = f"profiles/{username}/picture"
    
    if s3_key not in media_db:
        raise HTTPException(status_code=404, detail="Upload not found")
    
    media_db[s3_key]["size"] = request.size
    logger.info(f"Profile picture upload completed for user {username}, size: {request.size} bytes")
    
    return {"message": "Profile picture upload complete", "username": username, "size": request.size}


@app.delete("/profiles/{username}/picture")
def delete_profile_picture(username: str):
    """Delete a user's profile picture from storage and metadata. Internal call allowed."""
    if not username or len(username) < 1:
        raise HTTPException(status_code=400, detail="Invalid username")

    s3_key = f"profiles/{username}/picture"

    # remove metadata if present
    if s3_key in media_db:
        try:
            del media_db[s3_key]
        except KeyError:
            pass

    # attempt to delete from S3/MinIO
    try:
        s3 = get_s3_client()
        s3.delete_object(Bucket=MINIO_BUCKET, Key=s3_key)
    except Exception:
        # best-effort; if MinIO unavailable ignore
        pass

    return {"message": "Profile picture deleted", "username": username}
