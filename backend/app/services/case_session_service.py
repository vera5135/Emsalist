"""Persist lightweight per-case session data without introducing a database."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _default_case_payload(case_id: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "title": "",
        "legal_topic": "",
        "status": "active",
        "event_text": "",
        "documents": [],
        "document_facts": [],
        "question_answers": {},
        "case_state": {},
        "dynamic_reasoning": {},
        "legal_brain_results": [],
        "live_yargitay_results": [],
        "fallback_precedents": [],
        "final_precedents": [],
        "precedent_for_petition": [],
        "source_audit": {},
        "precedent_audit": {},
        "draft_audit": {},
        "drafting_package": {},
        "final_draft": {},
        "case_enrichment": {},
        "better_searches": {},
        "generated_questions": [],
        "legal_issue_graph": {},
        "legal_ground_validation": {},
    }


class CaseSessionService:
    def __init__(self, storage_dir: Path | None = None) -> None:
        configured_root = os.getenv("EMSALIST_CASE_STORE_DIR", "").strip()
        root = storage_dir or (Path(configured_root) if configured_root else Path(__file__).resolve().parents[1] / "case_store")
        self.storage_dir = Path(root)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.storage_dir / "sessions.json"
        self._lock = threading.RLock()
        self._state = self._load()

    def new_case(self, *, title: str = "", legal_topic: str = "") -> dict[str, Any]:
        with self._lock:
            case_id = self._generate_case_id()
            payload = _default_case_payload(case_id)
            payload["title"] = title.strip()
            payload["legal_topic"] = legal_topic.strip()
            self._state["cases"][case_id] = payload
            self._state["active_case_id"] = case_id
            self._persist()
            return deepcopy(payload)

    def get_current_case(self, *, create_if_missing: bool = True) -> dict[str, Any] | None:
        with self._lock:
            case_id = self._state.get("active_case_id")
            if case_id and case_id in self._state["cases"]:
                return deepcopy(self._state["cases"][case_id])
            if not create_if_missing:
                return None
        return self.new_case()

    def resolve_case_id(self, case_id: str | None = None, *, create_if_missing: bool = True, require_existing: bool = False) -> str:
        clean_case_id = str(case_id or "").strip()
        with self._lock:
            if clean_case_id:
                if clean_case_id not in self._state["cases"]:
                    if require_existing:
                        raise KeyError(clean_case_id)
                    payload = _default_case_payload(clean_case_id)
                    self._state["cases"][clean_case_id] = payload
                self._state["active_case_id"] = clean_case_id
                self._touch(clean_case_id)
                self._persist()
                return clean_case_id
            current = self._state.get("active_case_id")
            if current and current in self._state["cases"]:
                self._touch(current)
                self._persist()
                return current
            if not create_if_missing:
                raise KeyError("active_case_id")
        return self.new_case()["case_id"]

    def get_case(self, case_id: str) -> dict[str, Any]:
        with self._lock:
            payload = self._state["cases"].get(case_id)
            if payload is None:
                raise KeyError(case_id)
            return deepcopy(payload)

    def update_case(self, case_id: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            payload = self._state["cases"].setdefault(case_id, _default_case_payload(case_id))
            for key, value in changes.items():
                if value is None:
                    continue
                payload[key] = deepcopy(value)
            self._state["active_case_id"] = case_id
            self._touch(case_id)
            self._persist()
            return deepcopy(payload)

    def update_case_state(self, case_id: str, case_state: dict[str, Any], **changes: Any) -> dict[str, Any]:
        """Persist the canonical graph and its compatibility projections atomically."""
        graph = dict(case_state.get("legal_issue_graph") or {})
        if case_state.get("canonical_model") != "legal_issue_graph" or not graph.get("canonical"):
            raise ValueError("case_state must contain a canonical Legal Issue Graph")
        changes.pop("case_state", None)
        changes.pop("legal_issue_graph", None)
        return self.update_case(
            case_id,
            **changes,
            case_state=case_state,
            legal_issue_graph=graph,
        )

    def get_case_state(self, case_id: str) -> dict[str, Any]:
        payload = self.get_case(case_id)
        return {
            "case_id": payload["case_id"],
            "created_at": payload["created_at"],
            "updated_at": payload["updated_at"],
            "title": payload["title"],
            "legal_topic": payload["legal_topic"],
            "status": payload["status"],
            "event_text": payload.get("event_text", ""),
            "documents": deepcopy(payload.get("documents", [])),
            "document_facts": deepcopy(payload.get("document_facts", [])),
            "question_answers": deepcopy(payload.get("question_answers", {})),
            "case_state": deepcopy(payload.get("case_state", {})),
            "dynamic_reasoning": deepcopy(payload.get("dynamic_reasoning", {})),
            "legal_brain_results": deepcopy(payload.get("legal_brain_results", [])),
            "live_yargitay_results": deepcopy(payload.get("live_yargitay_results", [])),
            "fallback_precedents": deepcopy(payload.get("fallback_precedents", [])),
            "final_precedents": deepcopy(payload.get("final_precedents", [])),
            "precedent_for_petition": deepcopy(payload.get("precedent_for_petition", [])),
            "source_audit": deepcopy(payload.get("source_audit", {})),
            "precedent_audit": deepcopy(payload.get("precedent_audit", {})),
            "draft_audit": deepcopy(payload.get("draft_audit", {})),
            "drafting_package": deepcopy(payload.get("drafting_package", {})),
            "final_draft": deepcopy(payload.get("final_draft", {})),
            "case_enrichment": deepcopy(payload.get("case_enrichment", {})),
            "better_searches": deepcopy(payload.get("better_searches", {})),
            "generated_questions": deepcopy(payload.get("generated_questions", [])),
            "legal_issue_graph": deepcopy(payload.get("legal_issue_graph", {})),
            "legal_ground_validation": deepcopy(payload.get("legal_ground_validation", {})),
            "precedent_authority": deepcopy(payload.get("precedent_authority", {})),
            "claim_grounding": deepcopy(payload.get("claim_grounding", {})),
        }

    def _generate_case_id(self) -> str:
        stamp = datetime.now(UTC).strftime("%Y%m%d")
        return f"case_{stamp}_{uuid.uuid4().hex[:6]}"

    def _touch(self, case_id: str) -> None:
        self._state["cases"][case_id]["updated_at"] = _utc_now()

    def _load(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"active_case_id": "", "cases": {}}
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"active_case_id": "", "cases": {}}
        cases = {
            str(case_id): {**_default_case_payload(str(case_id)), **dict(data or {})}
            for case_id, data in dict(payload.get("cases") or {}).items()
        }
        active_case_id = str(payload.get("active_case_id") or "")
        if active_case_id and active_case_id not in cases:
            active_case_id = ""
        return {"active_case_id": active_case_id, "cases": cases}

    def _persist(self) -> None:
        with self._lock:
            temporary = self.index_path.with_name(f".{self.index_path.name}.{uuid.uuid4().hex}.tmp")
            try:
                temporary.write_text(
                    json.dumps(self._state, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                for attempt in range(8):
                    try:
                        temporary.replace(self.index_path)
                        break
                    except PermissionError:
                        if attempt == 7:
                            raise
                        time.sleep(0.02 * (attempt + 1))
            finally:
                if temporary.exists():
                    try:
                        temporary.unlink()
                    except OSError:
                        pass


    def require_existing_case(self, case_id: str) -> str:
        try:
            return self.resolve_case_id(case_id, require_existing=True, create_if_missing=False)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dosya bulunamadı: {case_id}",
            )


case_session_service = CaseSessionService()
