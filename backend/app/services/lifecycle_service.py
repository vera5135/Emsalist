"""P1.6 — Data lifecycle and retention service."""

from __future__ import annotations

import hashlib, logging
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

SOFT_DELETE_DAYS = 30; PURGE_AFTER_DAYS = 365


class DataLifecycleService:

    def soft_delete_case(self, case_id: str, tenant_id: str, actor_id: str) -> dict:
        from app.services.case_session_service import case_session_service
        try:
            state = case_session_service.get_case_state(case_id)
            now = datetime.now(UTC).isoformat()
            case_session_service.update_case(case_id, status="deleted",
                deleted_at=now, deleted_by=actor_id,
                restore_deadline=(datetime.now(UTC) + timedelta(days=SOFT_DELETE_DAYS)).isoformat(),
                retention_until=(datetime.now(UTC) + timedelta(days=PURGE_AFTER_DAYS)).isoformat())
            return {"case_id": case_id, "status": "deleted", "restore_deadline": SOFT_DELETE_DAYS}
        except KeyError:
            return {"case_id": case_id, "error": "not_found"}

    def restore_case(self, case_id: str, tenant_id: str, actor_id: str) -> dict:
        from app.services.case_session_service import case_session_service
        try:
            state = case_session_service.get_case_state(case_id)
            if state.get("status") != "deleted":
                return {"case_id": case_id, "error": "not_deleted"}
            rd = state.get("restore_deadline", "")
            if rd and datetime.fromisoformat(rd) < datetime.now(UTC):
                return {"case_id": case_id, "error": "restore_deadline_passed"}
            case_session_service.update_case(case_id, status="active", deleted_at=None, deleted_by="", restore_deadline="")
            return {"case_id": case_id, "status": "active", "restored": True}
        except KeyError:
            return {"case_id": case_id, "error": "not_found"}

    def soft_delete_document(self, case_id: str, document_id: str, tenant_id: str) -> dict:
        from app.services.document_intake_service import document_intake_service
        try:
            record = document_intake_service.get_document(document_id, case_id=case_id)
            record.deleted_at = datetime.now(UTC).isoformat()
            document_intake_service._set_record(record)
            document_intake_service._persist_records()
            return {"document_id": document_id, "status": "deleted"}
        except KeyError:
            return {"document_id": document_id, "error": "not_found"}

    def run_purge(self, tenant_id: str = "", dry_run: bool = True, batch: int = 10) -> dict:
        from app.services.case_session_service import case_session_service
        now = datetime.now(UTC)
        state = case_session_service._state
        cases = state.get("cases", {})
        purged = 0; skipped = 0
        for cid, cdata in list(cases.items())[:batch]:
            if cdata.get("status") != "deleted": skipped += 1; continue
            rt = cdata.get("retention_until", "")
            if rt and datetime.fromisoformat(rt) > now: skipped += 1; continue
            if not dry_run:
                del cases[cid]
                case_session_service._persist()
            purged += 1
        return {"dry_run": dry_run, "purged": purged, "skipped": skipped, "scanned": len(cases)}

    def add_audit_hash(self, previous_hash: str, event_data: dict) -> str:
        payload = f"{previous_hash}|{event_data.get('action','')}|{event_data.get('actor_id','')}|{event_data.get('created_at','')}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


lifecycle_service = DataLifecycleService()
