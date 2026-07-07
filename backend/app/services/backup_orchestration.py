"""P1.9 — Backup orchestration, storage, encryption, manifest, verification."""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import struct
import subprocess
import tarfile
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.engine import make_url

from app.config import get_settings
from app.services.backup_service import (
    BackupRepository, _new_id, _safe_hash, _iso,
    VALID_BACKUP_STATUSES, TERMINAL_BACKUP_STATUSES, BACKUP_STATUS_TRANSITIONS,
)
import logging

logger = logging.getLogger(__name__)

# ── Manifest ──
MANIFEST_FORMAT_VERSION = "1.0"


def build_manifest(
    backup_id: str,
    schema_revision: str,
    app_version: str,
    items: list[dict],
    encryption_data: dict | None = None,
    warnings: list[str] | None = None,
    excluded_components: list[str] | None = None,
) -> dict:
    now = datetime.now(UTC).isoformat()
    file_items = [
        {"logical_name": i["logical_name"], "storage_key": i["storage_key"],
         "item_type": i["item_type"], "size_bytes": i.get("size_bytes", 0),
         "sha256": i.get("sha256", "")}
        for i in items if i.get("item_type") != "database_dump"
    ]
    db_item = next((i for i in items if i.get("item_type") == "database_dump"), None)
    payload = {
        "format_version": MANIFEST_FORMAT_VERSION,
        "backup_id": backup_id,
        "created_at": now,
        "application_version": app_version,
        "schema_revision": schema_revision,
        "database": db_item,
        "files": file_items,
        "item_count": len(items),
        "total_size_bytes": sum(i.get("size_bytes", 0) for i in items),
        "encryption": encryption_data or {},
        "excluded_components": excluded_components or [],
        "required_restore_order": ["database_dump", "documents", "json_projection"],
        "warnings": warnings or [],
    }
    payload_bytes = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return {"manifest": payload, "manifest_sha256": _safe_hash(payload_bytes)}


# ── Encryption ──
def encrypt_backup(plaintext: bytes, key: bytes) -> tuple[bytes, bytes]:
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ciphertext, nonce


def decrypt_backup(ciphertext_with_nonce: bytes, key: bytes) -> bytes:
    nonce = ciphertext_with_nonce[:12]
    ciphertext = ciphertext_with_nonce[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


def _get_encryption_key() -> bytes:
    s = get_settings()
    raw = s.backup_encryption_key or ""
    if not raw:
        raise ValueError("BACKUP_ENCRYPTION_KEY not configured")
    key = raw.encode("utf-8")
    if len(key) < 32:
        key = hashlib.sha256(key).digest()
    return key[:32]


# ── Lock Manager ──
class BackupLockManager:
    @staticmethod
    async def acquire(db, lock_name: str, owner_hash: str, lease_seconds: int = 300) -> bool:
        from app.db.models import BackupLock
        from sqlalchemy import select, delete
        now = datetime.now(UTC)
        try:
            await db.execute(delete(BackupLock).where(
                BackupLock.lock_name == lock_name,
                BackupLock.lease_expires_at < now,
                BackupLock.released_at.is_(None),
            ))
            await db.flush()
        except Exception:
            await db.rollback()
        existing = await db.execute(
            select(BackupLock).where(
                BackupLock.lock_name == lock_name,
                BackupLock.released_at.is_(None),
            ).limit(1)
        )
        if existing.scalar() is not None:
            return False
        try:
            lock = BackupLock(
                id=_new_id(), lock_name=lock_name, owner_id_hash=owner_hash,
                acquired_at=now, lease_expires_at=now + timedelta(seconds=lease_seconds),
            )
            db.add(lock)
            await db.flush()
            return True
        except Exception:
            await db.rollback()
            return False

    @staticmethod
    async def release(db, lock_name: str, owner_hash: str) -> bool:
        from app.db.models import BackupLock
        from sqlalchemy import select
        row = await db.execute(
            select(BackupLock).where(
                BackupLock.lock_name == lock_name,
                BackupLock.owner_id_hash == owner_hash,
                BackupLock.released_at.is_(None),
            ).limit(1)
        )
        lock = row.scalar()
        if lock:
            lock.released_at = datetime.now(UTC)
            await db.flush()
            return True
        return False

    @staticmethod
    async def heartbeat(db, lock_name: str, owner_hash: str, lease_seconds: int = 300) -> bool:
        from app.db.models import BackupLock
        from sqlalchemy import select
        row = await db.execute(
            select(BackupLock).where(
                BackupLock.lock_name == lock_name,
                BackupLock.owner_id_hash == owner_hash,
                BackupLock.released_at.is_(None),
            ).limit(1)
        )
        lock = row.scalar()
        if lock:
            lock.lease_expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds)
            await db.flush()
            return True
        return False


# ── Storage ──
class BackupStorage:
    def __init__(self, base_dir: str | None = None):
        s = get_settings()
        self._base = Path(base_dir or s.backup_root or "backups").resolve()

    @property
    def root(self) -> Path:
        self._base.mkdir(parents=True, exist_ok=True)
        return self._base

    def _safe_path(self, rel_path: str) -> Path:
        p = (self.root / rel_path).resolve()
        if not str(p).startswith(str(self.root)) or ".." in rel_path:
            raise ValueError("Backup path traversal blocked")
        return p

    def write(self, rel_path: str, data: bytes) -> int:
        p = self._safe_path(rel_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return len(data)

    def read(self, rel_path: str) -> bytes:
        p = self._safe_path(rel_path)
        if not p.exists():
            raise FileNotFoundError(rel_path)
        return p.read_bytes()

    def delete(self, rel_path: str) -> bool:
        p = self._safe_path(rel_path)
        if p.exists():
            p.unlink()
            return True
        return False

    def list_archives(self) -> list[Path]:
        return sorted(self.root.glob("*.tar.gz"))


# ── Backup Service ──
class BackupService:
    def __init__(self):
        self.repo = BackupRepository()
        self.storage = BackupStorage()
        self.locks = BackupLockManager()
        self._owner_hash = uuid.uuid4().hex[:16]

    async def create(
        self, db,
        tenant_id: str = "",
        backup_type: str = "auto",
        scope: str = "full",
        created_by: str = "system",
        encrypt: bool | None = None,
        verify: bool | None = None,
    ) -> dict:
        s = get_settings()
        should_encrypt = encrypt if encrypt is not None else s.backup_encryption_enabled
        should_verify = verify if verify is not None else s.backup_verify_after_create

        run = await self.repo.create_run(db,
            tenant_id=tenant_id or None,
            backup_type=backup_type,
            scope=scope,
            status="preparing",
            storage_backend="local",
            created_by=created_by,
            correlation_id=uuid.uuid4().hex[:16],
            schema_revision=self._get_schema_revision(),
            application_version=s.app_version or "0.1.0",
            encrypted=should_encrypt,
        )
        run_id = run["id"]

        try:
            lock_name = "backup_create"
            if not await self.locks.acquire(db, lock_name, self._owner_hash):
                return await self.repo.update_run(db, run_id, status="failed",
                    safe_summary={"error": "Another backup is in progress"})

            await self.repo.update_run(db, run_id, status="preparing")

            await self.repo.update_run(db, run_id, status="dumping_database")
            db_info = await self._dump_database(db, run_id)

            await self.repo.update_run(db, run_id, status="collecting_files")
            file_items = self._collect_files(run_id)

            all_items = ([db_info] if db_info else []) + file_items
            await self.repo.update_run(db, run_id, status="creating_manifest",
                item_count=len(all_items),
                total_size_bytes=sum(i.get("size_bytes", 0) for i in all_items))

            manifest_result = build_manifest(
                run_id, run["schema_revision"], run["application_version"],
                all_items,
                encryption_data={"algorithm": "AES-256-GCM"} if should_encrypt else None,
                excluded_components=["logs", "cache", "rebuilt_indexes"],
            )
            manifest_data = manifest_result["manifest"]
            manifest_sha = manifest_result["manifest_sha256"]

            self.storage.write(f"{run_id}/manifest.json",
                              json.dumps(manifest_data, indent=2, ensure_ascii=False).encode("utf-8"))

            archive_path = self._build_archive(run_id, all_items, manifest_data)
            archive_data = Path(archive_path).read_bytes()
            archive_sha = _safe_hash(archive_data)

            encryption_meta = {}
            final_size = len(archive_data)
            manifest_entry = {
                "item_type": "manifest", "logical_name": "manifest.json",
                "storage_key": f"{run_id}/manifest.json", "size_bytes": 0, "sha256": manifest_sha,
            }
            await self.repo.add_item(db, run_id, "manifest", "manifest.json",
                                     f"{run_id}/manifest.json", sha256=manifest_sha, status="collected")

            if should_encrypt:
                await self.repo.update_run(db, run_id, status="encrypting")
                try:
                    key = _get_encryption_key()
                    encrypted, nonce = encrypt_backup(archive_data, key)
                    enc_sha = _safe_hash(encrypted)
                    rel_path = f"{run_id}/backup.tar.gz.enc"
                    self.storage.write(rel_path, encrypted)
                    os.remove(archive_path)  # remove plaintext archive
                    archive_path = str(self.storage._safe_path(rel_path))
                    final_size = len(encrypted)
                    encryption_meta = {"nonce_hex": nonce.hex(), "encrypted_sha256": enc_sha}
                except Exception as e:
                    await self.repo.update_run(db, run_id, status="failed",
                        safe_summary={"error": f"encryption_failed: {str(e)[:80]}"})
                    await self.locks.release(db, lock_name, self._owner_hash)
                    return await self.repo.get_run(db, run_id)
            else:
                rel_path = f"{run_id}/backup.tar.gz"
                self.storage.write(rel_path, archive_data)
                archive_path = str(self.storage._safe_path(rel_path))

            archive_storage_key = f"{run_id}/backup.tar.gz" + (".enc" if should_encrypt else "")
            await self.repo.add_item(db, run_id, "archive", "backup.tar.gz" + (".enc" if should_encrypt else ""),
                                     archive_storage_key, size_bytes=final_size,
                                     sha256=encryption_meta.get("encrypted_sha256", archive_sha),
                                     status="collected", safe_metadata=encryption_meta)

            await self.repo.update_run(db, run_id, status="verifying",
                manifest_sha256=manifest_sha,
                total_size_bytes=final_size,
                item_count=len(all_items) + 1,
                safe_summary={"db_item_present": db_info is not None,
                              "file_items": len(file_items),
                              "encryption": encryption_meta})

            if should_verify:
                verify_result = await self._verify_backup_and_record(db, run_id)
                if not verify_result["valid"]:
                    verrors = verify_result.get("issues", ["unknown"])
                    await self.repo.update_run(db, run_id, status="failed",
                        failure_count=len(verrors),
                        safe_summary={"error": f"verification_failed", "issues": verrors[:5]})
                    await self.locks.release(db, lock_name, self._owner_hash)
                    return await self.repo.get_run(db, run_id)

            retention = s.backup_retention_days or 30
            await self.repo.update_run(db, run_id, status="succeeded",
                completed_at=datetime.now(UTC),
                retention_until=datetime.now(UTC) + timedelta(days=retention))

            try:
                from app.core.metrics import record_backup
                from app.core.degraded_state import update_component_state, ComponentStatus
                record_backup("succeeded", final_size)
                update_component_state("backup", ComponentStatus.HEALTHY)
            except Exception:
                pass

            await self.locks.release(db, lock_name, self._owner_hash)
            return await self.repo.get_run(db, run_id)

        except Exception as e:
            logger.exception("backup_failed run_id=%s", run_id)
            try:
                await self.locks.release(db, "backup_create", self._owner_hash)
            except Exception:
                pass
            await self.repo.update_run(db, run_id, status="failed",
                failure_count=1,
                safe_summary={"error": str(e)[:200]})

            try:
                from app.core.metrics import record_backup
                from app.core.degraded_state import update_component_state, ComponentStatus
                record_backup("failed")
                update_component_state("backup", ComponentStatus.DEGRADED, error_code="backup_failed")
            except Exception:
                pass

            return await self.repo.get_run(db, run_id)

    async def verify(self, db, backup_run_id: str) -> dict:
        run = await self.repo.get_run(db, backup_run_id)
        if not run:
            raise KeyError(f"Backup not found: {backup_run_id}")
        return await self._verify_backup_and_record(db, backup_run_id)

    async def prune(self, db, dry_run: bool = True) -> dict:
        runs = await self.repo.list_runs(db, status="succeeded", limit=200)
        now = datetime.now(UTC)
        pruned = []
        skipped = []
        for run in runs:
            rt = run.get("retention_until")
            if rt:
                try:
                    rt_date = datetime.fromisoformat(rt)
                    if rt_date > now:
                        skipped.append(run["id"])
                        continue
                except (ValueError, TypeError):
                    pass
            if not dry_run:
                try:
                    self.storage.delete(f"{run['id']}/backup.tar.gz")
                    self.storage.delete(f"{run['id']}/backup.tar.gz.enc")
                    self.storage.delete(f"{run['id']}/manifest.json")
                except Exception:
                    pass
                await self.repo.update_run(db, run["id"], status="deleted", deleted_at=now)
            pruned.append(run["id"])
        return {"dry_run": dry_run, "pruned": len(pruned), "skipped": len(skipped),
                "pruned_ids": pruned[:10], "skipped_ids": skipped[:10]}

    # ── internal ──

    async def _dump_database(self, db, run_id: str) -> dict | None:
        s = get_settings()
        url = s.database_url or ""
        if url and "postgresql" in url:
            return await self._pg_dump(run_id)
        db_path = (Path(__file__).resolve().parents[1] / "case_store" / "emsalist.db")
        if db_path.exists():
            tmp_parent = Path(tempfile.mkdtemp(prefix="backup-sqlite-"))
            tmp_path = tmp_parent / "db.sqlite"
            shutil.copy2(str(db_path), str(tmp_path))
            data = tmp_path.read_bytes()
            sha = _safe_hash(data)
            rel = f"{run_id}/database.sqlite"
            self.storage.write(rel, data)
            shutil.rmtree(str(tmp_parent), ignore_errors=True)
            return {
                "item_type": "database_dump", "logical_name": "database.sqlite",
                "storage_key": rel, "size_bytes": len(data), "sha256": sha,
                "status": "collected", "safe_metadata": {"engine": "sqlite", "method": "file_copy"},
            }
        return None

    async def _pg_dump(self, run_id: str) -> dict | None:
        try:
            s = get_settings()
            parsed = make_url(s.database_url)
            parsed = parsed.set(drivername="postgresql")
            dbname = parsed.render_as_string(hide_password=False)
            result = subprocess.run(
                ["pg_dump", f"--dbname={dbname}", "--format=custom", "--no-owner", "--no-privileges"],
                capture_output=True, timeout=s.backup_database_timeout_seconds or 300,
            )
            if result.returncode != 0:
                logger.error("pg_dump_failed rc=%d stderr=%s", result.returncode, result.stderr.decode()[:200])
                return None
            data = result.stdout
            sha = _safe_hash(data)
            rel = f"{run_id}/database.dump"
            self.storage.write(rel, data)
            return {
                "item_type": "database_dump", "logical_name": "database.dump",
                "storage_key": rel, "size_bytes": len(data), "sha256": sha,
                "status": "collected", "safe_metadata": {"engine": "postgresql", "method": "pg_dump_custom"},
            }
        except FileNotFoundError:
            logger.warning("pg_dump not available")
            return None
        except Exception as e:
            logger.error("pg_dump error: %s", str(e)[:200])
            return None

    def _collect_files(self, run_id: str) -> list[dict]:
        items = []
        doc_dir = Path(__file__).resolve().parents[1] / "document_store" / "uploads"
        if doc_dir.exists():
            for f in doc_dir.glob("*"):
                if f.is_file() and not f.name.startswith("."):
                    try:
                        data = f.read_bytes()
                        rel = f"{run_id}/files/{f.name}"
                        self.storage.write(rel, data)
                        items.append({
                            "item_type": "document_file", "logical_name": f"docs/{f.name}",
                            "storage_key": rel, "size_bytes": len(data),
                            "sha256": _safe_hash(data), "status": "collected",
                        })
                    except OSError:
                        logger.warning("skipping file during backup collection: %s", f.name)
                    except Exception:
                        pass
        case_dir = Path(__file__).resolve().parents[1] / "case_store"
        if (case_dir / "sessions.json").exists():
            try:
                data = (case_dir / "sessions.json").read_bytes()
                rel = f"{run_id}/files/sessions.json"
                self.storage.write(rel, data)
                items.append({
                    "item_type": "json_projection", "logical_name": "projection/sessions.json",
                    "storage_key": rel, "size_bytes": len(data),
                    "sha256": _safe_hash(data), "status": "collected",
                })
            except OSError:
                logger.warning("skipping sessions.json during backup collection")
        return items

    def _build_archive(self, run_id: str, items: list[dict], manifest_data: dict) -> str:
        archive_path = str(self.storage._safe_path(f"{run_id}/backup.tar.gz"))
        with tarfile.open(archive_path, "w:gz") as tar:
            manifest_bytes = json.dumps(manifest_data, indent=2).encode("utf-8")
            info = tarfile.TarInfo(name=f"{run_id}/manifest.json")
            info.size = len(manifest_bytes)
            tar.addfile(info, io.BytesIO(manifest_bytes))

            for item in items:
                sk = item.get("storage_key", "")
                if not sk or ".." in sk or sk.startswith("/"):
                    continue
                src = self.storage._safe_path(sk)
                if src.exists():
                    tar.add(str(src), arcname=sk.split(f"{run_id}/")[-1])
        return archive_path

    async def _verify_backup(self, db, backup_run_id: str) -> dict:
        issues = []
        run = await self.repo.get_run(db, backup_run_id)
        if not run:
            return {"valid": False, "issues": ["run_not_found"]}
        run_id = run["id"]

        suffix = ".enc" if run.get("encrypted") else ""
        archive_rel = f"{run_id}/backup.tar.gz{suffix}"
        try:
            archive_data = self.storage.read(archive_rel)
        except FileNotFoundError:
            return {"valid": False, "issues": ["archive_not_found"]}

        if len(archive_data) == 0:
            return {"valid": False, "issues": ["archive_empty"]}

        if run.get("encrypted"):
            try:
                key = _get_encryption_key()
                archive_data = decrypt_backup(archive_data, key)
            except Exception:
                return {"valid": False, "issues": ["decryption_failed"]}

        archive_sha = _safe_hash(archive_data)

        try:
            with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:gz") as tar:
                names = tar.getnames()
                for m in tar.getmembers():
                    if ".." in m.name or m.name.startswith("/"):
                        issues.append("traversal_entry_detected")
                    if m.issym():
                        issues.append("symlink_blocked")
        except Exception as e:
            return {"valid": False, "issues": [f"archive_invalid: {str(e)[:100]}"]}

        items = await self.repo.get_items(db, backup_run_id)

        has_db = any(i["item_type"] == "database_dump" and i["sha256"] for i in items)
        if not has_db:
            issues.append("no_database_dump")

        has_manifest = any(i["item_type"] == "manifest" for i in items)
        if not has_manifest:
            issues.append("no_manifest")

        return {"valid": len(issues) == 0, "issues": issues, "archive_sha256": archive_sha,
                "item_count": len(items), "has_database": has_db, "has_manifest": has_manifest,
                "archive_size": len(archive_data)}

    async def _verify_backup_and_record(self, db, backup_run_id: str) -> dict:
        result = await self._verify_backup(db, backup_run_id)
        try:
            from app.core.metrics import record_backup_verify
            record_backup_verify("succeeded" if result["valid"] else "failed")
        except Exception:
            pass
        return result

    @staticmethod
    def _get_schema_revision() -> str:
        try:
            from alembic.script import ScriptDirectory
            from alembic.config import Config
            alc = Config()
            alc.set_main_option("script_location", "app/db/migrations")
            script = ScriptDirectory.from_config(alc)
            return script.get_current_head() or "unknown"
        except Exception:
            return "unknown"


backup_service = BackupService()
