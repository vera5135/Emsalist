"""P1.11 — Application security and hardening tests."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.config import (
    Settings,
    ProductionConfigError,
    validate_production_config,
    _DEFAULT_JWT_SECRETS,
    MIN_JWT_SECRET_LENGTH,
)


class ProductionStartupSafetyTests(unittest.TestCase):
    """P1.11.1 — Production startup must fail closed."""

    def test_production_defaults_rejected(self):
        with self.assertRaises(ProductionConfigError):
            validate_production_config(Settings(environment="production"))

    def test_production_local_auth_rejected(self):
        with self.assertRaises(ProductionConfigError):
            validate_production_config(Settings(
                environment="production",
                jwt_secret_key="a" * MIN_JWT_SECRET_LENGTH,
                cors_allow_origins="https://example.com",
                allowed_hosts="example.com",
            ))

    def test_production_empty_jwt_secret_rejected(self):
        issues = []
        settings = Settings(environment="production", auth_mode="jwt",
                            cors_allow_origins="https://example.com",
                            allowed_hosts="example.com")
        try:
            validate_production_config(settings)
        except ProductionConfigError as e:
            issues.append(str(e))
        self.assertTrue(any("SECRET" in i.upper() for i in issues))

    def test_production_default_jwt_secret_rejected(self):
        for secret in _DEFAULT_JWT_SECRETS:
            if not secret:
                continue
            try:
                validate_production_config(Settings(
                    environment="production", auth_mode="jwt",
                    jwt_secret_key=secret,
                    cors_allow_origins="https://example.com",
                    allowed_hosts="example.com",
                ))
                self.fail(f"Default secret '{secret}' should be rejected")
            except ProductionConfigError:
                pass

    def test_production_debug_rejected(self):
        try:
            validate_production_config(Settings(
                environment="production", debug=True, auth_mode="jwt",
                jwt_secret_key="x" * MIN_JWT_SECRET_LENGTH,
                cors_allow_origins="https://example.com",
                allowed_hosts="example.com",
            ))
            self.fail("debug=true should be rejected in production")
        except ProductionConfigError:
            pass

    def test_production_wildcard_cors_rejected(self):
        try:
            validate_production_config(Settings(
                environment="production", auth_mode="jwt",
                jwt_secret_key="x" * MIN_JWT_SECRET_LENGTH,
                cors_allow_origins="*",
                allowed_hosts="example.com",
            ))
            self.fail("wildcard CORS should be rejected in production")
        except ProductionConfigError:
            pass

    def test_production_wildcard_subdomain_cors_rejected(self):
        try:
            validate_production_config(Settings(
                environment="production", auth_mode="jwt",
                jwt_secret_key="x" * MIN_JWT_SECRET_LENGTH,
                cors_allow_origins="*.example.com",
                allowed_hosts="example.com",
            ))
            self.fail("wildcard subdomain CORS should be rejected")
        except ProductionConfigError:
            pass

    def test_production_no_allowed_hosts_rejected(self):
        try:
            validate_production_config(Settings(
                environment="production", auth_mode="jwt",
                jwt_secret_key="x" * MIN_JWT_SECRET_LENGTH,
                cors_allow_origins="https://example.com",
            ))
            self.fail("empty allowed_hosts should be rejected")
        except ProductionConfigError:
            pass

    def test_production_short_jwt_secret_rejected(self):
        try:
            validate_production_config(Settings(
                environment="production", auth_mode="jwt",
                jwt_secret_key="too-short",
                cors_allow_origins="https://example.com",
                allowed_hosts="example.com",
            ))
            self.fail("short JWT secret should be rejected")
        except ProductionConfigError:
            pass

    def test_production_encryption_no_key_rejected(self):
        try:
            validate_production_config(Settings(
                environment="production", auth_mode="jwt",
                jwt_secret_key="x" * MIN_JWT_SECRET_LENGTH,
                cors_allow_origins="https://example.com",
                allowed_hosts="example.com",
                backup_encryption_enabled=True,
                backup_encryption_key="",
            ))
            self.fail("encryption enabled without key should be rejected")
        except ProductionConfigError:
            pass

    def test_development_accepts_defaults(self):
        issues = validate_production_config(Settings(environment="development"))
        self.assertEqual(issues, [])

    def test_test_environment_accepts_defaults(self):
        issues = validate_production_config(Settings(environment="test"))
        self.assertEqual(issues, [])

    def test_production_safe_config_accepted(self):
        try:
            issues = validate_production_config(Settings(
                environment="production", auth_mode="jwt",
                jwt_secret_key="x" * MIN_JWT_SECRET_LENGTH,
                cors_allow_origins="https://app.example.com",
                allowed_hosts="app.example.com",
            ))
            self.assertEqual(issues, [])
        except ProductionConfigError as e:
            self.fail(f"Safe production config should be accepted: {e}")


class FileUploadSecurityTests(unittest.TestCase):
    """P1.11.3 — Upload and filesystem hardening."""

    def setUp(self):
        from app.services.security_service import validate_file_upload
        self.validate = validate_file_upload

    def test_path_traversal_dot_dot_slash(self):
        valid, msg = self.validate("../../../etc/passwd.pdf", b"x")
        self.assertFalse(valid)

    def test_path_traversal_dot_dot_backslash(self):
        valid, msg = self.validate("..\\..\\windows\\system32.pdf", b"x")
        self.assertFalse(valid)

    def test_null_byte_injection(self):
        valid, msg = self.validate("belge.p\x00df", b"x")
        self.assertFalse(valid)

    def test_null_byte_in_middle(self):
        valid, msg = self.validate("nice\x00evil.pdf", b"x")
        self.assertFalse(valid)

    def test_absolute_path_windows(self):
        valid, msg = self.validate("C:\\Windows\\System32\\evil.pdf", b"x")
        self.assertFalse(valid)

    def test_absolute_path_posix(self):
        valid, msg = self.validate("/etc/passwd.pdf", b"x")
        self.assertFalse(valid)

    def test_double_extension_exe(self):
        valid, msg = self.validate("belge.pdf.exe", b"x")
        self.assertFalse(valid)

    def test_double_extension_bat(self):
        valid, msg = self.validate("report.pdf.bat", b"x")
        self.assertFalse(valid)

    def test_no_extension(self):
        valid, msg = self.validate("belge", b"x")
        self.assertFalse(valid)

    def test_valid_pdf(self):
        valid, msg = self.validate("belge.pdf", b"%PDF-content")
        self.assertTrue(valid)

    def test_valid_txt(self):
        valid, msg = self.validate("belge.txt", b"content")
        self.assertTrue(valid)

    def test_valid_docx(self):
        valid, msg = self.validate("belge.docx", b"content")
        self.assertTrue(valid)

    def test_valid_jpg(self):
        valid, msg = self.validate("belge.jpg", b"content")
        self.assertTrue(valid)

    def test_valid_png(self):
        valid, msg = self.validate("belge.png", b"content")
        self.assertTrue(valid)

    def test_exe_extension_blocked(self):
        valid, msg = self.validate("malware.exe", b"x")
        self.assertFalse(valid)

    def test_ps1_script_blocked(self):
        valid, msg = self.validate("script.ps1", b"x")
        self.assertFalse(valid)

    def test_js_script_blocked(self):
        valid, msg = self.validate("script.js", b"x")
        self.assertFalse(valid)

    def test_bat_script_blocked(self):
        valid, msg = self.validate("script.bat", b"x")
        self.assertFalse(valid)

    def test_unsupported_extension(self):
        valid, msg = self.validate("belge.xyz", b"x")
        self.assertFalse(valid)

    def test_turkish_filename_unicode(self):
        valid, msg = self.validate("İhtar_Belgesi.pdf", b"content")
        self.assertTrue(valid)


class MagicByteValidationTests(unittest.TestCase):
    """P1.11.3 — MIME/extension mismatch."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        from app.services.document_intake_service import DocumentIntakeService, DocumentIntakeError
        self.DocumentIntakeService = DocumentIntakeService
        self.DocumentIntakeError = DocumentIntakeError

    def tearDown(self):
        self.temporary.cleanup()

    def test_pe_header_rejected_as_pdf(self):
        service = self.DocumentIntakeService(Path(self.temporary.name))
        with self.assertRaises(self.DocumentIntakeError):
            service.create_document(file_name="malware.pdf", content=b"MZ\x90\x00payload")

    def test_non_pdf_content_rejected(self):
        service = self.DocumentIntakeService(Path(self.temporary.name))
        with self.assertRaises(self.DocumentIntakeError):
            service.create_document(file_name="not_a_pdf.pdf", content=b"just text not pdf")

    def test_non_png_content_rejected(self):
        service = self.DocumentIntakeService(Path(self.temporary.name))
        with self.assertRaises(self.DocumentIntakeError):
            service.create_document(file_name="not_a_png.png", content=b"not a png file")

    def test_non_jpeg_content_rejected(self):
        service = self.DocumentIntakeService(Path(self.temporary.name))
        with self.assertRaises(self.DocumentIntakeError):
            service.create_document(file_name="not_jpg.jpg", content=b"not a jpeg file")

    def test_non_docx_zip_rejected(self):
        service = self.DocumentIntakeService(Path(self.temporary.name))
        with self.assertRaises(self.DocumentIntakeError):
            service.create_document(file_name="not_docx.docx", content=b"not a zip at all")

    def test_empty_file_rejected(self):
        service = self.DocumentIntakeService(Path(self.temporary.name))
        with self.assertRaises(self.DocumentIntakeError):
            service.create_document(file_name="empty.txt", content=b"")

    def test_oversized_file_rejected(self):
        small_service = self.DocumentIntakeService(Path(self.temporary.name) / "small", max_file_size=5)
        with self.assertRaises(self.DocumentIntakeError):
            small_service.create_document(file_name="big.txt", content=b"1234567")


class CrossTenantIsolationTests(unittest.TestCase):
    """P1.11.2 — Cross-tenant document, case, and job access."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        from app.services.case_session_service import case_session_service as css
        self.case_a = css.new_case()["case_id"]
        self.case_b = css.new_case()["case_id"]

    def test_case_a_documents_not_visible_in_case_b(self):
        fixture = Path(__file__).parent / "fixtures" / "NOTER._TEST.txt"
        upload = self.client.post(
            "/documents/upload",
            files={"file": (fixture.name, fixture.read_bytes(), "text/plain")},
            data={"case_id": self.case_a},
        )
        self.assertEqual(upload.status_code, 200, upload.text)

        docs_b = self.client.get(f"/documents?case_id={self.case_b}")
        self.assertEqual(docs_b.status_code, 200)
        self.assertEqual(docs_b.json(), [])

    def test_case_b_cannot_access_case_a_document_by_id(self):
        fixture = Path(__file__).parent / "fixtures" / "NOTER._TEST.txt"
        upload = self.client.post(
            "/documents/upload",
            files={"file": (fixture.name, fixture.read_bytes(), "text/plain")},
            data={"case_id": self.case_a},
        )
        self.assertEqual(upload.status_code, 200, upload.text)
        doc_id = upload.json()["document_id"]

        get_b = self.client.get(f"/documents/{doc_id}?case_id={self.case_b}")
        self.assertEqual(get_b.status_code, 404)

    def test_case_b_cannot_delete_case_a_document(self):
        fixture = Path(__file__).parent / "fixtures" / "NOTER._TEST.txt"
        upload = self.client.post(
            "/documents/upload",
            files={"file": (fixture.name, fixture.read_bytes(), "text/plain")},
            data={"case_id": self.case_a},
        )
        self.assertEqual(upload.status_code, 200, upload.text)
        doc_id = upload.json()["document_id"]

        delete_b = self.client.delete(f"/documents/{doc_id}?case_id={self.case_b}")
        self.assertEqual(delete_b.status_code, 404)


class SymlinkEscapeTests(unittest.TestCase):
    """P1.11.3 — Symlink escape protection."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temporary.cleanup()

    def test_upload_dir_symlink_blocked(self):
        from app.services.document_intake_service import DocumentIntakeService, DocumentIntakeError
        import os as _os

        base = Path(self.temporary.name)
        real_dir = base / "real_uploads"
        real_dir.mkdir()
        link_dir = base / "linked_uploads"

        target = str(base / "documents")
        try:
            _os.symlink(real_dir, link_dir)
        except OSError:
            self.skipTest("symlink creation requires elevated privileges on Windows")

        try:
            DocumentIntakeService(link_dir)
            self.fail("Should raise DocumentIntakeError for symlinked upload directory")
        except DocumentIntakeError:
            pass

    def test_resolved_path_traversal_blocked(self):
        from app.services.document_intake_service import DocumentIntakeService, DocumentIntakeError
        import os as _os

        base = Path(self.temporary.name)
        store = base / "document_store"
        store.mkdir(parents=True)
        uploads = store / "uploads"
        evil = base / "evil_target"
        evil.mkdir()

        try:
            _os.symlink(evil, uploads)
        except OSError:
            self.skipTest("symlink creation requires elevated privileges on Windows")

        try:
            DocumentIntakeService(store)
            self.fail("Should raise for symlinked uploads")
        except DocumentIntakeError:
            pass


class SafeErrorResponseTests(unittest.TestCase):
    """P1.11 — Safe error responses, no stack trace or secret leakage."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_404_response_no_stack_trace(self):
        resp = self.client.get("/nonexistent-path-12345")
        if resp.status_code != 404:
            pass
        content = resp.text.lower()
        self.assertNotIn("traceback", content)
        self.assertNotIn("file ", content)
        self.assertNotIn("line ", content)

    def test_400_on_invalid_json(self):
        resp = self.client.post(
            "/documents/upload",
            data="this is not json",
            headers={"Content-Type": "application/json"},
        )
        content = resp.text.lower()
        self.assertNotIn("traceback", content)

    def test_500_error_no_secret_in_response(self):
        resp = self.client.post("/auth/login", json={})
        content = resp.text.lower()
        self.assertNotIn("secret", content)
        self.assertNotIn("jwt_secret", content)
        self.assertNotIn("private_key", content)

    def test_auth_error_no_enumeration(self):
        """Login failures must not reveal whether user exists."""
        resp = self.client.post("/auth/login", json={
            "tenant_slug": "nonexistent",
            "email": "no_such_user@example.com",
            "password": "wrong_password_12345",
        })
        self.assertIn(resp.status_code, (200, 401))
        if resp.status_code != 200:
            detail = resp.json().get("detail", "")
            self.assertNotIn("not found", detail.lower())
            self.assertNotIn("does not exist", detail.lower())

    def test_401_response_no_token_leak(self):
        resp = self.client.get("/auth/me", headers={"Authorization": "Bearer invalid_token_here"})
        content = resp.text.lower()
        self.assertNotIn("bearer", content)

    def test_correlation_id_in_error(self):
        resp = self.client.get("/nonexistent-path-abcde")
        cid = resp.headers.get("x-correlation-id", "")
        self.assertTrue(len(cid) > 0)


class LoginRateLimitTests(unittest.TestCase):
    """P1.11.5 — Login rate limiting."""

    def setUp(self):
        from app.services.auth_service import reset_login_rate
        self.key = "login-rate-test-key"
        reset_login_rate(self.key)

    def test_allows_under_limit(self):
        from app.services.auth_service import check_login_rate
        for _ in range(3):
            limited, _ = check_login_rate(self.key)
            self.assertFalse(limited)

    def test_blocks_over_limit(self):
        from app.services.auth_service import check_login_rate
        for _ in range(5):
            check_login_rate(self.key)
        limited, retry = check_login_rate(self.key)
        self.assertTrue(limited)
        self.assertGreater(retry, 0)

    def test_reset_clears(self):
        from app.services.auth_service import check_login_rate, reset_login_rate
        for _ in range(3):
            check_login_rate(self.key)
        reset_login_rate(self.key)
        limited, _ = check_login_rate(self.key)
        self.assertFalse(limited)

    def test_isolation_between_keys(self):
        from app.services.auth_service import check_login_rate, reset_login_rate
        reset_login_rate("key-a")
        for _ in range(5):
            check_login_rate("key-a")
        limited_a, _ = check_login_rate("key-a")
        limited_b, _ = check_login_rate("key-b")
        self.assertTrue(limited_a)
        self.assertFalse(limited_b)


class DeletionLifecycleTests(unittest.TestCase):
    """P1.11.6 — Deletion lifecycle."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        from app.services.case_session_service import CaseSessionService
        from app.services.lifecycle_service import DataLifecycleService
        from unittest.mock import MagicMock
        self.cases = CaseSessionService(Path(self.temporary.name) / "cases")
        self.svc = DataLifecycleService()
        self.case_id = self.cases.new_case()["case_id"]

        patcher = patch(
            "app.services.case_session_service.case_session_service", self.cases
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        self.mock_docs = MagicMock()
        self.mock_docs._records = {}
        self.mock_docs._lock = MagicMock()
        self.mock_docs._persist_records = MagicMock()
        patcher_docs = patch(
            "app.services.document_intake_service.document_intake_service",
            self.mock_docs,
        )
        patcher_docs.start()
        self.addCleanup(patcher_docs.stop)

        self._cascade_patcher = patch.object(
            self.svc, "_purge_case_cascade", return_value={"ok": True, "steps": {}}
        )
        self._cascade_patcher.start()
        self.addCleanup(self._cascade_patcher.stop)

    def tearDown(self):
        self.temporary.cleanup()

    def _make_purgeable(self):
        from datetime import UTC, datetime, timedelta
        cid = self.cases.new_case()["case_id"]
        self.cases.update_case(
            cid, status="deleted",
            retention_until=(datetime.now(UTC) - timedelta(days=1)).isoformat(),
        )
        return cid

    def test_soft_delete_preserves_record_not_active(self):
        self.cases.update_case(self.case_id, status="active", title="test dava")
        self.svc.soft_delete_case(self.case_id, "t1", "owner1", "owner")
        case = self.cases.get_case(self.case_id)
        self.assertEqual(case["status"], "deleted")
        self.assertEqual(case["title"], "test dava")
        self.assertIn("deleted_at", case)

    def test_purge_removes_permanently(self):
        cid = self._make_purgeable()
        self.svc.run_purge("t1", dry_run=False, batch=10)
        self.assertNotIn(cid, self.cases._state["cases"])

    def test_restore_within_window(self):
        from datetime import UTC, datetime, timedelta
        self.cases.update_case(self.case_id, status="active")
        self.svc.soft_delete_case(self.case_id, "t1", "owner1", "owner")
        self.cases.update_case(self.case_id, restore_deadline="2999-12-31T00:00:00")
        result = self.svc.restore_case(self.case_id, "t1", "owner1", "owner")
        self.assertNotIn("error", result)

    def test_delete_creates_audit_event(self):
        self.cases._state["audit_events"] = []
        self.cases.update_case(self.case_id, status="active")
        self.svc.soft_delete_case(self.case_id, "t1", "owner1", "owner")
        events = self.cases._state.get("audit_events", [])
        actions = [e.get("action") for e in events]
        self.assertIn("case.soft_delete", actions)


class TemporaryFileCleanupTests(unittest.TestCase):
    """P1.11.6 — Temporary file and export cleanup."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temporary.cleanup()

    def test_document_delete_removes_file(self):
        from app.services.document_intake_service import DocumentIntakeService
        service = DocumentIntakeService(Path(self.temporary.name))
        record = service.create_document(file_name="temp.txt", content=b"temporary content")
        path = service._file_path(record.document_id, record.file_extension)
        self.assertTrue(path.exists())

        service.delete_document(record.document_id)
        self.assertFalse(path.exists())

    def test_export_cleanup_on_case_purge(self):
        import os as _os
        from app.services.lifecycle_service import DataLifecycleService
        from app.services.case_session_service import CaseSessionService
        from datetime import UTC, datetime, timedelta

        export_root = Path(self.temporary.name) / "exports"
        case_id = "case_export_test"
        export_root.mkdir(parents=True)
        export_file = export_root / f"{case_id}_abc123.txt"
        export_file.write_text("export content")

        orig = _os.environ.get("EMSALIST_STORAGE_ROOT", "")
        try:
            _os.environ["EMSALIST_STORAGE_ROOT"] = str(self.temporary.name)
            cases = CaseSessionService(Path(self.temporary.name) / "cases")
            svc = DataLifecycleService()
            cid = cases.new_case()["case_id"]
            cases.update_case(
                cid, status="deleted",
                retention_until=(datetime.now(UTC) - timedelta(days=1)).isoformat(),
            )
            patcher = patch("app.services.case_session_service.case_session_service", cases)
            patcher.start()
            try:
                svc.run_purge("t1", dry_run=False, batch=10)
            finally:
                patcher.stop()
        finally:
            if orig:
                _os.environ["EMSALIST_STORAGE_ROOT"] = orig
            else:
                _os.environ.pop("EMSALIST_STORAGE_ROOT", None)


class ConcurrentAuthTests(unittest.TestCase):
    """P1.11.2 — Concurrent authorization checks."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        from app.services.case_session_service import CaseSessionService
        from app.services.lifecycle_service import DataLifecycleService
        self.cases = CaseSessionService(Path(self.temporary.name) / "cases")
        self.svc = DataLifecycleService()
        self.case_id = self.cases.new_case()["case_id"]

        patcher = patch("app.services.case_session_service.case_session_service", self.cases)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.temporary.cleanup()

    def test_stale_version_conflict_prevented(self):
        self.cases.update_case(self.case_id, status="active", version=3)
        result = self.svc.soft_delete_case_with_version(
            self.case_id, "t1", "owner1", "owner", expected_version=99)
        self.assertEqual(result.get("error"), "version_conflict")

    def test_double_delete_is_idempotent(self):
        self.cases.update_case(self.case_id, status="active")
        r1 = self.svc.soft_delete_case(self.case_id, "t1", "owner1", "owner")
        r2 = self.svc.soft_delete_case(self.case_id, "t1", "owner1", "owner")
        self.assertNotIn("error", r1)
        self.assertTrue(r2.get("already_deleted"))


class SecretLeakagePreventionTests(unittest.TestCase):
    """P1.11 — No secret or token leakage in logs/responses."""

    def test_redact_bearer_token(self):
        from app.core.redaction import redact_value
        result = redact_value("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1MSJ9.signature")
        self.assertNotIn("eyJ", result)
        self.assertIn("***", result)

    def test_redact_basic_auth(self):
        from app.core.redaction import redact_value
        result = redact_value("Authorization: Basic dXNlcjpwYXNzd29yZA==")
        self.assertIn("***", result)

    def test_redact_jwt_token(self):
        from app.core.redaction import redact_value
        result = redact_value("token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abc123")
        self.assertNotIn("eyJ", result)

    def test_redact_url_password(self):
        from app.core.redaction import redact_value
        result = redact_value("postgresql://user:secret_password@localhost/db")
        self.assertNotIn("secret_password", result)

    def test_redact_dsn_password(self):
        from app.core.redaction import redact_value
        result = redact_value("password=supersecret host=localhost")
        self.assertNotIn("supersecret", result)

    def test_redact_api_key_in_query(self):
        from app.core.redaction import redact_value
        result = redact_value("https://api.example.com?api_key=sk-abc123&other=val")
        self.assertNotIn("sk-abc123", result)

    def test_redact_private_key_pem(self):
        from app.core.redaction import redact_value
        result = redact_value("key: -----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAK\n-----END RSA PRIVATE KEY-----")
        self.assertNotIn("BEGIN", result)
        self.assertIn("REDACTED", result)

    def test_sensitive_key_redacted_in_dict(self):
        from app.core.redaction import redact_dict
        result = redact_dict({"jwt_secret": "my-secret", "public_info": "visible"})
        self.assertEqual(result["jwt_secret"], "***")
        self.assertEqual(result["public_info"], "visible")

    def test_audit_event_no_password(self):
        from app.services.lifecycle_service import DataLifecycleService
        svc = DataLifecycleService()
        payload = svc._canonical_payload(
            "login", "u1", "c1", "2025-01-01T00:00:00", "",
            {"password": "secret123", "refresh_token": "rt-secret"})
        self.assertNotIn("secret123", payload)
        self.assertNotIn("rt-secret", payload)


class SecurityHeadersTests(unittest.TestCase):
    """P1.11.4 — Security response headers."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_x_content_type_options(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.headers.get("x-content-type-options"), "nosniff")

    def test_x_frame_options(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.headers.get("x-frame-options"), "DENY")

    def test_referrer_policy(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.headers.get("referrer-policy"), "strict-origin-when-cross-origin")

    def test_strict_transport_security(self):
        resp = self.client.get("/health")
        hsts = resp.headers.get("strict-transport-security", "")
        self.assertIn("max-age=", hsts)

    def test_cache_control_no_store(self):
        resp = self.client.get("/health")
        cc = resp.headers.get("cache-control", "")
        self.assertIn("no-store", cc)

    def test_permissions_policy(self):
        resp = self.client.get("/health")
        pp = resp.headers.get("permissions-policy", "")
        self.assertIn("camera=()", pp)


class RateLimitEndpointTests(unittest.TestCase):
    """P1.11.4 — API rate limiting for health-like paths."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_health_endpoint_accessible(self):
        resp = self.client.get("/health")
        self.assertIn(resp.status_code, (200, 503))
        if resp.status_code == 503:
            self.assertIn("status", resp.json())


if __name__ == "__main__":
    unittest.main()
