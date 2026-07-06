# Emsalist API Integration Guide

## Quick Start

### 1. Check API Health

```bash
curl http://localhost:8000/health
```

### 2. Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"tenant_slug":"local","email":"user@example.com","password":"password"}'
```

Response includes `access_token`, `token_type`, `expires_in`, and `user` info.

### 3. Use Authenticated Endpoints

```bash
curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer <access_token>"
```

### 4. Create a Case and Upload Documents

```bash
# Create case
curl -X POST http://localhost:8000/api/v1/case/new \
  -H "Content-Type: application/json" \
  -d '{}'

# Upload document (returns case_id from create step)
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -F "file=@document.pdf" \
  -F "case_id=<case_id>"

# List documents
curl "http://localhost:8000/api/v1/documents?case_id=<case_id>"
```

## Error Handling

All errors follow a unified format with `code`, `message`, `details`, and `request_id` fields.
See [ERROR_CODES.md](./ERROR_CODES.md) for the complete catalog.

## API Versioning

- Canonical path: `/api/v1/`
- Legacy paths: root-level (e.g., `/case/new`)
- New clients: use `/api/v1/` paths exclusively
- System endpoints (`/health`, `/live`, `/ready`, `/metrics`): unversioned

## Authentication Modes

### JWT Mode (`AUTH_MODE=jwt`)
- Obtain `access_token` via `POST /api/v1/auth/login`
- Include `Authorization: Bearer <token>` header
- Token expires after 30 minutes
- Refresh via `POST /api/v1/auth/refresh` (requires HttpOnly cookie)

### Local Mode (`AUTH_MODE=local`)
- All endpoints accessible without authentication
- For development only
- Never use in production

## File Upload Limits

- Maximum size: 15 MB
- Supported formats: PDF, TXT, DOCX, UDF, JPG, JPEG, PNG
- Duplicate detection via SHA256

## Cross-Origin (CORS)

In production, CORS is configured via `CORS_ALLOW_ORIGINS` environment variable.
Preflight requests are supported for configured origins.

## Rate Limiting

API rate limiting is active for non-localhost clients:
- 60 requests per 60-second window
- Returns `429 Too Many Requests` with `Retry-After` header
- Health/metrics endpoints are excluded
