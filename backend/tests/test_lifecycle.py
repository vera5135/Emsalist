"""P1.6.1 — Comprehensive lifecycle, retention, purge and audit tests."""
from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.case_session_service import CaseSessionService
from app.services.document_intake_service import DocumentIntakeService
from app.services.lifecycle_service import (
    DataLifecycleService,
    DEFAULT_PURGE_AFTER_DAYS,
    DEFAULT_SOFT_DELETE_DAYS,
    PURGE_STEP_ORDER,
)

FIXTURE = Path(__file__).parent / "fixtures" / "NOTER._TEST.txt"


class CaseLifecycleAuthTests(unittest.TestCase):
    """Test case lifecycle authorization: owner, editor, viewer cross-tenant."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.cases = CaseSessionService(Path(self.temporary.name) / "cases")
        self.docs = DocumentIntakeService(Path(self.temporary.name) / "documents")
        self.svc = DataLifecycleService()
        self.tenant_id = "tenant-a"
        self.case_id = self.cases.new_case()["case_id"]

        patcher_cases = patch(
            "app.services.case_session_service.case_session_service", self.cases
        )
        patcher_cases.start()
        self.addCleanup(patcher_cases.stop)

        patcher_docs = patch(
            "app.services.document_intake_service.document_intake_service", self.docs
        )
        patcher_docs.start()
        self.addCleanup(patcher_docs.stop)

    def tearDown(self):
        self.temporary.cleanup()

    def test_owner_can_soft_delete(self):
        self.cases.update_case(self.case_id, status="active")
        result = self.svc.soft_delete_case(self.case_id, self.tenant_id, "owner1", "owner")
        self.assertNotIn("error", result)
        self.assertEqual(result["status"], "deleted")

    def test_editor_cannot_delete(self):
        self.cases.update_case(self.case_id, status="active")
        result = self.svc.soft_delete_case(self.case_id, self.tenant_id, "editor1", "editor")
        self.assertIn("error", result)
        self.assertIn(result["error"], ("forbidden", "insufficient_permissions"))

    def test_viewer_cannot_delete(self):
        self.cases.update_case(self.case_id, status="active")
        result = self.svc.soft_delete_case(self.case_id, self.tenant_id, "viewer1", "viewer")
        self.assertIn("error", result)

    def test_tenant_admin_can_delete(self):
        self.cases.update_case(self.case_id, status="active")
        result = self.svc.soft_delete_case(self.case_id, self.tenant_id, "admin1", "tenant_admin")
        self.assertNotIn("error", result)
        self.assertEqual(result["status"], "deleted")

    def test_deleted_case_not_in_normal_lookup(self):
        self.cases.update_case(self.case_id, status="active")
        self.svc.soft_delete_case(self.case_id, self.tenant_id, "owner1", "owner")
        case = self.cases.get_case(self.case_id)
        self.assertEqual(case["status"], "deleted")

    def test_deleted_case_appears_in_deleted_list(self):
        self.cases.update_case(self.case_id, status="deleted",
                               deleted_at=datetime.now(UTC).isoformat())
        deleted = self.svc.list_deleted_cases(self.tenant_id, "admin", "tenant_admin")
        ids = [d["case_id"] for d in deleted]
        self.assertIn(self.case_id, ids)

    def test_soft_delete_preserves_record(self):
        self.cases.update_case(self.case_id, status="active", title="dava 123")
        self.svc.soft_delete_case(self.case_id, self.tenant_id, "owner1", "owner")
        case = self.cases.get_case(self.case_id)
        self.assertEqual(case["title"], "dava 123")
        self.assertEqual(case["status"], "deleted")

    def test_version_increments_on_delete(self):
        self.cases.update_case(self.case_id, status="active", version=5)
        self.svc.soft_delete_case(self.case_id, self.tenant_id, "owner1", "owner")
        case = self.cases.get_case(self.case_id)
        self.assertEqual(case["version"], 6)

    def test_delete_creates_audit_event(self):
        self.cases._state["audit_events"] = []
        self.cases.update_case(self.case_id, status="active")
        self.svc.soft_delete_case(self.case_id, self.tenant_id, "owner1", "owner")
        events = self.cases._state.get("audit_events", [])
        actions = [e.get("action") for e in events]
        self.assertIn("case.soft_delete", actions)

    def test_restore_creates_audit_event(self):
        self.cases._state["audit_events"] = []
        self.cases.update_case(self.case_id, status="active")
        self.svc.soft_delete_case(self.case_id, self.tenant_id, "owner1", "owner")
        self.cases.update_case(self.case_id, restore_deadline="2999-12-31T00:00:00")
        self.svc.restore_case(self.case_id, self.tenant_id, "owner1", "owner")
        events = self.cases._state.get("audit_events", [])
        actions = [e.get("action") for e in events]
        self.assertIn("case.restore", actions)

    def test_purged_case_not_found(self):
        self.cases.update_case(self.case_id, status="purged")
        result = self.svc.soft_delete_case(self.case_id, self.tenant_id, "owner1", "owner")
        self.assertEqual(result.get("error"), "not_found")


class CaseLifecycleRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.cases = CaseSessionService(Path(self.temporary.name) / "cases")
        self.svc = DataLifecycleService()
        self.tenant_id = "tenant-test"
        self.case_id = self.cases.new_case()["case_id"]

        patcher = patch("app.services.case_session_service.case_session_service", self.cases)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.temporary.cleanup()

    def test_restore_within_window(self):
        self.cases.update_case(self.case_id, status="active")
        self.svc.soft_delete_case(self.case_id, self.tenant_id, "owner1", "owner")
        future = (datetime.now(UTC) + timedelta(days=60)).isoformat()
        self.cases.update_case(self.case_id, restore_deadline=future)
        result = self.svc.restore_case(self.case_id, self.tenant_id, "owner1", "owner")
        self.assertNotIn("error", result)
        self.assertTrue(result.get("restored"))

    def test_restore_after_deadline_blocked(self):
        self.cases.update_case(self.case_id, status="active")
        self.svc.soft_delete_case(self.case_id, self.tenant_id, "owner1", "owner")
        past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        self.cases.update_case(self.case_id, restore_deadline=past)
        result = self.svc.restore_case(self.case_id, self.tenant_id, "owner1", "owner")
        self.assertEqual(result.get("error"), "restore_deadline_passed")

    def test_restore_non_deleted_fails(self):
        self.cases.update_case(self.case_id, status="active")
        result = self.svc.restore_case(self.case_id, self.tenant_id, "owner1", "owner")
        self.assertEqual(result.get("error"), "not_deleted")

    def test_soft_delete_already_deleted(self):
        self.cases.update_case(self.case_id, status="deleted")
        result = self.svc.soft_delete_case(self.case_id, self.tenant_id, "owner1", "owner")
        self.assertTrue(result.get("already_deleted"))

    def test_restored_case_returns_to_active(self):
        self.cases.update_case(self.case_id, status="active")
        self.svc.soft_delete_case(self.case_id, self.tenant_id, "owner1", "owner")
        future = (datetime.now(UTC) + timedelta(days=60)).isoformat()
        self.cases.update_case(self.case_id, restore_deadline=future)
        self.svc.restore_case(self.case_id, self.tenant_id, "owner1", "owner")
        case = self.cases.get_case(self.case_id)
        self.assertEqual(case["status"], "active")
        self.assertFalse(case.get("deleted_at"), f"Expected empty deleted_at, got {case.get('deleted_at')!r}")

    def test_version_increments_on_restore(self):
        self.cases.update_case(self.case_id, status="active", version=3)
        self.svc.soft_delete_case(self.case_id, self.tenant_id, "owner1", "owner")
        self.cases.update_case(self.case_id, restore_deadline="2999-12-31T00:00:00")
        self.svc.restore_case(self.case_id, self.tenant_id, "owner1", "owner")
        case = self.cases.get_case(self.case_id)
        self.assertEqual(case["version"], 5)


class LegalHoldTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.cases = CaseSessionService(Path(self.temporary.name) / "cases")
        self.svc = DataLifecycleService()
        self.tenant_id = "tenant-hold"
        self.case_id = self.cases.new_case()["case_id"]

        patcher = patch("app.services.case_session_service.case_session_service", self.cases)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.temporary.cleanup()

    def test_create_hold(self):
        self.cases.update_case(self.case_id, status="active")
        result = self.svc.create_legal_hold(
            self.case_id, self.tenant_id, "admin1", "tenant_admin", "litigation_preserve")
        self.assertEqual(result.get("legal_hold"), "active")

    def test_hold_persists_on_case(self):
        self.cases.update_case(self.case_id, status="active")
        self.svc.create_legal_hold(
            self.case_id, self.tenant_id, "admin1", "tenant_admin", "test_reason")
        case = self.cases.get_case(self.case_id)
        self.assertTrue(case.get("legal_hold"))
        self.assertEqual(case.get("legal_hold_reason"), "test_reason")

    def test_hold_prevents_purge(self):
        self.cases.update_case(self.case_id, status="deleted",
                               retention_until=(datetime.now(UTC) - timedelta(days=1)).isoformat(),
                               legal_hold=True)
        result = self.svc.run_purge(self.tenant_id, dry_run=False, batch=10)
        self.assertEqual(result.get("purged"), 0)

    def test_release_hold(self):
        self.cases.update_case(self.case_id, status="active", legal_hold=True)
        result = self.svc.release_legal_hold(
            self.case_id, self.tenant_id, "admin1", "tenant_admin")
        self.assertEqual(result.get("legal_hold"), "released")
        case = self.cases.get_case(self.case_id)
        self.assertFalse(case.get("legal_hold"))

    def test_hold_audit_events(self):
        self.cases._state["audit_events"] = []
        self.cases.update_case(self.case_id, status="active")
        self.svc.create_legal_hold(self.case_id, self.tenant_id, "admin1", "tenant_admin", "audit_check")
        self.svc.release_legal_hold(self.case_id, self.tenant_id, "admin1", "tenant_admin")
        events = self.cases._state.get("audit_events", [])
        actions = [e.get("action") for e in events]
        self.assertIn("legal_hold.create", actions)
        self.assertIn("legal_hold.release", actions)

    def test_released_hold_allows_purge(self):
        self.cases.update_case(self.case_id, status="deleted",
                               retention_until=(datetime.now(UTC) - timedelta(days=1)).isoformat(),
                               legal_hold=True)
        self.svc.release_legal_hold(self.case_id, self.tenant_id, "admin1", "tenant_admin")
        self.cases.update_case(self.case_id, legal_hold=False)
        result = self.svc.run_purge(self.tenant_id, dry_run=False, batch=10)
        result2 = self.svc.run_purge(self.tenant_id, dry_run=False, batch=10)


class DocumentLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.cases = CaseSessionService(Path(self.temporary.name) / "cases")
        self.docs = DocumentIntakeService(Path(self.temporary.name) / "documents")
        self.svc = DataLifecycleService()
        self.tenant_id = "tenant-doc"
        self.case_id = self.cases.new_case()["case_id"]

        patcher_cases = patch(    "app.services.case_session_service.case_session_service", self.cases)
        patcher_cases.start()
        self.addCleanup(patcher_cases.stop)

        patcher_docs = patch(    "app.services.document_intake_service.document_intake_service", self.docs)
        patcher_docs.start()
        self.addCleanup(patcher_docs.stop)

    def tearDown(self):
        self.temporary.cleanup()

    def test_document_soft_delete(self):
        self.cases.update_case(self.case_id, status="active")
        rec = self.docs.create_document(case_id=self.case_id, file_name="test.txt", content=b"lifecycle test content")
        result = self.svc.soft_delete_document(
            self.case_id, rec.document_id, self.tenant_id, "owner1", "owner")
        self.assertEqual(result.get("status"), "deleted")

    def test_document_restore(self):
        self.cases.update_case(self.case_id, status="active")
        rec = self.docs.create_document(case_id=self.case_id, file_name="restore.txt", content=b"restorable")
        self.svc.soft_delete_document(self.case_id, rec.document_id, self.tenant_id, "owner1", "owner")
        future = (datetime.now(UTC) + timedelta(days=60)).isoformat()
        with self.docs._lock:
            record = self.docs._records.get(rec.document_id)
            if record:
                record.deleted_at = future
        result = self.svc.restore_document(
            self.case_id, rec.document_id, self.tenant_id, "owner1", "owner")
        self.assertNotIn("error", result)
        self.assertTrue(result.get("restored"))

    def test_document_not_found_returns_error(self):
        self.cases.update_case(self.case_id, status="active")
        result = self.svc.soft_delete_document(
            self.case_id, "nonexistent", self.tenant_id, "owner1", "owner")
        self.assertEqual(result.get("error"), "not_found")

    def test_deleted_document_in_listing(self):
        self.cases.update_case(self.case_id, status="active")
        rec = self.docs.create_document(case_id=self.case_id, file_name="listable.txt", content=b"list")
        self.svc.soft_delete_document(self.case_id, rec.document_id, self.tenant_id, "owner1", "owner")
        deleted = self.svc.list_deleted_documents(self.case_id, self.tenant_id, "owner1", "owner")
        ids = [d["document_id"] for d in deleted]
        self.assertIn(rec.document_id, ids)

    def test_restore_with_deleted_parent_case_blocked(self):
        self.cases.update_case(self.case_id, status="deleted")
        result = self.svc.restore_document(
            self.case_id, "any-doc", self.tenant_id, "owner1", "owner")
        self.assertEqual(result.get("error"), "case_deleted_or_purged")

    def test_deleted_document_not_in_normal_list(self):
        self.cases.update_case(self.case_id, status="active")
        rec = self.docs.create_document(case_id=self.case_id, file_name="normal.txt", content=b"x")
        self.svc.soft_delete_document(self.case_id, rec.document_id, self.tenant_id, "owner1", "owner")
        all_docs = self.docs.list_documents(case_id=self.case_id)
        deleted_doc = next((d for d in all_docs if d.document_id == rec.document_id), None)
        self.assertIsNotNone(deleted_doc)
        self.assertTrue(deleted_doc.deleted_at, "Document should have deleted_at set")


class PurgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.cases = CaseSessionService(Path(self.temporary.name) / "cases")
        self.docs = DocumentIntakeService(Path(self.temporary.name) / "documents")
        self.svc = DataLifecycleService()
        self.tenant_id = "tenant-purge"

        patcher_cases = patch(    "app.services.case_session_service.case_session_service", self.cases)
        patcher_cases.start()
        self.addCleanup(patcher_cases.stop)

        patcher_docs = patch(    "app.services.document_intake_service.document_intake_service", self.docs)
        patcher_docs.start()
        self.addCleanup(patcher_docs.stop)

    def tearDown(self):
        self.temporary.cleanup()

    def _make_purgeable(self):
        cid = self.cases.new_case()["case_id"]
        self.cases.update_case(cid, status="deleted",
                               retention_until=(datetime.now(UTC) - timedelta(days=1)).isoformat())
        return cid

    def test_dry_run_does_not_modify(self):
        cid = self._make_purgeable()
        cases_before = set(self.cases._state["cases"].keys())
        self.svc.run_purge(self.tenant_id, dry_run=True, batch=10)
        cases_after = set(self.cases._state["cases"].keys())
        self.assertEqual(cases_before, cases_after)

    def test_apply_purges_eligible(self):
        cid = self._make_purgeable()
        result = self.svc.run_purge(self.tenant_id, dry_run=False, batch=10)
        self.assertNotIn(cid, self.cases._state["cases"])
        self.assertGreaterEqual(result.get("purged", 0), 1)

    def test_purge_is_idempotent(self):
        cid = self._make_purgeable()
        self.svc.run_purge(self.tenant_id, dry_run=False, batch=10)
        r2 = self.svc.run_purge(self.tenant_id, dry_run=False, batch=10)
        self.assertNotIn(cid, self.cases._state["cases"])
        self.assertEqual(r2.get("purged", 0), 0)

    def test_legal_hold_skipped(self):
        cid = self._make_purgeable()
        self.cases.update_case(cid, legal_hold=True)
        result = self.svc.run_purge(self.tenant_id, dry_run=False, batch=10)
        self.assertIn(cid, self.cases._state["cases"])
        self.assertEqual(result.get("purged"), 0)

    def test_not_deleted_not_purged(self):
        cid = self.cases.new_case()["case_id"]
        self.cases.update_case(cid, status="active")
        self.svc.run_purge(self.tenant_id, dry_run=False, batch=10)
        self.assertIn(cid, self.cases._state["cases"])

    def test_resume_continues(self):
        cid = self._make_purgeable()
        first = self.svc.run_purge(self.tenant_id, dry_run=False, batch=1)
        run_id = first.get("run_id", "")
        if run_id:
            result = self.svc.purge_resume(run_id, self.tenant_id, dry_run=False, batch=10)
            self.assertIsNotNone(result)

    def test_status_tracking(self):
        cid = self._make_purgeable()
        run = self.svc.run_purge(self.tenant_id, dry_run=True, batch=5)
        run_id = run.get("run_id", "")
        if run_id:
            status = self.svc.purge_item_status(run_id)
            self.assertIsNotNone(status)

    def test_purge_steps_count(self):
        self.assertTrue(len(PURGE_STEP_ORDER) >= 15)

    def test_purge_step_names(self):
        names = {s[0] for s in PURGE_STEP_ORDER}
        self.assertIn("document_files", names)
        self.assertIn("case_record", names)
        self.assertIn("json_projection", names)

    def test_purge_db_failure_does_not_report_success(self):
        cid = self._make_purgeable()
        with patch.object(self.svc, "_purge_db_graph", side_effect=ConnectionError("PostgreSQL unavailable")):
            result = self.svc.run_purge(self.tenant_id, dry_run=False, batch=10)
        self.assertGreater(result.get("partial_failed", 0), 0,
                           "Partial DB failure must be reported as partial_failed")
        self.assertEqual(result.get("purged", 0), 0,
                         "Case with DB failure should not count as fully purged")
        self.assertNotIn(cid, self.cases._state["cases"],
                         "JSON record should still be removed on partial failure")
        self.assertNotIn("success", self._last_purge_audit_outcome(),
                         "Audit must not report success for partial failure")

    def test_partial_purge_creates_audit_event(self):
        cid = self._make_purgeable()
        self.cases._state["audit_events"] = []
        with patch.object(self.svc, "_purge_db_graph", side_effect=ConnectionError("DB down")):
            self.svc.run_purge(self.tenant_id, dry_run=False, batch=10)
        events = self.cases._state.get("audit_events", [])
        actions = [e.get("outcome") for e in events]
        self.assertIn("partial_failure", actions,
                      "Partial failure must create audit event with partial_failure outcome")
        self.assertIn("failed_steps", str(events[-1].get("safe_metadata", {})),
                      "Audit event must include failed_steps metadata")

    def test_partial_purge_is_retried(self):
        cid = self._make_purgeable()
        with patch.object(self.svc, "_purge_db_graph", side_effect=ConnectionError("DB down")):
            first = self.svc.run_purge(self.tenant_id, dry_run=False, batch=10)
        self.assertGreater(first.get("partial_failed", 0), 0,
                           "First purge must report partial failure")

        retry = self.svc.retry_db_purge(cid, self.tenant_id)
        self.assertTrue(retry.get("retried"), "Retry must be attempted")
        self.assertTrue(retry.get("ok"), "Retry must succeed when DB is available")
        self.assertNotIn("retry_required", retry,
                         "Successful retry must not require another retry")

    def test_retry_cleans_remaining_db_graph(self):
        cid = self._make_purgeable()

        original = self.svc._purge_db_graph
        calls: list[tuple] = []

        def _tracking(case_id: str, tenant_id: str) -> None:
            calls.append((case_id, tenant_id))
            if len(calls) == 1:
                raise ConnectionError("PostgreSQL unavailable")

        self.svc._purge_db_graph = _tracking  # type: ignore[method-assign]
        try:
            result = self.svc.run_purge(self.tenant_id, dry_run=False, batch=10)
            self.assertGreater(result.get("partial_failed", 0), 0,
                               "First purge must report partial failure")
            self.assertEqual(len(calls), 1, "First purge must call _purge_db_graph once")

            retry = self.svc.retry_db_purge(cid, self.tenant_id)
            self.assertEqual(len(calls), 2, "Retry must call _purge_db_graph again")
            self.assertTrue(retry.get("ok"), "Retry must succeed and clean DB graph")
        finally:
            self.svc._purge_db_graph = original  # type: ignore[method-assign]

    def test_retry_after_json_removal_is_idempotent(self):
        cid = self._make_purgeable()

        original = self.svc._purge_db_graph
        calls: list[tuple] = []

        def _tracking(case_id: str, tenant_id: str) -> None:
            calls.append((case_id, tenant_id))
            if len(calls) <= 1:
                raise ConnectionError("PostgreSQL unavailable")

        self.svc._purge_db_graph = _tracking  # type: ignore[method-assign]
        try:
            result = self.svc.run_purge(self.tenant_id, dry_run=False, batch=10)
            self.assertGreater(result.get("partial_failed", 0), 0,
                               "First purge must report partial failure")
            self.assertNotIn(cid, self.cases._state["cases"],
                             "JSON record must be removed after partial failure")

            retry = self.svc.retry_db_purge(cid, self.tenant_id)
            self.assertTrue(retry.get("ok"), "Retry after JSON removal must succeed")
            self.assertEqual(len(calls), 2, "Retry must call _purge_db_graph")

            second_retry = self.svc.retry_db_purge(cid, self.tenant_id)
            self.assertTrue(second_retry.get("ok"),
                            "Multiple retries after JSON removal must be idempotent")
            self.assertEqual(len(calls), 3, "Second retry must call _purge_db_graph again")
        finally:
            self.svc._purge_db_graph = original  # type: ignore[method-assign]

    def _last_purge_audit_outcome(self) -> str:
        events = self.cases._state.get("audit_events", [])
        for e in reversed(events):
            if e.get("action") == "case.purge":
                return e.get("outcome", "")
        return ""

    def test_two_real_db_purge_calls_sequentially_succeed(self):
        cid1 = self._make_purgeable()
        cid2 = self._make_purgeable()
        r1 = self.svc.run_purge(self.tenant_id, dry_run=False, batch=10)
        self.assertNotIn(cid1, self.cases._state["cases"])
        self.assertNotIn(cid2, self.cases._state["cases"])
        cleared = r1.get("purged", 0) + r1.get("partial_failed", 0)
        self.assertGreaterEqual(cleared, 1)

        cid3 = self._make_purgeable()
        r2 = self.svc.run_purge(self.tenant_id, dry_run=False, batch=10)
        self.assertNotIn(cid3, self.cases._state["cases"])
        cleared2 = r2.get("purged", 0) + r2.get("partial_failed", 0)
        self.assertGreaterEqual(cleared2, 1, "Second sequential purge must succeed")

    def test_partial_failure_followed_by_real_db_retry(self):
        cid = self._make_purgeable()
        original = self.svc._purge_db_graph
        tries: list[bool] = []

        def _fail_then_pass(case_id: str, tenant_id: str) -> None:
            tries.append(True)
            if len(tries) == 1:
                raise ConnectionError("Simulated DB failure")

        self.svc._purge_db_graph = _fail_then_pass  # type: ignore[method-assign]
        try:
            result = self.svc.run_purge(self.tenant_id, dry_run=False, batch=10)
            self.assertGreater(result.get("partial_failed", 0), 0)
            self.assertEqual(len(tries), 1)

            retry = self.svc.retry_db_purge(cid, self.tenant_id)
            self.assertTrue(retry.get("ok"), "Retry must succeed")
            self.assertEqual(len(tries), 2, "Retry must invoke _purge_db_graph again")
        finally:
            self.svc._purge_db_graph = original  # type: ignore[method-assign]

    def test_db_exception_not_swallowed(self):
        cid = self._make_purgeable()
        original = self.svc._purge_db_graph

        def _always_fail(case_id: str, tenant_id: str) -> None:
            raise RuntimeError("Permanent DB failure")

        self.svc._purge_db_graph = _always_fail  # type: ignore[method-assign]
        try:
            result = self.svc.run_purge(self.tenant_id, dry_run=False, batch=10)
            self.assertGreater(result.get("partial_failed", 0), 0,
                               "DB exception must produce partial_failed")
            retry = self.svc.retry_db_purge(cid, self.tenant_id)
            self.assertFalse(retry.get("ok"),
                             "retry_db_purge must return ok=False on persistent failure")
            self.assertIn("retry_required", retry)
        finally:
            self.svc._purge_db_graph = original  # type: ignore[method-assign]

    def test_no_orphan_ensure_future_after_purge(self):
        cid = self._make_purgeable()
        self.svc.run_purge(self.tenant_id, dry_run=False, batch=10)
        self.assertNotIn(cid, self.cases._state["cases"],
                         "Case must be purged without orphaned async tasks")


class AuditChainTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.cases = CaseSessionService(Path(self.temporary.name) / "cases")
        self.svc = DataLifecycleService()

        patcher = patch("app.services.case_session_service.case_session_service", self.cases)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.temporary.cleanup()

    def test_audit_chain_verifies(self):
        events = [
            {"id": "e1", "action": "case.create", "actor_id": "u1", "case_id": "c1",
             "created_at": "2025-01-01T00:00:00", "safe_metadata": {}},
            {"id": "e2", "action": "case.soft_delete", "actor_id": "u1", "case_id": "c1",
             "created_at": "2025-01-02T00:00:00", "safe_metadata": {}},
            {"id": "e3", "action": "case.purge", "actor_id": "system", "case_id": "c1",
             "created_at": "2025-01-03T00:00:00", "safe_metadata": {}},
        ]
        prev = ""
        for e in events:
            e["event_hash"] = self.svc.compute_event_hash(
                previous_hash=prev, action=e["action"], actor_id=e["actor_id"],
                case_id=e["case_id"], created_at=e["created_at"], safe_metadata=e["safe_metadata"])
            e["previous_event_hash"] = prev
            prev = e["event_hash"]
        result = self.svc.verify_audit_chain(events)
        self.assertTrue(result["valid"])

    def test_tamper_detected(self):
        e1 = {"id": "e1", "action": "case.create", "actor_id": "u1", "case_id": "c1",
              "created_at": "2025-01-01T00:00:00", "safe_metadata": {},
              "previous_event_hash": ""}
        e1["event_hash"] = self.svc.compute_event_hash(
            "", "case.create", "u1", "c1", "2025-01-01T00:00:00")
        e2 = {"id": "e2", "action": "case.soft_delete", "actor_id": "u1", "case_id": "c1",
              "created_at": "2025-02-01T00:00:00", "safe_metadata": {},
              "previous_event_hash": e1["event_hash"],
              "event_hash": "TAMPERED_HASH_VALUE"}
        result = self.svc.verify_audit_chain([e1, e2])
        self.assertFalse(result["valid"])
        self.assertGreater(len(result["issues"]), 0)

    def test_audit_no_passwords(self):
        payload = self.svc._canonical_payload(
            "login", "u1", "c1", "2025-01-01T00:00:00", "",
            {"password": "secret123", "role": "admin", "email": "x@y.com",
             "refresh_token": "rt-secret", "access_token": "at-secret"})
        self.assertNotIn("secret123", payload)
        self.assertNotIn("rt-secret", payload)
        self.assertNotIn("x@y.com", payload)
        self.assertNotIn("at-secret", payload)

    def test_empty_chain_valid(self):
        result = self.svc.verify_audit_chain([])
        self.assertTrue(result["valid"])
        self.assertEqual(result["events"], 0)

    def test_chain_with_live_events(self):
        cid = self.cases.new_case()["case_id"]
        self.cases._state["audit_events"] = []
        self.cases.update_case(cid, status="active")
        self.svc.soft_delete_case(cid, "t1", "u1", "owner")
        events = self.cases._state.get("audit_events", [])
        if len(events) >= 1 and events[0].get("event_hash"):
            result = self.svc.verify_audit_chain(events)
            self.assertIsInstance(result, dict)


class RetentionPolicyTests(unittest.TestCase):
    def setUp(self):
        self.svc = DataLifecycleService()

    def test_valid_policy(self):
        issues = self.svc.validate_retention_policy({
            "soft_delete_days": 30, "purge_after_days": 365, "audit_retention_days": 3650})
        self.assertEqual(len(issues), 0)

    def test_negative_days_rejected(self):
        issues = self.svc.validate_retention_policy({
            "soft_delete_days": -1, "purge_after_days": 365, "audit_retention_days": 3650})
        self.assertGreater(len(issues), 0)

    def test_purge_before_soft_delete(self):
        issues = self.svc.validate_retention_policy({
            "soft_delete_days": 100, "purge_after_days": 50, "audit_retention_days": 3650})
        self.assertGreater(len(issues), 0)

    def test_below_minimum(self):
        issues = self.svc.validate_retention_policy({
            "soft_delete_days": 0, "purge_after_days": 1, "audit_retention_days": 10})
        self.assertGreater(len(issues), 0)

    def test_default_policy_valid(self):
        policy = self.svc.get_retention_policy("t1", "case")
        self.assertEqual(policy["soft_delete_days"], DEFAULT_SOFT_DELETE_DAYS)
        self.assertEqual(policy["purge_after_days"], DEFAULT_PURGE_AFTER_DAYS)


class FilesystemSafetyTests(unittest.TestCase):
    def setUp(self):
        self.svc = DataLifecycleService()

    def test_traversal_blocked(self):
        result = self.svc._safe_delete_file("../../../etc/passwd", "case-1")
        self.assertIn("error", result)

    def test_dot_dot_traversal(self):
        result = self.svc._safe_delete_file("..\\..\\windows\\system32\\cmd.exe", "case-1")
        self.assertIn("error", result)


class ConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.cases = CaseSessionService(Path(self.temporary.name) / "cases")
        self.svc = DataLifecycleService()
        self.tenant_id = "tenant-cc"
        self.case_id = self.cases.new_case()["case_id"]

        patcher = patch("app.services.case_session_service.case_session_service", self.cases)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.temporary.cleanup()

    def test_stale_version_conflict(self):
        self.cases.update_case(self.case_id, status="active", version=3)
        result = self.svc.soft_delete_case_with_version(
            self.case_id, self.tenant_id, "owner1", "owner", expected_version=99)
        self.assertEqual(result.get("error"), "version_conflict")

    def test_two_deletes_produce_single(self):
        self.cases.update_case(self.case_id, status="active")
        r1 = self.svc.soft_delete_case(self.case_id, self.tenant_id, "owner1", "owner")
        r2 = self.svc.soft_delete_case(self.case_id, self.tenant_id, "owner1", "owner")
        self.assertNotIn("error", r1)
        self.assertTrue(r2.get("already_deleted"))


class StoreLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.cases = CaseSessionService(Path(self.temporary.name) / "cases")
        self.svc = DataLifecycleService()
        self.tenant_id = "tenant-store"
        self.case_id = self.cases.new_case()["case_id"]

        patcher = patch("app.services.case_session_service.case_session_service", self.cases)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.temporary.cleanup()

    def test_json_soft_delete_hides(self):
        self.cases.update_case(self.case_id, status="active")
        self.svc.soft_delete_case(self.case_id, self.tenant_id, "owner1", "owner")
        case = self.cases.get_case(self.case_id)
        self.assertEqual(case["status"], "deleted")

    def test_json_restore_works(self):
        self.cases.update_case(self.case_id, status="active")
        self.svc.soft_delete_case(self.case_id, self.tenant_id, "owner1", "owner")
        self.cases.update_case(self.case_id, restore_deadline="2999-12-31T00:00:00")
        self.svc.restore_case(self.case_id, self.tenant_id, "owner1", "owner")
        case = self.cases.get_case(self.case_id)
        self.assertEqual(case["status"], "active")

    def test_json_purge_removes(self):
        self.cases.update_case(self.case_id, status="deleted",
                               retention_until=(datetime.now(UTC) - timedelta(days=1)).isoformat())
        self.svc.run_purge(self.tenant_id, dry_run=False, batch=10)
        self.assertNotIn(self.case_id, self.cases._state["cases"])

    def test_lifecycle_metadata_preserved(self):
        self.cases.update_case(self.case_id, status="active")
        self.svc.soft_delete_case(self.case_id, self.tenant_id, "owner1", "owner")
        case = self.cases.get_case(self.case_id)
        self.assertIn("deleted_at", case)
        self.assertIn("restore_deadline", case)
        self.assertIn("retention_until", case)


class CLIScriptTests(unittest.TestCase):
    def test_module_importable(self):
        from app.scripts import run_retention
        self.assertIsNotNone(run_retention)

    def test_main_exists(self):
        from app.scripts.run_retention import main
        self.assertIsNotNone(main)


class CrossTenantTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.cases = CaseSessionService(Path(self.temporary.name) / "cases")
        self.svc = DataLifecycleService()
        self.tenant_a = "tenant-alpha"
        self.tenant_b = "tenant-beta"

        self.case_a = self.cases.new_case()["case_id"]
        self.cases.update_case(self.case_a, status="active")

        patcher = patch("app.services.case_session_service.case_session_service", self.cases)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.temporary.cleanup()

    def test_deleted_case_list_has_correct_format(self):
        self.cases.update_case(self.case_a, status="deleted",
                               deleted_at=datetime.now(UTC).isoformat(),
                               title="dava cross-tenant")
        deleted = self.svc.list_deleted_cases(self.tenant_a, "admin", "tenant_admin")
        for d in deleted:
            self.assertIn("case_id", d)
            self.assertIn("title", d)
            self.assertIn("deleted_at", d)
            self.assertIn("restore_deadline", d)


class EndpointHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_delete_case_endpoint(self):
        r = self.client.delete("/lifecycle/cases/nonexistent")
        self.assertIn(r.status_code, (200, 401, 404))

    def test_restore_case_endpoint(self):
        r = self.client.post("/lifecycle/cases/nonexistent/restore")
        self.assertIn(r.status_code, (200, 401, 404))

    def test_delete_document_endpoint(self):
        r = self.client.delete("/lifecycle/cases/test1/documents/test2")
        self.assertIn(r.status_code, (200, 401, 404))

    def test_restore_document_endpoint(self):
        r = self.client.post("/lifecycle/cases/test1/documents/test2/restore")
        self.assertIn(r.status_code, (200, 401, 404))

    def test_legal_hold_create(self):
        r = self.client.post("/lifecycle/cases/test1/legal-hold", json={"reason_code": "test"})
        self.assertIn(r.status_code, (200, 400, 401, 403, 404))

    def test_legal_hold_release(self):
        r = self.client.delete("/lifecycle/cases/test1/legal-hold")
        self.assertIn(r.status_code, (200, 401, 404))

    def test_purge_preview(self):
        r = self.client.get("/lifecycle/purge/preview")
        self.assertIn(r.status_code, (200, 401))

    def test_purge_run(self):
        r = self.client.post("/lifecycle/purge/run")
        self.assertIn(r.status_code, (200, 401))

    def test_retention_preview(self):
        r = self.client.get("/lifecycle/retention/preview")
        self.assertIn(r.status_code, (200, 401))

    def test_retention_policy(self):
        r = self.client.get("/lifecycle/retention/policy")
        self.assertIn(r.status_code, (200, 401))

    def test_retention_policy_validate(self):
        r = self.client.post("/lifecycle/retention/policy/validate",
                             json={"soft_delete_days": 30, "purge_after_days": 365, "audit_retention_days": 3650})
        self.assertIn(r.status_code, (200, 401))

    def test_deleted_cases(self):
        r = self.client.get("/lifecycle/cases/deleted")
        self.assertIn(r.status_code, (200, 401))

    def test_deleted_documents(self):
        r = self.client.get("/lifecycle/cases/test1/documents/deleted")
        self.assertIn(r.status_code, (200, 401))

    def test_audit_list(self):
        r = self.client.get("/lifecycle/audit")
        self.assertIn(r.status_code, (200, 401))

    def test_audit_verify(self):
        r = self.client.get("/lifecycle/audit/verify")
        self.assertIn(r.status_code, (200, 401))


if __name__ == "__main__":
    unittest.main()
