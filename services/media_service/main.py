from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional
import uuid
import boto3
import os
from datetime import datetime, timedelta

app = FastAPI()

# MinIO/S3 configuration (will be set via environment variables)
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "media")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

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
        # Fallback for testing without MinIO
        upload_url = f"http://minio:9000/{MINIO_BUCKET}/{media_id}"
    
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
        # Fallback for testing without MinIO
        download_url = f"http://minio:9000/{MINIO_BUCKET}/{media_id}"
    
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
