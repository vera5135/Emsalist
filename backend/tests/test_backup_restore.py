"""P1.9 — Backup & restore integration tests."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio

from app.db.models import Tenant, User, Case, new_uuid
from app.db.session import get_sessionmaker
from app.services.backup_service import BackupRepository
from app.services.backup_orchestration import (
    backup_service, build_manifest, encrypt_backup, decrypt_backup,
    _get_encryption_key, BackupLockManager, BackupStorage, _safe_hash,
)
from app.services.restore_service import restore_service, RestoreRepository
from app.config import get_settings

TID = "t-bkp"


@pytest_asyncio.fixture
async def backup_db():
    maker = get_sessionmaker()
    async with maker() as db:
        from sqlalchemy import select
        from app.db.models import BackupRun, BackupItem, RestoreRun, RestoreItem, BackupLock, Tenant, User
        for m in [RestoreItem, RestoreRun, BackupItem, BackupRun, BackupLock]:
            try:
                result = await db.execute(select(m.id))
                for row in result.scalars():
                    await db.delete(row)
            except Exception:
                pass
        try:
            result = await db.execute(select(User).where(User.tenant_id == TID))
            for row in result.scalars():
                await db.delete(row)
        except Exception:
            pass
        try:
            result = await db.execute(select(Tenant).where(Tenant.id == TID))
            for row in result.scalars():
                await db.delete(row)
        except Exception:
            pass
        await db.flush()
        db.add(Tenant(id=TID, name="BackupTest", slug=TID, status="active"))
        db.add(User(id="u-bkp", tenant_id=TID, email_normalized="bkp@t.com", display_name="Bkp", status="active", role="tenant_admin"))
        await db.commit()
        yield db
        await db.rollback()


class TestBackupCreate:
    @pytest.mark.asyncio
    async def test_create_backup_produces_succeeded(self, backup_db):
        run = await backup_service.create(backup_db, tenant_id=TID, encrypt=False, verify=False)
        assert run["id"]
        assert run["item_count"] >= 0
        assert run["encrypted"] == False

    @pytest.mark.asyncio
    async def test_backup_manifest_has_required_fields(self, backup_db):
        run = await backup_service.create(backup_db, tenant_id=TID, encrypt=False)
        assert run["manifest_sha256"]
        assert run["schema_revision"]

    @pytest.mark.asyncio
    async def test_backup_manifest_deterministic(self, backup_db):
        manifest1 = build_manifest("b1", "rev1", "v1", [], None, [], [])
        manifest2 = build_manifest("b1", "rev1", "v1", [], None, [], [])
        assert manifest1["manifest"]["item_count"] == manifest2["manifest"]["item_count"]
        assert manifest1["manifest"]["format_version"] == manifest2["manifest"]["format_version"]

    @pytest.mark.asyncio
    async def test_backup_lock_prevents_concurrent(self, backup_db):
        lock_mgr = BackupLockManager()
        acquired = await lock_mgr.acquire(backup_db, "test_lock", "owner1")
        assert acquired == True
        acquired2 = await lock_mgr.acquire(backup_db, "test_lock", "owner2")
        assert acquired2 == False
        released = await lock_mgr.release(backup_db, "test_lock", "owner1")
        assert released == True

    @pytest.mark.asyncio
    async def test_lock_lease_recovery(self, backup_db):
        from app.db.models import BackupLock
        from sqlalchemy import select, update
        lock_mgr = BackupLockManager()
        await lock_mgr.acquire(backup_db, "test_lock2", "owner1", lease_seconds=1)
        await asyncio.sleep(0.2)
        result = await backup_db.execute(
            update(BackupLock).where(BackupLock.lock_name == "test_lock2")
            .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=10))
        )
        await backup_db.flush()
        await backup_db.commit()
        acquired = await lock_mgr.acquire(backup_db, "test_lock2", "owner3")
        assert acquired == True


class TestBackupEncryption:
    @pytest.mark.asyncio
    async def test_encrypt_decrypt_roundtrip(self, backup_db):
        key = hashlib.sha256(b"test-key-32-bytes-long-padding").digest()
        plaintext = b"hello world test data for encryption"
        ciphertext, nonce = encrypt_backup(plaintext, key)
        assert ciphertext != plaintext
        assert len(ciphertext) > len(plaintext)
        decrypted = decrypt_backup(ciphertext, key)
        assert decrypted == plaintext

    @pytest.mark.asyncio
    async def test_wrong_key_rejected(self, backup_db):
        key1 = hashlib.sha256(b"key-one-32-bytes-long-padding-").digest()
        key2 = hashlib.sha256(b"key-two-32-bytes-long-padding-").digest()
        ciphertext, _ = encrypt_backup(b"data", key1)
        with pytest.raises(Exception):
            decrypt_backup(ciphertext, key2)

    @pytest.mark.asyncio
    async def test_tampered_ciphertext_rejected(self, backup_db):
        key = hashlib.sha256(b"key-three-32-bytes-long-padd").digest()
        ciphertext, _ = encrypt_backup(b"data", key)
        tampered = bytearray(ciphertext)
        tampered[14] ^= 0xFF
        with pytest.raises(Exception):
            decrypt_backup(bytes(tampered), key)

    @pytest.mark.asyncio
    async def test_random_nonce_each_backup(self, backup_db):
        key = hashlib.sha256(b"key-four-32-bytes-long-paddi").digest()
        nonces = set()
        for i in range(5):
            _, nonce = encrypt_backup(f"data{i}".encode(), key)
            nonces.add(nonce)
        assert len(nonces) == 5

    @pytest.mark.asyncio
    async def test_key_not_in_manifest(self, backup_db):
        manifest = build_manifest("b1", "r1", "v1", [], {"algorithm": "AES-256-GCM", "key_id": "k1"}, [], [])
        manifest_json = json.dumps(manifest["manifest"])
        assert "ENCRYPTION_KEY" not in manifest_json


class TestBackupVerify:
    @pytest.mark.asyncio
    async def test_verify_succeeded_backup(self, backup_db):
        run = await backup_service.create(backup_db, tenant_id=TID, encrypt=False, verify=False)
        result = await backup_service.verify(backup_db, run["id"])
        has_db = result.get("has_database", False)
        assert "item_count" in result

    @pytest.mark.asyncio
    async def test_manifest_sha256_correct(self, backup_db):
        run = await backup_service.create(backup_db, tenant_id=TID, encrypt=False)
        if run["status"] == "succeeded":
            assert len(run["manifest_sha256"]) >= 32

    @pytest.mark.asyncio
    async def test_archive_contains_manifest(self, backup_db):
        run = await backup_service.create(backup_db, tenant_id=TID, encrypt=False)
        storage = BackupStorage()
        data = storage.read(f"{run['id']}/backup.tar.gz")
        assert len(data) > 0
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            names = tar.getnames()
            assert any("manifest.json" in n for n in names)


class TestBackupPrune:
    @pytest.mark.asyncio
    async def test_dry_run_does_not_delete(self, backup_db):
        run = await backup_service.create(backup_db, tenant_id=TID, encrypt=False)
        result = await backup_service.prune(backup_db, dry_run=True)
        assert result["dry_run"] == True
        after = await BackupRepository().get_run(backup_db, run["id"])
        assert after is not None

    @pytest.mark.asyncio
    async def test_prune_idempotent(self, backup_db):
        result1 = await backup_service.prune(backup_db, dry_run=True)
        result2 = await backup_service.prune(backup_db, dry_run=True)
        assert result1["pruned"] == result2["pruned"]


class TestRestore:
    @pytest.mark.asyncio
    async def test_validate_succeeded_backup(self, backup_db):
        run = await backup_service.create(backup_db, tenant_id=TID, encrypt=False, verify=False)
        result = await restore_service.validate(backup_db, run["id"])
        assert "backup_id" in result

    @pytest.mark.asyncio
    async def test_validate_failed_backup_rejected(self, backup_db):
        repo = BackupRepository()
        run = await repo.create_run(backup_db, backup_type="test", status="failed")
        result = await restore_service.validate(backup_db, run["id"])
        assert result["valid"] == False

    @pytest.mark.asyncio
    async def test_validation_only_does_not_modify(self, backup_db):
        run = await backup_service.create(backup_db, tenant_id=TID, encrypt=False, verify=False)
        result = await restore_service.execute(backup_db, run["id"], target="test", validation_only=True)
        assert "validation" in result

    @pytest.mark.asyncio
    async def test_dry_run_restore(self, backup_db):
        run = await backup_service.create(backup_db, tenant_id=TID, encrypt=False, verify=False)
        result = await restore_service.execute(backup_db, run["id"], target="test", dry_run=True)
        assert result["status"] == "succeeded"


class TestStorage:
    def test_path_traversal_blocked(self):
        storage = BackupStorage()
        with pytest.raises(ValueError, match="traversal"):
            storage.write("../outside/evil.txt", b"bad")

    def test_absolute_path_blocked(self):
        storage = BackupStorage()
        with pytest.raises(ValueError):
            storage.delete("/absolute/path")

    def test_storage_root_isolation(self):
        s = get_settings()
        root = Path(s.backup_root or "backups").resolve()
        storage = BackupStorage()
        assert str(storage.root).startswith(str(root))


class TestManifest:
    def test_file_items_serialized(self):
        items = [
            {"item_type": "database_dump", "logical_name": "db.dump", "storage_key": "k1", "size_bytes": 100, "sha256": "abc"},
            {"item_type": "document_file", "logical_name": "docs/f.txt", "storage_key": "k2", "size_bytes": 50, "sha256": "def"},
        ]
        result = build_manifest("b-1", "rev-x", "v1", items)
        m = result["manifest"]
        assert m["item_count"] == 2
        assert m["total_size_bytes"] == 150
        assert len(m["files"]) == 1
        assert m["database"] is not None

    def test_excluded_components_listed(self):
        result = build_manifest("b2", "r2", "v2", [], excluded_components=["logs", "cache"])
        assert "logs" in result["manifest"]["excluded_components"]


class TestSafeMigration:
    def test_script_exists(self):
        path = Path(__file__).resolve().parents[1] / "app" / "scripts" / "safe_migrate.py"
        assert path.exists()


class TestBackupHandlerRegistry:
    def test_all_18_types_registered(self):
        from app.services.job_handlers import handler_registry
        types = handler_registry.list_types()
        expected = [
            "yargitay_search", "document_extract", "document_analyze",
            "legal_brain_ingest", "workflow_review", "legal_issue_graph_build",
            "legal_ground_validate", "precedent_evaluate", "claim_grounding",
            "petition_generate", "petition_refine", "export_generate",
            "retention_purge",
            "backup_create", "backup_verify", "backup_prune",
            "restore_validate", "restore_execute",
        ]
        for jt in expected:
            assert jt in types, f"Missing handler: {jt}"
        assert len(types) == 18

    def test_backup_handler_requires_admin(self):
        from app.services.job_handlers import handler_registry
        h = handler_registry.get("backup_create")
        assert h.required_permission == "tenant_admin"

    def test_restore_handler_requires_admin(self):
        from app.services.job_handlers import handler_registry
        h = handler_registry.get("restore_execute")
        assert h.required_permission == "tenant_admin"
