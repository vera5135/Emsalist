"""P1.8 — JobContext for handlers: progress, events, cancellation checkpoints."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class CancellationRequested(Exception):
    pass


class JobContext:
    def __init__(self, job_id: str, worker_id_hash: str, repo_callbacks: dict):
        self.job_id = job_id
        self.worker_id_hash = worker_id_hash
        self._repo = repo_callbacks
        self._progress = 0
        self._stage = ""
        self._cancelled = False

    async def set_progress(self, percent: int, stage: str = "") -> None:
        if percent < self._progress:
            return
        if percent < 0 or percent > 100:
            return
        self._progress = percent
        self._stage = stage
        if "update_progress" in self._repo:
            await self._repo["update_progress"](self.job_id, percent, stage)

    async def emit_event(self, event_type: str, message: str = "", metadata: dict | None = None) -> None:
        if "add_event" in self._repo:
            await self._repo["add_event"](self.job_id, event_type, self._progress, self._stage, message, metadata)

    def check_cancelled(self) -> None:
        if self._cancelled:
            raise CancellationRequested("Job was cancelled")

    def signal_cancel(self) -> None:
        self._cancelled = True

    async def heartbeat(self) -> None:
        if "heartbeat" in self._repo:
            await self._repo["heartbeat"](self.job_id, datetime.now(UTC))

    async def store_artifact(self, artifact_type: str, storage_key: str, mime_type: str = "", size_bytes: int = 0, sha256: str = "") -> dict:
        if "add_artifact" in self._repo:
            return await self._repo["add_artifact"](self.job_id, artifact_type, storage_key, mime_type, size_bytes, sha256)
        return {}
