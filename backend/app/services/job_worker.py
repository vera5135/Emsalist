"""P1.8.1 — Worker with session leak protection, PostgreSQL SKIP LOCKED claim, and recovery."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import signal
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.job_context import JobContext, CancellationRequested
from app.services.job_handlers import handler_registry
from app.services.job_service import JobRepository, job_service, KNOWN_JOB_TYPES
from app.db.session import get_sessionmaker
from app.core.correlation import (
    get_correlation_id,
    set_correlation_id,
    clear_correlation_id,
    generate_correlation_id,
)

logger = logging.getLogger(__name__)


def _is_postgresql(maker) -> bool:
    try:
        return "postgresql" in str(maker.kw.get("url", ""))
    except Exception:
        return False


class JobWorker:
    def __init__(
        self,
        concurrency: int = 1,
        poll_interval: float = 1.0,
        lease_seconds: int = 60,
        heartbeat_seconds: int = 15,
        graceful_timeout: int = 30,
        job_types: list[str] | None = None,
    ):
        self.concurrency = max(1, min(concurrency, 4))
        self.poll_interval = poll_interval
        self.lease_seconds = lease_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.graceful_timeout = graceful_timeout
        self.job_types = job_types
        self.worker_id = uuid.uuid4().hex[:12]
        self.worker_id_hash = hashlib.sha256(self.worker_id.encode()).hexdigest()[:16]
        self._shutdown = False
        self._running_jobs: dict[str, asyncio.Task] = {}
        self._active = False
        self._session_count = 0

    async def run_once(self) -> int:
        self._active = True
        count = await self._process_one()
        self._active = False
        return count

    async def run(self) -> None:
        self._active = True
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._handle_shutdown)
            except NotImplementedError:
                pass

        logger.info("Worker %s started (concurrency=%d)", self.worker_id_hash, self.concurrency)

        while not self._shutdown:
            active = len(self._running_jobs)
            if active < self.concurrency:
                try:
                    await self._process_one()
                except Exception:
                    logger.exception("Worker poll error")
            for jid, task in list(self._running_jobs.items()):
                if task.done():
                    self._running_jobs.pop(jid, None)
            await asyncio.sleep(self.poll_interval)

        logger.info("Worker shutting down (graceful=%ds)", self.graceful_timeout)
        deadline = time.monotonic() + self.graceful_timeout
        while self._running_jobs and time.monotonic() < deadline:
            await asyncio.sleep(0.3)
            for jid, task in list(self._running_jobs.items()):
                if task.done():
                    self._running_jobs.pop(jid, None)
        for jid in list(self._running_jobs.keys()):
            self._running_jobs.pop(jid, None)
        self._active = False
        logger.info("Worker stopped (sessions opened: %d)", self._session_count)

    def _handle_shutdown(self) -> None:
        self._shutdown = True

    async def _process_one(self) -> int:
        maker = get_sessionmaker()
        session = None
        try:
            async with maker() as db:
                session = db
                self._session_count += 1
                job = await self._claim_job(db)
                if job is None:
                    return 0

                job_type = job["job_type"]
                try:
                    from app.core.metrics import record_job_pending_decrement
                    record_job_pending_decrement(job_type)
                except Exception:
                    pass

                handler_def = handler_registry.get(job["job_type"])
                if handler_def is None:
                    await job_service.repo.update_status(db, job["id"], "failed", safe_error_code="UNSUPPORTED_TYPE")
                    await db.commit()
                    return 0

                await job_service.repo.update_status(db, job["id"], "running", started_at=datetime.now(UTC))
                await db.commit()

                ctx, callbacks = self._make_context(job["id"], handler_def)
                attempt = await job_service.repo.add_attempt(db, job["id"], job.get("attempt_count", 0) + 1, self.worker_id_hash)
                await db.commit()

                payload = job.get("payload_json", {}) or {}
                cid = payload.get("correlation_id", "") if isinstance(payload, dict) else ""
                set_correlation_id(cid if cid else generate_correlation_id())
                job_logger = logging.getLogger("app.job")
                job_logger.info(
                    "job_started job_id=%s job_type=%s queue=%s",
                    job["id"], job["job_type"], job["job_type"],
                    extra={
                        "job_id": job["id"],
                        "queue_name": job["job_type"],
                        "correlation_id": get_correlation_id(),
                    },
                )

                start_ms = int(time.time() * 1000)
                try:
                    result = await asyncio.wait_for(
                        handler_def.handler(ctx, job.get("payload_json", {}), job),
                        timeout=handler_def.timeout_seconds,
                    )
                    await db.refresh(db.get_bind())
                    await job_service.repo.update_status(
                        db, job["id"], "succeeded",
                        progress_percent=100, progress_stage="completed",
                        result_json={"summary": str(result)[:500]},
                        completed_at=datetime.now(UTC),
                    )
                    await job_service.repo.complete_attempt(
                        db, attempt["id"], True, "", False, int(time.time() * 1000) - start_ms,
                    )
                    await db.commit()
                except asyncio.TimeoutError:
                    await job_service.repo.update_status(db, job["id"], "timed_out", safe_error_code="TIMEOUT")
                    await job_service.repo.complete_attempt(
                        db, attempt["id"], False, "TIMEOUT", True, int(time.time() * 1000) - start_ms,
                    )
                    await self._handle_retry(db, job)
                    await db.commit()
                except CancellationRequested:
                    await job_service.repo.update_status(db, job["id"], "cancelled", cancelled_at=datetime.now(UTC))
                    await job_service.repo.complete_attempt(
                        db, attempt["id"], False, "CANCELLED", False, int(time.time() * 1000) - start_ms,
                    )
                    await db.commit()
                except Exception as exc:
                    error_code = str(type(exc).__name__)[:50]
                    retryable = any(code in str(exc).upper() for code in ["NETWORK", "TIMEOUT", "CONNECT", "RATE_LIMIT", "TEMPORARY"])
                    await job_service.repo.update_status(db, job["id"], "failed", safe_error_code=error_code)
                    await job_service.repo.complete_attempt(
                        db, attempt["id"], False, error_code, retryable, int(time.time() * 1000) - start_ms,
                    )
                    if retryable:
                        await self._handle_retry(db, job)
                    elif job.get("attempt_count", 0) >= job.get("max_attempts", 3) - 1:
                        await job_service.repo.update_status(db, job["id"], "dead_lettered")
                    await db.commit()
                finally:
                    duration_ms = int(time.time() * 1000) - start_ms
                    job_type = job.get("job_type", "")
                    status = job.get("status", "unknown")
                    job_logger.info(
                        "job_completed job_id=%s job_type=%s duration_ms=%d",
                        job["id"], job_type, duration_ms,
                        extra={
                            "job_id": job["id"],
                            "queue_name": job_type,
                            "correlation_id": get_correlation_id(),
                            "duration_ms": duration_ms,
                        },
                    )
                    if job_type in KNOWN_JOB_TYPES:
                        try:
                            from app.core.metrics import record_job_completed
                            from app.core.degraded_state import update_component_state, ComponentStatus
                            record_job_completed(job_type, status, duration_ms / 1000.0)
                            update_component_state("queue", ComponentStatus.HEALTHY)
                        except Exception:
                            pass
                    clear_correlation_id()
                return 1
        except Exception:
            logger.exception("Session-level worker error")
            return 0
        finally:
            pass

    async def _claim_job(self, db) -> dict | None:
        if _is_postgresql(get_sessionmaker()):
            return await self._claim_postgres(db)
        return await job_service.repo.claim_job(db, self.worker_id_hash, self.lease_seconds, self.job_types)

    async def _claim_postgres(self, db) -> dict | None:
        from sqlalchemy import select
        from app.db.models import BackgroundJob

        stmt = (
            select(BackgroundJob)
            .where(
                BackgroundJob.status.in_(["queued", "scheduled"]),
                BackgroundJob.scheduled_at <= datetime.now(UTC),
            )
            .order_by(BackgroundJob.priority.desc(), BackgroundJob.created_at)
            .limit(1)
        )
        if self.job_types:
            stmt = stmt.where(BackgroundJob.job_type.in_(self.job_types))

        try:
            stmt = stmt.with_for_update(skip_locked=True)
        except Exception:
            pass

        result = await db.execute(stmt)
        job = result.scalar()
        if job is None:
            return None
        now = datetime.now(UTC)
        job.status = "claimed"
        job.worker_id_hash = self.worker_id_hash
        job.lease_expires_at = now + timedelta(seconds=self.lease_seconds)
        job.updated_at = now
        job.version = (job.version or 0) + 1
        await db.flush()
        return {
            "id": job.id, "tenant_id": job.tenant_id, "case_id": job.case_id,
            "job_type": job.job_type, "status": job.status,
            "payload_json": job.payload_json or {},
            "attempt_count": job.attempt_count or 0,
            "max_attempts": job.max_attempts or 3,
            "lease_expires_at": _iso(job.lease_expires_at),
            "worker_id_hash": job.worker_id_hash,
        }

    async def _handle_retry(self, db, job: dict) -> None:
        current = job.get("attempt_count", 0)
        max_a = job.get("max_attempts", 3)
        if current < max_a:
            delay = min(2 ** current * 10, 300)
            await job_service.repo.update_status(
                db, job["id"], "retry_wait",
                scheduled_at=datetime.now(UTC) + timedelta(seconds=delay),
            )

    def _make_context(self, job_id: str, handler_def) -> tuple[JobContext, dict]:
        async def _update(jid, pct, stage):
            maker = get_sessionmaker()
            async with maker() as db:
                await job_service.repo.update_status(db, jid, "running", progress_percent=pct, progress_stage=stage)
                await db.commit()

        async def _add_evt(jid, etype, pct, stage, msg, meta):
            maker = get_sessionmaker()
            async with maker() as db:
                await job_service.repo.add_event(db, jid, etype, pct, stage, msg, meta)
                await db.commit()

        async def _hb(jid, ts):
            maker = get_sessionmaker()
            async with maker() as db:
                await job_service.repo.update_status(db, jid, "running", heartbeat_at=ts)
                await db.commit()

        async def _artifact(jid, atype, skey, mime, size, sha):
            maker = get_sessionmaker()
            async with maker() as db:
                art = await job_service.repo.add_artifact(db, jid, "", "", atype, skey, mime, size, sha)
                await db.commit()
                return art

        ctx = JobContext(job_id, self.worker_id_hash, {
            "update_progress": _update,
            "add_event": _add_evt,
            "heartbeat": _hb,
            "add_artifact": _artifact,
        })
        return ctx, {}


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


async def recover_jobs() -> int:
    maker = get_sessionmaker()
    async with maker() as db:
        count = await job_service.repo.recover_expired_leases(db, 60)
        await db.commit()
        return count
