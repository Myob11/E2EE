# E2EE Chat App - API Documentation

## Base URL
```
https://secra.top
```

For local development:
```
http://localhost:8000
```

> A Postman collection and environment file are provided in the repository:
> - `postman_collection.json`
> - `postman_environment.json`
>
> Import these into Postman and set `base_url` to your target host.

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

### Search Users
**Endpoint:** `GET /api/users?query={username_prefix}`

Search for users by username prefix. This is intended for friend search in the frontend.

**Headers:**
- `Authorization: Bearer {{auth_token}}`

**Response:**
```json
[
  {
    "id": "user_2",
    "username": "alice",
    "public_key": "string",
    "registration_id": 12345
  }
]
```

---

### Register Signal Key Bundle
**Endpoint:** `POST /api/users/{user_id}/keys`

Register or refresh a Signal-style key bundle for a user device.

**Request Body:**
```json
{
  "identity_key": "string",
  "signed_prekey": "string",
  "one_time_prekeys": ["string"],
  "registration_id": 12345,
  "device_id": "android-phone-1"
}
```

**Response:**
```json
{
  "user_id": "user_1",
  "device_id": "android-phone-1",
  "status": "ok"
}
```

---

### Add Friend
**Endpoint:** `POST /api/users/{user_id}/friends`

Add a friend relationship for the authenticated user.

**Request Body:**
```json
{
  "friend_id": "user_2"
}
```

**Response:**
```json
{
  "user_id": "user_1",
  "friend_id": "user_2",
  "status": "accepted"
}
```

---

### List Friends
**Endpoint:** `GET /api/users/{user_id}/friends`

List friends for the authenticated user.

**Response:**
```json
[
  {
    "id": "user_2",
    "username": "alice",
    "public_key": "string",
    "registration_id": 12345
  }
]
```

---

### Remove Friend
**Endpoint:** `DELETE /api/users/{user_id}/friends/{friend_id}`

Remove an existing friend relationship.

**Response:**
```json
{
  "user_id": "user_1",
  "friend_id": "user_2",
  "status": "removed"
}
```

---

### Get User Key Bundle
**Endpoint:** `GET /api/users/{user_id}/bundle`

Retrieve a user's public Signal key bundle for session establishment.
One one-time prekey is consumed on each request.

**Response:**
```json
{
  "user_id": "user_1",
  "identity_key": "string",
  "signed_prekey": "string",
  "one_time_prekey": "string",
  "registration_id": 12345,
  "device_id": "android-phone-1"
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

### Get Chats
**Endpoint:** `GET /api/chats`

Returns chats for the requested user. The backend forwards query parameters to the chat service.

**Query Parameters:**
- `user_id` (required): the ID of the user whose chats should be returned

**Example:**
```http
GET /api/chats?user_id=user_1
Authorization: Bearer <token>
```

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

### Get Chat
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

### Add Member
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

### Remove Member
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

The current MVP stores messages, read receipts, and chat indexes in Redis. New messages are published to the Redis channel `chat_messages`, and the API Gateway fans them out to websocket clients in the matching chat room.

### Send Message
**Endpoint:** `POST /api/chats/{chat_id}/messages`

Send an encrypted message to a chat. The backend stores ciphertext only.

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
  "created_at": "2026-04-20T12:00:00Z",
  "is_read": true
}
```

---

### Get Messages
**Endpoint:** `GET /api/chats/{chat_id}/messages`

Get messages for a chat with pagination.

**Query Parameters:**
- `limit` (optional, default `50`)
- `before` (optional ISO-8601 UTC timestamp cursor)

**Response:**
```json
[
  {
    "id": "msg_xyz789",
    "chat_id": "chat_abc123",
    "sender_id": "user_1",
    "ciphertext": "encrypted_message_content",
    "message_type": "text",
    "created_at": "2026-04-20T12:00:00Z",
    "is_read": false
  }
]
```

Example request:
```http
GET /api/chats/chat_abc123/messages?limit=20&before=2026-04-20T12:00:00Z
Authorization: Bearer <token>
```

---

### Get Message
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
  "created_at": "2026-04-20T12:00:00Z",
  "is_read": false
}
```

---

### Delete Message
**Endpoint:** `DELETE /api/messages/{message_id}`

Delete a message sent by the authenticated user.

**Response:**
```json
{
  "message": "Message deleted",
  "message_id": "msg_xyz789"
}
```

---

### Mark Message As Read
**Endpoint:** `POST /api/messages/{message_id}/read`

Marks the message as read for the authenticated user.

**Response:**
```json
{
  "message_id": "msg_f5349dcf",
  "user_id": "user_11",
  "is_read": true
}
```

---

### Get Read Status
**Endpoint:** `GET /api/messages/{message_id}/read`

Returns whether the authenticated user has read the message.

**Response:**
```json
{
  "message_id": "msg_f5349dcf",
  "user_id": "user_11",
  "is_read": true
}
```

---

## Realtime WebSocket Push

### Chat Stream
**Endpoint:** `WS /ws/chats/{chat_id}`

Use this websocket to receive realtime message delivery for a chat. The gateway validates the JWT and checks that the connected user is a chat member before upgrading the connection.

**Authentication:**
- `?token=<jwt>` query parameter, or
- `Authorization: Bearer <jwt>` header

**Initial server event:**
```json
{
  "type": "connected",
  "chat_id": "chat_abc123",
  "user_id": "user_1"
}
```

**Incoming message event:**
```json
{
  "type": "message.new",
  "id": "msg_xyz789",
  "chat_id": "chat_abc123",
  "sender_id": "user_1",
  "ciphertext": "encrypted_message_content",
  "message_type": "text",
  "created_at": "2026-04-20T12:00:00Z"
}
```

The socket stays open after the initial connect message. Clients can keep it alive with periodic traffic if needed.

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

- JWT is required for chat, message, friend, and Signal key-bundle endpoints.
- Public endpoints in the current backend are `/health`, `/api/auth/register`, `/api/auth/login`, `/api/users/{user_id}/public-key`, `/api/users/{user_id}/bundle`, and the media endpoints.
- Realtime message delivery is exposed through `/ws/chats/{chat_id}` and requires the same JWT as the HTTP routes.
- Messages are encrypted on the client using the Signal protocol; the backend stores and relays ciphertext only.
- Chat and message state are currently backed by Redis. The MongoDB container remains in the compose stack for future expansion, but it is not the current message store.
- Media files are stored in MinIO (S3-compatible storage).
- The API Gateway proxies all HTTP requests to the appropriate microservices.

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
  -H "Authorization: Bearer <token>" \
  -d '{"member_ids": ["user_1", "user_2"], "is_group": false}'
```

### Send Message
```bash
curl -X POST https://secra.top/api/chats/chat_abc123/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"chat_id": "chat_abc123", "sender_id": "user_1", "ciphertext": "encrypted...", "message_type": "text"}'
```