# MCP Document Store Server

JSON-RPC 2.0 MCP tool server for Career Roadmap AI — manages CV uploads, portfolio documents, certificates, and other user evidence files.

**Port:** `3009`

---

## Tools

| Method | Rate limit | Description |
|---|---|---|
| `upload_document` | 30/min | Store a base64-encoded file (max 10 MB, max 20 docs/user) |
| `get_document` | 30/min | Retrieve document metadata (+ optional base64 content) |
| `list_documents` | 30/min | List all documents for a user, optionally filtered by type |
| `delete_document` | 10/min | Permanently delete a document |

### Document types

`cv` · `portfolio` · `certificate` · `cover_letter` · `transcript` · `other`

---

## Storage backends

Select via `BLOB_STORAGE_PROVIDER` env var:

| Value | Description |
|---|---|
| `local` (default) | Local filesystem — good for dev/test |
| `azure` | Azure Blob Storage |
| `cloudinary` | Cloudinary raw assets (same credentials as the RAG layer) |

---

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `BLOB_STORAGE_PROVIDER` | No | `local` | Storage backend |
| `LOCAL_STORAGE_BASE_PATH` | No | `data/documents` | Base dir for local storage |
| `AZURE_STORAGE_CONNECTION_STRING` | azure only | — | Azure connection string |
| `AZURE_STORAGE_CONTAINER` | No | `career-roadmap-documents` | Azure container name |
| `CLOUDINARY_CLOUD_NAME` | cloudinary only | — | Cloudinary cloud name |
| `CLOUDINARY_API_KEY` | cloudinary only | — | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | cloudinary only | — | Cloudinary API secret |
| `CLOUDINARY_UPLOAD_FOLDER` | No | `career-roadmap/documents` | Root folder in Cloudinary |
| `MCP_REDIS_URL` | No | `redis://localhost:6379/8` | Redis for rate limiting |
| `MCP_API_KEY` | No | — | HMAC API key (X-MCP-API-Key header) |
| `SENTRY_DSN` | No | — | Sentry error tracking |
| `MAX_FILE_SIZE_MB` | No | `10` | Per-file size limit |
| `MAX_DOCUMENTS_PER_USER` | No | `20` | Per-user document cap |

---

## Running locally

```bash
# From mcp-servers/document-store/
poetry install
uvicorn server:app --host 0.0.0.0 --port 3009 --reload
```

Health checks:
- `GET /livez` — liveness (always 200 if process is up)
- `GET /readyz` — readiness (200 if storage backend is reachable, 503 otherwise)
- `GET /metrics` — Prometheus metrics

---

## Example call

```bash
# Upload a CV
curl -s -X POST http://localhost:3009/ \
  -H 'Content-Type: application/json' \
  -H 'X-MCP-API-Key: <key>' \
  -H 'X-User-ID: user-abc' \
  -d '{
    "jsonrpc": "2.0",
    "method": "upload_document",
    "params": {
      "user_id": "user-abc",
      "filename": "resume.pdf",
      "document_type": "cv",
      "content_type": "application/pdf",
      "content_base64": "<base64-encoded PDF>"
    },
    "id": 1
  }' | jq .
```

---

## Tests

```bash
poetry run pytest tests/ -v
```
