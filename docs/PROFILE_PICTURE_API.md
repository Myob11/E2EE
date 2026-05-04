# Profile Picture API Documentation

This API allows frontend applications to upload, download, and manage user profile pictures using MinIO S3 storage.

## Endpoints

### 1. Get Upload URL
**POST** `/profiles/{username}/picture`

Get a pre-signed S3 URL for uploading a profile picture.

**Parameters:**
- `username` (path): Username for the profile picture
- `content_type` (query, optional): Image MIME type. Default: `image/jpeg`
  - Supported: `image/jpeg`, `image/png`, `image/webp`, `image/gif`

**Response:**
```json
{
  "username": "john_doe",
  "key": "profiles/john_doe/picture",
  "upload_url": "http://212.235.185.13:9000/profiles/profiles/john_doe/picture?...",
  "expires_at": "2026-05-04T15:30:00Z"
}
```

**Frontend Usage (JavaScript):**
```javascript
// Step 1: Get upload URL
const response = await fetch(
  'http://localhost:8004/profiles/john_doe/picture?content_type=image/jpeg',
  { method: 'POST' }
);
const { upload_url } = await response.json();

// Step 2: Upload file to MinIO
const file = document.getElementById('imageInput').files[0];
await fetch(upload_url, {
  method: 'PUT',
  body: file,
  headers: { 'Content-Type': 'image/jpeg' }
});

// Step 3: Mark upload as complete
await fetch('http://localhost:8004/profiles/john_doe/picture/complete', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ size: file.size })
});
```

---

### 2. Get Download URL
**GET** `/profiles/{username}/picture`

Get a pre-signed S3 URL for downloading a profile picture.

**Parameters:**
- `username` (path): Username for the profile picture

**Response:**
```json
{
  "username": "john_doe",
  "key": "profiles/john_doe/picture",
  "download_url": "http://212.235.185.13:9000/profiles/profiles/john_doe/picture?...",
  "expires_at": "2026-05-04T15:30:00Z",
  "content_type": "image/jpeg"
}
```

**Frontend Usage (JavaScript):**
```javascript
// Get download URL
const response = await fetch('http://localhost:8004/profiles/john_doe/picture');
const { download_url, content_type } = await response.json();

// Display image in frontend
const img = document.getElementById('profilePic');
img.src = download_url;
img.alt = 'Profile Picture';

// Or download as file
const link = document.createElement('a');
link.href = download_url;
link.download = 'profile-picture.jpg';
link.click();
```

---

### 3. Get Picture Metadata
**GET** `/profiles/{username}/picture/metadata`

Get metadata about a profile picture.

**Parameters:**
- `username` (path): Username for the profile picture

**Response:**
```json
{
  "username": "john_doe",
  "key": "profiles/john_doe/picture",
  "content_type": "image/jpeg",
  "size": 125432,
  "uploaded_at": "2026-05-04T14:30:00Z"
}
```

**Frontend Usage (JavaScript):**
```javascript
const response = await fetch('http://localhost:8004/profiles/john_doe/picture/metadata');
const metadata = await response.json();

console.log(`Profile picture: ${metadata.size} bytes, uploaded: ${metadata.uploaded_at}`);
```

---

### 4. Complete Upload
**POST** `/profiles/{username}/picture/complete`

Mark a profile picture upload as complete and store its size.

**Parameters:**
- `username` (path): Username
- `size` (body, number): File size in bytes

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

---

## Complete Upload Flow

### Frontend Implementation Example

```html
<!DOCTYPE html>
<html>
<head>
  <title>Profile Picture Upload</title>
</head>
<body>
  <div>
    <input type="file" id="imageInput" accept="image/*" />
    <button onclick="uploadProfilePicture()">Upload</button>
    <img id="profilePic" width="200" />
  </div>

  <script>
    const API_BASE = 'http://localhost:8004';
    const username = 'john_doe'; // Get from logged-in user

    async function uploadProfilePicture() {
      const fileInput = document.getElementById('imageInput');
      const file = fileInput.files[0];

      if (!file) {
        alert('Please select an image');
        return;
      }

      // Validate file type
      const validTypes = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];
      if (!validTypes.includes(file.type)) {
        alert('Please select a valid image type (JPEG, PNG, WebP, or GIF)');
        return;
      }

      try {
        // Step 1: Get upload URL
        console.log('Getting upload URL...');
        const uploadResponse = await fetch(
          `${API_BASE}/profiles/${username}/picture?content_type=${file.type}`,
          { method: 'POST' }
        );
        const uploadData = await uploadResponse.json();
        const { upload_url } = uploadData;

        // Step 2: Upload to MinIO
        console.log('Uploading file...');
        const putResponse = await fetch(upload_url, {
          method: 'PUT',
          body: file,
          headers: { 'Content-Type': file.type }
        });

        if (!putResponse.ok) {
          throw new Error('Upload failed: ' + putResponse.statusText);
        }

        // Step 3: Mark upload as complete
        console.log('Marking upload as complete...');
        const completeResponse = await fetch(
          `${API_BASE}/profiles/${username}/picture/complete`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ size: file.size })
          }
        );
        const completeData = await completeResponse.json();
        console.log('Upload complete:', completeData);

        // Step 4: Display the uploaded picture
        await displayProfilePicture();
      } catch (error) {
        console.error('Error uploading profile picture:', error);
        alert('Error uploading picture: ' + error.message);
      }
    }

    async function displayProfilePicture() {
      try {
        // Get download URL
        const downloadResponse = await fetch(
          `${API_BASE}/profiles/${username}/picture`
        );
        const downloadData = await downloadResponse.json();
        const { download_url } = downloadData;

        // Display image
        const img = document.getElementById('profilePic');
        img.src = download_url;
        img.alt = 'Your Profile Picture';
      } catch (error) {
        console.error('Error loading profile picture:', error);
      }
    }

    // Load profile picture on page load
    window.addEventListener('load', displayProfilePicture);
  </script>
</body>
</html>
```

---

## Error Responses

| Status | Error | Description |
|--------|-------|-------------|
| 400 | Invalid username | Username is empty or invalid |
| 400 | Invalid image content type | File type is not supported |
| 404 | Profile picture not found | No picture exists for this username |
| 500 | Server error | MinIO connection failed (will still work locally) |

---

## Configuration

The media service uses the following environment variables (set in `docker-compose.yml`):

```yaml
MINIO_ENDPOINT=212.235.185.13:9000
MINIO_ACCESS_KEY=user-01
MINIO_SECRET_KEY=thestrongestvajePass01
MINIO_BUCKET=profiles
MINIO_SECURE=false
DOMAIN=secra.top
```

**Current Setup:**
- **Endpoint**: External MinIO at `212.235.185.13:9000`
- **Bucket**: `profiles` (contains all profile pictures)
- **Key Format**: `profiles/{username}/picture`
- **Access**: Public URLs via pre-signed URLs (1-hour expiration)

---

## Fallback Behavior

When MinIO is unavailable, the API returns fallback URLs in the format:
```
http://profiles.secra.top/{username}/picture
```

This allows the API to respond gracefully even if the S3 service is down.

---

## Testing the API

### Using cURL

```bash
# Get upload URL
curl -X POST 'http://localhost:8004/profiles/john_doe/picture?content_type=image/jpeg'

# Get download URL
curl 'http://localhost:8004/profiles/john_doe/picture'

# Get metadata
curl 'http://localhost:8004/profiles/john_doe/picture/metadata'

# Mark upload complete
curl -X POST 'http://localhost:8004/profiles/john_doe/picture/complete' \
  -H 'Content-Type: application/json' \
  -d '{"size": 125432}'
```

### Using Python

```python
import requests
import json

BASE_URL = 'http://localhost:8004'
username = 'john_doe'

# Get upload URL
upload_resp = requests.post(
    f'{BASE_URL}/profiles/{username}/picture',
    params={'content_type': 'image/jpeg'}
)
upload_data = upload_resp.json()
print('Upload URL:', upload_data['upload_url'])

# Upload file
with open('profile.jpg', 'rb') as f:
    file_size = len(f.read())
    f.seek(0)
    requests.put(upload_data['upload_url'], data=f)

# Mark complete
requests.post(
    f'{BASE_URL}/profiles/{username}/picture/complete',
    json={'size': file_size}
)

# Get download URL
download_resp = requests.get(f'{BASE_URL}/profiles/{username}/picture')
download_data = download_resp.json()
print('Download URL:', download_data['download_url'])
```

---

## Notes

- **Pre-signed URLs expire after 1 hour** for security
- **Each username can have only one profile picture** (new upload replaces old)
- **File size limit depends on MinIO configuration** (typically 5GB+)
- **Access is public** (anyone with the download URL can view the picture)
- **CORS must be enabled** on MinIO for cross-origin frontend requests
