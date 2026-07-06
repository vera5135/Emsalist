# Emsalist Production Environment Variables

## Required for Production

Set these before starting the application in production:

| Variable | Description | Example |
|----------|-------------|---------|
| `EMSALIST_ENVIRONMENT` | Must be `production` | `production` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://user:pass@host:5432/emsalist` |
| `JWT_SECRET_KEY` | Minimum 32 characters | (generated secret) |
| `AUTH_MODE` | Must be `jwt` | `jwt` |
| `ALLOWED_HOSTS` | Comma-separated hostnames | `api.example.com,app.example.com` |
| `CORS_ALLOW_ORIGINS` | Comma-separated origins | `https://app.example.com` |

## Encryption

Required only when `BACKUP_ENCRYPTION_ENABLED=true`:

| Variable | Description |
|----------|-------------|
| `BACKUP_ENCRYPTION_ENABLED` | `true` or `false` |
| `BACKUP_ENCRYPTION_KEY` | Encryption key for backups |

## AI Providers (Optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_ENABLED` | Enable Gemini AI features | `false` |
| `GEMINI_API_KEY` | Gemini API key | — |
| `GEMINI_MODEL` | Gemini model name | `gemini-2.5-flash` |
| `GEMINI_TIMEOUT_SECONDS` | API timeout | `30` |

## Storage

| Variable | Description | Default |
|----------|-------------|---------|
| `EMSALIST_STORAGE_ROOT` | Base path for uploads/exports/backups | `backend/document_store` (container: `/data`) |
| `EMSALIST_MAX_UPLOAD_SIZE` | Maximum file upload in bytes | `15728640` (15 MB) |

## Logging

| Variable | Description | Default (production) |
|----------|-------------|---------------------|
| `EMSALIST_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |
| `EMSALIST_LOG_FORMAT` | `json` or `text` | `json` |
| `EMSALIST_LOG_SERVICE_NAME` | Service name in logs | `emsalist-api` |

## Observability

| Variable | Description | Default |
|----------|-------------|---------|
| `EMSALIST_METRICS_ENABLED` | Enable Prometheus metrics | `true` |

## Build Metadata

| Variable | Description |
|----------|-------------|
| `EMSALIST_COMMIT` | Git commit SHA (set at build time) |
| `EMSALIST_BUILD_TIMESTAMP` | ISO 8601 UTC timestamp (set at build time) |

## Development Override

| Variable | Description |
|----------|-------------|
| `EMSALIST_SKIP_PRODUCTION_VALIDATION` | Set to `true` to bypass production safety checks (for migration jobs only) |
