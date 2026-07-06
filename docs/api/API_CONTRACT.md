# Emsalist API Contract — v1

## Base URL

```
http://localhost:8000/api/v1
```

## Authentication

All endpoints under `/api/v1` support JWT Bearer token authentication:

```
Authorization: Bearer <access_token>
```

When `AUTH_MODE=local`, authentication is bypassed for development.

### Login

```
POST /api/v1/auth/login
```

Request:
```json
{
  "tenant_slug": "local",
  "email": "user@example.com",
  "password": "password"
}
```

Response:
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": "user-id",
    "tenant": "local",
    "role": "lawyer"
  }
}
```

### Token Refresh

```
POST /api/v1/auth/refresh
```

Requires `refresh_token` cookie (HttpOnly).

### Current User

```
GET /api/v1/auth/me
Authorization: Bearer <token>
```

---

## Cases

### List Cases
```
GET /api/v1/case/current
```

### Create Case
```
POST /api/v1/case/new
```

### Analyze Case
```
POST /api/v1/case/analyze
```

---

## Documents

### Upload
```
POST /api/v1/documents/upload
Content-Type: multipart/form-data

Fields:
  - file: (binary)
  - document_type: string (optional)
  - case_id: string (optional)
```

Supported formats: `.pdf`, `.txt`, `.docx`, `.udf`, `.jpg`, `.jpeg`, `.png`
Maximum size: 15 MB

### List
```
GET /api/v1/documents?case_id=<id>
```

### Analyze
```
POST /api/v1/documents/analyze
```

### Delete
```
DELETE /api/v1/documents/{document_id}?case_id=<id>
```

---

## Background Jobs

### Create Job
```
POST /api/v1/jobs
```

### List Jobs
```
GET /api/v1/jobs?case_id=<id>&status=<status>
```

### Get Job
```
GET /api/v1/jobs/{job_id}
```

### Cancel Job
```
POST /api/v1/jobs/{job_id}/cancel
```

### Retry Job
```
POST /api/v1/jobs/{job_id}/retry
```

---

## Lifecycle

### Soft Delete Case
```
DELETE /api/v1/lifecycle/cases/{case_id}
```

### Restore Case
```
POST /api/v1/lifecycle/cases/{case_id}/restore
```

### Legal Hold
```
POST   /api/v1/lifecycle/cases/{case_id}/legal-hold
DELETE /api/v1/lifecycle/cases/{case_id}/legal-hold
```

### Purge
```
GET  /api/v1/lifecycle/purge/preview
POST /api/v1/lifecycle/purge/run
```

---

## AI Services

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/ai/enrich-case` | Case enrichment |
| `POST /api/v1/ai/generate-legal-questions` | Generate legal questions |
| `POST /api/v1/ai/build-better-searches` | Improve search queries |
| `POST /api/v1/ai/audit-sources` | Audit legal sources |
| `POST /api/v1/ai/audit-precedents` | Audit precedents |
| `POST /api/v1/ai/audit-draft` | Audit petition draft |
| `POST /api/v1/ai/refine-draft` | Refine petition draft |

---

## Capabilities

```
GET /api/v1/meta/capabilities
```

Response:
```json
{
  "api_version": "v1",
  "features": {
    "document_upload": true,
    "document_analysis": true,
    "background_jobs": true,
    "ai_enrichment": false,
    "legal_brain": true,
    "yargitay_search": true,
    "petition_drafting": true,
    "case_lifecycle": true,
    "backup_restore": true,
    "metrics": true
  },
  "limits": {
    "max_upload_size_bytes": 15728640,
    "supported_extensions": [".pdf", ".txt", ".docx", ".udf", ".jpg", ".jpeg", ".png"]
  }
}
```

---

## Legacy Compatibility

All endpoints also exist at their original paths (without `/api/v1` prefix) for backward compatibility
with the existing web frontend. New clients should use `/api/v1/` paths exclusively.

## System Endpoints

System endpoints are NOT versioned:

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Health check with component status |
| `GET /live` | Liveness probe |
| `GET /ready` | Readiness probe |
| `GET /metrics` | Prometheus metrics |
