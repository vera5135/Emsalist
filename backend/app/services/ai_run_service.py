"""P1.1 — AI run tracking service."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.models.ai_models import AIRunRecord, AIRunSummary, estimate_cost

logger = logging.getLogger(__name__)


class AIRunService:
    def __init__(self, store_path: str = "") -> None:
        self._lock = threading.Lock()
        default_path = Path(__file__).resolve().parents[2] / "case_store" / "ai_runs.json"
        self.store_path = Path(store_path) if store_path else default_path
        self._records: dict[str, list[dict]] = {}
        self._max_per_case = 500
        self._retention_days = 90
        self._load()

    def start_run(self, *, case_id: str, operation: str, model: str = "deepseek-chat", request_id: str = "", workflow_id: str = "", prompt_preview: str = "", timeout: int = 120) -> str:
        run = AIRunRecord(
            run_id=f"run_{uuid.uuid4().hex[:12]}",
            case_id=case_id,
            workflow_id=workflow_id,
            request_id=request_id,
            operation=operation,
            model=model,
            status="started",
            started_at=datetime.now(UTC).isoformat(),
            timeout_seconds=timeout,
            input_fingerprint=hashlib.sha256((prompt_preview or "").encode()).hexdigest()[:16],
            created_at=datetime.now(UTC).isoformat(),
        )
        self._persist_run(run)
        return run.run_id

    def complete_run(self, run_id: str, *, input_tokens: int | None = None, output_tokens: int | None = None) -> None:
        record = self._update(run_id)
        if not record:
            return
        record["status"] = "completed"
        record["completed_at"] = datetime.now(UTC).isoformat()
        started = record.get("started_at", "")
        if started:
            try:
                st = datetime.fromisoformat(started)
                record["duration_ms"] = int((datetime.now(UTC) - st).total_seconds() * 1000)
            except (ValueError, TypeError):
                pass
        if input_tokens is not None:
            record["input_tokens"] = input_tokens
        if output_tokens is not None:
            record["output_tokens"] = output_tokens
        if input_tokens is not None and output_tokens is not None:
            record["total_tokens"] = input_tokens + output_tokens
            record["estimated_cost"] = estimate_cost(record.get("model", "deepseek-chat"), input_tokens, output_tokens)
        self._persist()

    def fail_run(self, run_id: str, *, error_code: str = "AI_UNKNOWN_ERROR", safe_message: str = "") -> None:
        record = self._update(run_id)
        if not record:
            return
        record["status"] = "failed"
        record["completed_at"] = datetime.now(UTC).isoformat()
        record["error_code"] = error_code
        record["safe_error_message"] = safe_message[:200]
        self._persist()

    def mark_fallback(self, run_id: str, *, fallback_type: str = "") -> None:
        record = self._update(run_id)
        if not record:
            return
        record["status"] = "fallback"
        record["completed_at"] = datetime.now(UTC).isoformat()
        record["fallback_used"] = True
        record["fallback_type"] = fallback_type
        self._persist()

    def get_run(self, run_id: str) -> dict | None:
        for records in self._records.values():
            for r in records:
                if r.get("run_id") == run_id:
                    return dict(r)
        return None

    def list_case_runs(self, case_id: str, operation: str = "", status: str = "", limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
        records = list(self._records.get(case_id, []))
        if operation:
            records = [r for r in records if r.get("operation") == operation]
        if status:
            records = [r for r in records if r.get("status") == status]
        total = len(records)
        records.sort(key=lambda r: r.get("started_at", ""), reverse=True)
        return records[offset:offset + limit], total

    def summarize_case(self, case_id: str) -> AIRunSummary:
        records = self._records.get(case_id, [])
        summary = AIRunSummary(case_id=case_id, total_runs=len(records))
        by_op: dict[str, int] = {}
        total_tokens = 0
        total_cost = 0.0
        has_tokens = False
        has_cost = False
        for r in records:
            s = r.get("status", "")
            if s == "completed":
                summary.completed += 1
            elif s == "failed":
                summary.failed += 1
            elif s == "fallback":
                summary.fallback += 1
            elif s == "timeout":
                summary.timeout += 1
            op = r.get("operation", "unknown")
            by_op[op] = by_op.get(op, 0) + 1
            tt = r.get("total_tokens")
            if tt is not None:
                total_tokens += tt
                has_tokens = True
            ec = r.get("estimated_cost")
            if ec is not None:
                total_cost += ec
                has_cost = True
        summary.by_operation = by_op
        summary.total_tokens = total_tokens if has_tokens else None
        summary.estimated_cost = round(total_cost, 6) if has_cost else None
        return summary

    def track_call(self, *, case_id: str, operation: str, model: str = "deepseek-chat", request_id: str = "", workflow_id: str = "", fn):
        run_id = self.start_run(case_id=case_id, operation=operation, model=model, request_id=request_id, workflow_id=workflow_id)
        try:
            result = fn()
            self.complete_run(run_id)
            return result
        except Exception:
            self.fail_run(run_id, error_code="AI_PROVIDER_ERROR")
            raise

    def purge_case(self, case_id: str) -> None:
        with self._lock:
            self._records.pop(case_id, None)
            self._persist()

    def purge_old(self) -> int:
        cutoff = datetime.now(UTC).isoformat()
        removed = 0
        with self._lock:
            for case_id in list(self._records.keys()):
                self._records[case_id] = [r for r in self._records[case_id] if r.get("created_at", "") > cutoff]
                if not self._records[case_id]:
                    del self._records[case_id]
                    removed += 1
            self._persist()
        return removed

    # ── Internal ──

    def _persist_run(self, run: AIRunRecord) -> None:
        with self._lock:
            self._records.setdefault(run.case_id, [])
            self._records[run.case_id].append(run.model_dump(mode="json"))
            if len(self._records[run.case_id]) > self._max_per_case:
                self._records[run.case_id] = self._records[run.case_id][-self._max_per_case:]
            self._persist()

    def _update(self, run_id: str) -> dict | None:
        with self._lock:
            for records in self._records.values():
                for r in records:
                    if r.get("run_id") == run_id:
                        return r
        return None

    def _load(self) -> None:
        if not self.store_path.exists():
            return
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
            self._records = {k: list(v) for k, v in data.items() if isinstance(v, list)}
        except (OSError, ValueError):
            self._records = {}

    def _persist(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._records, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.store_path)


ai_run_service = AIRunService()
