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

### List Devices
**Endpoint:** `GET /api/users/{user_id}/devices`

List registered devices and metadata for the authenticated user. Requires `Authorization: Bearer <token>` and the `user_id` in the token must match the path `user_id`.

**Response:**
```json
[
  {
    "device_id": "android-phone-1",
    "identity_key": "BASE64_IDENTITY_KEY",
    "registration_id": 12345
  }
]
```

### Delete Device (Revoke)
**Endpoint:** `DELETE /api/users/{user_id}/devices/{device_id}`

Revoke and remove a device for the current user. This deletes any pending one-time prekeys for the device and removes the device record.

**Response:**
```json
{
  "user_id": "user_1",
  "device_id": "android-phone-1",
  "status": "revoked"
}
```

### Rotate Signed Prekey
**Endpoint:** `POST /api/users/{user_id}/devices/{device_id}/rotate`

Rotate and publish a new signed prekey for an existing device. Body should contain the new `signed_prekey` and optional `registration_id`.

**Request Body:**
```json
{
  "signed_prekey": "BASE64_SIGNED_PREKEY",
  "registration_id": 12345
}
```

**Response:**
```json
{
  "user_id": "user_1",
  "device_id": "android-phone-1",
  "status": "rotated"
}
```

### Implementation notes: atomic prekey consumption
The service now stores one-time prekeys in a dedicated table `one_time_prekeys` and consumes them atomically using a `DELETE ... RETURNING` pattern with `FOR UPDATE SKIP LOCKED` to prevent race conditions. Legacy `devices.one_time_prekeys` JSONB arrays are migrated to the new table at startup; the JSONB array is cleared to avoid duplication.


## Chat Service

### Create Chat
**Endpoint:** `POST /api/chats`

Create a new chat (1:1 or group).

For individual chats (`is_group=false`), the backend enforces uniqueness by member pair:
- exactly 2 members are required
- if a chat for the same two members already exists, that existing chat is returned instead of creating a duplicate

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

The current MVP stores messages, read receipts, and chat indexes in MongoDB. New messages are published to the WebSocket stream via the API Gateway, and the API Gateway fans them out to websocket clients in the matching chat room.

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

## Message Read Receipts

### Mark Message As Read
**Endpoint:** `POST /api/messages/{message_id}/read`

Mark a message as read for the authenticated user.

**Headers:**
- `Authorization: Bearer {{auth_token}}`

**Response:**
```json
{
  "message_id": "msg_f5349dcf",
  "user_id": "user_11",
  "is_read": true
}
```

---

### Get Message Read Status
**Endpoint:** `GET /api/messages/{message_id}/read`

Check if the authenticated user has read a specific message.

**Headers:**
- `Authorization: Bearer {{auth_token}}`

**Response:**
```json
{
  "message_id": "msg_f5349dcf",
  "user_id": "user_11",
  "is_read": true
}
```

---

### Chat Stream
**Endpoint:** `WS /ws/chats/{chat_id}`

Use this websocket to receive realtime message delivery for a chat. The gateway validates the JWT and checks that the connected user is a chat member before upgrading the connection.

Message delivery flow:
- The message service stores the ciphertext in MongoDB first.
- It then POSTs an internal event to the API gateway at `/internal/events`.
- The gateway fan-outs that event to every websocket client connected to the same `chat_id`.
- The websocket receives the same `message.new` payload for sender and recipients, so the frontend should deduplicate by `message.id`.

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

The socket stays open after the initial connect message. Clients can keep it alive with periodic traffic if needed.

**Frontend example (TypeScript / browser WebSocket):**
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

export function connectChatStream(chatId: string, token: string, onMessage: (payload: ChatEvent) => void) {
  const socket = new WebSocket(`wss://secra.top/ws/chats/${chatId}?token=${encodeURIComponent(token)}`);

  socket.onopen = () => {
    console.log("chat websocket connected");
  };

  socket.onmessage = (event) => {
    const payload = JSON.parse(event.data) as ChatEvent;
    onMessage(payload);

    if (payload.type === "message.new") {
      const message = payload.message;

      // Example UI update path:
      // - ignore if the message is already in local state
      // - decrypt ciphertext on the client using the local Signal session state
      // - append the plaintext to the message list
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

**Frontend example usage:**
```ts
const socket = connectChatStream(chatId, authToken, (event) => {
  if (event.type === "connected") {
    console.log(`joined chat ${event.chat_id}`);
    return;
  }

  if (event.type === "message.new") {
    const incoming = event.message;
    // Compare incoming.id with local message IDs to avoid duplicates.
    // Decrypt incoming.ciphertext on the client, then store/render the plaintext.
  }
});

// Later, when leaving the chat screen:
socket.close();
```

---

## Media Service (MinIO S3 Profile Pictures)

The media service provides profile picture management using MinIO S3 storage for persistent, scalable file storage with pre-signed URLs for secure access.

### MinIO S3 Configuration

**Current Setup:**
- **Endpoint**: External MinIO at `212.235.185.13:9000`
- **Bucket**: `user-01` (persistent public MinIO bucket for all profile pictures)
- **Key Format**: `user-01/profiles/{username}/picture`
- **Access**: Public URLs via pre-signed URLs (1-hour expiration)
- **Supported Formats**: JPEG, PNG, WebP, GIF

**Environment Variables:**
```yaml
MINIO_ENDPOINT=212.235.185.13:9000
MINIO_ACCESS_KEY=user-01
MINIO_SECRET_KEY=thestrongestvajePass01
MINIO_BUCKET=user-01
MINIO_SECURE=false
DOMAIN=secra.top
```

---

### 1. Get Profile Picture Upload URL
**Endpoint:** `POST /api/profiles/{username}/picture`

Get a pre-signed S3 URL for uploading a profile picture. This URL is valid for 1 hour.

**Parameters:**
- `username` (path): Username for the profile picture
- `content_type` (query, optional): Image MIME type. Default: `image/jpeg`
  - Supported: `image/jpeg`, `image/png`, `image/webp`, `image/gif`

**Request Body:**
```json
{
  "content_type": "image/jpeg"
}
```

**Response:**
```json
{
  "username": "john_doe",
  "key": "user-01/profiles/john_doe/picture",
  "upload_url": "http://212.235.185.13:9000/user-01/profiles/john_doe/picture?AWSAccessKeyId=user-01&...",
  "expires_at": "2026-05-04T15:30:00Z"
}
```

**cURL Example:**
```bash
curl -X POST 'http://localhost:8004/profiles/john_doe/picture' \
  -H 'Content-Type: application/json' \
  -d '{"content_type": "image/jpeg"}'
```

**JavaScript Example:**
```javascript
async function getUploadUrl(username, contentType = 'image/jpeg') {
  const response = await fetch(
    `http://localhost:8004/profiles/${username}/picture`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content_type: contentType })
    }
  );
  if (!response.ok) throw new Error(`Failed to get upload URL: ${response.status}`);
  return await response.json();
}
```

---

### 2. Upload File to MinIO

After receiving the upload URL, upload the file directly to MinIO using a PUT request.

**cURL Example:**
```bash
curl -X PUT 'http://212.235.185.13:9000/user-01/profiles/john_doe/picture?AWSAccessKeyId=user-01&...' \
  -H 'Content-Type: image/jpeg' \
  --data-binary @/path/to/profile.jpg
```

**React Component Example:**
```typescript
import React, { useState } from 'react';

export function ProfilePictureUpload({ username }: { username: string }) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Validate file type
    if (!['image/jpeg', 'image/png', 'image/webp', 'image/gif'].includes(file.type)) {
      setError('Invalid image format. Please upload JPEG, PNG, WebP, or GIF.');
      return;
    }

    // Validate file size (max 5MB)
    if (file.size > 5 * 1024 * 1024) {
      setError('File is too large. Maximum size is 5MB.');
      return;
    }

    setUploading(true);
    setError(null);
    setSuccess(false);

    try {
      // Step 1: Get presigned upload URL from backend
      const uploadUrlResponse = await fetch(
        `http://localhost:8004/profiles/${username}/picture`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content_type: file.type })
        }
      );

      if (!uploadUrlResponse.ok) {
        throw new Error(`Backend error: ${uploadUrlResponse.status}`);
      }

      const { upload_url } = await uploadUrlResponse.json();

      // Step 2: Upload file directly to MinIO using presigned URL
      const uploadResponse = await fetch(upload_url, {
        method: 'PUT',
        body: file,
        headers: { 'Content-Type': file.type }
      });

      if (!uploadResponse.ok) {
        throw new Error(`MinIO upload failed: ${uploadResponse.status}`);
      }

      // Step 3: Mark upload as complete (optional but recommended)
      const completeResponse = await fetch(
        `http://localhost:8004/profiles/${username}/picture/complete`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ size: file.size })
        }
      );

      if (!completeResponse.ok) {
        console.warn('Failed to mark upload complete, but file was uploaded');
      }

      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="profile-picture-upload">
      <input
        type="file"
        accept="image/*"
        onChange={handleFileChange}
        disabled={uploading}
      />
      {uploading && <p>Uploading...</p>}
      {success && <p style={{ color: 'green' }}>✓ Profile picture uploaded!</p>}
      {error && <p style={{ color: 'red' }}>✗ {error}</p>}
    </div>
  );
}
```

---

### 3. Mark Profile Picture Upload as Complete
**Endpoint:** `POST /api/profiles/{username}/picture/complete`

Mark a profile picture upload as complete and store its size (optional but recommended).

**Parameters:**
- `username` (path): Username

**Request Body:**
```json
{
  "size": 125432
}
```

**Response:**
```json
{
  "message": "Profile picture upload complete",
  "username": "john_doe",
  "size": 125432
}
```

**cURL Example:**
```bash
curl -X POST 'http://localhost:8004/profiles/john_doe/picture/complete' \
  -H 'Content-Type: application/json' \
  -d '{"size": 125432}'
```

---

### 4. Get Profile Picture Download URL
**Endpoint:** `GET /api/profiles/{username}/picture`

Get a pre-signed S3 URL for downloading a profile picture. URL is valid for 1 hour.

**Parameters:**
- `username` (path): Username for the profile picture

**Response:**
```json
{
  "username": "john_doe",
  "key": "user-01/profiles/john_doe/picture",
  "download_url": "http://212.235.185.13:9000/user-01/profiles/john_doe/picture?AWSAccessKeyId=user-01&...",
  "expires_at": "2026-05-04T15:30:00Z",
  "content_type": "image/jpeg"
}
```

**cURL Example:**
```bash
curl 'http://localhost:8004/profiles/john_doe/picture'
```

**React Component Example:**
```typescript
import React, { useState, useEffect } from 'react';

export function ProfilePictureDisplay({ username }: { username: string }) {
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchProfilePicture = async () => {
      try {
        const response = await fetch(
          `http://localhost:8004/profiles/${username}/picture`
        );

        if (response.status === 404) {
          setImageUrl(null); // No picture uploaded yet
          return;
        }

        if (!response.ok) {
          throw new Error(`Failed to get download URL: ${response.status}`);
        }

        const { download_url } = await response.json();
        setImageUrl(download_url);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load profile picture');
      } finally {
        setLoading(false);
      }
    };

    fetchProfilePicture();
  }, [username]);

  if (loading) return <div>Loading profile picture...</div>;
  if (error) return <div style={{ color: 'red' }}>Error: {error}</div>;
  
  return (
    <div className="profile-picture">
      {imageUrl ? (
        <img
          src={imageUrl}
          alt={`${username}'s profile picture`}
          style={{ width: '200px', height: '200px', borderRadius: '50%' }}
        />
      ) : (
        <div className="placeholder">No profile picture</div>
      )}
    </div>
  );
}
```

---

### 5. Get Profile Picture Metadata
**Endpoint:** `GET /api/profiles/{username}/picture/metadata`

Get metadata about a profile picture.

**Parameters:**
- `username` (path): Username for the profile picture

**Response:**
```json
{
  "username": "john_doe",
  "key": "user-01/profiles/john_doe/picture",
  "content_type": "image/jpeg",
  "size": 125432,
  "uploaded_at": "2026-05-04T14:30:00Z"
}
```

**cURL Example:**
```bash
curl 'http://localhost:8004/profiles/john_doe/picture/metadata'
```

---

### Complete Profile Picture Upload Flow (Step-by-Step)

**Frontend Implementation:**

1. **User selects image from file input**
   - Validate file type (JPEG, PNG, WebP, GIF)
   - Validate file size (recommended max 5MB)

2. **Request upload URL from backend:**
   ```
   POST /api/profiles/{username}/picture
   Body: { "content_type": "image/jpeg" }
   ```

3. **Upload directly to MinIO using presigned URL:**
   ```
   PUT {upload_url}
   Body: file binary data
   ```

4. **(Optional) Mark upload complete:**
   ```
   POST /api/profiles/{username}/picture/complete
   Body: { "size": file.size }
   ```

5. **Download picture when needed:**
   ```
   GET /api/profiles/{username}/picture
   Response: { "download_url": "..." }
   ```

6. **Display image in UI using download_url**

---

### Error Responses

| Status | Error | Description |
|--------|-------|-------------|
| 400 | Invalid username | Username is empty or invalid |
| 400 | Invalid image content type | File type is not supported (only JPEG, PNG, WebP, GIF) |
| 404 | Profile picture not found | No picture exists for this username |
| 413 | File too large | File exceeds size limit |
| 500 | Server error | MinIO connection failed or internal error |

---

### Fallback Behavior

When MinIO is unavailable, the API returns fallback URLs in the format:
```
http://profiles.secra.top/{username}/picture
```

This allows the API to respond gracefully even if the S3 service is down.

---

### Legacy Media Upload Endpoints

#### Get Media Upload URL
**Endpoint:** `POST /api/media/upload-url`

**Request Body:**
```json
{
  "filename": "image.jpg",
  "content_type": "image/jpeg",
  "user_id": "user_1"
}
```

#### Mark Media Upload Complete
**Endpoint:** `POST /api/media/complete`

**Request Body:**
```json
{
  "media_id": "media_abc123",
  "size": 1024000
}
```

#### Get Media Download URL
**Endpoint:** `GET /api/media/{media_id}/download-url`

#### Get Media Metadata
**Endpoint:** `GET /api/media/{media_id}`

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

| Service | Internal Port | External Port | Access |
|---------|---------------|---------------|--------|
| NGINX | 80, 443 | 80, 443 | Public |
| API Gateway | 8000 | (via NGINX) | Internal |
| Auth Service | 8001 | (via NGINX) | Internal |
| Chat Service | 8002 | (via NGINX) | Internal |
| Message Service | 8003 | (via NGINX) | Internal |
| Media Service | 8004 | (via NGINX) | Internal |
| PostgreSQL | 5432 | **Not exposed** | Internal only |
| MongoDB | 27017 | **Not exposed** | Internal only |
| MinIO | 9000 | **Not exposed** | Internal only |
| Prometheus | 9090 | - | Internal only |
| Grafana | 3000 | - | Internal only |
| Loki | 3100 | - | Internal only |
| Alertmanager | 9093 | - | Internal only |

**Security Note:** All databases (PostgreSQL, MongoDB, MinIO) are only accessible within the Docker internal network and are not exposed to the host or internet.

---

## Notes

- **JWT Authentication:** Required for all protected endpoints (chat, message, friend, Signal key-bundle endpoints)
- **Public Endpoints:** `/health`, `/api/auth/register`, `/api/auth/login`, `/api/users/{user_id}/public-key`, `/api/users/{user_id}/bundle`, and media download endpoints
- **Realtime Message Delivery:** WebSocket at `/ws/chats/{chat_id}` requires JWT token
- **End-to-End Encryption:** Messages are encrypted on the client using Signal protocol; backend stores and relays ciphertext only
- **Chat & Message Storage:** Backed by MongoDB for scalability and flexibility
- **Media Storage:** Profile pictures and media files stored in MinIO (S3-compatible)
- **Message Delivery:** API Gateway proxies HTTP requests and distributes WebSocket messages to connected clients
- **Database Security:** All databases (PostgreSQL, MongoDB, MinIO) are internal-only with strong authentication
- **Monitoring:** Prometheus metrics, Grafana dashboards, Loki logs, and Alertmanager for proactive monitoring
- **Health Status:** Each service has health checks; failed services are automatically restarted

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