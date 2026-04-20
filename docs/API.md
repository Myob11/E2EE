# E2EE Chat App - API Documentation

## Base URL
```
https://secra.top
```

For local development:
```
http://localhost:8000
```

---

## Authentication Service

### Register User
**Endpoint:** `POST /api/auth/register`

Register a new user with public key for E2EE encryption.

**Request Body:**
```json
{
  "username": "string",
  "password": "string",
  "public_key": "string (optional)"
}
```

**Response:**
```json
{
  "id": "user_1",
  "username": "string",
  "public_key": "string"
}
```

---

### Login
**Endpoint:** `POST /api/auth/login`

Login and receive access token.

**Request Body:**
```json
{
  "username": "string",
  "password": "string"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

---

### Get Current User
**Endpoint:** `GET /api/users/me`

Get current authenticated user info.

**Response:**
```json
{
  "id": "user_1",
  "username": "string",
  "public_key": "string"
}
```

---

### Get User Public Key
**Endpoint:** `GET /api/users/{user_id}/public-key`

Get a user's public key for E2EE encryption.

**Response:**
```json
{
  "user_id": "user_1",
  "public_key": "string"
}
```

---

## Chat Service

### Create Chat
**Endpoint:** `POST /api/chats`

Create a new chat (1:1 or group).

**Request Body:**
```json
{
  "name": "string (optional, for groups)",
  "member_ids": ["user_1", "user_2"],
  "is_group": false
}
```

**Response:**
```json
{
  "id": "chat_abc123",
  "name": "string",
  "is_group": false,
  "member_ids": ["user_1", "user_2"],
  "created_at": "2026-04-20T12:00:00Z"
}
```

---

### Get All Chats
**Endpoint:** `GET /api/chats`

Get all chats for the current user.

**Response:**
```json
[
  {
    "id": "chat_abc123",
    "name": "string",
    "is_group": false,
    "member_ids": ["user_1", "user_2"],
    "created_at": "2026-04-20T12:00:00Z"
  }
]
```

---

### Get Specific Chat
**Endpoint:** `GET /api/chats/{chat_id}`

Get a specific chat by ID.

**Response:**
```json
{
  "id": "chat_abc123",
  "name": "string",
  "is_group": false,
  "member_ids": ["user_1", "user_2"],
  "created_at": "2026-04-20T12:00:00Z"
}
```

---

### Add Member to Chat
**Endpoint:** `POST /api/chats/{chat_id}/members`

Add a member to a chat.

**Request Body:**
```json
{
  "user_id": "user_3"
}
```

**Response:**
```json
{
  "message": "Member added",
  "chat_id": "chat_abc123",
  "user_id": "user_3"
}
```

---

### Remove Member from Chat
**Endpoint:** `DELETE /api/chats/{chat_id}/members/{user_id}`

Remove a member from a chat.

**Response:**
```json
{
  "message": "Member removed",
  "chat_id": "chat_abc123",
  "user_id": "user_3"
}
```

---

## Message Service

### Send Message
**Endpoint:** `POST /api/chats/{chat_id}/messages`

Send an encrypted message to a chat. The message content is encrypted on the client using the Signal protocol.

**Request Body:**
```json
{
  "chat_id": "chat_abc123",
  "sender_id": "user_1",
  "ciphertext": "encrypted_message_content",
  "message_type": "text"
}
```

**Response:**
```json
{
  "id": "msg_xyz789",
  "chat_id": "chat_abc123",
  "sender_id": "user_1",
  "ciphertext": "encrypted_message_content",
  "message_type": "text",
  "created_at": "2026-04-20T12:00:00Z"
}
```

---

### Get Messages
**Endpoint:** `GET /api/chats/{chat_id}/messages`

Get messages for a chat with pagination.

**Query Parameters:**
- `limit` (optional, default: 50)

**Response:**
```json
[
  {
    "id": "msg_xyz789",
    "chat_id": "chat_abc123",
    "sender_id": "user_1",
    "ciphertext": "encrypted_message_content",
    "message_type": "text",
    "created_at": "2026-04-20T12:00:00Z"
  }
]
```

---

### Get Specific Message
**Endpoint:** `GET /api/messages/{message_id}`

Get a specific message by ID.

**Response:**
```json
{
  "id": "msg_xyz789",
  "chat_id": "chat_abc123",
  "sender_id": "user_1",
  "ciphertext": "encrypted_message_content",
  "message_type": "text",
  "created_at": "2026-04-20T12:00:00Z"
}
```

---

### Delete Message
**Endpoint:** `DELETE /api/messages/{message_id}`

Delete a message.

**Response:**
```json
{
  "message": "Message deleted",
  "message_id": "msg_xyz789"
}
```

---

## Media Service

### Get Upload URL
**Endpoint:** `POST /api/media/upload-url`

Get a pre-signed URL for uploading media files.

**Request Body:**
```json
{
  "filename": "image.jpg",
  "content_type": "image/jpeg",
  "user_id": "user_1"
}
```

**Response:**
```json
{
  "upload_id": "media_abc123",
  "upload_url": "http://minio:9000/media/media_abc123?signature=...",
  "expires_at": "2026-04-20T13:00:00Z"
}
```

---

### Complete Upload
**Endpoint:** `POST /api/media/complete`

Mark media upload as complete.

**Request Body:**
```json
{
  "media_id": "media_abc123",
  "size": 1024000
}
```

**Response:**
```json
{
  "message": "Upload complete",
  "media_id": "media_abc123"
}
```

---

### Get Download URL
**Endpoint:** `GET /api/media/{media_id}/download-url`

Get a pre-signed URL for downloading media.

**Response:**
```json
{
  "media_id": "media_abc123",
  "download_url": "http://minio:9000/media/media_abc123?signature=...",
  "expires_at": "2026-04-20T13:00:00Z"
}
```

---

### Get Media Metadata
**Endpoint:** `GET /api/media/{media_id}`

Get media file metadata.

**Response:**
```json
{
  "id": "media_abc123",
  "filename": "image.jpg",
  "content_type": "image/jpeg",
  "size": 1024000,
  "uploaded_by": "user_1",
  "created_at": "2026-04-20T12:00:00Z"
}
```

---

## Health Check

### API Gateway Health
**Endpoint:** `GET /health`

**Response:**
```json
{
  "status": "ok",
  "service": "api_gateway"
}
```

---

## Domain Configuration

| Service | Domain |
|---------|--------|
| API Gateway | `secra.top` |
| MinIO Console | `minio.secra.top` |
| Media Files | `media.secra.top` |

### DNS Records (Cloudflare)
Point the following records to your server's IP:

| Type | Name | Value |
|------|------|-------|
| A | secra.top | YOUR_SERVER_IP |
| A | www.secra.top | YOUR_SERVER_IP |
| A | minio.secra.top | YOUR_SERVER_IP |
| A | media.secra.top | YOUR_SERVER_IP |

---

## Service Ports (Internal)

| Service | Internal Port | External Port |
|---------|---------------|---------------|
| NGINX | 80, 443 | 80, 443 |
| API Gateway | 8000 | (via NGINX) |
| Auth Service | 8001 | (via NGINX) |
| Chat Service | 8002 | (via NGINX) |
| Message Service | 8003 | (via NGINX) |
| Media Service | 8004 | (via NGINX) |
| PostgreSQL | 5432 | - |
| Redis | 6379 | - |
| MongoDB | 27017 | - |
| MinIO | 9000 | - |
| MinIO Console | 9001 | - |

---

## Notes

- All endpoints (except `/health` and `/api/auth/register`) require authentication via JWT token.
- Messages are encrypted on the client using the Signal protocol — the backend only stores and relays ciphertext.
- Media files are stored in MinIO (S3-compatible storage).
- The API Gateway proxies all requests to the appropriate microservices.

---

## SSL/TLS Configuration

For production with HTTPS:

1. **Using Let's Encrypt (recommended):**
   ```bash
   # Install certbot
   sudo apt install certbot python3-certbot-nginx
   
   # Generate certificate
   sudo certbot --nginx -d secra.top -d www.secra.top
   ```

---

## Example Requests

### Register User
```bash
curl -X POST https://secra.top/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "secret123", "public_key": "..."}'
```

### Login
```bash
curl -X POST https://secra.top/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "secret123"}'
```

### Create Chat
```bash
curl -X POST https://secra.top/api/chats \
  -H "Content-Type: application/json" \
  -d '{"member_ids": ["user_1", "user_2"], "is_group": false}'
```

### Send Message
```bash
curl -X POST https://secra.top/api/chats/chat_abc123/messages \
  -H "Content-Type: application/json" \
  -d '{"chat_id": "chat_abc123", "sender_id": "user_1", "ciphertext": "encrypted...", "message_type": "text"}'
```