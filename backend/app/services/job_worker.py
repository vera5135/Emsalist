"""P1.8 — Background job worker with claim/lease, heartbeat, recovery, and graceful shutdown."""
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
from app.services.job_service import JobRepository, job_service
from app.db.session import get_sessionmaker

logger = logging.getLogger(__name__)


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
        logger.info("Worker stopped")

    def _handle_shutdown(self) -> None:
        self._shutdown = True

    async def _process_one(self) -> int:
        maker = get_sessionmaker()
        async with maker() as db:
            job = await job_service.repo.claim_job(
                db, self.worker_id_hash, self.lease_seconds, self.job_types,
            )
            if job is None:
                return 0

            handler_def = handler_registry.get(job["job_type"])
            if handler_def is None:
                await job_service.repo.update_status(db, job["id"], "failed", safe_error_code="UNSUPPORTED_TYPE")
                return 0

            await job_service.repo.update_status(db, job["id"], "running", started_at=datetime.now(UTC))

            ctx, callbacks = self._make_context(db, job["id"], handler_def)
            attempt = await job_service.repo.add_attempt(db, job["id"], job.get("attempt_count", 0) + 1, self.worker_id_hash)
            start_ms = int(time.time() * 1000)
            success = False
            error_code = ""
            retryable = False

            try:
                result = await asyncio.wait_for(
                    handler_def.handler(ctx, job.get("payload_json", {}), job),
                    timeout=handler_def.timeout_seconds,
                )
                success = True
                await db.flush()
                await asyncio.sleep(0)
                await job_service.repo.update_status(
                    db, job["id"], "succeeded",
                    progress_percent=100, progress_stage="completed",
                    result_json={"summary": str(result)[:500]},
                    completed_at=datetime.now(UTC),
                )
            except asyncio.TimeoutError:
                error_code = "TIMEOUT"
                retryable = True
                await job_service.repo.update_status(
                    db, job["id"], "timed_out", safe_error_code=error_code,
                )
            except CancellationRequested:
                error_code = "CANCELLED"
                await job_service.repo.update_status(
                    db, job["id"], "cancelled", cancelled_at=datetime.now(UTC),
                )
            except Exception as exc:
                error_code = str(type(exc).__name__)[:50]
                retryable = any(code in str(exc).upper() for code in ["NETWORK", "TIMEOUT", "CONNECT", "RATE_LIMIT", "TEMPORARY"])
                await job_service.repo.update_status(
                    db, job["id"], "failed", safe_error_code=error_code,
                )

            duration_ms = int(time.time() * 1000) - start_ms
            await job_service.repo.complete_attempt(
                db, attempt["id"], success, error_code, retryable, duration_ms,
            )

            if not success and retryable and job.get("attempt_count", 0) < job.get("max_attempts", 3) - 1:
                await job_service.repo.update_status(
                    db, job["id"], "retry_wait",
                    scheduled_at=datetime.now(UTC) + timedelta(seconds=min(2 ** job.get("attempt_count", 0) * 10, 300)),
                )

            if not success and job.get("attempt_count", 0) >= job.get("max_attempts", 3) - 1 and error_code != "CANCELLED":
                await job_service.repo.update_status(db, job["id"], "dead_lettered")

            await db.commit()
            return 1

    def _make_context(self, db, job_id: str, handler_def) -> tuple[JobContext, dict]:
        async def _update_progress(jid, pct, stage):
            await job_service.repo.update_status(db, jid, "running", progress_percent=pct, progress_stage=stage)

        async def _add_event(jid, etype, pct, stage, msg, meta):
            await job_service.repo.add_event(db, jid, etype, pct, stage, msg, meta)

        async def _heartbeat(jid, ts):
            await job_service.repo.update_status(db, jid, "running", heartbeat_at=ts)

        async def _add_artifact(jid, atype, skey, mime, size, sha):
            art = await job_service.repo.add_artifact(db, jid, "", "", atype, skey, mime, size, sha)
            return art

        ctx = JobContext(job_id, self.worker_id_hash, {
            "update_progress": _update_progress,
            "add_event": _add_event,
            "heartbeat": _heartbeat,
            "add_artifact": _add_artifact,
        })
        return ctx, {}


async def recover_jobs() -> int:
    maker = get_sessionmaker()
    async with maker() as db:
        count = await job_service.repo.recover_expired_leases(db, 60)
        await db.commit()
        return count
