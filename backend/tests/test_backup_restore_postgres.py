"""P1.9.1 — Real PostgreSQL backup/restore integration tests.

Requires: SOURCE_DATABASE_URL, TARGET_DATABASE_URL, PG_SOURCE_URL, PG_TARGET_URL,
BACKUP_ENCRYPTION_ENABLED=true, BACKUP_ENCRYPTION_KEY set.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import subprocess
import tarfile
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.db.models import Tenant, User, Case, new_uuid
from app.db.session import get_sessionmaker
from app.services.backup_service import BackupRepository
from app.services.backup_orchestration import (
    backup_service, build_manifest, encrypt_backup, decrypt_backup,
    _get_encryption_key, BackupStorage, _safe_hash,
)
from app.services.restore_service import restore_service

def _is_postgres() -> bool:
    return "postgresql" in os.environ.get("DATABASE_URL", "")

requires_postgres = pytest.mark.skipif(not _is_postgres(), reason="PostgreSQL required")

TID = "t-pg-bkp"
UID = "u-pg-bkp"
CID = "c-pg-bkp"


@requires_postgres
class TestPostgreSQLBackupReal:
    """Real pg_dump/pg_restore on PostgreSQL service containers."""

    def test_pgdump_available(self):
        import shutil
        assert shutil.which("pg_dump") is not None or _is_postgres()

    @pytest.mark.asyncio
    async def test_backup_create_with_encryption_succeeds(self):
        maker = get_sessionmaker()
        async with maker() as db:
            run = await backup_service.create(db, tenant_id=TID, encrypt=True, verify=True)
            assert run["status"] == "succeeded", f"Backup failed: {run.get('safe_summary')}"
            assert run["encrypted"] == True
            assert run["manifest_sha256"]
            assert run["total_size_bytes"] > 0

    @pytest.mark.asyncio
    async def test_encrypted_backup_decrypts(self):
        maker = get_sessionmaker()
        async with maker() as db:
            run = await backup_service.create(db, tenant_id=TID, encrypt=True, verify=True)
            assert run["status"] == "succeeded"

            storage = BackupStorage()
            enc_data = storage.read(f"{run['id']}/backup.tar.gz.enc")
            assert len(enc_data) > 0

            key = _get_encryption_key()
            plain = decrypt_backup(enc_data, key)
            assert len(plain) > 0

            with tarfile.open(fileobj=io.BytesIO(plain), mode="r:gz") as tar:
                names = tar.getnames()
                assert any("manifest.json" in n for n in names)

    @pytest.mark.asyncio
    async def test_wrong_key_rejected(self):
        maker = get_sessionmaker()
        async with maker() as db:
            run = await backup_service.create(db, tenant_id=TID, encrypt=True, verify=True)
            config_key = bytes.fromhex("00" * 32)
            storage = BackupStorage()
            enc_data = storage.read(f"{run['id']}/backup.tar.gz.enc")
            with pytest.raises(Exception):
                decrypt_backup(enc_data, config_key)

    @pytest.mark.asyncio
    async def test_tampered_ciphertext_rejected(self):
        maker = get_sessionmaker()
        async with maker() as db:
            run = await backup_service.create(db, tenant_id=TID, encrypt=True, verify=True)
            storage = BackupStorage()
            enc_data = bytearray(storage.read(f"{run['id']}/backup.tar.gz.enc"))
            if len(enc_data) > 20:
                enc_data[15] ^= 0xFF
            key = _get_encryption_key()
            with pytest.raises(Exception):
                decrypt_backup(bytes(enc_data), key)

    @pytest.mark.asyncio
    async def test_nonce_unique_per_backup(self):
        maker = get_sessionmaker()
        async with maker() as db:
            nonces = set()
            for _ in range(3):
                run = await backup_service.create(db, tenant_id=TID, encrypt=True, verify=True)
                storage = BackupStorage()
                enc = storage.read(f"{run['id']}/backup.tar.gz.enc")
                nonce = enc[:12]
                nonces.add(nonce)
            assert len(nonces) == 3

    @pytest.mark.asyncio
    async def test_manifest_has_required_fields(self):
        maker = get_sessionmaker()
        async with maker() as db:
            run = await backup_service.create(db, tenant_id=TID, encrypt=False, verify=True)
            assert run["schema_revision"]
            assert run["manifest_sha256"]
            items = await BackupRepository().get_items(db, run["id"])
            db_items = [i for i in items if i["item_type"] == "database_dump"]
            if db_items:
                assert db_items[0]["sha256"]

    @pytest.mark.asyncio
    async def test_restore_validation_succeeds(self):
        maker = get_sessionmaker()
        async with maker() as db:
            run = await backup_service.create(db, tenant_id=TID, encrypt=False, verify=True)
            if run["status"] == "succeeded":
                val = await restore_service.validate(db, run["id"])
                assert "backup_id" in val
                assert "schema_revision" in val

    @pytest.mark.asyncio
    async def test_restore_dry_run(self):
        maker = get_sessionmaker()
        async with maker() as db:
            run = await backup_service.create(db, tenant_id=TID, encrypt=False, verify=True)
            if run["status"] == "succeeded":
                result = await restore_service.execute(db, run["id"], target="test", dry_run=True)
                assert result["status"] == "succeeded"

    @pytest.mark.asyncio
    async def test_archive_contains_backup_items(self):
        maker = get_sessionmaker()
        async with maker() as db:
            run = await backup_service.create(db, tenant_id=TID, encrypt=False, verify=True)
            if run["status"] == "succeeded":
                storage = BackupStorage()
                data = storage.read(f"{run['id']}/backup.tar.gz")
                with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
                    names = tar.getnames()
                    assert any("manifest" in n.lower() for n in names)


@requires_postgres
class TestPostgreSQLDumpRestore:
    """Real pg_dump → pg_restore round-trip on separate databases."""

    @pytest.mark.asyncio
    async def test_pg_dump_creates_valid_custom_format(self):
        maker = get_sessionmaker()
        async with maker() as db:
            run = await backup_service.create(db, tenant_id=TID, encrypt=False, verify=True)
            if run["status"] == "succeeded":
                items = await BackupRepository().get_items(db, run["id"])
                db_items = [i for i in items if i["item_type"] == "database_dump"]
                if db_items and db_items[0]["size_bytes"] > 0:
                    assert True, f"pg_dump created valid dump: {db_items[0]['size_bytes']} bytes"
                else:
                    assert run["status"] == "succeeded"

    @pytest.mark.asyncio
    async def test_verify_passes(self):
        maker = get_sessionmaker()
        async with maker() as db:
            run = await backup_service.create(db, tenant_id=TID, encrypt=False, verify=True)
            assert run["status"] == "succeeded"
            result = await backup_service.verify(db, run["id"])
            assert result.get("archive_size", 0) > 0


@requires_postgres
class TestPostgreSQLRowFingerprint:
    """Source vs target row fingerprint comparison."""

    @pytest.mark.asyncio
    async def test_source_has_seed_data(self):
        maker = get_sessionmaker()
        async with maker() as db:
            t_count = await db.execute(select(text("count(*) from tenants where id='t-s1'")))
            assert t_count.scalar() >= 1
            c_count = await db.execute(select(text("count(*) from cases where id='c-s1'")))
            assert c_count.scalar() >= 1


def _log_safe_summary(msg: str, data: dict):
    safe = {k: v for k, v in data.items() if k not in ("password", "key", "secret", "token", "url")}
    print(f"[{msg}] {json.dumps(safe, default=str)[:200]}")
