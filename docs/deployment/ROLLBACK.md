# Emsalist Rollback Strategy

## Quick Rollback

If a deployment causes issues, rollback immediately:

```bash
# 1. Switch to previous container image
docker compose -f docker-compose.yml down
export EMSALIST_IMAGE_TAG=<previous-tag>
docker compose -f docker-compose.yml up -d

# 2. Verify
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/meta/version
```

## Migration Safety

### Forward-only migrations
Most Alembic migrations are forward-only (they cannot be automatically reversed if data transformation occurred).
Before deploying:

1. Review the migration in `backend/app/db/migrations/`
2. If destructive columns/tables are renamed:
   - Deploy new schema columns as nullable/optional first
   - Deploy code that writes to both old and new columns
   - Migrate existing data
   - Deploy code that reads from new columns only
   - Remove old columns in a later migration
3. If simple additive migrations (new tables):
   - These are safe to rollback via `alembic downgrade -1`

### Downgrade support
```bash
# Check current state
python scripts/check_migration_state.py

# Downgrade one revision (requires revision to support downgrade)
alembic downgrade -1
```

## Database Restore

If migration goes wrong and rollback is not possible:

```bash
# 1. Restore from latest backup
python -c "
from app.services.backup_service import restore_latest
restore_latest(restore_to_db='emsalist')
"

# 2. Verify data integrity
python -c "
from app.db.session import check_db_health
import asyncio
print(asyncio.run(check_db_health()))
"
```

## Volume Safety

| Volume | Rollback Impact | Action |
|--------|----------------|--------|
| `pgdata` | Database state | Restore from backup if migration corrupted |
| `upload_data` | User-uploaded documents | No action needed — uploads are backward compatible |
| `export_data` | Generated exports | Can be re-generated |
| `backup_data` | Backup files | Do not delete — needed for restore |

## Background Job Handling

Jobs queued during a bad deployment:
1. Rolling back may leave stale job records
2. Workers will pick up and fail jobs incompatible with old version
3. Cancel active jobs before rollback:
   ```
   GET /api/v1/jobs?status=queued
   POST /api/v1/jobs/{job_id}/cancel
   ```

## Emergency Secret Rotation

If secrets are compromised during deployment:
1. Rotate all secrets immediately (see SECRET_ROTATION.md)
2. Revoke all active sessions: `POST /api/v1/auth/logout-all`
3. Verify no unauthorized access in audit logs: `GET /api/v1/lifecycle/audit`

## Rollback Smoke Test

After rollback, verify:
- `GET /health` → 200
- `GET /ready` → 200
- `POST /api/v1/auth/login` → 200
- `GET /api/v1/case/current` → 200
- `GET /api/v1/documents` → 200
- OpenAPI schema matches: `diff docs/api/openapi-v1.json <(curl -s http://localhost:8000/openapi.json)`

## Version Verification

```bash
curl http://localhost:8000/api/v1/meta/version | python -m json.tool
```

Expected output should show the rolled-back version.
