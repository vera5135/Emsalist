# Emsalist API Error Codes

## Standard Error Response

All API errors follow a unified structure:

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "The requested resource was not found",
    "details": null,
    "request_id": "abc123-correlation-id"
  }
}
```

## Error Codes

### 4xx — Client Errors

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 422 | Request contains invalid data |
| `AUTHENTICATION_REQUIRED` | 401 | Authentication required |
| `INVALID_CREDENTIALS` | 401 | Email or password is incorrect |
| `TOKEN_INVALID` | 401 | Token is malformed or invalid |
| `TOKEN_EXPIRED` | 401 | Token has expired |
| `ACCESS_DENIED` | 403 | Insufficient permissions |
| `RESOURCE_NOT_FOUND` | 404 | Generic resource not found |
| `CASE_NOT_FOUND` | 404 | Case does not exist or is not accessible |
| `DOCUMENT_NOT_FOUND` | 404 | Document does not exist or is not accessible |
| `INVALID_FILE` | 400 | File is invalid (corrupted, wrong format) |
| `FILE_TOO_LARGE` | 413 | File exceeds maximum upload size |
| `UNSUPPORTED_FILE_TYPE` | 400 | File type is not supported |
| `DUPLICATE_DOCUMENT` | 409 | Document with identical content already exists |
| `CONFLICT` | 409 | Request conflicts with current state |
| `RATE_LIMITED` | 429 | Too many requests |
| `JOB_NOT_FOUND` | 404 | Background job not found |
| `JOB_CANNOT_CANCEL` | 409 | Job cannot be cancelled (already completed) |

### 5xx — Server Errors

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `INTERNAL_ERROR` | 500 | Unexpected internal error |
| `SERVICE_UNAVAILABLE` | 503 | Service temporarily unavailable |
| `BACKUP_FAILED` | 500 | Backup operation failed |
| `RESTORE_FAILED` | 500 | Restore operation failed |
| `EXPORT_FAILED` | 500 | Export operation failed |

## Request Tracing

Every error response includes a `request_id` field containing the correlation ID.
Include this value when reporting issues for faster diagnosis.

## Authentication Errors

Authentication endpoints return generic error messages to prevent user enumeration:

- Invalid credentials: `INVALID_CREDENTIALS`
- Disabled account: `AUTHENTICATION_REQUIRED`
- Locked account: `AUTHENTICATION_REQUIRED`

## Authorization Errors

Case and document endpoints return `CASE_NOT_FOUND` (404) instead of `ACCESS_DENIED` (403)
when the requesting user is not a member of the case, to prevent resource enumeration.
