# Encryption Flow

This document explains how end-to-end encryption is intended to work in this project, which endpoints the client must call, and what data is sent at each step.

The design is Signal-style E2EE:
- Encryption and decryption happen on the client.
- The backend stores and relays ciphertext only.
- The backend handles key distribution, not plaintext.
- Transport still uses TLS/HTTPS or WSS, but TLS is not the encryption layer for message contents.

## 1. Cryptographic Model

The intended flow follows the Signal family of protocols:

- Identity key: long-term client key pair generated on the device.
- Signed prekey: medium-term key published by the client and signed by the identity key.
- One-time prekeys: short-lived keys uploaded in batches and consumed once.
- X3DH-style setup: used to establish the first shared session secret.
- Double Ratchet: used after session setup to encrypt subsequent messages and provide forward secrecy.

The server keeps only the public pieces needed for key discovery:
- public identity key material
- signed prekey
- one-time prekeys
- registration metadata and device metadata

The server must never receive plaintext message content or private key material.

## 2. End-to-End Sequence

### Step 1: Register the user account

Create the account first so the backend has a user record and registration metadata.

Endpoint:
- POST /api/auth/register

Example request:
```json
{
  "username": "alice",
  "password": "Secret123!",
  "public_key": "BASE64_PUBLIC_KEY"
}
```

Use this when the client also wants to attach the user's public key at signup. If the app generates keys locally after registration, the public key can be uploaded later.

### Step 2: Generate Signal keys locally

The client generates the following on-device:
- identity key pair
- signed prekey
- batch of one-time prekeys
- registration id
- device id

This material stays local except for the public portions that are uploaded.

### Step 3: Upload the key bundle

Publish the device's public key material to the auth service.

Endpoint:
- POST /api/users/{user_id}/keys

Example request:
```json
{
  "identity_key": "BASE64_IDENTITY_KEY",
  "signed_prekey": "BASE64_SIGNED_PREKEY",
  "one_time_prekeys": [
    "BASE64_PREKEY_1",
    "BASE64_PREKEY_2",
    "BASE64_PREKEY_3"
  ],
  "registration_id": 12345,
  "device_id": "android-phone-1"
}
```

What the server stores:
- public identity key
- signed prekey
- one-time prekeys in a dedicated table
- registration id and device id

### Step 4: Discover the recipient

Before encryption can start, the sender needs the recipient's user identity and key bundle.

Typical lookup flow:
- GET /api/users?query={username_prefix}
- POST /api/users/{user_id}/friends

Search users first, then establish the friend relationship if your app requires it before chat creation.

### Step 5: Fetch the recipient key bundle

This is the key step for session establishment.

Endpoint:
- GET /api/users/{user_id}/bundle

Example response:
```json
{
  "user_id": "user_2",
  "identity_key": "BASE64_IDENTITY_KEY",
  "signed_prekey": "BASE64_SIGNED_PREKEY",
  "one_time_prekey": "BASE64_ONE_TIME_PREKEY",
  "registration_id": 67890,
  "device_id": "android-phone-2"
}
```

Important behavior:
- One one-time prekey is consumed on each request.
- If the recipient runs out of one-time prekeys, the client must publish more.

### Step 6: Establish the session locally

The client performs the X3DH-style handshake locally using:
- sender identity key
- sender ephemeral material
- recipient identity key
- recipient signed prekey
- recipient one-time prekey, if available

The result is a shared session secret stored only on the clients.

No server endpoint is involved in this computation.

### Step 7: Create or reuse the chat

If the chat does not exist yet, create it first.

Endpoint:
- POST /api/chats

Example request:
```json
{
  "name": "Alice and Bob",
  "member_ids": ["user_1", "user_2"],
  "is_group": false
}
```

For 1:1 chats, the backend deduplicates by member pair and returns the existing chat if one already exists.

### Step 8: Encrypt the message on the client

Before sending, encrypt the plaintext using the session state and Double Ratchet.

Input on the client:
- plaintext message
- local session state
- message counters / ratchet state

Output:
- ciphertext
- message metadata needed by the app, such as message type and device id

The plaintext never leaves the device.

### Step 9: Send ciphertext to the message service

Endpoint:
- POST /api/chats/{chat_id}/messages

Example request:
```json
{
  "chat_id": "chat_abc123",
  "sender_id": "user_1",
  "ciphertext": "BASE64_ENCRYPTED_PAYLOAD",
  "message_type": "text"
}
```

Example response:
```json
{
  "id": "msg_xyz789",
  "chat_id": "chat_abc123",
  "sender_id": "user_1",
  "ciphertext": "BASE64_ENCRYPTED_PAYLOAD",
  "message_type": "text",
  "created_at": "2026-04-20T12:00:00Z",
  "is_read": false
}
```

The server stores ciphertext only.

### Step 10: Receive realtime delivery over WebSocket

Endpoint:
- WS /ws/chats/{chat_id}

Authentication:
- ?token=<jwt>
- or Authorization: Bearer <jwt>

Incoming event example:
```json
{
  "type": "message.new",
  "chat_id": "chat_abc123",
  "message": {
    "id": "msg_xyz789",
    "chat_id": "chat_abc123",
    "sender_id": "user_1",
    "ciphertext": "BASE64_ENCRYPTED_PAYLOAD",
    "message_type": "text",
    "created_at": "2026-04-20T12:00:00Z"
  }
}
```

The client decrypts the ciphertext locally using the session state for that sender and chat.

## 3. Endpoint Call Order

For a first message to a new recipient, the usual sequence is:

1. POST /api/auth/register
2. POST /api/users/{user_id}/keys
3. GET /api/users?query={username_prefix}
4. POST /api/users/{user_id}/friends
5. GET /api/users/{recipient_id}/bundle
6. POST /api/chats
7. Encrypt plaintext locally
8. POST /api/chats/{chat_id}/messages
9. Open WS /ws/chats/{chat_id}

For later messages in the same session, the flow is shorter:

1. Encrypt locally with the stored ratchet state
2. POST /api/chats/{chat_id}/messages
3. Receive updates on WS /ws/chats/{chat_id}

## 4. What the Backend Stores

Auth service:
- username and password hash
- public key material
- device records
- signed prekeys
- one-time prekeys

Chat service:
- chat metadata
- membership lists

Message service:
- ciphertext
- sender id
- chat id
- timestamps
- read receipts

What it does not store:
- plaintext messages
- private identity keys
- private prekeys
- session secrets

## 5. Client Responsibilities

The client must:
- generate keys locally
- protect private keys in local secure storage
- fetch recipient bundles before first contact
- consume and manage ratchet state locally
- decrypt incoming ciphertext locally
- re-upload one-time prekeys before exhaustion
- rotate signed prekeys periodically

## 6. Example Client Flow

Pseudo-flow for sending a first message:

```text
register user
generate local Signal keys
upload public key bundle
find recipient user id
create or reuse chat
fetch recipient bundle
derive shared session secret locally
encrypt plaintext locally
send ciphertext to message endpoint
listen on websocket for delivery events
decrypt incoming ciphertext locally
```

Pseudo-flow for receiving a message:

```text
open websocket for the chat
receive message.new event
find local session state for sender/chat
decrypt ciphertext locally
render plaintext in UI
mark message as read if needed
```

## 7. Read Receipts

Read receipts are not encryption, but they fit into the same messaging flow.

Endpoints:
- POST /api/messages/{message_id}/read
- GET /api/messages/{message_id}/read

These endpoints only update message status. They do not change the encrypted payload.

## 8. Important Limitations

The current backend structure supports the Signal-style workflow, but a production client still needs to handle the following correctly:

- prekey replenishment when one-time prekeys run low
- device registration for multiple devices per user
- secure local key storage on the mobile device
- replay protection and ratchet state persistence
- identity verification / safety number handling if you want Signal-like trust guarantees

## 9. Summary

The intended design is a standard E2EE messaging model:
- the client encrypts and decrypts
- the server distributes public prekeys
- the server stores ciphertext only
- the websocket delivers encrypted events in realtime

If you implement the client to follow the endpoint sequence above, the backend already matches the expected Signal-style flow.