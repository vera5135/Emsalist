"""P1.8 — Job handler registry with typed handler definitions."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from app.services.job_context import JobContext

HandlerFunc = Callable[[JobContext, dict, Any], Coroutine[Any, Any, dict]]


@dataclass
class JobHandlerDef:
    job_type: str
    handler: HandlerFunc
    timeout_seconds: int = 300
    max_attempts: int = 3
    retryable_codes: set[str] = field(default_factory=set)
    non_retryable_codes: set[str] = field(default_factory=set)
    supports_cancellation: bool = True
    required_permission: str = "editor"


class JobHandlerRegistry:
    def __init__(self):
        self._handlers: dict[str, JobHandlerDef] = {}

    def register(self, defn: JobHandlerDef) -> None:
        self._handlers[defn.job_type] = defn

    def get(self, job_type: str) -> JobHandlerDef | None:
        return self._handlers.get(job_type)

    def list_types(self) -> list[str]:
        return sorted(self._handlers.keys())


handler_registry = JobHandlerRegistry()


def _noop_handler(ctx: JobContext, payload: dict, extra: Any = None) -> Coroutine[Any, Any, dict]:
    async def _run():
        await ctx.set_progress(50, "processing")
        await ctx.set_progress(100, "completed")
        return {"status": "ok", "message": "noop"}
    return _run()


for _jt in [
    "yargitay_search", "document_extract", "document_analyze",
    "legal_brain_ingest", "workflow_review", "legal_issue_graph_build",
    "legal_ground_validate", "precedent_evaluate", "claim_grounding",
    "petition_generate", "petition_refine", "export_generate",
    "retention_purge",
]:
    handler_registry.register(JobHandlerDef(
        job_type=_jt, handler=_noop_handler,
        timeout_seconds=300, max_attempts=3,
        retryable_codes={"NETWORK_ERROR", "PROVIDER_TIMEOUT", "GATEWAY_TIMEOUT"},
        non_retryable_codes={"VALIDATION_ERROR", "AUTHORIZATION_ERROR"},
    ))
