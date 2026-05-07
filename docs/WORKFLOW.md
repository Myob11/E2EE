# 🏗️ E2EE BACKEND SYSTEM - COMPLETE TECHNICAL DOCUMENTATION

## TABLE OF CONTENTS
1. System Overview & Architecture
2. Network Configuration & Communication Flow
3. Individual Service Breakdown
4. Database Layer - What Stores What
5. Persistence & Data Flow
6. Service-to-Service Communication
7. Request Flow Examples
8. Security & Authentication
9. Data Lifecycle & Retention

---

## 1. SYSTEM OVERVIEW & ARCHITECTURE

### 1.1 High-Level Architecture

Your E2EE Chat App backend is built on a **microservices architecture** with:
- **5 Core Microservices** (Auth, Chat, Message, Media, API Gateway)
- **3 Databases** (PostgreSQL, MongoDB, MinIO S3)
- **Complete Monitoring Stack** (Prometheus, Grafana, Loki, Alertmanager)
- **Docker Compose** for orchestration (isolated containers with internal Docker network)

**Key Architectural Principle:** All databases are **INTERNAL ONLY** - not exposed to the internet. Only NGINX (ports 80/443) and the API Gateway (port 8000 for local testing) are exposed.

### 1.2 Network Topology

```
┌─────────────────────────────────────────────────────┐
│              EXTERNAL / INTERNET                     │
│                                                      │
│  Mobile App (Android) → HTTPS/HTTP/WebSocket       │
└─────┬───────────────────────────────────────────────┘
          │ (Encrypted TLS Connection)
┌─────────▼────────────────────────────────────────────┐
│         HOST MACHINE (Linux/macOS)                   │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  NGINX Reverse Proxy (Port 80/443)          │   │
│  │  Container: e2ee_nginx                       │   │
│  │  Maps: / → http://e2ee_api_gateway:8000     │   │
│  └──────────────────────────────────────────────┘   │
│                    │                                 │
│  ┌────────────────┴──────────────────────────────┐  │
│  │                                                │  │
│  │        DOCKER BRIDGE NETWORK                  │  │
│  │        (e2ee_e2ee_network)                    │  │
│  │                                                │  │
│  │  ┌─────────────────────────────────────────┐ │  │
│  │  │ API GATEWAY (FastAPI Port 8000)         │ │  │
│  │  │ Container: e2ee_api_gateway             │ │  │
│  │  │ Env: AUTH_SERVICE_URL=http://e2ee...   │ │  │
│  │  │      CHAT_SERVICE_URL=http://e2ee...   │ │  │
│  │  │      MESSAGE_SERVICE_URL=http://e2ee.. │ │  │
│  │  │      MEDIA_SERVICE_URL=http://e2ee...  │ │  │
│  │  │ Role: Routes all requests               │ │  │
│  │  └─────────────────────────────────────────┘ │  │
│  │                    │                           │  │
│  │   ┌────────────────┼────────────────┐         │  │
│  │   │                │                │         │  │
│  │   ▼                ▼                ▼         │  │
│  │ ┌──────────┐    ┌──────────┐    ┌───────────┐ │  │
│  │ │AUTH SVC  │    │CHAT SVC  │    │MESSAGE SVC│ │  │
│  │ │Port 8001 │    │Port 8002 │    │Port 8003  │ │  │
│  │ └────┬─────┘    └────┬─────┘    └─────┬─────┘ │  │
│  │      │               │                 │       │  │
│  │      ▼               ▼                 ▼       │  │
│  │ ┌─────────────┐  ┌──────────┐  ┌──────────┐  │  │
│  │ │  PostgreSQL │  │ MongoDB  │  │ MongoDB  │  │  │
│  │ │  Port 5432  │  │ Port 27017      Port 27017 │  │
│  │ │(Internal)   │  │(Internal)│  │(Internal)│  │  │
│  │ └─────────────┘  └──────────┘  └──────────┘  │  │
│  │                                              │  │
│  │   ┌────────────────────┐                     │  │
│  │   │   MEDIA SERVICE    │                     │  │
│  │   │   Port 8004        │                     │  │
│  │   └────────┬───────────┘                     │  │
│  │            │                                 │  │
│  │            ▼                                 │  │
│  │   ┌────────────────────┐                     │  │
│  │   │  MinIO S3 Storage  │                     │  │
│  │   │ Port 9000 (Internal)                     │  │
│  │   └────────────────────┘                     │  │
│  │                                              │  │
│  │ ┌──────────────────────────────────────────┐ │  │
│  │ │       MONITORING STACK (Local)           │ │  │
│  │ │ Prometheus (9090) → Metrics Collection   │ │  │
│  │ │ Grafana (3000) → Dashboards              │ │  │
│  │ │ Loki (3100) → Log Aggregation            │ │  │
│  │ │ Alertmanager (9093) → Alert Routing      │ │  │
│  │ │ Promtail → Log Shipper                   │ │  │
│  │ └──────────────────────────────────────────┘ │  │
│  │                                                │  │
│  └────────────────────────────────────────────────┘  │
│                                                       │
└───────────────────────────────────────────────────────┘
```

---

## 2. NETWORK CONFIGURATION & COMMUNICATION

### 2.1 Docker Network Setup

**Network Name:** `e2ee_e2ee_network`
**Driver:** Bridge (default Docker bridge networking)

All containers are attached to this network, enabling **internal service-to-service communication** via container names as DNS hostnames:

```bash
# Example: From API Gateway to Auth Service
curl http://e2ee_auth_service:8001/health

# Example: From Auth Service to PostgreSQL
postgresql://demo:demo@postgres:5432/auth_db
```

### 2.2 Port Exposure Strategy

**PUBLIC PORTS (exposed to host/internet):**
- **Port 80/443** (NGINX) - Reverse proxy for HTTPS/HTTP traffic
- **Port 8000** (API Gateway) - Direct access for local development/testing
- **Port 3000** (Grafana) - Monitoring dashboards
- **Port 9090** (Prometheus) - Metrics collection
- **Port 3100** (Loki) - Log aggregation
- **Port 9093** (Alertmanager) - Alert management

**INTERNAL PORTS (Docker network only, not exposed):**
- **Port 8001** (Auth Service)
- **Port 8002** (Chat Service)
- **Port 8003** (Message Service)
- **Port 8004** (Media Service)
- **Port 5432** (PostgreSQL)
- **Port 27017** (MongoDB)
- **Port 9000** (MinIO)

**Security Benefit:** Database ports are NEVER exposed, preventing direct attacks. All external traffic must go through NGINX/API Gateway with authentication.

### 2.3 Environment Variable Dependencies

Each service gets configuration via environment variables loaded from `.env`:

```yaml
API_GATEWAY:
  - AUTH_SERVICE_URL=http://e2ee_auth_service:8001
  - CHAT_SERVICE_URL=http://e2ee_chat_service:8002
  - MESSAGE_SERVICE_URL=http://e2ee_message_service:8003
  - MEDIA_SERVICE_URL=http://e2ee_media_service:8004
  - DOMAIN=secra.top
  - SECRET_KEY=${SECRET_KEY from .env}

AUTH_SERVICE:
  - DATABASE_URL=postgresql://demo:demo@postgres:5432/auth_db
  - SECRET_KEY=${SECRET_KEY from .env}

CHAT_SERVICE:
  - MONGODB_URL=mongodb://mongodb:27017
  - MONGODB_DB=messages_db
  - MONGO_USER=${MONGO_USER from .env}
  - MONGO_PASSWORD=${MONGO_PASSWORD from .env}
  - SECRET_KEY=${SECRET_KEY from .env}

MESSAGE_SERVICE:
  - MONGODB_URL=mongodb://mongodb:27017
  - MONGODB_DB=messages_db
  - MONGO_USER=${MONGO_USER from .env}
  - MONGO_PASSWORD=${MONGO_PASSWORD from .env}
  - CHAT_SERVICE_URL=http://chat_service:8002
  - SECRET_KEY=${SECRET_KEY from .env}

MEDIA_SERVICE:
  - MINIO_ENDPOINT=minio:9000
  - MINIO_ACCESS_KEY=${MINIO_USER from .env}
  - MINIO_SECRET_KEY=${MINIO_PASSWORD from .env}
  - MINIO_BUCKET=profiles
  - MINIO_SECURE=false (because internal communication)
  - DOMAIN=secra.top
```

---

## 3. INDIVIDUAL SERVICE BREAKDOWN

### 3.1 NGINX REVERSE PROXY (Port 80/443)

**Purpose:** First entry point for ALL external traffic

**Configuration:**
- **Image:** nginx:alpine (lightweight)
- **Container:** e2ee_nginx
- **Volume Mount:** `./services/api_gateway/nginx/nginx.conf` (read-only)
- **Depends On:** api_gateway
- **Restart Policy:** unless-stopped (auto-restart on failure)

**What It Does:**
1. Listens on ports 80 (HTTP) and 443 (HTTPS)
2. Routes all incoming requests to `http://e2ee_api_gateway:8000`
3. Handles SSL/TLS termination (in production with Let's Encrypt)
4. Applies security headers
5. Rate limiting and DDoS protection

**Traffic Flow:**
```
Client HTTPS Request (secra.top)
         ↓
    NGINX (Port 443)
         ↓
    TLS Decryption
         ↓
    Route to localhost:8000 internally
         ↓
    API Gateway
```

---

### 3.2 API GATEWAY (FastAPI, Port 8000)

**Purpose:** Central routing hub - all requests are routed through here

**Configuration:**
- **Language:** Python with FastAPI framework
- **Image:** Custom (built from `./services/api_gateway/Dockerfile`)
- **Container:** e2ee_api_gateway
- **Direct Port:** 8000 (also accessible via NGINX)
- **Depends On:** auth_service, chat_service, message_service, media_service
- **Restart Policy:** unless-stopped

**Key Features:**
1. **Request Routing** - Routes `/api/auth/*` → Auth Service, `/api/chats/*` → Chat Service, etc.
2. **JWT Validation** - Extracts and validates JWT tokens on protected endpoints
3. **WebSocket Handling** - `/ws/chats/{chat_id}` for realtime message delivery
4. **CORS Management** - Handles cross-origin requests from Android app
5. **Request/Response Transformation** - Normalizes responses across services

**Service URLs it uses:**
```python
AUTH_SERVICE_URL = "http://e2ee_auth_service:8001"
CHAT_SERVICE_URL = "http://e2ee_chat_service:8002"
MESSAGE_SERVICE_URL = "http://e2ee_message_service:8003"
MEDIA_SERVICE_URL = "http://e2ee_media_service:8004"
```

**Request Examples:**
```
POST /api/auth/register → POST http://e2ee_auth_service:8001/register
GET /api/users/me → GET http://e2ee_auth_service:8001/users/me
POST /api/chats → POST http://e2ee_chat_service:8002/chats
POST /api/chats/{id}/messages → POST http://e2ee_message_service:8003/chats/{id}/messages
GET /ws/chats/{id} → WebSocket upgrade to Message Service
```

**WebSocket Flow:**
```
1. Client connects to: wss://secra.top/ws/chats/chat_abc123?token=<jwt>
2. NGINX passes to API Gateway
3. API Gateway validates JWT
4. Creates persistent WebSocket connection
5. Subscribes to chat message updates from Message Service
6. Any new message → published to all connected clients
7. Client receives realtime notification
8. Client decrypts and displays message
```

---

### 3.3 AUTH SERVICE (FastAPI, Port 8001)

**Purpose:** User management, authentication, and Signal key bundle management

**Configuration:**
- **Language:** Python with FastAPI
- **Image:** Custom (built from `./services/auth_service/Dockerfile`)
- **Container:** e2ee_auth_service
- **Database:** PostgreSQL (internal connection)
- **Depends On:** postgres
- **Restart Policy:** unless-stopped

**Database Connection:**
```
DATABASE_URL=postgresql://demo:demo@postgres:5432/auth_db

breakdown:
- User: demo
- Password: demo
- Host: postgres (Docker hostname)
- Port: 5432
- Database: auth_db
```

**Key Responsibilities:**

1. **User Registration**
   - Endpoint: `POST /api/auth/register`
   - Validates username (unique), email (unique), password strength
   - Hashes password with bcrypt/scrypt
   - Creates user record in PostgreSQL
   - Returns user_id and registration_id

2. **User Authentication**
   - Endpoint: `POST /api/auth/login`
   - Validates credentials against PostgreSQL
   - Generates JWT token (HS256 algorithm)
   - Token includes: user_id, exp (expiry), iat (issued at)
   - Token TTL: 24 hours (default)

3. **User Profile Management**
   - Endpoint: `GET /api/users/me`
   - Endpoint: `GET /api/users/{user_id}`
   - Returns user profile with public_key
   - Only profile data (no sensitive info)

4. **User Search**
   - Endpoint: `GET /api/users?query=alice`
   - Full-text search on username
   - Uses SQL LIKE query on PostgreSQL
   - Returns matching users (for friend search)

5. **Signal Key Bundle Management**
   - Endpoint: `POST /api/users/{user_id}/keys`
   - Stores cryptographic keys for E2EE:
     - identity_key (long-term, generated on device)
     - signed_prekey (updated periodically)
     - one_time_prekeys (ephemeral, consumed once per message)
     - registration_id (device identifier)
   - Backend NEVER sees private keys - only public bundles
   
   - Endpoint: `GET /api/users/{user_id}/bundle`
   - Returns public key bundle to other users
   - Consumes one one_time_prekey per request
   - Used for X3DH key exchange

   Additional implementation notes:
   - One-time prekeys are now stored in a dedicated `one_time_prekeys` table and consumed atomically using `DELETE ... RETURNING` with `FOR UPDATE SKIP LOCKED` semantics to avoid race conditions.
   - Legacy JSONB arrays in the `devices.one_time_prekeys` column are migrated at startup; the JSONB is cleared after migration to prevent duplication.
   - New device management endpoints added: `GET /api/users/{user_id}/devices`, `DELETE /api/users/{user_id}/devices/{device_id}`, and `POST /api/users/{user_id}/devices/{device_id}/rotate` for signed-prekey rotation.

   KMS / Vault integration notes
   - The codebase centralizes secret access via `services/auth_service/secrets.py`. By default it reads environment variables.
   - For production, integrate HashiCorp Vault (or cloud KMS). Recommended pattern:
      1. Deploy Vault and enable transit/kv engines.
      2. Store server-side secrets (JWT signing key, DB passwords, MinIO keys) in Vault.
      3. Use short-lived tokens or instance-auth (AWS IAM, Kubernetes service account) to fetch secrets at startup.
      4. Do NOT store client private keys in Vault; clients must keep private keys locally.

   Example Vault usage (high-level):
   ```bash
   # store secret
   vault kv put secret/e2ee JWT_SECRET="<64-char-random>"
   # read secret (server at startup)
   export SECRET_KEY=$(vault kv get -field=JWT_SECRET secret/e2ee)
   ```

   The `secrets.py` helper can be extended to call Vault APIs or use the `hvac` library.

6. **Friend Management**
   - Endpoint: `POST /api/users/{user_id}/friends`
   - Creates friendship record in PostgreSQL
   - Status: "pending" → "accepted" → "removed"
   
   - Endpoint: `GET /api/users/{user_id}/friends`
   - Lists all friends with their public_key and registration_id
   
   - Endpoint: `DELETE /api/users/{user_id}/friends/{friend_id}`
   - Removes friendship relationship

**PostgreSQL Tables Used:**
```sql
users:
  id (PRIMARY KEY)
  username (UNIQUE)
  email (UNIQUE)
  password_hash
  created_at
  updated_at

friends:
  id (PRIMARY KEY)
  user_id (FOREIGN KEY → users.id)
  friend_id (FOREIGN KEY → users.id)
  status (pending/accepted/removed)
  created_at

devices:
  id (PRIMARY KEY)
  user_id (FOREIGN KEY → users.id)
  device_name
  device_token
  last_seen
  created_at

Index on: username, email, user_id (for fast lookups)
```

**Example PostgreSQL Queries:**

```sql
-- Register user
INSERT INTO users (username, email, password_hash) 
VALUES ('alice', 'alice@example.com', 'hashed_password');

-- Login
SELECT id, password_hash FROM users WHERE username = 'alice';

-- Search users
SELECT id, username, registration_id FROM users 
WHERE username LIKE 'ali%';

-- Add friend
INSERT INTO friends (user_id, friend_id, status) 
VALUES (1, 2, 'accepted');

-- List friends
SELECT u.id, u.username, u.registration_id FROM friends f
JOIN users u ON f.friend_id = u.id
WHERE f.user_id = 1 AND f.status = 'accepted';
```

---

### 3.4 CHAT SERVICE (FastAPI, Port 8002)

**Purpose:** Chat room management and metadata storage

**Configuration:**
- **Language:** Python with FastAPI
- **Image:** Custom (built from `./services/chat_service/Dockerfile`)
- **Container:** e2ee_chat_service
- **Database:** MongoDB (internal connection)
- **Database Name:** messages_db
- **Depends On:** mongodb
- **Restart Policy:** unless-stopped

**MongoDB Connection:**
```
MONGODB_URL=mongodb://mongodb:27017
MONGO_USER=admin (from .env)
MONGO_PASSWORD=<random_32_char_password> (from .env)
Database: messages_db
```

**Key Responsibilities:**

1. **Create Chat**
   - Endpoint: `POST /api/chats`
   - Creates 1:1 or group chats
   - For 1:1 chats: enforces 2 members and uniqueness (no duplicate 1:1 chats)
   - Returns chat_id, member_ids, is_group, created_at

2. **List Chats**
   - Endpoint: `GET /api/chats?user_id={user_id}`
   - Returns all chats where user is a member
   - Paginated results

3. **Get Chat Details**
   - Endpoint: `GET /api/chats/{chat_id}`
   - Returns metadata: name, members, created_at, status

4. **Add Member to Chat**
   - Endpoint: `POST /api/chats/{chat_id}/members`
   - Adds new user to chat
   - Only group chats (1:1 chats are read-only)

5. **Remove Member from Chat**
   - Endpoint: `DELETE /api/chats/{chat_id}/members/{user_id}`
   - Removes user from chat
   - Soft-delete (marks inactive rather than removes)

**MongoDB Collections:**

```javascript
// chats collection
{
  "_id": ObjectId("..."),
  "name": "Alice & Bob Chat",
  "member_ids": ["user_1", "user_2"],
  "is_group": false,
  "created_at": ISODate("2026-05-07T12:00:00Z"),
  "status": "active",  // active, archived
  "created_by": "user_1"
}

// Example with many members (group chat)
{
  "_id": ObjectId("..."),
  "name": "Team Channel",
  "member_ids": ["user_1", "user_2", "user_3", "user_4"],
  "is_group": true,
  "created_at": ISODate("2026-05-07T12:00:00Z"),
  "status": "active",
  "created_by": "user_1"
}
```

**MongoDB Indexing:**
```javascript
db.chats.createIndex({ "member_ids": 1 });  // Fast lookup of user's chats
db.chats.createIndex({ "created_at": -1 });  // Sort by newest first
```

---

### 3.5 MESSAGE SERVICE (FastAPI, Port 8003)

**Purpose:** Message storage, retrieval, delivery, and read receipts

**Configuration:**
- **Language:** Python with FastAPI
- **Image:** Custom (built from `./services/message_service/Dockerfile`)
- **Container:** e2ee_message_service
- **Database:** MongoDB (same as Chat Service)
- **Depends On:** mongodb, chat_service
- **Restart Policy:** unless-stopped

**Key Responsibilities:**

1. **Send Message**
   - Endpoint: `POST /api/chats/{chat_id}/messages`
   - Accepts: `{ chat_id, sender_id, ciphertext, message_type }`
   - **CRITICAL:** Ciphertext only - backend never decrypts
   - Stores message in MongoDB
   - Publishes to WebSocket channel
   - Returns message_id

2. **Get Messages (Paginated)**
   - Endpoint: `GET /api/chats/{chat_id}/messages?limit=50&before=<timestamp>`
   - Cursor-based pagination (uses timestamp)
   - Returns last 50 messages (or specified limit)
   - Used for message history on app load

3. **Get Specific Message**
   - Endpoint: `GET /api/messages/{message_id}`
   - Returns single message by ID
   - Includes read status

4. **Delete Message**
   - Endpoint: `DELETE /api/messages/{message_id}`
   - Only message sender can delete
   - Soft-delete (marks deleted_at rather than removes)

5. **Mark As Read**
   - Endpoint: `POST /api/messages/{message_id}/read`
   - Records which users have read the message
   - Stores user_id and timestamp

6. **Get Read Status**
   - Endpoint: `GET /api/messages/{message_id}/read`
   - Returns who has read this message
   - Shows read receipts to sender

**MongoDB Collections:**

```javascript
// messages collection
{
  "_id": ObjectId("..."),
  "chat_id": "chat_abc123",
  "sender_id": "user_1",
  "ciphertext": "base64_encoded_encrypted_content...",
  "message_type": "text",  // text, media, system, etc
  "created_at": ISODate("2026-05-07T12:00:00Z"),
  "deleted_at": null,
  "attachments": []  // media_ids if message has files
}

// read_receipts collection (tracks who read what)
{
  "_id": ObjectId("..."),
  "message_id": ObjectId("..."),
  "user_id": "user_2",
  "read_at": ISODate("2026-05-07T12:00:05Z")
}
```

**MongoDB Indexes:**
```javascript
// Fast lookups for message history
db.messages.createIndex({ "chat_id": 1, "created_at": -1 });

// Fast lookups for read receipts
db.read_receipts.createIndex({ "message_id": 1 });
db.read_receipts.createIndex({ "user_id": 1, "message_id": 1 });
```

**WebSocket Integration:**

When message is sent:
```
1. Message Service stores in MongoDB
2. Message Service publishes to API Gateway WebSocket channel
3. API Gateway sends to all WebSocket clients in that chat
4. Clients receive: { type: "message.new", id, chat_id, sender_id, ciphertext, created_at }
5. Client decrypts locally and displays
```

---

### 3.6 MEDIA SERVICE (FastAPI, Port 8004)

**Purpose:** Profile picture upload/download with signed URLs (S3 API)

**Configuration:**
- **Language:** Python with FastAPI
- **Image:** Custom (built from `./services/media_service/Dockerfile`)
- **Container:** e2ee_media_service
- **Storage:** MinIO (S3-compatible)
- **Depends On:** minio (indirectly)
- **Restart Policy:** unless-stopped

**MinIO Connection:**
```
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin (from .env)
MINIO_SECRET_KEY=<random_32_char_password> (from .env)
MINIO_BUCKET=profiles
MINIO_SECURE=false (no TLS for internal communication)
```

**Key Responsibilities:**

1. **Get Profile Picture Upload URL**
   - Endpoint: `POST /api/profiles/{username}/picture?content_type=image/jpeg`
   - Generates time-limited signed URL (1 hour expiry)
   - URL allows direct upload to MinIO without server
   - Returns: `{ upload_url, expires_at, key }`

2. **Complete Profile Upload**
   - Endpoint: `POST /api/profiles/{username}/picture/complete`
   - Marks upload as complete
   - Stores metadata: size, uploaded_at, content_type
   - Could trigger image processing (resize, crop) in future

3. **Get Profile Picture Download URL**
   - Endpoint: `GET /api/profiles/{username}/picture`
   - Generates signed S3 URL for download (1 hour expiry)
   - Allows direct download from MinIO
   - Returns: `{ download_url, expires_at, content_type }`

4. **Get Profile Picture Metadata**
   - Endpoint: `GET /api/profiles/{username}/picture/metadata`
   - Returns: size, content_type, uploaded_at
   - Useful for UI (show "loading" if size is large)

**MinIO Storage Structure:**

```
Bucket: profiles/
├── profiles/alice/picture          (JPEG image)
├── profiles/bob/picture            (PNG image)
├── profiles/charlie/picture        (WebP image)
└── .../
```

**Signed URL Example:**
```
Generated by Media Service:
http://212.235.185.13:9000/profiles/alice/picture?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=...&X-Amz-Date=...&X-Amz-Expires=3600&X-Amz-Signature=...

This URL:
- Valid for 1 hour
- Allows direct PUT to upload
- Allows direct GET to download
- No need for Authorization header
- Backend signs the URL with private key
```

---

## 4. DATABASE LAYER - WHAT STORES WHAT

### 4.1 PostgreSQL (Relational Data)

**Purpose:** Structured user data with relationships

**Database:** auth_db
**Tables:**

1. **users** - User accounts
   ```sql
   id: INT PRIMARY KEY AUTO_INCREMENT
   username: VARCHAR(255) UNIQUE NOT NULL
   email: VARCHAR(255) UNIQUE NOT NULL
   password_hash: VARCHAR(255) NOT NULL
   created_at: TIMESTAMP
   updated_at: TIMESTAMP
   
   Example row:
   id=1, username='alice', email='alice@example.com', 
   password_hash='$2b$12$...'
   ```

2. **friends** - Friendship relationships
   ```sql
   id: INT PRIMARY KEY
   user_id: INT FOREIGN KEY → users.id
   friend_id: INT FOREIGN KEY → users.id
   status: VARCHAR(50) DEFAULT 'pending'
   created_at: TIMESTAMP
   
   UNIQUE(user_id, friend_id)  -- No duplicate friendships
   
   Example rows:
   id=1, user_id=1, friend_id=2, status='accepted'
   id=2, user_id=1, friend_id=3, status='pending'
   ```

3. **devices** - Device registrations (for Signal keys)
   ```sql
   id: INT PRIMARY KEY
   user_id: INT FOREIGN KEY → users.id
   device_name: VARCHAR(255)
   device_token: VARCHAR(255) UNIQUE
   last_seen: TIMESTAMP
   created_at: TIMESTAMP
   
   Example row:
   id=1, user_id=1, device_name='alice_android_phone',
   device_token='device_token_xyz', last_seen='2026-05-07 12:00:00'
   ```

**Persistence:** YES - Data survives container restart
**Volume:** `postgres_data:/var/lib/postgresql/data`
**Backup Strategy:** Manual backups recommended for production

---

### 4.2 MongoDB (Document-Oriented Data)

**Purpose:** Flexible document storage for chats and messages

**Database:** messages_db
**Collections:**

1. **chats** - Chat rooms
   ```javascript
   {
     "_id": ObjectId("507f1f77bcf86cd799439011"),
     "name": "Alice & Bob",
     "member_ids": ["user_1", "user_2"],
     "is_group": false,
     "created_at": ISODate("2026-05-07T12:00:00Z"),
     "status": "active",
     "created_by": "user_1"
   }
   ```

2. **messages** - Chat messages
   ```javascript
   {
     "_id": ObjectId("507f1f77bcf86cd799439012"),
     "chat_id": "507f1f77bcf86cd799439011",
     "sender_id": "user_1",
     "ciphertext": "base64_encoded_encrypted_message...",
     "message_type": "text",
     "created_at": ISODate("2026-05-07T12:00:05Z"),
     "deleted_at": null,
     "edited_at": null,
     "attachments": []
   }
   ```

3. **read_receipts** - Who read what
   ```javascript
   {
     "_id": ObjectId("507f1f77bcf86cd799439013"),
     "message_id": ObjectId("507f1f77bcf86cd799439012"),
     "user_id": "user_2",
     "read_at": ISODate("2026-05-07T12:00:10Z")
   }
   ```

**Persistence:** YES - Data survives container restart
**Volume:** `mongodb_data:/data/db`
**Backup Strategy:** Manual mongodump backups recommended for production

---

### 4.3 MinIO S3 Storage (File Storage)

**Purpose:** Profile pictures and media files

**Bucket:** profiles
**Structure:**
```
profiles/
  alice/picture              (image file)
  bob/picture                (image file)
  charlie/picture            (image file)
  ...
```

**Metadata Storage:** Stored in MongoDB separately (not with the file)
```javascript
{
  "username": "alice",
  "filename": "picture",
  "size": 125432,
  "content_type": "image/jpeg",
  "uploaded_at": ISODate("2026-05-07T12:00:00Z"),
  "path": "profiles/alice/picture"
}
```

**Persistence:** YES - Files survive container restart
**Volume:** `minio_data:/data`
**Access:** Only through Media Service (via signed URLs)
**Expiry:** None (permanent storage)

---

## 5. PERSISTENCE & DATA FLOW

### 5.1 What IS Persistent

Data that **survives container restart/stop**:

1. **PostgreSQL Data** (`postgres_data` volume)
   - Users, passwords, friends, devices
   - Survives indefinitely until volume is deleted
   - Can be backed up with pg_dump

2. **MongoDB Data** (`mongodb_data` volume)
   - Chats, messages, read receipts
   - Survives indefinitely until volume is deleted
   - Can be backed up with mongodump

3. **MinIO Data** (`minio_data` volume)
   - Profile pictures and media files
   - Survives indefinitely until volume is deleted
   - Can be backed up with file copy

4. **Prometheus Metrics** (`prometheus_data` volume)
   - Historical metrics (useful for trends)
   - Keeps last 15 days by default

5. **Grafana Dashboards** (`grafana_data` volume)
   - Dashboard configurations
   - User data and preferences

6. **Loki Logs** (`loki_data` volume)
   - Historical logs (24-48 hours retention)
   - Used for troubleshooting

7. **Alertmanager Data** (`alertmanager_data` volume)
   - Alert rules and history

### 5.2 What IS NOT Persistent (In-Memory)

Data that **does NOT survive container restart**:
- JWT tokens (regenerate on login)
- WebSocket connections (clients reconnect)
- Service cache (rebuild on startup)
- Temporary files (cleaned up automatically)

### 5.3 Data Lifecycle - User Registration to Message

```
1. USER REGISTRATION
   ├─ Android App: User enters username/password
   ├─ Sends: POST /api/auth/register
   ├─ NGINX: Routes to API Gateway (port 443)
   ├─ API Gateway: Routes to Auth Service (port 8001)
   ├─ Auth Service: Hashes password, creates user in PostgreSQL
   ├─ PostgreSQL: INSERT into users table
   ├─ Auth Service: Returns user_id
   └─ Response: { id: "user_1", username: "alice" }

2. USER LOGIN
   ├─ Android App: User enters username/password
   ├─ Sends: POST /api/auth/login
   ├─ Auth Service: Validates credentials against PostgreSQL
   ├─ PostgreSQL: SELECT password_hash FROM users WHERE username='alice'
   ├─ Auth Service: Compares hashes
   ├─ Auth Service: Generates JWT (user_id, exp, iat)
   └─ Response: { access_token: "eyJh...", token_type: "bearer" }

3. KEY BUNDLE REGISTRATION
   ├─ Android App: Generates Signal keys locally
   ├─ Android App: Sends: POST /api/users/user_1/keys
   │  Body: { identity_key, signed_prekey, one_time_prekeys, registration_id }
   ├─ Auth Service: Stores in PostgreSQL devices table
   └─ PostgreSQL: INSERT INTO devices (user_id, device_name, device_token)

4. CREATE 1:1 CHAT
   ├─ Android App: User selects friend "bob"
   ├─ Sends: POST /api/chats
   │  Body: { member_ids: ["user_1", "user_2"], is_group: false }
   ├─ API Gateway: Routes to Chat Service
   ├─ Chat Service: Checks if 1:1 chat exists between alice & bob
   ├─ MongoDB: INSERT into chats collection
   ├─ Chat Service: Returns chat_id
   └─ Response: { id: "chat_abc123", member_ids: [...] }

5. GET RECIPIENT KEY BUNDLE
   ├─ Android App: Wants to send message to bob
   ├─ Sends: GET /api/users/bob/bundle
   ├─ Auth Service: Retrieves bob's public keys from PostgreSQL
   ├─ Auth Service: Returns bundle WITHOUT private keys
   ├─ Android App: Performs X3DH key exchange locally
   ├─ Android App: Derives session key (local memory only)
   └─ Response: { identity_key, signed_prekey, one_time_prekey }

6. SEND ENCRYPTED MESSAGE
   ├─ Android App: Encrypts message with session key (Signal protocol)
   ├─ Android App: Sends: POST /api/chats/chat_abc123/messages
   │  Body: { sender_id: "user_1", ciphertext: "base64...", message_type: "text" }
   ├─ API Gateway: Validates JWT
   ├─ Message Service: Stores ciphertext in MongoDB (NO DECRYPTION)
   ├─ MongoDB: INSERT into messages collection
   ├─ Message Service: Publishes to WebSocket channel
   ├─ API Gateway: Broadcasts to all connected clients in chat
   └─ Response: { id: "msg_xyz", chat_id: "...", created_at: "..." }

7. REALTIME DELIVERY (WebSocket)
   ├─ All connected clients: Receive WebSocket message
   │  Payload: { type: "message.new", id, chat_id, sender_id, ciphertext, created_at }
   ├─ Bob's Device: Receives notification over WebSocket
   ├─ Bob's App: Decrypts ciphertext locally with session key
   ├─ Bob's App: Displays plaintext message
   └─ Sends: POST /api/messages/msg_xyz/read (mark as read)

8. MARK AS READ
   ├─ Android App: Sends: POST /api/messages/msg_xyz/read
   ├─ Message Service: Records in MongoDB read_receipts
   ├─ MongoDB: INSERT into read_receipts
   ├─ Message Service: Publishes to WebSocket
   ├─ API Gateway: Broadcasts read receipt to sender
   └─ Alice's Device: Shows "Delivered ✓✓" indicator
```

---

## 6. SERVICE-TO-SERVICE COMMUNICATION

### 6.1 HTTP Communication (Synchronous)

All services communicate via HTTP/REST over Docker network:

**Pattern:**
```
Service A → HTTP Request → Service B (via container hostname:port)
                              ↓
                         Process request
                              ↓
                         HTTP Response
Service A ← JSON Response ← Service B
```

**Examples:**

```bash
# Message Service calls Chat Service to verify chat membership
POST http://e2ee_chat_service:8002/chats/chat_abc123/members/user_1

# Media Service uploads to MinIO
PUT http://minio:9000/profiles/alice/picture
  (with signed request headers)

# Auth Service communicates with PostgreSQL
psql://demo:demo@postgres:5432/auth_db
```

### 6.2 Database Communication (Direct Connections)

Services connect directly to databases:

**Auth Service → PostgreSQL:**
```python
connection_string = "postgresql://demo:demo@postgres:5432/auth_db"
# Direct TCP connection to port 5432
```

**Chat/Message Services → MongoDB:**
```python
connection_string = "mongodb://admin:password@mongodb:27017"
# Direct TCP connection to port 27017
# Authentication: MONGO_USER/MONGO_PASSWORD
```

**Media Service → MinIO:**
```python
endpoint = "minio:9000"
access_key = "minioadmin"
secret_key = "<password>"
# Direct TCP connection to port 9000
# Authentication: Access key + Secret key
```

### 6.3 WebSocket Communication (Persistent)

For realtime message delivery:

```
Client A ─ WebSocket ─ API Gateway ─ Message Service ─ MongoDB
                            │
                            └─ Event Stream ─ Client B
                                   ↓
                            Client B ─ WebSocket ─ API Gateway

Flow:
1. Client A connects: ws://api_gateway:8000/ws/chats/chat_abc123
2. API Gateway: Validates JWT, opens connection
3. Message Service publishes: { type: "message.new", ... }
4. API Gateway: Reads from message queue
5. API Gateway: Sends to all WebSocket clients in that chat
6. Client B: Receives realtime message notification
```

---

## 7. REQUEST FLOW EXAMPLES

### 7.1 Simple Request Flow - Get Current User

```
┌─────────────┐
│ Mobile App  │
└─────┬───────┘
      │ GET /api/users/me
      │ Header: Authorization: Bearer <JWT>
      │
┌─────▼────────────────┐
│  NGINX (Port 443)    │ (TLS Termination)
└─────┬────────────────┘
      │ localhost:8000 (internal)
      │
┌─────▼──────────────────────────┐
│  API Gateway (FastAPI)         │
│  1. Extract JWT from header    │
│  2. Validate token signature   │
│  3. Extract user_id from token │
│  4. Route to Auth Service      │
└─────┬──────────────────────────┘
      │ GET http://e2ee_auth_service:8001/users/me
      │ Header: User-ID: user_1
      │
┌─────▼────────────────────────┐
│ Auth Service (FastAPI)       │
│ 1. Receive user_id           │
│ 2. Query PostgreSQL          │
└─────┬────────────────────────┘
      │ SELECT * FROM users WHERE id=1
      │
┌─────▼────────────────────────┐
│ PostgreSQL (TCP 5432)        │
│ 1. Execute query             │
│ 2. Return user row           │
└─────┬────────────────────────┘
      │ {id:1, username:'alice', ...}
      │
┌─────▼────────────────────────┐
│ Auth Service                 │
│ Format response JSON         │
└─────┬────────────────────────┘
      │ { id, username, email, created_at }
      │
┌─────▼──────────────────────────┐
│ API Gateway                    │
│ 1. Receive response from Auth  │
│ 2. Pass through to client      │
└─────┬──────────────────────────┘
      │ JSON Response
      │
┌─────▼─────────────┐
│ Mobile App        │
│ Display user data │
└───────────────────┘

⏱️ Total Time: ~50-100ms (depends on network)
```

### 7.2 Complex Request Flow - Send Encrypted Message

```
┌──────────────────────────┐
│ Mobile App - Alice       │
│ 1. Get recipient bundle  │
│ 2. Derive session key    │
│ 3. Encrypt message       │
│ 4. Send ciphertext       │
└──────────┬───────────────┘
           │
           ├─ GET /api/users/bob/bundle
           │  [1] → NGINX → [2] API Gateway → [3] Auth Service
           │                                  ↓
           │                        Query PostgreSQL
           │                                  ↓
           │             [3] Returns: {identity_key, signed_prekey, one_time_prekey}
           │             [2] Returns response to client
           │
           │ [Locally on device: X3DH + Double Ratchet]
           │
           └─ POST /api/chats/chat_abc123/messages
              Header: Authorization: Bearer <JWT>
              Body: { ciphertext: "base64...", message_type: "text" }
              │
              [1] NGINX (80/443) → [2] API Gateway (8000)
                                      │
                                      ├─ Validate JWT
                                      ├─ Route to Message Service
                                      │
                                      [4] Message Service (8003)
                                          │
                                          ├─ Verify user in chat
                                          ├─ Store in MongoDB
                                          ├─ Publish to WebSocket
                                          │
                                          [5] MongoDB: messages collection
                                              │
                                              PERSISTED: {_id, chat_id, sender_id, ciphertext, created_at}
                                          │
                                          [6] API Gateway WebSocket Channel
                                              │
                                          ┌───┴────┬─────────────────┐
                                          │        │                 │
                                       ┌──▼──┐  ┌─▼────┐         ┌──▼──┐
                                       │Bob's│  │Bob's │         │ ... │
                                       │Dev1 │  │Dev2  │         │     │
                                       └─────┘  └──────┘         └─────┘
                                          │        │
                      [Locally: Decrypt using session key]

⏱️ Total Time:
  - Get bundle: ~50ms
  - Local encryption: ~10ms
  - Send message: ~100ms
  - Delivery to Bob: ~50-200ms (depends on WebSocket latency)
```

---

## 8. SECURITY & AUTHENTICATION

### 8.1 Authentication Flow

1. **Registration**
   ```
   Username → Email Validation → Password Hashing (bcrypt) → Store in PostgreSQL
   Return: user_id
   ```

2. **Login**
   ```
   Username + Password → Auth Service → Validate against password_hash → JWT Generation
   
   JWT Structure:
   Header:  { alg: "HS256", typ: "JWT" }
   Payload: { user_id: "user_1", exp: 1715084400, iat: 1715080800 }
   Signature: HMAC-SHA256(secret_key)
   
   Secret Key: ${SECRET_KEY} from .env (32-char random)
   ```

3. **Token Validation**
   ```
   API Gateway: Intercepts all requests
   1. Extract Authorization header
   2. Check token format (Bearer <token>)
   3. Verify signature with SECRET_KEY
   4. Check expiration (exp < now?)
   5. Extract user_id
   If any step fails: 401 Unauthorized
   ```

### 8.2 Cryptographic Security

**End-to-End Encryption:**
- **Algorithm:** Signal Protocol (Double Ratchet Algorithm + X3DH)
- **Key Exchange:** X3DH (Elliptic Curve Diffie-Hellman)
- **Message Encryption:** AES-256-GCM or ChaCha20-Poly1305
- **Backend Role:** NONE - zero-knowledge (never touches plaintext)

**Backend Credentials:**
```yaml
PostgreSQL:
  Username: demo
  Password: demo (hardcoded for dev, should be from .env)

MongoDB:
  Username: ${MONGO_USER} (from .env)
  Password: ${MONGO_PASSWORD} (from .env)

MinIO:
  Username: ${MINIO_USER} (from .env)
  Password: ${MINIO_PASSWORD} (from .env)

API Secret:
  SECRET_KEY: ${SECRET_KEY} (from .env, 64-char random)
```

### 8.3 Database Isolation (Security Hardening)

All databases are **INTERNAL ONLY**:
- PostgreSQL: Port 5432 (not exposed)
- MongoDB: Port 27017 (not exposed)
- MinIO: Port 9000 (not exposed)

Attackers cannot:
- Connect directly to databases
- Brute force credentials
- Exploit default ports

Only attack surface:
- NGINX ports 80/443 (DDoS protected by Cloudflare)
- API Gateway port 8000 (requires JWT for most endpoints)

---

## 9. DATA LIFECYCLE & RETENTION

### 9.1 How Data Flows Through the System

```
USER DATA:
  Registration → PostgreSQL (users table) → Persists forever
  Credentials  → PostgreSQL (password_hash) → Hashed, never plaintext
  Devices      → PostgreSQL (devices table) → Updated on each login

CHAT DATA:
  Create Chat → MongoDB (chats collection) → Persists forever
  Members     → MongoDB (member_ids array) → Updated as members join/leave

MESSAGE DATA:
  Send Msg    → MongoDB (messages collection) → Persists forever
  Ciphertext  → MongoDB (stored as Base64) → Never decrypted by backend
  Read Status → MongoDB (read_receipts) → Updated as users read

MEDIA DATA:
  Profile Pic → MinIO (profiles/username/picture) → Persists forever
  Metadata    → MongoDB or MySQL → Tracks size, type, upload date

MONITORING DATA:
  Logs        → Loki (24-48 hour retention)
  Metrics     → Prometheus (15 day retention)
  Alerts      → Alertmanager (permanent records)
```

### 9.2 Backup Strategy (Recommended for Production)

```yaml
PostgreSQL:
  Tool: pg_dump
  Frequency: Daily at 2 AM
  Retention: 30 days
  Command: pg_dump -U demo auth_db > backup_$(date +%Y%m%d).sql

MongoDB:
  Tool: mongodump
  Frequency: Daily at 2 AM
  Retention: 30 days
  Command: mongodump --uri "mongodb://admin:pass@localhost:27017" --out backup_$(date +%Y%m%d)

MinIO:
  Tool: Restic or S3 sync
  Frequency: Daily
  Retention: 7 days
  Command: minio sync profiles/ s3://backup-bucket/profiles/

Logs & Metrics:
  Archive: Weekly
  Retention: 90 days
  Location: Separate cloud storage
```

---

## 10. SUMMARY TABLE - COMPLETE SYSTEM OVERVIEW

| Component | Type | Container | Port | Protocol | Persistence | Depends On | Purpose |
|-----------|------|-----------|------|----------|-------------|-----------|---------|
| NGINX | Reverse Proxy | e2ee_nginx | 80/443 | HTTP/HTTPS | No | api_gateway | Public entry point |
| API Gateway | FastAPI | e2ee_api_gateway | 8000 | HTTP | No | all services | Request routing & JWT validation |
| Auth Service | FastAPI | e2ee_auth_service | 8001 | HTTP | No | postgres | User management & auth |
| Chat Service | FastAPI | e2ee_chat_service | 8002 | HTTP | No | mongodb | Chat room management |
| Message Service | FastAPI | e2ee_message_service | 8003 | HTTP | No | mongodb, chat_service | Message storage & delivery |
| Media Service | FastAPI | e2ee_media_service | 8004 | HTTP | No | minio | Profile picture management |
| PostgreSQL | Relational DB | e2ee_postgres | 5432 | PostgreSQL | YES | none | User, friend, device data |
| MongoDB | Document DB | e2ee_mongodb | 27017 | MongoDB | YES | none | Chats, messages, receipts |
| MinIO | S3 Storage | e2ee_minio | 9000 | S3 | YES | none | Profile pictures |
| Prometheus | Metrics | e2ee_prometheus | 9090 | HTTP | YES (15 days) | none | Metrics collection |
| Grafana | Dashboards | e2ee_grafana | 3000 | HTTP | YES | prometheus | Visualization |
| Loki | Logs | e2ee_loki | 3100 | HTTP | YES (24-48h) | none | Log aggregation |
| Alertmanager | Alerts | e2ee_alertmanager | 9093 | HTTP | YES | none | Alert routing |
| Promtail | Log Shipper | e2ee_promtail | - | - | No | none | Forward logs to Loki |

---

This is your complete backend system! Every request goes through this flow, every piece of data follows these paths, and every service has a specific role. The system is designed for security (databases isolated), scalability (microservices), and observability (monitoring stack).
