"""P1.9 — Backup service: create, verify, encrypt, prune backups."""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

VALID_BACKUP_STATUSES = frozenset({
    "pending", "preparing", "locked", "dumping_database", "collecting_files",
    "creating_manifest", "encrypting", "verifying",
    "succeeded", "failed", "cancelled", "expired", "deleted",
})

TERMINAL_BACKUP_STATUSES = frozenset({"succeeded", "failed", "cancelled", "expired", "deleted"})

BACKUP_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"preparing", "cancelled"},
    "preparing": {"locked", "failed", "cancelled"},
    "locked": {"dumping_database", "failed", "cancelled"},
    "dumping_database": {"collecting_files", "failed", "cancelled"},
    "collecting_files": {"creating_manifest", "failed", "cancelled"},
    "creating_manifest": {"encrypting", "verifying", "failed", "cancelled"},
    "encrypting": {"verifying", "failed", "cancelled"},
    "verifying": {"succeeded", "failed"},
    "succeeded": {"expired", "deleted"},
    "failed": {"deleted"},
    "cancelled": {"deleted"},
    "expired": {"deleted"},
    "deleted": set(),
}


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _safe_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:32]


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


class BackupRepository:
    @staticmethod
    async def create_run(db, **kwargs) -> dict:
        from app.db.models import BackupRun
        from sqlalchemy import select, text
        run_id = _new_id()
        kwargs.setdefault("started_at", datetime.now(UTC))
        run = BackupRun(id=run_id, **kwargs)
        db.add(run)
        await db.flush()
        return _run_to_dict(run)

    @staticmethod
    async def get_run(db, run_id: str) -> dict | None:
        from app.db.models import BackupRun
        from sqlalchemy import select
        r = await db.execute(select(BackupRun).where(BackupRun.id == run_id))
        row = r.scalar()
        return _run_to_dict(row) if row else None

    @staticmethod
    async def list_runs(db, status: str = "", limit: int = 50) -> list[dict]:
        from app.db.models import BackupRun
        from sqlalchemy import select
        q = select(BackupRun).where(BackupRun.deleted_at.is_(None)).order_by(BackupRun.created_at.desc()).limit(limit)
        if status:
            q = q.where(BackupRun.status == status)
        rows = await db.execute(q)
        return [_run_to_dict(r) for r in rows.scalars()]

    @staticmethod
    async def update_run(db, run_id: str, **fields) -> dict | None:
        from app.db.models import BackupRun
        from sqlalchemy import select
        r = await db.execute(select(BackupRun).where(BackupRun.id == run_id))
        row = r.scalar()
        if row is None:
            return None
        for k, v in fields.items():
            setattr(row, k, v)
        row.updated_at = datetime.now(UTC)
        await db.flush()
        return _run_to_dict(row)

    @staticmethod
    async def add_item(db, backup_run_id: str, item_type: str, logical_name: str,
                       storage_key: str, size_bytes: int = 0, sha256: str = "",
                       encrypted_sha256: str | None = None, status: str = "pending",
                       safe_metadata: dict | None = None) -> dict:
        from app.db.models import BackupItem
        item = BackupItem(
            id=_new_id(),
            backup_run_id=backup_run_id,
            item_type=item_type,
            logical_name=logical_name,
            storage_key=storage_key,
            size_bytes=size_bytes,
            sha256=sha256,
            encrypted_sha256=encrypted_sha256,
            status=status,
            safe_metadata=safe_metadata or {},
        )
        db.add(item)
        await db.flush()
        return _item_to_dict(item)

    @staticmethod
    async def get_items(db, backup_run_id: str) -> list[dict]:
        from app.db.models import BackupItem
        from sqlalchemy import select
        rows = await db.execute(
            select(BackupItem).where(BackupItem.backup_run_id == backup_run_id)
        )
        return [_item_to_dict(r) for r in rows.scalars()]


def _run_to_dict(r) -> dict:
    from app.db.models import BackupRun
    return {
        "id": r.id, "tenant_id": r.tenant_id, "backup_type": r.backup_type,
        "status": r.status, "scope": r.scope, "storage_backend": r.storage_backend,
        "started_at": _iso(r.started_at), "completed_at": _iso(r.completed_at),
        "created_by": r.created_by, "correlation_id": r.correlation_id,
        "schema_revision": r.schema_revision, "application_version": r.application_version,
        "encrypted": r.encrypted, "manifest_sha256": r.manifest_sha256,
        "total_size_bytes": r.total_size_bytes, "item_count": r.item_count,
        "warning_count": r.warning_count, "failure_count": r.failure_count,
        "safe_summary": r.safe_summary, "retention_until": _iso(r.retention_until),
        "deleted_at": _iso(r.deleted_at), "created_at": _iso(r.created_at),
    }


def _item_to_dict(i) -> dict:
    from app.db.models import BackupItem
    return {
        "id": i.id, "backup_run_id": i.backup_run_id, "item_type": i.item_type,
        "logical_name": i.logical_name, "storage_key": i.storage_key,
        "size_bytes": i.size_bytes, "sha256": i.sha256,
        "encrypted_sha256": i.encrypted_sha256, "status": i.status,
        "failure_code": i.failure_code, "safe_metadata": i.safe_metadata,
        "created_at": _iso(i.created_at),
    }
