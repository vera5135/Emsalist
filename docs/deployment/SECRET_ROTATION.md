# Emsalist Secret Rotation

## When to Rotate

- Key compromise or suspected compromise
- Employee departure with access to secrets
- Scheduled rotation (recommended: every 90 days)
- After any security incident

## Secrets to Rotate

| Secret | Rotation Method | Impact |
|--------|----------------|--------|
| `JWT_SECRET_KEY` | Generate new key, restart API | Invalidates all active sessions — notify users |
| `BACKUP_ENCRYPTION_KEY` | Generate new key, re-encrypt existing backups | Old backups must be decrypted with old key before rotation |
| `GEMINI_API_KEY` | Generate new key in AI provider dashboard, update env | Temporary API outage during restart |
| Database password | Update PostgreSQL, update `DATABASE_URL`, restart API | Brief downtime while both old and new passwords are accepted |

## JWT Secret Rotation Procedure

1. Generate a new secure random key (minimum 32 characters):
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
2. Update `JWT_SECRET_KEY` in your environment/secret manager
3. Restart the API service
4. All existing sessions are invalidated — users must re-authenticate
5. Verify authentication works: `GET /api/v1/auth/me`

## Backup Encryption Key Rotation

1. Generate new key
2. Decrypt all existing backups with old key
3. Update `BACKUP_ENCRYPTION_KEY` 
4. Restart the API
5. New backups use new key
6. Store old key securely until all old backups are expired per retention policy

## AI Provider Key Rotation

1. Log into AI provider dashboard (Google AI Studio, DeepSeek, etc.)
2. Create a new API key
3. Update `GEMINI_API_KEY` or equivalent env variable
4. Restart the API
5. Delete/revoke the old key in the provider dashboard
6. Verify AI features work

## Database Password Rotation

1. Update PostgreSQL with new password:
   ```sql
   ALTER USER emsalist WITH PASSWORD 'new_password';
   ```
2. Update `DATABASE_URL` environment variable
3. Restart the API
4. Verify database connectivity: `GET /health`

## Post-Rotation Verification

After any rotation, verify:
- `GET /health` returns healthy
- `GET /api/v1/auth/login` works
- `GET /api/v1/meta/version` confirms deployment
- Logs show no authentication errors

## Audit Trail

Record every rotation:
- What was rotated
- Who performed the rotation
- Timestamp (UTC)
- Verification result
- Any incidents or issues
