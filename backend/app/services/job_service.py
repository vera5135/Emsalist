"""P1.8 — Durable background job service with queue, handlers, progress, and lifecycle."""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BackgroundJob, BackgroundJobAttempt, BackgroundJobEvent, BackgroundJobArtifact, new_uuid
from app.db.session import get_sessionmaker

logger = logging.getLogger(__name__)

VALID_STATUSES = frozenset({
    "queued", "scheduled", "claimed", "running", "retry_wait",
    "cancellation_requested", "cancelled", "succeeded", "failed",
    "timed_out", "dead_lettered",
})

TERMINAL_STATUSES = frozenset({"succeeded", "cancelled", "dead_lettered"})

STATUS_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"claimed", "cancelled"},
    "scheduled": {"queued", "claimed", "cancelled"},
    "claimed": {"running", "timed_out"},
    "running": {"succeeded", "failed", "retry_wait", "cancellation_requested", "timed_out"},
    "retry_wait": {"queued", "dead_lettered"},
    "cancellation_requested": {"cancelled"},
    "cancelled": set(),
    "succeeded": set(),
    "failed": {"queued", "dead_lettered"},
    "timed_out": {"retry_wait", "dead_lettered", "queued"},
    "dead_lettered": {"queued"},
}

KNOWN_JOB_TYPES = frozenset({
    "yargitay_search", "document_extract", "document_analyze",
    "legal_brain_ingest", "workflow_review", "legal_issue_graph_build",
    "legal_ground_validate", "precedent_evaluate", "claim_grounding",
    "petition_generate", "petition_refine", "export_generate",
    "retention_purge",
    "backup_create", "backup_verify", "backup_prune",
    "restore_validate", "restore_execute",
})

RETRYABLE_CODES = frozenset({
    "NETWORK_ERROR", "PROVIDER_TIMEOUT", "GATEWAY_TIMEOUT",
    "RATE_LIMITED", "DB_TEMP_ERROR", "LEASE_LOST", "WORKER_RESTART",
})

NON_RETRYABLE_CODES = frozenset({
    "VALIDATION_ERROR", "AUTHORIZATION_ERROR", "CASE_DELETED",
    "CASE_PURGED", "LEGAL_HOLD_ACTIVE", "INVALID_DOCUMENT",
    "POLICY_VIOLATION", "UNSUPPORTED_TYPE", "BUSINESS_RULE",
})


def _canonical_status_transition(current: str, target: str) -> bool:
    if current not in STATUS_TRANSITIONS:
        return False
    return target in STATUS_TRANSITIONS[current]


def _compute_idempotency_key(tenant_id: str, case_id: str | None, job_type: str, payload_fingerprint: str) -> str:
    parts = [tenant_id, case_id or "", job_type, payload_fingerprint]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


def _safe_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ── Repository ──


class JobRepository:
    @staticmethod
    async def create_job(
        db: AsyncSession,
        tenant_id: str,
        job_type: str,
        payload: dict,
        case_id: str | None = None,
        created_by: str = "system",
        priority: int = 0,
        max_attempts: int = 3,
        timeout_seconds: int = 300,
        correlation_id: str = "",
        request_id: str = "",
    ) -> dict:
        phash = _safe_hash(payload)
        idem_key = _compute_idempotency_key(tenant_id, case_id, job_type, phash)
        existing = await db.execute(
            select(BackgroundJob).where(
                BackgroundJob.tenant_id == tenant_id,
                BackgroundJob.idempotency_key == idem_key,
                BackgroundJob.status.notin_(TERMINAL_STATUSES),
            ).limit(1)
        )
        row = existing.scalar()
        if row is not None:
            return _job_to_dict(row)

        job = BackgroundJob(
            id=new_uuid(),
            tenant_id=tenant_id,
            case_id=case_id,
            created_by=created_by,
            job_type=job_type,
            status="queued",
            priority=priority,
            idempotency_key=idem_key,
            payload_json=payload,
            safe_payload_hash=phash,
            max_attempts=max_attempts,
            timeout_seconds=timeout_seconds,
            correlation_id=correlation_id,
            request_id=request_id,
        )
        db.add(job)
        await db.flush()
        await db.commit()

        if job_type in KNOWN_JOB_TYPES:
            from app.core.metrics import record_job_enqueued, record_job_pending
            record_job_enqueued(job_type)
            record_job_pending(job_type, 1)

        return _job_to_dict(job)

    @staticmethod
    async def get_job(db: AsyncSession, tenant_id: str, job_id: str) -> dict | None:
        result = await db.execute(
            select(BackgroundJob).where(
                BackgroundJob.id == job_id,
                BackgroundJob.tenant_id == tenant_id,
            ).limit(1)
        )
        row = result.scalar()
        return _job_to_dict(row) if row else None

    @staticmethod
    async def list_jobs(
        db: AsyncSession,
        tenant_id: str,
        case_id: str = "",
        status: str = "",
        job_type: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        query = select(BackgroundJob).where(BackgroundJob.tenant_id == tenant_id)
        if case_id:
            query = query.where(BackgroundJob.case_id == case_id)
        if status:
            query = query.where(BackgroundJob.status == status)
        if job_type:
            query = query.where(BackgroundJob.job_type == job_type)
        query = query.order_by(BackgroundJob.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(query)
        return [_job_to_dict(r) for r in result.scalars()]

    @staticmethod
    async def update_status(
        db: AsyncSession,
        job_id: str,
        new_status: str,
        current_status: str | None = None,
        **fields,
    ) -> dict | None:
        stmt = select(BackgroundJob).where(BackgroundJob.id == job_id)
        if current_status:
            stmt = stmt.where(BackgroundJob.status == current_status)
        result = await db.execute(stmt.limit(1))
        job = result.scalar()
        if job is None:
            return None
        if not _canonical_status_transition(job.status, new_status):
            return None
        job.status = new_status
        job.updated_at = datetime.now(UTC)
        for key, value in fields.items():
            setattr(job, key, value)
        await db.flush()
        await db.commit()
        return _job_to_dict(job)

    @staticmethod
    async def claim_job(
        db: AsyncSession,
        worker_id_hash: str,
        lease_seconds: int = 60,
        job_types: list[str] | None = None,
    ) -> dict | None:
        stmt = select(BackgroundJob).where(
            BackgroundJob.status.in_(["queued", "scheduled"]),
            BackgroundJob.scheduled_at <= datetime.now(UTC),
        ).order_by(BackgroundJob.priority.desc(), BackgroundJob.created_at).limit(1)

        if job_types:
            stmt = stmt.where(BackgroundJob.job_type.in_(job_types))

        result = await db.execute(stmt)
        job = result.scalar()
        if job is None:
            return None

        now = datetime.now(UTC)
        job.status = "claimed"
        job.worker_id_hash = worker_id_hash
        job.lease_expires_at = now + timedelta(seconds=lease_seconds)
        job.updated_at = now
        job.version = (job.version or 0) + 1
        await db.flush()
        await db.commit()
        return _job_to_dict(job)

    @staticmethod
    async def recover_expired_leases(db: AsyncSession, lease_seconds: int = 60) -> int:
        now = datetime.now(UTC)
        result = await db.execute(
            select(BackgroundJob.id).where(
                BackgroundJob.status.in_(["claimed", "running"]),
                BackgroundJob.lease_expires_at < now,
            )
        )
        expired = result.scalars().all()
        count = 0
        for job_id in expired:
            await db.execute(
                update(BackgroundJob)
                .where(BackgroundJob.id == job_id)
                .values(status="queued", worker_id_hash=None, lease_expires_at=None, updated_at=now)
            )
            count += 1
        if count:
            await db.commit()
        return count

    @staticmethod
    async def list_events(
        db: AsyncSession, tenant_id: str, job_id: str, since_seq: int = 0
    ) -> list[dict]:
        result = await db.execute(
            select(BackgroundJobEvent).where(
                BackgroundJobEvent.job_id == job_id,
                BackgroundJobEvent.sequence_number > since_seq,
            ).order_by(BackgroundJobEvent.sequence_number)
        )
        return [_event_to_dict(r) for r in result.scalars()]

    @staticmethod
    async def add_event(
        db: AsyncSession, job_id: str, event_type: str, progress: int | None = None,
        stage: str | None = None, message: str | None = None, metadata: dict | None = None,
    ) -> dict:
        seq_result = await db.execute(
            select(func.coalesce(func.max(BackgroundJobEvent.sequence_number), 0))
            .where(BackgroundJobEvent.job_id == job_id)
        )
        seq = (seq_result.scalar() or 0) + 1
        event = BackgroundJobEvent(
            id=new_uuid(),
            job_id=job_id,
            sequence_number=seq,
            event_type=event_type,
            progress_percent=progress,
            stage=stage,
            safe_message=_truncate(message, 500) if message else None,
            safe_metadata=metadata or {},
        )
        db.add(event)
        await db.flush()
        return _event_to_dict(event)

    @staticmethod
    async def add_attempt(
        db: AsyncSession, job_id: str, attempt_number: int, worker_id_hash: str,
        status: str = "started",
    ) -> dict:
        attempt = BackgroundJobAttempt(
            id=new_uuid(),
            job_id=job_id,
            attempt_number=attempt_number,
            status=status,
            worker_id_hash=worker_id_hash,
        )
        db.add(attempt)
        await db.flush()
        return _attempt_to_dict(attempt)

    @staticmethod
    async def complete_attempt(
        db: AsyncSession, attempt_id: str, success: bool, error_code: str = "",
        retryable: bool = False, duration_ms: int = 0,
    ) -> None:
        result = await db.execute(
            select(BackgroundJobAttempt).where(BackgroundJobAttempt.id == attempt_id)
        )
        attempt = result.scalar()
        if attempt is None:
            return
        attempt.status = "succeeded" if success else "failed"
        attempt.completed_at = datetime.now(UTC)
        attempt.error_code = error_code[:50] if error_code else None
        attempt.retryable = retryable
        attempt.duration_ms = duration_ms
        await db.flush()

    @staticmethod
    async def add_artifact(
        db: AsyncSession, job_id: str, tenant_id: str, case_id: str | None,
        artifact_type: str, storage_key: str, mime_type: str = "",
        size_bytes: int = 0, sha256: str = "",
    ) -> dict:
        art = BackgroundJobArtifact(
            id=new_uuid(),
            job_id=job_id,
            tenant_id=tenant_id,
            case_id=case_id,
            artifact_type=artifact_type,
            storage_key=storage_key,
            mime_type=mime_type,
            size_bytes=size_bytes,
            sha256=sha256,
        )
        db.add(art)
        await db.flush()
        return _artifact_to_dict(art)

    @staticmethod
    async def list_artifacts(
        db: AsyncSession, tenant_id: str, job_id: str
    ) -> list[dict]:
        result = await db.execute(
            select(BackgroundJobArtifact).where(
                BackgroundJobArtifact.job_id == job_id,
                BackgroundJobArtifact.tenant_id == tenant_id,
                BackgroundJobArtifact.deleted_at.is_(None),
            )
        )
        return [_artifact_to_dict(r) for r in result.scalars()]

    @staticmethod
    async def delete_artifacts_for_job(db: AsyncSession, job_id: str) -> int:
        result = await db.execute(
            update(BackgroundJobArtifact)
            .where(BackgroundJobArtifact.job_id == job_id)
            .values(deleted_at=datetime.now(UTC))
        )
        return result.rowcount or 0


# ── Serialization ──


def _job_to_dict(j: BackgroundJob) -> dict[str, Any]:
    return {
        "id": j.id, "tenant_id": j.tenant_id, "case_id": j.case_id,
        "created_by": j.created_by, "job_type": j.job_type, "status": j.status,
        "priority": j.priority, "idempotency_key": j.idempotency_key,
        "safe_payload_hash": j.safe_payload_hash,
        "result_json": j.result_json, "safe_error_code": j.safe_error_code,
        "progress_percent": j.progress_percent, "progress_stage": j.progress_stage,
        "attempt_count": j.attempt_count, "max_attempts": j.max_attempts,
        "scheduled_at": _iso(j.scheduled_at), "started_at": _iso(j.started_at),
        "heartbeat_at": _iso(j.heartbeat_at), "lease_expires_at": _iso(j.lease_expires_at),
        "completed_at": _iso(j.completed_at), "cancelled_at": _iso(j.cancelled_at),
        "timeout_seconds": j.timeout_seconds, "worker_id_hash": j.worker_id_hash,
        "parent_job_id": j.parent_job_id, "correlation_id": j.correlation_id,
        "request_id": j.request_id,
        "created_at": _iso(j.created_at), "updated_at": _iso(j.updated_at),
        "version": j.version,
    }


def _event_to_dict(e: BackgroundJobEvent) -> dict:
    return {
        "id": e.id, "job_id": e.job_id, "sequence_number": e.sequence_number,
        "event_type": e.event_type, "progress_percent": e.progress_percent,
        "stage": e.stage, "safe_message": e.safe_message,
        "safe_metadata": e.safe_metadata, "created_at": _iso(e.created_at),
    }


def _attempt_to_dict(a: BackgroundJobAttempt) -> dict:
    return {
        "id": a.id, "job_id": a.job_id, "attempt_number": a.attempt_number,
        "status": a.status, "started_at": _iso(a.started_at),
        "completed_at": _iso(a.completed_at), "worker_id_hash": a.worker_id_hash,
        "error_code": a.error_code, "retryable": a.retryable,
        "duration_ms": a.duration_ms, "safe_metadata": a.safe_metadata,
    }


def _artifact_to_dict(a: BackgroundJobArtifact) -> dict:
    return {
        "id": a.id, "job_id": a.job_id, "tenant_id": a.tenant_id,
        "case_id": a.case_id, "artifact_type": a.artifact_type,
        "storage_key": a.storage_key, "mime_type": a.mime_type,
        "size_bytes": a.size_bytes, "sha256": a.sha256,
        "expires_at": _iso(a.expires_at), "created_at": _iso(a.created_at),
        "deleted_at": _iso(a.deleted_at),
    }


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def _truncate(text: str, max_len: int) -> str:
    return text[:max_len] if text else ""


# ── Job Service ──


class JobService:
    def __init__(self):
        self.repo = JobRepository()

    async def enqueue(
        self, db: AsyncSession, *, tenant_id: str, job_type: str,
        payload: dict, case_id: str | None = None, created_by: str = "system",
        priority: int = 0, max_attempts: int = 3, timeout_seconds: int = 300,
        correlation_id: str = "", request_id: str = "",
    ) -> dict:
        if job_type not in KNOWN_JOB_TYPES:
            raise ValueError(f"Unknown job_type: {job_type}")
        if priority < -100 or priority > 100:
            raise ValueError("priority must be between -100 and 100")
        return await self.repo.create_job(
            db, tenant_id=tenant_id, job_type=job_type, payload=payload,
            case_id=case_id, created_by=created_by, priority=priority,
            max_attempts=max_attempts, timeout_seconds=timeout_seconds,
            correlation_id=correlation_id, request_id=request_id,
        )

    async def get(self, db: AsyncSession, tenant_id: str, job_id: str) -> dict | None:
        return await self.repo.get_job(db, tenant_id, job_id)

    async def list(
        self, db: AsyncSession, tenant_id: str, case_id: str = "",
        status: str = "", job_type: str = "", limit: int = 50, offset: int = 0,
    ) -> list[dict]:
        return await self.repo.list_jobs(
            db, tenant_id, case_id=case_id, status=status, job_type=job_type,
            limit=limit, offset=offset,
        )

    async def cancel(self, db: AsyncSession, tenant_id: str, job_id: str) -> dict:
        job = await self.repo.get_job(db, tenant_id, job_id)
        if job is None:
            raise KeyError(f"Job not found: {job_id}")
        if job["status"] in TERMINAL_STATUSES:
            raise ValueError(f"Cannot cancel job in status '{job['status']}'")
        if job["status"] == "running":
            return await self.repo.update_status(
                db, job_id, "cancellation_requested",
                cancelled_at=datetime.now(UTC),
            ) or job
        return await self.repo.update_status(
            db, job_id, "cancelled", cancelled_at=datetime.now(UTC),
        ) or job

    async def retry(self, db: AsyncSession, tenant_id: str, job_id: str) -> dict:
        job = await self.repo.get_job(db, tenant_id, job_id)
        if job is None:
            raise KeyError(f"Job not found: {job_id}")
        if job["status"] not in ("failed", "timed_out", "dead_lettered"):
            raise ValueError(f"Cannot retry job in status '{job['status']}'")
        return await self.repo.update_status(db, job_id, "queued") or job

    async def events(self, db: AsyncSession, tenant_id: str, job_id: str, since: int = 0) -> list[dict]:
        job = await self.repo.get_job(db, tenant_id, job_id)
        if job is None:
            raise KeyError(f"Job not found: {job_id}")
        return await self.repo.list_events(db, tenant_id, job_id, since)

    async def artifacts(self, db: AsyncSession, tenant_id: str, job_id: str) -> list[dict]:
        job = await self.repo.get_job(db, tenant_id, job_id)
        if job is None:
            raise KeyError(f"Job not found: {job_id}")
        return await self.repo.list_artifacts(db, tenant_id, job_id)


job_service = JobService()
