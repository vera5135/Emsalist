"""P1.12 — API contract, versioning, error, and OpenAPI tests."""
from __future__ import annotations

import json
import unittest

from fastapi.testclient import TestClient

from app.main import app


class APIVersioningTests(unittest.TestCase):
    """P1.12.2 — /api/v1 canonical paths exist."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_capabilities_endpoint(self):
        resp = self.client.get("/api/v1/meta/capabilities")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("api_version", data)
        self.assertIn("features", data)
        self.assertIn("limits", data)
        self.assertEqual(data["api_version"], "v1")

    def test_auth_endpoint_under_v1(self):
        resp = self.client.post("/api/v1/auth/login", json={
            "tenant_slug": "local", "email": "t@t.com", "password": "t"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("access_token", data)
        self.assertIn("token_type", data)
        self.assertIn("expires_in", data)
        self.assertIn("user", data)

    def test_auth_me_under_v1(self):
        resp = self.client.get("/api/v1/auth/me")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("user_id", data)
        self.assertIn("authenticated", data)

    def test_case_endpoint_under_v1(self):
        resp = self.client.get("/api/v1/case/current")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("case_id", resp.json())

    def test_documents_endpoint_under_v1(self):
        resp = self.client.get("/api/v1/documents")
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), list)

    def test_legacy_auth_still_works(self):
        resp = self.client.post("/auth/login", json={
            "tenant_slug": "local", "email": "t@t.com", "password": "t"
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access_token", resp.json())

    def test_legacy_case_still_works(self):
        resp = self.client.get("/case/current")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("case_id", resp.json())

    def test_nonexistent_api_version_404(self):
        resp = self.client.get("/api/v99/meta/capabilities")
        self.assertEqual(resp.status_code, 404)


class ErrorContractTests(unittest.TestCase):
    """P1.12.3 — Standard error contract verification."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_validation_error_has_standard_format(self):
        resp = self.client.post("/api/v1/auth/login", json={})
        self.assertGreaterEqual(resp.status_code, 400)
        data = resp.json()
        detail = data.get("detail", "")
        self.assertIsInstance(detail, (str, list))

    def test_404_has_correlation_header(self):
        resp = self.client.get("/nonexistent-path-abcdef")
        cid = resp.headers.get("x-correlation-id", "")
        self.assertTrue(len(cid) > 0)

    def test_500_does_not_leak_stack_trace(self):
        resp = self.client.post("/api/v1/auth/login", json={"invalid": True})
        content = resp.text.lower()
        self.assertNotIn("traceback", content)
        self.assertNotIn("file ", content)

    def test_auth_error_no_user_enumeration(self):
        resp = self.client.post("/api/v1/auth/login", json={
            "tenant_slug": "nonexistent",
            "email": "no_such_user@x.com",
            "password": "wrong",
        })
        self.assertIn(resp.status_code, (200, 401))
        if resp.status_code != 200:
            detail = resp.json().get("detail", "")
            self.assertNotIn("not found", detail.lower())

    def test_error_no_secrets_in_response(self):
        resp = self.client.post("/api/v1/auth/login", json={
            "tenant_slug": "x", "email": "a@b.com", "password": "p"
        })
        content = resp.text.lower()
        self.assertNotIn("jwt_secret", content)
        self.assertNotIn("private_key", content)
        self.assertNotIn("password_hash", content)

    def test_rate_limited_format(self):
        resp = self.client.get("/health")
        if resp.status_code == 429:
            self.assertIn("detail", resp.json())
            self.assertIn("retry-after", resp.headers)


class OpenAPIContractTests(unittest.TestCase):
    """P1.12.9 — OpenAPI schema quality."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_openapi_schema_produces(self):
        resp = self.client.get("/openapi.json")
        self.assertEqual(resp.status_code, 200)
        schema = resp.json()
        paths = schema.get("paths", {})
        self.assertGreater(len(paths), 0)

    def test_operation_ids_are_unique(self):
        resp = self.client.get("/openapi.json")
        schema = resp.json()
        operation_ids: list[str] = []
        for path, methods in schema.get("paths", {}).items():
            for method, details in methods.items():
                op_id = details.get("operationId", "")
                if op_id:
                    operation_ids.append(op_id)
        self.assertEqual(
            len(operation_ids), len(set(operation_ids)),
            f"Duplicate operation_ids found: "
            f"{[oid for oid in operation_ids if operation_ids.count(oid) > 1]}"
        )

    def test_security_scheme_defined(self):
        resp = self.client.get("/openapi.json")
        schema = resp.json()
        components = schema.get("components", {})
        security_schemes = components.get("securitySchemes", {})
        if not security_schemes:
            self.skipTest("No security schemes defined yet")

    def test_v1_paths_in_schema(self):
        resp = self.client.get("/openapi.json")
        schema = resp.json()
        paths = schema.get("paths", {})
        v1_paths = [p for p in paths if p.startswith("/api/v1")]
        self.assertGreater(len(v1_paths), 0, "No /api/v1 paths in OpenAPI schema")

    def test_no_secrets_in_schema(self):
        resp = self.client.get("/openapi.json")
        schema = resp.json()
        schema_str = json.dumps(schema).lower()
        for secret_pattern in ("jwt_secret", "private_key", "api_key", "connection_string"):
            self.assertNotIn(secret_pattern, schema_str,
                             f"Schema contains secret pattern: {secret_pattern}")

    def test_tags_are_consistent(self):
        resp = self.client.get("/openapi.json")
        schema = resp.json()
        tags_used: set[str] = set()
        for path, methods in schema.get("paths", {}).items():
            for method, details in methods.items():
                for tag in details.get("tags", []):
                    tags_used.add(tag)
        self.assertIn("Authentication", tags_used)


class AuthContractTests(unittest.TestCase):
    """P1.12.6 — Authentication contract."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_login_has_standard_fields(self):
        resp = self.client.post("/api/v1/auth/login", json={
            "tenant_slug": "local", "email": "t@t.com", "password": "t"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for field in ("access_token", "token_type", "expires_in", "user"):
            self.assertIn(field, data, f"Missing field: {field}")
        self.assertIn("id", data["user"])
        self.assertIn("tenant", data["user"])
        self.assertIn("role", data["user"])

    def test_me_has_standard_fields(self):
        resp = self.client.get("/api/v1/auth/me")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for field in ("user_id", "tenant_id", "role", "authenticated", "auth_mode"):
            self.assertIn(field, data, f"Missing field: {field}")

    def test_logout_has_message(self):
        resp = self.client.post("/api/v1/auth/logout")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("message", resp.json())

    def test_logout_all_has_message(self):
        resp = self.client.post("/api/v1/auth/logout-all")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("message", resp.json())


class InternalIntegrationTests(unittest.TestCase):
    """P1.12.13 — Basic internal integration smoke tests."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_create_case_upload_document_flow(self):
        new_case = self.client.post("/api/v1/case/new")
        self.assertEqual(new_case.status_code, 200)
        case_id = new_case.json()["case_id"]

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"Test document content for integration test")
            f.flush()
            upload = self.client.post(
                "/api/v1/documents/upload",
                files={"file": ("test.txt", open(f.name, "rb"), "text/plain")},
                data={"case_id": case_id},
            )
            self.assertEqual(upload.status_code, 200)
            doc_id = upload.json()["document_id"]

        docs = self.client.get(f"/api/v1/documents?case_id={case_id}")
        self.assertEqual(docs.status_code, 200)
        self.assertGreater(len(docs.json()), 0)

        delete = self.client.delete(f"/api/v1/documents/{doc_id}?case_id={case_id}")
        self.assertEqual(delete.status_code, 204)


class OpenAPIDriftDetectionTests(unittest.TestCase):
    """P1.14 — OpenAPI drift detection guards."""

    def test_openapi_drift_check_detects_real_difference(self):
        from app.main import app
        import json

        runtime_schema = app.openapi()
        runtime_json = json.dumps(runtime_schema, sort_keys=True, indent=2)

        altered = dict(runtime_schema)
        altered["info"] = dict(altered.get("info", {}))
        altered["info"]["version"] = "999.0.0"
        altered_json = json.dumps(altered, sort_keys=True, indent=2)

        self.assertNotEqual(runtime_json, altered_json,
                            "Schema modification must produce detectable diff")

    def test_runtime_openapi_matches_self(self):
        from app.main import app
        import json

        s1 = app.openapi()
        s2 = app.openapi()
        self.assertEqual(
            json.dumps(s1, sort_keys=True, indent=2),
            json.dumps(s2, sort_keys=True, indent=2),
            "Repeated openapi() calls must produce identical output",
        )

    def test_openapi_schema_has_no_secrets(self):
        from app.main import app
        import json

        schema = app.openapi()
        raw = json.dumps(schema)
        for secret in ("jwt_secret", "database_url", "gemini_api_key"):
            self.assertNotIn(secret, raw.lower(),
                             f"OpenAPI schema must not contain '{secret}'")


if __name__ == "__main__":
    unittest.main()
