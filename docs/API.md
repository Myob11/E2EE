# E2EE Chat App - API Documentation

## Base URL

Production:
```text
https://secra.top
```

Local development:
```text
http://localhost:8000
```

> A Postman collection and environment file are provided in the repository:
>
> - `postman_collection.json`
> - `postman_environment.json`
>
> Import these into Postman and set `base_url` to your target host.

---

# Authentication Service

## Register User

**Endpoint:** `POST /api/auth/register`

Register a new user with a public key for E2EE encryption.

### Request Body

```json
{
  "username": "string",
  "password": "string",
  "public_key": "string (optional)"
}
```

### Response

```json
{
  "id": "user_1",
  "username": "string",
  "public_key": "string"
}
```

---

## Login

**Endpoint:** `POST /api/auth/login`

Login and receive an access token.

### Request Body

```json
{
  "username": "string",
  "password": "string"
}
```

### Response

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

---

## Get Current User

**Endpoint:** `GET /api/users/me`

Get current authenticated user info.

### Response

```json
{
  "id": "user_1",
  "username": "string",
  "public_key": "string"
}
```

---

## Delete My Account

**Endpoint:** `DELETE /api/users/me`

Deletes the authenticated user's account and associated data.

This endpoint will:

- Delete all messages sent by the user
- Delete individual (1:1) chats the user is part of and remove the user from group chats
- Delete the user's profile picture from object storage
- Remove the user's record from the authentication database (this cascades to devices, keys, and friend relations)

### Headers

```http
Authorization: Bearer <jwt>
```

### Response

```json
{
  "status": "ok",
  "user_id": "user_1",
  "results": {
    "messages_deleted": 55,
    "chats_deleted": 1,
    "chats_updated": 0,
    "profile_picture_deleted": true,
    "downstream_errors": {
      "message_service": null,
      "chat_service": null,
      "media_service": null
    }
  }
}
```

### Notes

- This operation is destructive and irreversible.
- Cleanup failures are reported inside `downstream_errors`.

### Field Notes

| Field | Description |
|---|---|
| `messages_deleted` | Number of message documents removed |
| `chats_deleted` | Number of deleted 1:1 chats |
| `chats_updated` | Number of updated group chats |
| `profile_picture_deleted` | Whether profile picture deletion succeeded |
| `downstream_errors` | Per-service cleanup errors |

---

## Get User Public Key

**Endpoint:** `GET /api/users/{user_id}/public-key`

Get a user's public key for E2EE encryption.

### Response

```json
{
  "user_id": "user_1",
  "public_key": "string"
}
```

---

## Search Users

**Endpoint:** `GET /api/users?query={username_prefix}`

Search for users by username prefix.

### Headers

```http
Authorization: Bearer {{auth_token}}
```

### Response

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

## Register Signal Key Bundle

**Endpoint:** `POST /api/users/{user_id}/keys`

Register or refresh a Signal-style key bundle for a user device.

### Request Body

```json
{
  "identity_key": "string",
  "signed_prekey": "string",
  "one_time_prekeys": ["string"],
  "registration_id": 12345,
  "device_id": "android-phone-1"
}
```

### Response

```json
{
  "user_id": "user_1",
  "device_id": "android-phone-1",
  "status": "ok"
}
```

---

## Add Friend

**Endpoint:** `POST /api/users/{user_id}/friends`

Add a friend relationship for the authenticated user.

### Request Body

```json
{
  "friend_id": "user_2"
}
```

### Response

```json
{
  "user_id": "user_1",
  "friend_id": "user_2",
  "status": "accepted"
}
```

---

## List Friends

**Endpoint:** `GET /api/users/{user_id}/friends`

List friends for the authenticated user.

### Response

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

## Remove Friend

**Endpoint:** `DELETE /api/users/{user_id}/friends/{friend_id}`

Remove an existing friend relationship.

### Response

```json
{
  "user_id": "user_1",
  "friend_id": "user_2",
  "status": "removed"
}
```

---

## Get User Key Bundle

**Endpoint:** `GET /api/users/{user_id}/bundle`

Retrieve a user's public Signal key bundle for session establishment.

One one-time prekey is consumed on each request.

### Response

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

## List Devices

**Endpoint:** `GET /api/users/{user_id}/devices`

List registered devices and metadata for the authenticated user.

### Headers

```http
Authorization: Bearer <token>
```

### Response

```json
[
  {
    "device_id": "android-phone-1",
    "identity_key": "BASE64_IDENTITY_KEY",
    "registration_id": 12345
  }
]
```

---

## Delete Device (Revoke)

**Endpoint:** `DELETE /api/users/{user_id}/devices/{device_id}`

Revoke and remove a device for the current user.

### Response

```json
{
  "user_id": "user_1",
  "device_id": "android-phone-1",
  "status": "revoked"
}
```

---

## Rotate Signed Prekey

**Endpoint:** `POST /api/users/{user_id}/devices/{device_id}/rotate`

Rotate and publish a new signed prekey for an existing device.

### Request Body

```json
{
  "signed_prekey": "BASE64_SIGNED_PREKEY",
  "registration_id": 12345
}
```

### Response

```json
{
  "user_id": "user_1",
  "device_id": "android-phone-1",
  "status": "rotated"
}
```

---

## Implementation Notes: Atomic Prekey Consumption

The service stores one-time prekeys in a dedicated table `one_time_prekeys` and consumes them atomically using:

```sql
DELETE ... RETURNING
```

with:

```sql
FOR UPDATE SKIP LOCKED
```

This prevents race conditions.

Legacy `devices.one_time_prekeys` JSONB arrays are migrated automatically at startup.

---

# Chat Service

## Create Chat

**Endpoint:** `POST /api/chats`

Create a new chat (1:1 or group).

### Notes

For individual chats (`is_group=false`):

- Exactly 2 members are required
- Existing chats between the same users are reused

### Request Body

```json
{
  "name": "string (optional, for groups)",
  "member_ids": ["user_1", "user_2"],
  "is_group": false
}
```

### Response

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

## Get Chats

**Endpoint:** `GET /api/chats`

Returns chats for the requested user.

### Query Parameters

| Parameter | Required | Description |
|---|---|---|
| `user_id` | Yes | User whose chats should be returned |

### Example

```http
GET /api/chats?user_id=user_1
Authorization: Bearer <token>
```

### Response

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

## Get Chat

**Endpoint:** `GET /api/chats/{chat_id}`

Get a specific chat by ID.

### Response

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

## Add Member

**Endpoint:** `POST /api/chats/{chat_id}/members`

Add a member to a chat.

### Request Body

```json
{
  "user_id": "user_3"
}
```

### Response

```json
{
  "message": "Member added",
  "chat_id": "chat_abc123",
  "user_id": "user_3"
}
```

---

## Remove Member

**Endpoint:** `DELETE /api/chats/{chat_id}/members/{user_id}`

Remove a member from a chat.

### Response

```json
{
  "message": "Member removed",
  "chat_id": "chat_abc123",
  "user_id": "user_3"
}
```

---

## Delete Chat

**Endpoint:** `DELETE /api/chats/{chat_id}`

Delete an entire chat.

Only chat members can delete the chat.

### Headers

```http
Authorization: Bearer {{auth_token}}
```

### Response

```json
{
  "message": "Chat deleted",
  "chat_id": "chat_abc123"
}
```

### Error Response

```json
{
  "detail": "Cannot delete a chat you are not a member of"
}
```

---

# Message Service

The MVP stores messages, read receipts, and chat indexes in MongoDB.

Messages are distributed through the API Gateway WebSocket fan-out system.

---

## Send Message

**Endpoint:** `POST /api/chats/{chat_id}/messages`

Send an encrypted message.

### Request Body

```json
{
  "chat_id": "chat_abc123",
  "sender_id": "user_1",
  "ciphertext": "encrypted_message_content",
  "message_type": "text"
}
```

### Response

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

## Get Messages

**Endpoint:** `GET /api/chats/{chat_id}/messages`

Get messages with pagination.

### Query Parameters

| Parameter | Default | Description |
|---|---|---|
| `limit` | `50` | Number of messages |
| `before` | - | ISO-8601 UTC cursor |

### Example

```http
GET /api/chats/chat_abc123/messages?limit=20&before=2026-04-20T12:00:00Z
Authorization: Bearer <token>
```

### Response

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

---

## Get Message

**Endpoint:** `GET /api/messages/{message_id}`

Get a specific message by ID.

### Response

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

## Delete Message

**Endpoint:** `DELETE /api/messages/{message_id}`

Delete a message sent by the authenticated user.

### Response

```json
{
  "message": "Message deleted",
  "message_id": "msg_xyz789"
}
```

---

## Mark Message As Read

**Endpoint:** `POST /api/messages/{message_id}/read`

Mark a message as read.

### Response

```json
{
  "message_id": "msg_f5349dcf",
  "user_id": "user_11",
  "is_read": true
}
```

---

## Get Read Status

**Endpoint:** `GET /api/messages/{message_id}/read`

Get read status for the authenticated user.

### Response

```json
{
  "message_id": "msg_f5349dcf",
  "user_id": "user_11",
  "is_read": true
}
```

---

# Chat Stream (WebSocket)

**Endpoint:** `WS /ws/chats/{chat_id}`

Realtime encrypted message delivery.

### Authentication

Either:

```text
?token=<jwt>
```

or:

```http
Authorization: Bearer <jwt>
```

### Initial Event

```json
{
  "type": "connected",
  "chat_id": "chat_abc123",
  "user_id": "user_1"
}
```

### Incoming Message Event

```json
{
  "type": "message.new",
  "chat_id": "chat_abc123",
  "message": {
    "id": "msg_xyz789",
    "chat_id": "chat_abc123",
    "sender_id": "user_1",
    "ciphertext": "encrypted_message_content",
    "message_type": "text",
    "created_at": "2026-04-20T12:00:00Z"
  }
}
```

### TypeScript Example

```ts
type ChatEvent =
  | { type: "connected"; chat_id: string; user_id: string }
  | {
      type: "message.new";
      chat_id: string;
      message: {
        id: string;
        chat_id: string;
        sender_id: string;
        ciphertext: string;
        message_type: string;
        created_at: string;
      };
    };

export function connectChatStream(
  chatId: string,
  token: string,
  onMessage: (payload: ChatEvent) => void
) {
  const socket = new WebSocket(
    `wss://secra.top/ws/chats/${chatId}?token=${encodeURIComponent(token)}`
  );

  socket.onopen = () => {
    console.log("chat websocket connected");
  };

  socket.onmessage = (event) => {
    const payload = JSON.parse(event.data) as ChatEvent;
    onMessage(payload);

    if (payload.type === "message.new") {
      const message = payload.message;

      console.log("new message", message.id, message.ciphertext);
    }
  };

  socket.onerror = (error) => {
    console.error("chat websocket error", error);
  };

  socket.onclose = () => {
    console.log("chat websocket closed");
  };

  return socket;
}
```

---

# Media Service (MinIO S3 Profile Pictures)

The media service manages profile pictures using MinIO S3-compatible storage.

---

## MinIO Configuration

| Setting | Value |
|---|---|
| Endpoint | `212.235.185.13:9000` |
| Bucket | `user-01` |
| Key Format | `user-01/profiles/{username}/picture` |
| URL Expiration | 1 hour |
| Formats | JPEG, PNG, WebP, GIF |

### Environment Variables

```yaml
MINIO_ENDPOINT=212.235.185.13:9000
MINIO_ACCESS_KEY=${MINIO_USER:-minioadmin}
MINIO_SECRET_KEY=${MINIO_PASSWORD:-<REDACTED>}
MINIO_BUCKET=user-01
MINIO_SECURE=false
DOMAIN=secra.top
```

---

## Get Profile Picture Upload URL

**Endpoint:** `POST /api/profiles/{username}/picture`

Get a pre-signed upload URL.

### Request Body

```json
{
  "content_type": "image/jpeg"
}
```

### Response

```json
{
  "username": "john_doe",
  "key": "user-01/profiles/john_doe/picture",
  "upload_url": "http://212.235.185.13:9000/user-01/profiles/john_doe/picture?...",
  "expires_at": "2026-05-04T15:30:00Z"
}
```

---

## Upload File to MinIO

Use the returned `upload_url`.

### Example

```bash
curl -X PUT 'http://212.235.185.13:9000/user-01/profiles/john_doe/picture?...' \
  -H 'Content-Type: image/jpeg' \
  --data-binary @/path/to/profile.jpg
```

---

## Mark Upload Complete

**Endpoint:** `POST /api/profiles/{username}/picture/complete`

### Request Body

```json
{
  "size": 125432
}
```

### Response

```json
{
  "message": "Profile picture upload complete",
  "username": "john_doe",
  "size": 125432
}
```

---

## Get Profile Picture Download URL

**Endpoint:** `GET /api/profiles/{username}/picture`

### Response

```json
{
  "username": "john_doe",
  "key": "user-01/profiles/john_doe/picture",
  "download_url": "http://212.235.185.13:9000/user-01/profiles/john_doe/picture?...",
  "expires_at": "2026-05-04T15:30:00Z",
  "content_type": "image/jpeg"
}
```

---

## Get Profile Picture Metadata

**Endpoint:** `GET /api/profiles/{username}/picture/metadata`

### Response

```json
{
  "username": "john_doe",
  "key": "user-01/profiles/john_doe/picture",
  "content_type": "image/jpeg",
  "size": 125432,
  "uploaded_at": "2026-05-04T14:30:00Z"
}
```

---

# Error Responses

| Status | Error | Description |
|---|---|---|
| 400 | Invalid username | Username is invalid |
| 400 | Invalid image content type | Unsupported file type |
| 404 | Profile picture not found | No picture exists |
| 413 | File too large | File exceeds limit |
| 500 | Server error | Internal or MinIO error |

---

# Fallback Behavior

When MinIO is unavailable:

```text
http://profiles.secra.top/{username}/picture
```

---

# Health Check

## API Gateway Health

**Endpoint:** `GET /health`

### Response

```json
{
  "status": "ok",
  "service": "api_gateway"
}
```

---

# Domain Configuration

| Service | Domain |
|---|---|
| API Gateway | `secra.top` |
| MinIO Console | `minio.secra.top` |
| Media Files | `media.secra.top` |

---

# Service Ports

| Service | Internal Port | External Port | Access |
|---|---|---|---|
| NGINX | 80, 443 | 80, 443 | Public |
| API Gateway | 8000 | via NGINX | Internal |
| Auth Service | 8001 | via NGINX | Internal |
| Chat Service | 8002 | via NGINX | Internal |
| Message Service | 8003 | via NGINX | Internal |
| Media Service | 8004 | via NGINX | Internal |
| PostgreSQL | 5432 | Not exposed | Internal |
| MongoDB | 27017 | Not exposed | Internal |
| MinIO | 9000 | Not exposed | Internal |

---

# Security Notes

- JWT authentication is required for protected endpoints
- Messages are end-to-end encrypted using the Signal protocol
- Backend stores ciphertext only
- Databases are internal-only
- WebSocket streams require JWT authentication
- Media is stored in MinIO
- Services are monitored with Prometheus, Grafana, Loki, and Alertmanager

---

# SSL/TLS Configuration

## Let's Encrypt

```bash
sudo apt install certbot python3-certbot-nginx

sudo certbot --nginx -d secra.top -d www.secra.top
```

---

# Example Requests

## Register User

```bash
curl -X POST https://secra.top/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"<REDACTED_PASSWORD>","public_key":"..."}'
```

---

## Login

```bash
curl -X POST https://secra.top/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"<REDACTED_PASSWORD>"}'
```

---

## Create Chat

```bash
curl -X POST https://secra.top/api/chats \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"member_ids":["user_1","user_2"],"is_group":false}'
```

---

## Send Message

```bash
curl -X POST https://secra.top/api/chats/chat_abc123/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"chat_id":"chat_abc123","sender_id":"user_1","ciphertext":"encrypted...","message_type":"text"}'
```
