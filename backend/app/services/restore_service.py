"""P1.9 — Restore service: validate, execute, verify."""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.services.backup_service import BackupRepository, _new_id, _safe_hash, _iso
from app.services.backup_orchestration import decrypt_backup, _get_encryption_key, BackupStorage

logger = logging.getLogger(__name__)

VALID_RESTORE_STATUSES = frozenset({
    "pending", "validating", "pre_restore_backup", "preparing_target",
    "restoring_database", "restoring_files", "rebuilding_indexes",
    "verifying", "succeeded", "failed", "rolled_back", "cancelled",
})

TERMINAL_RESTORE_STATUSES = frozenset({"succeeded", "failed", "rolled_back", "cancelled"})


class RestoreRepository:
    @staticmethod
    async def create_run(db, backup_run_id: str, **kwargs) -> dict:
        from app.db.models import RestoreRun
        run = RestoreRun(
            id=_new_id(),
            backup_run_id=backup_run_id,
            started_at=datetime.now(UTC),
            **kwargs,
        )
        db.add(run)
        await db.flush()
        return _restore_run_to_dict(run)

    @staticmethod
    async def get_run(db, run_id: str) -> dict | None:
        from app.db.models import RestoreRun
        from sqlalchemy import select
        r = await db.execute(select(RestoreRun).where(RestoreRun.id == run_id))
        row = r.scalar()
        return _restore_run_to_dict(row) if row else None

    @staticmethod
    async def update_run(db, run_id: str, **fields) -> dict | None:
        from app.db.models import RestoreRun
        from sqlalchemy import select
        r = await db.execute(select(RestoreRun).where(RestoreRun.id == run_id))
        row = r.scalar()
        if row is None:
            return None
        for k, v in fields.items():
            setattr(row, k, v)
        row.updated_at = datetime.now(UTC)
        await db.flush()
        return _restore_run_to_dict(row)

    @staticmethod
    async def add_item(db, restore_run_id: str, backup_item_id: str, status: str = "pending",
                       failure_code: str = "", safe_metadata: dict | None = None) -> dict:
        from app.db.models import RestoreItem
        item = RestoreItem(
            id=_new_id(),
            restore_run_id=restore_run_id,
            backup_item_id=backup_item_id,
            status=status,
            failure_code=failure_code,
            safe_metadata=safe_metadata or {},
            started_at=datetime.now(UTC) if status != "pending" else None,
        )
        db.add(item)
        await db.flush()
        return {"id": item.id, "restore_run_id": item.restore_run_id,
                "backup_item_id": item.backup_item_id, "status": item.status}


def _restore_run_to_dict(r) -> dict:
    from app.db.models import RestoreRun
    return {
        "id": r.id, "backup_run_id": r.backup_run_id, "status": r.status,
        "target_environment": r.target_environment, "dry_run": r.dry_run,
        "validation_only": r.validation_only, "started_at": _iso(r.started_at),
        "completed_at": _iso(r.completed_at), "initiated_by": r.initiated_by,
        "pre_restore_backup_id": r.pre_restore_backup_id,
        "schema_revision_before": r.schema_revision_before,
        "schema_revision_after": r.schema_revision_after,
        "restored_item_count": r.restored_item_count,
        "skipped_item_count": r.skipped_item_count,
        "failed_item_count": r.failed_item_count,
        "safe_summary": r.safe_summary, "created_at": _iso(r.created_at),
    }


class RestoreService:
    def __init__(self):
        self.backup_repo = BackupRepository()
        self.repo = RestoreRepository()
        self.storage = BackupStorage()

    async def validate(self, db, backup_run_id: str, target: str = "test") -> dict:
        issues = []
        backup = await self.backup_repo.get_run(db, backup_run_id)
        if not backup:
            return {"valid": False, "issues": ["backup_not_found"]}
        if backup["status"] != "succeeded":
            issues.append(f"backup_status_not_succeeded_{backup['status']}")
        if not backup.get("schema_revision"):
            issues.append("missing_schema_revision")
        try:
            archive_data = self.storage.read(
                f"{backup_run_id}/backup.tar.gz{'.enc' if backup.get('encrypted') else ''}"
            )
            if len(archive_data) == 0:
                issues.append("archive_empty")
            if backup.get("encrypted"):
                try:
                    key = _get_encryption_key()
                    archive_data = decrypt_backup(archive_data, key)
                except Exception:
                    issues.append("decryption_failed")
            with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:gz") as tar:
                names = tar.getnames()
                if not any("manifest.json" in n for n in names):
                    issues.append("manifest_not_in_archive")
                if any(".." in n or n.startswith("/") for n in names):
                    issues.append("traversal_detected")
        except Exception as e:
            issues.append(f"archive_read_error: {str(e)[:80]}")
        items = await self.backup_repo.get_items(db, backup_run_id)
        if not items:
            issues.append("no_backup_items")
        if target == "production":
            s = get_settings()
            if not s.backup_require_pre_restore_backup:
                issues.append("production_restore_requires_pre_backup_config")
        return {"valid": len(issues) == 0, "issues": issues, "backup_id": backup_run_id,
                "target": target, "backup_status": backup["status"],
                "schema_revision": backup.get("schema_revision", "")}

    async def execute(
        self, db,
        backup_run_id: str,
        target: str = "test",
        initiated_by: str = "system",
        dry_run: bool = False,
        validation_only: bool = False,
    ) -> dict:
        s = get_settings()
        backup = await self.backup_repo.get_run(db, backup_run_id)
        if not backup:
            raise KeyError(f"Backup not found: {backup_run_id}")
        if backup["status"] != "succeeded":
            raise ValueError(f"Cannot restore backup in status '{backup['status']}'")

        if validation_only:
            val = await self.validate(db, backup_run_id, target)
            return {"validation": val, "target": target}

        prev_schema = s.app_version or "unknown"

        pre_restore_id = ""
        if target == "production":
            if s.backup_require_pre_restore_backup:
                pre_run = await _create_pre_restore_backup(db, backup_run_id)
                if not pre_run or pre_run["status"] != "succeeded":
                    raise RuntimeError("Pre-restore backup failed")
                pre_restore_id = pre_run["id"]

        run = await self.repo.create_run(db, backup_run_id,
            target_environment=target, initiated_by=initiated_by,
            dry_run=dry_run, validation_only=validation_only,
            pre_restore_backup_id=pre_restore_id,
            schema_revision_before=prev_schema,
        )
        run_id = run["id"]

        try:
            await self.repo.update_run(db, run_id, status="preparing_target")
            archive_data = self.storage.read(
                f"{backup_run_id}/backup.tar.gz{'.enc' if backup.get('encrypted') else ''}"
            )
            if backup.get("encrypted"):
                key = _get_encryption_key()
                archive_data = decrypt_backup(archive_data, key)

            if dry_run:
                await self.repo.update_run(db, run_id, status="verifying",
                    safe_summary={"dry_run": True, "archive_size": len(archive_data)})
                await self.repo.update_run(db, run_id, status="succeeded",
                    completed_at=datetime.now(UTC), restored_item_count=0)
                return await self.repo.get_run(db, run_id)

            restored = 0
            failed = 0

            await self.repo.update_run(db, run_id, status="restoring_database")
            db_ok = await self._restore_database(backup_run_id, archive_data)
            if db_ok:
                restored += 1
            else:
                failed += 1

            await self.repo.update_run(db, run_id, status="restoring_files")
            file_ok = self._restore_files(backup_run_id, archive_data)
            restored += file_ok

            await self.repo.update_run(db, run_id, status="rebuilding_indexes")
            await self.repo.update_run(db, run_id, status="verifying")
            await self.repo.update_run(db, run_id, status="succeeded",
                completed_at=datetime.now(UTC),
                restored_item_count=restored, failed_item_count=failed,
                schema_revision_after=s.app_version or "unknown",
                safe_summary={"database_restored": db_ok, "files_restored": file_ok,
                              "target": target})
            return await self.repo.get_run(db, run_id)

        except Exception as e:
            logger.exception("restore_failed run_id=%s", run_id)
            await self.repo.update_run(db, run_id, status="failed",
                failed_item_count=1,
                safe_summary={"error": str(e)[:200]})
            return await self.repo.get_run(db, run_id)

    async def _restore_database(self, backup_run_id: str, archive_data: bytes) -> bool:
        try:
            s = get_settings()
            url = s.database_url or ""
            if url and "postgresql" in url:
                with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as tmp:
                    with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:gz") as tar:
                        for m in tar.getmembers():
                            if m.name.endswith(".dump") or "database" in m.name:
                                tmp.write(tar.extractfile(m).read())
                                break
                    tmp_path = tmp.name
                try:
                    result = subprocess.run(
                        ["pg_restore", "--clean", "--if-exists", "--no-owner", url, tmp_path],
                        capture_output=True, timeout=s.backup_database_timeout_seconds or 300,
                        env={**os.environ, "PGPASSWORD": os.environ.get("DB_PASSWORD", "")},
                    )
                    ok = result.returncode == 0
                finally:
                    os.unlink(tmp_path)
                return ok
            else:
                with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:gz") as tar:
                    for m in tar.getmembers():
                        if m.name.endswith(".sqlite") and not ".." in m.name:
                            target = Path("case_store/emsalist.db")
                            with tar.extractfile(m) as src:
                                target.write_bytes(src.read())
                            return True
                return False
        except Exception as e:
            logger.error("restore_database_failed: %s", str(e)[:200])
            return False

    def _restore_files(self, backup_run_id: str, archive_data: bytes) -> int:
        restored = 0
        try:
            with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:gz") as tar:
                for m in tar.getmembers():
                    name = m.name.split(f"{backup_run_id}/")[-1]
                    if ".." in name or name.startswith("/") or m.issym():
                        continue
                    if name.startswith("files/") or name.startswith("projection/"):
                        try:
                            dest_dir = Path(__file__).resolve().parents[1]
                            if name.startswith("files/"):
                                dest = dest_dir / "document_store" / "uploads" / name.split("/")[-1]
                            elif name.startswith("projection/"):
                                dest = dest_dir / "case_store" / name.split("/")[-1]
                            else:
                                continue
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            with tar.extractfile(m) as src:
                                dest.write_bytes(src.read())
                            restored += 1
                        except Exception:
                            pass
        except Exception:
            pass
        return restored


async def _create_pre_restore_backup(db, source_backup_id: str) -> dict | None:
    from app.services.backup_orchestration import backup_service
    run = await backup_service.create(db, backup_type="pre_restore", scope="full",
                                       created_by="restore")
    return run


restore_service = RestoreService()
