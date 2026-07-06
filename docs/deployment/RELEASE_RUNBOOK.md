# Emsalist Release Runbook

## Pre-Release Checklist

- [ ] All CI checks pass on `main`
- [ ] `git diff --check` clean
- [ ] Working tree clean, no dirty files
- [ ] Security scan shows no new high/critical findings
- [ ] Dependency audit shows no known vulnerabilities
- [ ] Migration state: `python backend/scripts/check_migration_state.py`
- [ ] OpenAPI schema matches: `diff docs/api/openapi-v1.json <generated-openapi.json>`
- [ ] Docker build succeeds
- [ ] Docker Compose smoke test passes
- [ ] Rollback plan reviewed

## Release Steps

### 1. Tag the Release
```bash
git tag -a v0.1.0-rc.N -m "Emsalist Phase 1 Release Candidate N"
git push origin v0.1.0-rc.N
```

### 2. Build Container
```bash
docker build \
  --build-arg BUILD_COMMIT=$(git rev-parse HEAD) \
  --build-arg BUILD_TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
  -t emsalist-api:v0.1.0-rc.N \
  -t emsalist-api:latest .
```

### 3. Record Image Digest
```bash
docker inspect emsalist-api:v0.1.0-rc.N --format='{{.Id}}'
```

### 4. Run Database Migrations
```bash
docker compose run --rm migration
```

### 5. Deploy
```bash
docker compose up -d
```

### 6. Smoke Test
```bash
curl -f http://localhost:8000/live || exit 1
curl -f http://localhost:8000/ready || echo "Not ready yet — retrying..."
curl -f http://localhost:8000/api/v1/meta/version | python -m json.tool
curl -f http://localhost:8000/api/v1/meta/capabilities | python -m json.tool
```

### 7. Monitor
- Check logs: `docker compose logs -f api`
- Check health: `curl http://localhost:8000/health`
- Check metrics: `curl http://localhost:8000/metrics`

## Verifications

| Check | Command | Expected |
|-------|---------|----------|
| Alive | `GET /live` | 200 |
| Ready | `GET /ready` | 200 |
| Health | `GET /health` | 200, status healthy |
| Auth | `POST /api/v1/auth/login` | 200 + access_token |
| Cases | `GET /api/v1/case/current` | 200 |
| Documents | `GET /api/v1/documents` | 200 |
| API version | `GET /api/v1/meta/version` | 200 |
| Capabilities | `GET /api/v1/meta/capabilities` | 200 |

## If Something Goes Wrong

See [ROLLBACK.md](./ROLLBACK.md).

## Post-Release

- [ ] Verify audit logs: `GET /api/v1/lifecycle/audit`
- [ ] Check no errors in logs for 5 minutes
- [ ] Notify team/consumers
- [ ] Tag as stable if 24h without issues
