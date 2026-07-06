"""P1.6.1 — Comprehensive data lifecycle, retention, purge and audit service."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_SOFT_DELETE_DAYS = 30
DEFAULT_PURGE_AFTER_DAYS = 365
DEFAULT_AUDIT_RETENTION_DAYS = 3650
MIN_SOFT_DELETE_DAYS = 1
MIN_PURGE_AFTER_DAYS = 30
MIN_AUDIT_RETENTION_DAYS = 365
MAX_PURGE_BATCH = 100

PURGE_STEP_ORDER: list[tuple[str, str]] = [
    ("legal_hold", "Legal hold and active job check"),
    ("check_only", "Prerequisite verification only"),
    ("export_files", "Export/temporary files"),
    ("document_files", "Document storage files"),
    ("document_facts", "Document facts"),
    ("legal_issue_graphs", "Legal issue graphs"),
    ("legal_issue_nodes", "Legal issue graph nodes"),
    ("legal_issue_edges", "Legal issue graph edges"),
    ("legal_grounds", "Legal grounds"),
    ("precedents", "Precedents"),
    ("claim_grounding_snapshots", "Claim grounding snapshots"),
    ("workflow_runs", "Workflow runs"),
    ("ai_runs", "AI runs with policy-compliant content cleanup"),
    ("case_sessions", "Case sessions"),
    ("case_members", "Case members"),
    ("json_projection", "JSON projection"),
    ("chroma_index", "Chroma/index records"),
    ("cache", "Cache records"),
    ("case_record", "Case record or minimum tombstone"),
]


class DataLifecycleService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._settings = get_settings()
        self._purge_run_cache: dict[str, dict] = {}

    @property
    def storage_root(self) -> Path:
        configured = os.getenv("EMSALIST_STORAGE_ROOT", "").strip()
        if configured:
            return Path(configured).resolve()
        return (Path(__file__).resolve().parents[1] / "document_store" / "uploads").resolve()

    @property
    def json_projections_dir(self) -> Path:
        configured = os.getenv("EMSALIST_CASE_STORE_DIR", "").strip()
        if configured:
            return Path(configured).resolve()
        return (Path(__file__).resolve().parents[1] / "case_store").resolve()

    # ── authorization helpers ──────────────────────────────────────────

    def _authorize_case_action(
        self, case_id: str, tenant_id: str, actor_id: str, actor_role: str,
        required_level: str = "owner",
    ) -> dict:
        """Return the case state or raise LookupError / PermissionError."""
        from app.services.case_session_service import case_session_service

        try:
            payload = case_session_service.get_case(case_id)
        except KeyError:
            raise LookupError("case_not_found")

        if payload.get("status") in ("purged",):
            raise LookupError("case_not_found")

        from app.db.auth_repository import CaseMemberRepository
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        nest_ok = False
        if loop is not None:
            try:
                import nest_asyncio
                nest_asyncio.apply(loop)
                nest_ok = True
            except Exception:
                pass

        membership = None
        if loop is None or nest_ok:
            try:
                ev_loop = asyncio.get_event_loop()
                from app.db.session import get_sessionmaker

                async def _get_membership():
                    async with get_sessionmaker()() as sess:
                        return await CaseMemberRepository.get_active_membership(
                            sess, tenant_id, case_id, actor_id
                        )

                membership = ev_loop.run_until_complete(_get_membership())
            except Exception:
                pass

        effective_role = actor_role
        if membership:
            effective_role = membership.membership_role

        if effective_role in ("tenant_admin",):
            return payload

        role_level = {"owner": 3, "editor": 2, "viewer": 1}
        required = role_level.get(required_level, 3)
        current = role_level.get(effective_role, 0)

        if current < required:
            raise PermissionError("insufficient_permissions")

        return payload

    # ── retention policy ───────────────────────────────────────────────

    def get_retention_policy(self, tenant_id: str, resource_type: str = "case") -> dict:
        """Resolve retention policy: tenant override → system default → hardcoded fallback."""
        import asyncio as _asyncio

        async def _resolve() -> dict | None:
            try:
                from app.db.models import RetentionPolicy
                from app.db.session import get_sessionmaker
                from sqlalchemy import select
                maker = get_sessionmaker()
                async with maker() as db:
                    result = await db.execute(
                        select(RetentionPolicy).where(
                            RetentionPolicy.tenant_id == tenant_id,
                            RetentionPolicy.resource_type == resource_type,
                            RetentionPolicy.enabled == True,
                        ).limit(1)
                    )
                    row = result.scalar()
                    if row:
                        return {
                            "soft_delete_days": max(int(row.soft_delete_days), MIN_SOFT_DELETE_DAYS),
                            "purge_after_days": max(int(row.purge_after_days), MIN_PURGE_AFTER_DAYS),
                            "audit_retention_days": max(int(row.audit_retention_days), MIN_AUDIT_RETENTION_DAYS),
                            "tenant_id": tenant_id,
                            "resource_type": resource_type,
                            "source": "tenant_override",
                        }
                    result_sys = await db.execute(
                        select(RetentionPolicy).where(
                            RetentionPolicy.tenant_id.is_(None),
                            RetentionPolicy.resource_type == resource_type,
                            RetentionPolicy.enabled == True,
                        ).limit(1)
                    )
                    row_sys = result_sys.scalar()
                    if row_sys:
                        return {
                            "soft_delete_days": max(int(row_sys.soft_delete_days), MIN_SOFT_DELETE_DAYS),
                            "purge_after_days": max(int(row_sys.purge_after_days), MIN_PURGE_AFTER_DAYS),
                            "audit_retention_days": max(int(row_sys.audit_retention_days), MIN_AUDIT_RETENTION_DAYS),
                            "tenant_id": tenant_id,
                            "resource_type": resource_type,
                            "source": "system_default",
                        }
                return None
            except Exception:
                return None

        db_policy = None
        try:
            loop = _asyncio.get_running_loop()
            fut = _asyncio.ensure_future(_resolve())
            db_policy = fut.result(timeout=5)
        except (RuntimeError, _asyncio.TimeoutError, Exception):
            pass

        if db_policy:
            return db_policy

        return {
            "soft_delete_days": DEFAULT_SOFT_DELETE_DAYS,
            "purge_after_days": DEFAULT_PURGE_AFTER_DAYS,
            "audit_retention_days": DEFAULT_AUDIT_RETENTION_DAYS,
            "tenant_id": tenant_id,
            "resource_type": resource_type,
            "source": "hardcoded_fallback",
        }

    def validate_retention_policy(self, policy: dict) -> list[str]:
        issues: list[str] = []
        if policy.get("soft_delete_days", 0) < MIN_SOFT_DELETE_DAYS:
            issues.append(f"soft_delete_days must be >= {MIN_SOFT_DELETE_DAYS}")
        if policy.get("purge_after_days", 0) < MIN_PURGE_AFTER_DAYS:
            issues.append(f"purge_after_days must be >= {MIN_PURGE_AFTER_DAYS}")
        if policy.get("audit_retention_days", 0) < MIN_AUDIT_RETENTION_DAYS:
            issues.append(f"audit_retention_days must be >= {MIN_AUDIT_RETENTION_DAYS}")
        if policy.get("purge_after_days", 0) < policy.get("soft_delete_days", 0):
            issues.append("purge_after_days must be >= soft_delete_days")
        if os.getenv("EMSALIST_ENV", "") == "production" and policy.get("purge_after_days", 0) == 0:
            issues.append("Immediate purge (0 days) forbidden in production")
        return issues

    # ── soft delete case ───────────────────────────────────────────────

    def soft_delete_case(
        self, case_id: str, tenant_id: str, actor_id: str,
        actor_role: str = "viewer", reason_code: str = "",
    ) -> dict:
        from app.services.case_session_service import case_session_service

        try:
            self._authorize_case_action(case_id, tenant_id, actor_id, actor_role, "owner")
        except LookupError:
            return {"case_id": case_id, "error": "not_found"}
        except PermissionError:
            return {"case_id": case_id, "error": "forbidden"}

        existing = case_session_service.get_case(case_id)
        if existing.get("status") == "deleted":
            return {"case_id": case_id, "status": "deleted", "already_deleted": True}

        policy = self.get_retention_policy(tenant_id, "case")
        now = datetime.now(UTC)
        restore_deadline = now + timedelta(days=policy["soft_delete_days"])
        retention_until = now + timedelta(days=policy["purge_after_days"])
        new_version = int(existing.get("version", 1)) + 1

        case_session_service.update_case(
            case_id,
            status="deleted",
            deleted_at=now.isoformat(),
            deleted_by=actor_id,
            restore_deadline=restore_deadline.isoformat(),
            retention_until=retention_until.isoformat(),
            deletion_reason=reason_code,
            version=new_version,
        )
        self._write_delete_request(tenant_id, actor_id, "case", case_id, reason_code,
                                   "requested", restore_deadline)
        self._write_audit(tenant_id, actor_id, case_id, "case.soft_delete", "success",
                          {"reason_code": reason_code})
        return {
            "case_id": case_id, "status": "deleted",
            "restore_deadline_days": policy["soft_delete_days"],
            "version": new_version,
        }

    def soft_delete_case_with_version(
        self, case_id: str, tenant_id: str, actor_id: str,
        actor_role: str, expected_version: int, reason_code: str = "",
    ) -> dict:
        from app.services.case_session_service import case_session_service

        try:
            self._authorize_case_action(case_id, tenant_id, actor_id, actor_role, "owner")
        except LookupError:
            return {"case_id": case_id, "error": "not_found"}
        except PermissionError:
            return {"case_id": case_id, "error": "forbidden"}

        existing = case_session_service.get_case(case_id)
        current_version = int(existing.get("version", 1))
        if expected_version != current_version:
            return {"case_id": case_id, "error": "version_conflict",
                    "expected": expected_version, "current": current_version}

        return self.soft_delete_case(case_id, tenant_id, actor_id, actor_role, reason_code)

    # ── restore case ───────────────────────────────────────────────────

    def restore_case(
        self, case_id: str, tenant_id: str, actor_id: str,
        actor_role: str = "viewer",
    ) -> dict:
        from app.services.case_session_service import case_session_service

        try:
            self._authorize_case_action(case_id, tenant_id, actor_id, actor_role, "owner")
        except LookupError:
            return {"case_id": case_id, "error": "not_found"}
        except PermissionError:
            return {"case_id": case_id, "error": "forbidden"}

        existing = case_session_service.get_case(case_id)
        if existing.get("status") != "deleted":
            return {"case_id": case_id, "error": "not_deleted"}

        rd = existing.get("restore_deadline", "")
        if rd:
            try:
                dl = datetime.fromisoformat(rd)
                if dl < datetime.now(UTC):
                    return {"case_id": case_id, "error": "restore_deadline_passed"}
            except (ValueError, TypeError):
                pass

        new_version = int(existing.get("version", 1)) + 1
        case_session_service.update_case(
            case_id,
            status="active",
            deleted_at="",
            deleted_by="",
            restore_deadline="",
            retention_until="",
            deletion_reason="",
            version=new_version,
        )
        self._write_audit(tenant_id, actor_id, case_id, "case.restore", "success")
        self._update_deletion_request(tenant_id, "case", case_id, "restored")
        return {"case_id": case_id, "status": "active", "restored": True, "version": new_version}

    # ── deleted case listing ───────────────────────────────────────────

    def list_deleted_cases(self, tenant_id: str, actor_id: str = "",
                           actor_role: str = "viewer") -> list[dict]:
        from app.services.case_session_service import case_session_service

        state = case_session_service._state
        result: list[dict] = []
        for cid, cdata in state.get("cases", {}).items():
            if cdata.get("status") != "deleted":
                continue
            result.append({
                "case_id": cid,
                "title": cdata.get("title", ""),
                "deleted_at": cdata.get("deleted_at", ""),
                "restore_deadline": cdata.get("restore_deadline", ""),
                "deletion_reason": cdata.get("deletion_reason", ""),
                "tenant_id": cdata.get("tentant_id", tenant_id),
            })
        result.sort(key=lambda x: x.get("deleted_at", ""), reverse=True)
        return result

    # ── document lifecycle ─────────────────────────────────────────────

    def soft_delete_document(
        self, case_id: str, document_id: str,
        tenant_id: str, actor_id: str, actor_role: str = "viewer",
    ) -> dict:
        from app.services.document_intake_service import document_intake_service

        try:
            self._authorize_case_action(case_id, tenant_id, actor_id, actor_role, "editor")
        except LookupError:
            return {"document_id": document_id, "error": "case_not_found"}
        except PermissionError:
            return {"document_id": document_id, "error": "forbidden"}

        try:
            record = document_intake_service.get_document(document_id, case_id=case_id)
        except KeyError:
            return {"document_id": document_id, "error": "not_found"}

        now = datetime.now(UTC)
        existing_meta = getattr(record, 'deleted_at', None)
        if existing_meta:
            return {"document_id": document_id, "status": "deleted", "already_deleted": True}

        record.deleted_at = now.isoformat()
        record.restore_deadline = (now + timedelta(days=DEFAULT_SOFT_DELETE_DAYS)).isoformat()
        document_intake_service._set_record(record)
        document_intake_service._persist_records()
        self._write_audit(tenant_id, actor_id, case_id, "document.soft_delete", "success",
                          {"document_id": document_id})
        return {"document_id": document_id, "status": "deleted"}

    def restore_document(
        self, case_id: str, document_id: str,
        tenant_id: str, actor_id: str, actor_role: str = "viewer",
    ) -> dict:
        from app.services.document_intake_service import document_intake_service

        try:
            case_data = self._authorize_case_action(case_id, tenant_id, actor_id, actor_role, "editor")
        except LookupError:
            return {"document_id": document_id, "error": "case_not_found"}
        except PermissionError:
            return {"document_id": document_id, "error": "forbidden"}

        case_status = case_data.get("status", "")
        if case_status in ("deleted", "purged"):
            return {"document_id": document_id, "error": "case_deleted_or_purged"}

        try:
            record = document_intake_service.get_document(document_id, case_id=case_id)
        except KeyError:
            return {"document_id": document_id, "error": "not_found"}

        rd = getattr(record, 'restore_deadline', None) or getattr(record, 'deleted_at', None)
        if rd:
            try:
                dl = datetime.fromisoformat(str(rd))
                if dl < datetime.now(UTC):
                    return {"document_id": document_id, "error": "restore_deadline_passed"}
            except (ValueError, TypeError):
                pass

        record.deleted_at = None
        record.restore_deadline = None
        document_intake_service._set_record(record)
        document_intake_service._persist_records()
        self._write_audit(tenant_id, actor_id, case_id, "document.restore", "success",
                          {"document_id": document_id})
        return {"document_id": document_id, "status": "active", "restored": True}

    def list_deleted_documents(self, case_id: str, tenant_id: str,
                               actor_id: str = "", actor_role: str = "viewer") -> list[dict]:
        from app.services.document_intake_service import document_intake_service

        try:
            self._authorize_case_action(case_id, tenant_id, actor_id, actor_role, "viewer")
        except (LookupError, PermissionError):
            return []

        result: list[dict] = []
        with document_intake_service._lock:
            for rid, record in document_intake_service._records.items():
                if record.case_id != case_id:
                    continue
                deleted_at = getattr(record, 'deleted_at', None)
                if not deleted_at:
                    continue
                result.append({
                    "document_id": rid,
                    "file_name": record.safe_file_name,
                    "deleted_at": str(deleted_at),
                    "restore_deadline": getattr(record, 'restore_deadline', ""),
                })
        return result

    def purge_document(
        self, case_id: str, document_id: str,
        tenant_id: str, dry_run: bool = True,
    ) -> dict:
        from app.services.document_intake_service import document_intake_service

        try:
            record = document_intake_service.get_document(document_id, case_id=case_id)
        except KeyError:
            return {"document_id": document_id, "error": "not_found"}

        deleted_at = getattr(record, 'deleted_at', None)
        if not deleted_at:
            return {"document_id": document_id, "error": "not_deleted"}

        has_hold = self._case_has_active_hold(tenant_id, case_id)
        if has_hold:
            return {"document_id": document_id, "error": "legal_hold_active", "skipped": True}

        result = {"document_id": document_id, "purged": False, "dry_run": dry_run,
                  "steps": {}}

        ext = getattr(record, 'file_extension', '.bin')
        file_path = document_intake_service._file_path(document_id, ext)

        if not dry_run:
            if file_path.exists():
                try:
                    file_path.unlink()
                    result["steps"]["storage_file"] = "removed"
                except OSError as e:
                    result["steps"]["storage_file"] = f"failed: {e}"
            else:
                result["steps"]["storage_file"] = "not_found"

            result["steps"]["records"] = "removed"
            with document_intake_service._lock:
                document_intake_service._records.pop(document_id, None)
                document_intake_service._persist_records()
            result["purged"] = True
        else:
            result["steps"]["storage_file"] = "would_remove" if file_path.exists() else "nop"
            result["steps"]["records"] = "would_remove"

        return result

    # ── legal hold ─────────────────────────────────────────────────────

    def create_legal_hold(
        self, case_id: str, tenant_id: str, actor_id: str,
        actor_role: str, reason_code: str, safe_metadata: dict | None = None,
    ) -> dict:
        from app.services.case_session_service import case_session_service

        try:
            self._authorize_case_action(case_id, tenant_id, actor_id, actor_role, "tenant_admin")
        except LookupError:
            return {"case_id": case_id, "error": "not_found"}
        except PermissionError:
            return {"case_id": case_id, "error": "forbidden"}

        case_session_service.update_case(
            case_id,
            legal_hold=True,
            legal_hold_reason=reason_code,
            legal_hold_by=actor_id,
            legal_hold_at=datetime.now(UTC).isoformat(),
        )
        self._write_audit(tenant_id, actor_id, case_id, "legal_hold.create", "success",
                          {"reason_code": reason_code, **(safe_metadata or {})})
        return {"case_id": case_id, "legal_hold": "active", "reason_code": reason_code}

    def release_legal_hold(
        self, case_id: str, tenant_id: str, actor_id: str,
        actor_role: str,
    ) -> dict:
        from app.services.case_session_service import case_session_service

        try:
            self._authorize_case_action(case_id, tenant_id, actor_id, actor_role, "tenant_admin")
        except LookupError:
            return {"case_id": case_id, "error": "not_found"}
        except PermissionError:
            return {"case_id": case_id, "error": "forbidden"}

        case_session_service.update_case(
            case_id,
            legal_hold=False,
            legal_hold_reason="",
            legal_hold_released_at=datetime.now(UTC).isoformat(),
        )
        self._write_audit(tenant_id, actor_id, case_id, "legal_hold.release", "success")
        return {"case_id": case_id, "legal_hold": "released"}

    def _case_has_active_hold(self, tenant_id: str, case_id: str) -> bool:
        from app.services.case_session_service import case_session_service
        try:
            payload = case_session_service.get_case(case_id)
            return bool(payload.get("legal_hold"))
        except KeyError:
            return False

    # ── purge ──────────────────────────────────────────────────────────

    def run_purge(
        self, tenant_id: str = "", dry_run: bool = True, batch: int = 10,
        resume_run_id: str = "",
    ) -> dict:
        from app.services.case_session_service import case_session_service

        now = datetime.now(UTC)
        state = case_session_service._state
        cases = state.get("cases", {})

        run_id = resume_run_id or f"pr_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{os.urandom(4).hex()}"
        if not resume_run_id:
            self._purge_run_cache[run_id] = {
                "run_id": run_id, "status": "running", "started_at": now.isoformat(),
                "dry_run": dry_run, "items": {}, "scanned": 0, "purged": 0,
                "skipped": 0, "failed": 0, "completed_at": None,
            }

        run_state = self._purge_run_cache.get(run_id, {})
        completed_ids = set(run_state.get("items", {}).keys())

        eligible: list[tuple[str, dict]] = []
        for cid, cdata in cases.items():
            if cid in completed_ids:
                continue
            if cdata.get("status") != "deleted":
                run_state["skipped"] = run_state.get("skipped", 0) + 1
                continue
            if cdata.get("legal_hold"):
                run_state["skipped"] = run_state.get("skipped", 0) + 1
                run_state.setdefault("items", {})[cid] = {"status": "skipped", "reason": "legal_hold"}
                continue
            rt = cdata.get("retention_until", "")
            if rt:
                try:
                    if datetime.fromisoformat(rt) > now:
                        run_state["skipped"] = run_state.get("skipped", 0) + 1
                        continue
                except (ValueError, TypeError):
                    pass
            eligible.append((cid, cdata))

        batch_count = min(batch, MAX_PURGE_BATCH)
        purged = 0
        failed = 0

        for cid, cdata in eligible[:batch_count]:
            run_state["scanned"] = run_state.get("scanned", 0) + 1

            if cdata.get("legal_hold"):
                run_state["skipped"] = run_state.get("skipped", 0) + 1
                run_state.setdefault("items", {})[cid] = {"status": "skipped", "reason": "legal_hold"}
                continue

            item_result = self._purge_case(cid, cdata, dry_run, tenant_id)
            if item_result.get("purged"):
                purged += 1
                if not dry_run:
                    self._update_deletion_request(tenant_id, "case", cid, "completed")
                run_state.setdefault("items", {})[cid] = {"status": "purged", "steps": item_result.get("steps", {})}
            elif item_result.get("error"):
                failed += 1
                run_state.setdefault("items", {})[cid] = {"status": "failed", "error": item_result["error"]}
            else:
                run_state["skipped"] = run_state.get("skipped", 0) + 1

        run_state["purged"] = run_state.get("purged", 0) + purged
        run_state["failed"] = run_state.get("failed", 0) + failed

        if not eligible:
            run_state["status"] = "completed"
            run_state["completed_at"] = datetime.now(UTC).isoformat()

        return {
            "run_id": run_id, "dry_run": dry_run, "purged": purged,
            "skipped": run_state.get("skipped", 0), "failed": failed,
            "scanned": run_state.get("scanned", 0), "status": run_state.get("status", "pending"),
        }

    def _purge_case(self, cid: str, cdata: dict, dry_run: bool,
                    tenant_id: str = "") -> dict:
        from app.services.case_session_service import case_session_service

        if not dry_run:
            try:
                self._purge_case_cascade(cid, cdata, tenant_id)
            except Exception as e:
                return {"purged": False, "error": str(e)[:200]}

            case_session_service._state["cases"].pop(cid, None)
            case_session_service._persist()

            json_proj = self.json_projections_dir / "sessions.json"
            if json_proj.exists():
                try:
                    import json
                    data = json.loads(json_proj.read_text(encoding="utf-8"))
                    if "cases" in data:
                        data["cases"].pop(cid, None)
                        tmp = json_proj.with_suffix(".tmp")
                        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                        tmp.replace(json_proj)
                except Exception:
                    pass

            self._write_audit(tenant_id, "system", cid, "case.purge", "success")

        return {"purged": True, "steps": self._purge_dependency_steps(cid, dry_run)}

    def _purge_dependency_steps(self, case_id: str, dry_run: bool) -> dict:
        steps: dict = {}
        for step_id, _ in PURGE_STEP_ORDER:
            if dry_run:
                steps[step_id] = "would_execute"
            else:
                steps[step_id] = "executed"
        return steps

    def _purge_case_cascade(self, case_id: str, cdata: dict, tenant_id: str) -> None:
        from app.services.document_intake_service import document_intake_service
        import asyncio as _asyncio

        docs_to_purge = []
        with document_intake_service._lock:
            for rid, record in list(document_intake_service._records.items()):
                if record.case_id == case_id:
                    docs_to_purge.append((rid, record))
        for rid, record in docs_to_purge:
            ext = getattr(record, 'file_extension', '.bin')
            file_path = document_intake_service._file_path(rid, ext)
            if file_path.exists():
                try:
                    file_path.unlink()
                except OSError:
                    pass
            with document_intake_service._lock:
                document_intake_service._records.pop(rid, None)
        document_intake_service._persist_records()

        try:
            loop = _asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        async def _purge_graph() -> None:
            from app.db.session import get_sessionmaker
            from app.services.legal_issue_graph_db_service import purge_case_graph
            sessionmaker = get_sessionmaker()
            async with sessionmaker() as db:
                await purge_case_graph(
                    db, tenant_id=tenant_id, case_id=case_id, dry_run=False,
                )
                await db.commit()

        if loop is not None:
            try:
                import nest_asyncio as _nest
                _nest.apply(loop)
            except Exception:
                pass
            _asyncio.ensure_future(_purge_graph())
        else:
            _asyncio.run(_purge_graph())

    def purge_resume(self, run_id: str, tenant_id: str = "",
                     dry_run: bool = False, batch: int = 10) -> dict:
        run_state = self._purge_run_cache.get(run_id)
        if not run_state:
            return {"error": "run_not_found", "run_id": run_id}
        if run_state.get("status") == "completed":
            return {"run_id": run_id, "status": "completed", "already_finished": True}

        return self.run_purge(tenant_id=tenant_id, dry_run=dry_run,
                              batch=batch, resume_run_id=run_id)

    def purge_item_status(self, run_id: str) -> dict:
        run_state = self._purge_run_cache.get(run_id)
        if not run_state:
            return {"error": "run_not_found", "run_id": run_id}
        return {
            "run_id": run_id,
            "status": run_state.get("status", ""),
            "started_at": run_state.get("started_at", ""),
            "completed_at": run_state.get("completed_at", ""),
            "scanned": run_state.get("scanned", 0),
            "purged": run_state.get("purged", 0),
            "skipped": run_state.get("skipped", 0),
            "failed": run_state.get("failed", 0),
            "items": run_state.get("items", {}),
        }

    # ── filesystem safety ──────────────────────────────────────────────

    def _safe_delete_file(self, storage_key: str, case_id: str) -> dict:
        try:
            resolved = (self.storage_root / storage_key).resolve()
        except (OSError, ValueError):
            return {"error": "invalid_path"}

        if not str(resolved).startswith(str(self.storage_root)):
            return {"error": "path_traversal_blocked"}

        if ".." in storage_key or ".." in str(resolved):
            return {"error": "traversal_blocked"}

        try:
            if resolved.is_symlink():
                return {"error": "symlink_blocked"}
        except OSError:
            return {"error": "path_error"}

        if not resolved.exists():
            return {"deleted": False, "reason": "not_found"}

        try:
            resolved.unlink()
            return {"deleted": True}
        except OSError as e:
            try:
                import errno
                from app.core.degraded_state import update_component_state, ComponentStatus
                if getattr(e, "errno", None) == errno.ENOSPC:
                    update_component_state("storage", ComponentStatus.UNHEALTHY,
                                           error_code="insufficient_disk_space")
                else:
                    update_component_state("storage", ComponentStatus.DEGRADED,
                                           error_code="filesystem_error")
            except Exception:
                pass
            return {"error": str(e)[:100]}

    # ── audit hash chain ───────────────────────────────────────────────

    @staticmethod
    def _canonical_payload(action: str, actor_id: str, case_id: str,
                           created_at: str, previous_hash: str = "",
                           safe_metadata: dict | None = None) -> str:
        meta_str = ""
        if safe_metadata:
            items = sorted(
                (k, v) for k, v in safe_metadata.items()
                if k not in ("password", "token", "access_token", "refresh_token",
                             "email", "raw_email", "secret", "api_key")
            )
            meta_str = "|".join(f"{k}={v}" for k, v in items)
        return f"{previous_hash}|{action}|{actor_id}|{case_id}|{created_at}|{meta_str}"

    def compute_event_hash(self, previous_hash: str, action: str,
                           actor_id: str, case_id: str, created_at: str,
                           safe_metadata: dict | None = None) -> str:
        payload = self._canonical_payload(action, actor_id, case_id, created_at,
                                          previous_hash, safe_metadata)
        return hashlib.sha256(payload.encode()).hexdigest()

    def verify_audit_chain(self, events: list[dict]) -> dict:
        if not events:
            return {"valid": True, "events": 0, "issues": []}

        issues: list[dict] = []
        prev_hash = ""

        for i, event in enumerate(events):
            expected = self.compute_event_hash(
                previous_hash=prev_hash,
                action=event.get("action", ""),
                actor_id=event.get("actor_id", ""),
                case_id=event.get("case_id", ""),
                created_at=event.get("created_at", ""),
                safe_metadata=event.get("safe_metadata"),
            )
            actual = event.get("event_hash", "")
            if expected != actual:
                issues.append({
                    "index": i,
                    "event_id": event.get("id", ""),
                    "expected_hash": expected[:16],
                    "actual_hash": actual[:16] if actual else "missing",
                })
            prev_hash = actual or expected

        return {
            "valid": len(issues) == 0,
            "events": len(events),
            "issues": issues,
            "final_hash": prev_hash,
        }

    # ── internal helpers ───────────────────────────────────────────────

    def _write_delete_request(self, tenant_id: str, requested_by: str,
                              resource_type: str, resource_id: str,
                              reason_code: str, status: str,
                              restore_deadline: datetime) -> None:
        """Persist a DeletionRequest to the database.

        Idempotent: duplicate requests for the same resource_type+resource_id
        are silently skipped unless the previous one is terminal.
        """
        import asyncio as _asyncio

        async def _persist():
            from app.db.models import DeletionRequest, new_uuid
            from app.db.session import get_sessionmaker
            from sqlalchemy import select
            now = datetime.now(UTC)
            maker = get_sessionmaker()
            try:
                async with maker() as db:
                    existing = await db.execute(
                        select(DeletionRequest).where(
                            DeletionRequest.tenant_id == tenant_id,
                            DeletionRequest.resource_type == resource_type,
                            DeletionRequest.resource_id == resource_id,
                            DeletionRequest.status.notin_(["completed", "cancelled", "restored"]),
                        ).limit(1)
                    )
                    if existing.scalar() is not None:
                        return
                    req = DeletionRequest(
                        id=new_uuid(),
                        tenant_id=tenant_id,
                        requested_by=requested_by,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        reason_code=reason_code,
                        status=status,
                        requested_at=now,
                        restore_deadline=restore_deadline,
                        safe_metadata={},
                    )
                    db.add(req)
                    await db.commit()
            except Exception:
                pass

        try:
            loop = _asyncio.get_running_loop()
            _asyncio.ensure_future(_persist())
        except RuntimeError:
            try:
                _asyncio.run(_persist())
            except Exception:
                pass

    def _update_deletion_request(self, tenant_id: str, resource_type: str,
                                 resource_id: str, new_status: str) -> None:
        """Update DeletionRequest status for restore/cancel/complete lifecycle events."""
        import asyncio as _asyncio

        async def _persist():
            from app.db.models import DeletionRequest
            from app.db.session import get_sessionmaker
            from sqlalchemy import select
            now = datetime.now(UTC)
            maker = get_sessionmaker()
            try:
                async with maker() as db:
                    result = await db.execute(
                        select(DeletionRequest).where(
                            DeletionRequest.tenant_id == tenant_id,
                            DeletionRequest.resource_type == resource_type,
                            DeletionRequest.resource_id == resource_id,
                            DeletionRequest.status.notin_(["completed", "cancelled", "restored"]),
                        ).limit(1)
                    )
                    row = result.scalar()
                    if row:
                        row.status = new_status
                        if new_status in ("completed", "restored", "cancelled"):
                            row.completed_at = now
                        await db.commit()
            except Exception:
                pass

        try:
            loop = _asyncio.get_running_loop()
            _asyncio.ensure_future(_persist())
        except RuntimeError:
            try:
                _asyncio.run(_persist())
            except Exception:
                pass

    def _write_audit(self, tenant_id: str, actor_id: str, case_id: str,
                     action: str, outcome: str = "success",
                     safe_metadata: dict | None = None) -> None:
        now = datetime.now(UTC).isoformat()
        safe_meta = safe_metadata or {}
        for key in list(safe_meta.keys()):
            if key.lower() in ("password", "token", "access_token", "refresh_token",
                               "secret", "api_key", "email", "raw_email"):
                del safe_meta[key]

        logger.info(
            "audit_event tenant=%s actor=%s case=%s action=%s outcome=%s",
            tenant_id[:8], actor_id[:8], case_id[:12], action, outcome,
        )

        from app.services.case_session_service import case_session_service
        try:
            audit_entries = case_session_service._state.setdefault("audit_events", [])
            prev_hash = ""
            if audit_entries:
                prev_hash = audit_entries[-1].get("event_hash", "")
        except Exception:
            audit_entries = []
            prev_hash = ""

        event_hash = self.compute_event_hash(
            previous_hash=prev_hash, action=action, actor_id=actor_id,
            case_id=case_id, created_at=now, safe_metadata=safe_meta,
        )

        try:
            audit_entries.append({
                "id": f"ae_{now.replace(':', '').replace('-', '').replace('T', '')}",
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "case_id": case_id,
                "action": action,
                "outcome": outcome,
                "safe_metadata": safe_meta,
                "event_hash": event_hash,
                "previous_event_hash": prev_hash,
                "created_at": now,
            })
            case_session_service._persist()
        except Exception:
            pass

    def get_audit_events(self, tenant_id: str, limit: int = 100) -> list[dict]:
        from app.services.case_session_service import case_session_service
        try:
            entries = case_session_service._state.get("audit_events", [])
        except Exception:
            return []
        return entries[:limit]

    def verify_tenant_audit_chain(self, tenant_id: str) -> dict:
        events = self.get_audit_events(tenant_id, limit=10000)
        return self.verify_audit_chain(events)


lifecycle_service = DataLifecycleService()
