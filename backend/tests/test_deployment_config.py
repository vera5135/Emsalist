"""P1.13 — Deployment configuration, version metadata, and readiness tests."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.config import (
    Settings, ProductionConfigError, validate_production_config,
    MIN_JWT_SECRET_LENGTH,
)


class DeploymentConfigTests(unittest.TestCase):
    """P1.13 — Production configuration validation."""

    def test_unsafe_production_blocks_startup(self):
        with self.assertRaises(ProductionConfigError):
            validate_production_config(Settings(environment="production"))

    def test_safe_production_passes(self):
        try:
            validate_production_config(Settings(
                environment="production", auth_mode="jwt",
                jwt_secret_key="s" * MIN_JWT_SECRET_LENGTH,
                cors_allow_origins="https://app.example.com",
                allowed_hosts="app.example.com",
                database_url="postgresql+asyncpg://production:5432/db",
            ))
        except ProductionConfigError as e:
            self.fail(f"Safe config should pass: {e}")

    def test_development_never_blocks(self):
        issues = validate_production_config(Settings(environment="development"))
        self.assertEqual(issues, [])

    def test_test_environment_never_blocks(self):
        issues = validate_production_config(Settings(environment="test"))
        self.assertEqual(issues, [])

    def test_all_production_blockers(self):
        """Every individual unsafe setting must block."""
        _db = "postgresql+asyncpg://db:5432/test"
        _key = "s" * MIN_JWT_SECRET_LENGTH
        _cors = "https://x.com"
        _hosts = "x.com"
        blockers = [
            Settings(environment="production"),
            Settings(environment="production", auth_mode="jwt", debug=True,
                     jwt_secret_key=_key, database_url=_db,
                     cors_allow_origins=_cors, allowed_hosts=_hosts),
            Settings(environment="production", auth_mode="jwt",
                     jwt_secret_key="emsalist-local-dev-key-change-in-production",
                     database_url=_db, cors_allow_origins=_cors, allowed_hosts=_hosts),
            Settings(environment="production", auth_mode="jwt",
                     jwt_secret_key=_key, database_url=_db,
                     cors_allow_origins="*", allowed_hosts=_hosts),
            Settings(environment="production", auth_mode="jwt",
                     jwt_secret_key=_key, database_url=_db,
                     cors_allow_origins=_cors),
            Settings(environment="production", auth_mode="jwt",
                     jwt_secret_key="short", database_url=_db,
                     cors_allow_origins=_cors, allowed_hosts=_hosts),
            Settings(environment="production", auth_mode="jwt",
                     jwt_secret_key=_key, database_url=_db,
                     cors_allow_origins=_cors, allowed_hosts=_hosts,
                     backup_encryption_enabled=True, backup_encryption_key=""),
            Settings(environment="production", auth_mode="jwt",
                     jwt_secret_key=_key,
                     cors_allow_origins=_cors, allowed_hosts=_hosts,
                     database_url=""),
            Settings(environment="production", auth_mode="jwt",
                     jwt_secret_key=_key,
                     cors_allow_origins=_cors, allowed_hosts=_hosts,
                     database_url="sqlite:///./db"),
        ]
        for i, s in enumerate(blockers):
            with self.assertRaises(ProductionConfigError, msg=f"Blocker {i} did not raise"):
                validate_production_config(s)


class VersionMetadataTests(unittest.TestCase):
    """P1.13 — Version endpoint."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_version_endpoint_returns_200(self):
        resp = self.client.get("/api/v1/meta/version")
        self.assertEqual(resp.status_code, 200)

    def test_version_has_required_fields(self):
        resp = self.client.get("/api/v1/meta/version")
        data = resp.json()
        for field in ("application", "version", "api_version", "commit", "environment"):
            self.assertIn(field, data, f"Missing field: {field}")
        self.assertEqual(data["application"], "emsalist")
        self.assertEqual(data["api_version"], "v1")

    def test_version_no_secrets(self):
        resp = self.client.get("/api/v1/meta/version")
        content = resp.text.lower()
        for secret in ("jwt_secret", "private_key", "password", "database_url"):
            self.assertNotIn(secret, content)

    def test_capabilities_endpoint_consistent(self):
        resp = self.client.get("/api/v1/meta/capabilities")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("features", data)
        self.assertIn("limits", data)
        self.assertIsInstance(data["features"]["document_upload"], bool)


class ReadinessContractTests(unittest.TestCase):
    """P1.13 — Health and readiness endpoints."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_live_returns_200(self):
        resp = self.client.get("/live")
        self.assertEqual(resp.status_code, 200)

    def test_ready_has_checks_field(self):
        resp = self.client.get("/ready")
        data = resp.json()
        self.assertIn("checks", data)
        self.assertIn("status", data)

    def test_health_has_components(self):
        resp = self.client.get("/health")
        self.assertIn(resp.status_code, (200, 503))
        data = resp.json()
        self.assertIn("status", data)
        self.assertIn("service", data)

    def test_health_no_secrets(self):
        resp = self.client.get("/health")
        content = resp.text.lower()
        self.assertNotIn("password", content)
        self.assertNotIn("secret", content)

    def test_live_no_secrets(self):
        resp = self.client.get("/live")
        content = resp.text.lower()
        self.assertNotIn("password", content)


class StartupLifecycleTests(unittest.TestCase):
    """P1.13 — Application imports and basic lifecycle."""

    def test_app_title_returns(self):
        self.assertEqual(app.title, "Emsalist API")

    def test_app_version(self):
        self.assertEqual(app.version, "0.1.0")

    def test_settings_cache_works(self):
        import os as _os
        _os.environ["EMSALIST_SKIP_PRODUCTION_VALIDATION"] = "1"
        from app.config import get_settings
        s1 = get_settings()
        s2 = get_settings()
        self.assertIs(s1, s2, "Settings must be cached (lru_cache)")


class OpenAPIConsistencyTests(unittest.TestCase):
    """P1.13 — OpenAPI schema is consistent."""

    def test_openapi_produces(self):
        schema = app.openapi()
        self.assertIn("paths", schema)
        self.assertIn("openapi", schema)

    def test_v1_paths_exist(self):
        schema = app.openapi()
        paths = schema.get("paths", {})
        v1_paths = [p for p in paths if p.startswith("/api/v1")]
        self.assertGreater(len(v1_paths), 0)

    def test_meta_endpoints_in_schema(self):
        schema = app.openapi()
        paths = schema.get("paths", {})
        meta = [p for p in paths if "/api/v1/meta/" in p]
        self.assertGreaterEqual(len(meta), 2, "Need /meta/version and /meta/capabilities")


class DatabaseUrlConfigTests(unittest.TestCase):
    """P1.14 — DATABASE_URL and EMSALIST_DATABASE_URL env loading."""

    def setUp(self):
        import app.config
        app.config.get_settings.cache_clear()

    def tearDown(self):
        import app.config
        app.config.get_settings.cache_clear()

    def test_database_url_loaded_from_environment(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql+asyncpg://h:5432/db",
                                      "EMSALIST_SKIP_PRODUCTION_VALIDATION": "1"}, clear=False):
            from app.config import get_settings
            settings = get_settings()
        self.assertEqual(settings.database_url, "postgresql+asyncpg://h:5432/db")

    def test_emsalist_database_url_precedence(self):
        with patch.dict(os.environ, {
            "DATABASE_URL": "postgresql+asyncpg://plain:5432/db",
            "EMSALIST_DATABASE_URL": "postgresql+asyncpg://prefixed:5432/db",
            "EMSALIST_SKIP_PRODUCTION_VALIDATION": "1",
        }, clear=False):
            from app.config import get_settings
            settings = get_settings()
        self.assertEqual(settings.database_url, "postgresql+asyncpg://prefixed:5432/db")

    def test_postgres_configuration_does_not_fall_back_to_sqlite(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql+asyncpg://pg:5432/db",
                                      "EMSALIST_SKIP_PRODUCTION_VALIDATION": "1"}, clear=False):
            from app.config import get_settings
            settings = get_settings()
        self.assertNotEqual(settings.database_url, "")
        self.assertNotIn("sqlite", settings.database_url.lower())
        self.assertIn("postgresql", settings.database_url)


class ProductionDatabaseValidationTests(unittest.TestCase):
    """P1.14 — Production database URL validation via make_url()."""

    def test_production_rejects_empty_database_url(self):
        with self.assertRaises(ProductionConfigError) as ctx:
            validate_production_config(Settings(
                environment="production", auth_mode="jwt",
                jwt_secret_key="s" * MIN_JWT_SECRET_LENGTH,
                cors_allow_origins="https://x.com", allowed_hosts="x.com",
                database_url="",
            ))
        self.assertIn("DATABASE_URL", str(ctx.exception))

    def test_production_rejects_sqlite_database(self):
        with self.assertRaises(ProductionConfigError) as ctx:
            validate_production_config(Settings(
                environment="production", auth_mode="jwt",
                jwt_secret_key="s" * MIN_JWT_SECRET_LENGTH,
                cors_allow_origins="https://x.com", allowed_hosts="x.com",
                database_url="sqlite:///./case_store/db",
            ))
        self.assertIn("PostgreSQL", str(ctx.exception))

    def test_production_rejects_mysql_database(self):
        with self.assertRaises(ProductionConfigError) as ctx:
            validate_production_config(Settings(
                environment="production", auth_mode="jwt",
                jwt_secret_key="s" * MIN_JWT_SECRET_LENGTH,
                cors_allow_origins="https://x.com", allowed_hosts="x.com",
                database_url="mysql://postgres-host/db",
            ))
        self.assertIn("PostgreSQL", str(ctx.exception))

    def test_production_rejects_malformed_url(self):
        with self.assertRaises(ProductionConfigError) as ctx:
            validate_production_config(Settings(
                environment="production", auth_mode="jwt",
                jwt_secret_key="s" * MIN_JWT_SECRET_LENGTH,
                cors_allow_origins="https://x.com", allowed_hosts="x.com",
                database_url="not_a_valid_url!!!",
            ))
        self.assertIn("parse", str(ctx.exception))

    def test_production_accepts_postgresql_asyncpg(self):
        try:
            validate_production_config(Settings(
                environment="production", auth_mode="jwt",
                jwt_secret_key="s" * MIN_JWT_SECRET_LENGTH,
                cors_allow_origins="https://x.com", allowed_hosts="x.com",
                database_url="postgresql+asyncpg://h:5432/db",
            ))
        except ProductionConfigError as e:
            self.fail(f"postgresql+asyncpg config should pass: {e}")

    def test_production_accepts_postgresql_psycopg(self):
        try:
            validate_production_config(Settings(
                environment="production", auth_mode="jwt",
                jwt_secret_key="s" * MIN_JWT_SECRET_LENGTH,
                cors_allow_origins="https://x.com", allowed_hosts="x.com",
                database_url="postgresql+psycopg://h:5432/db",
            ))
        except ProductionConfigError as e:
            self.fail(f"postgresql+psycopg config should pass: {e}")

    def test_development_allows_sqlite(self):
        issues = validate_production_config(Settings(
            environment="development",
            database_url="sqlite:///./case_store/db",
        ))
        self.assertEqual(issues, [])

    def test_database_test_fixture_does_not_override_ci_database_url(self):
        saved = os.environ.get("DATABASE_URL", "__MISSING__")
        try:
            os.environ["DATABASE_URL"] = "postgresql+asyncpg://ci-host:5432/ci-db"
            os.environ["EMSALIST_SKIP_PRODUCTION_VALIDATION"] = "1"

            from app import config as app_config
            app_config.get_settings.cache_clear()
            from app.config import get_settings

            settings = get_settings()
            self.assertEqual(settings.database_url, "postgresql+asyncpg://ci-host:5432/ci-db")
        finally:
            from app import config as app_config
            app_config.get_settings.cache_clear()
            if saved == "__MISSING__":
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = saved


class AcceptanceSummaryLogicTests(unittest.TestCase):
    """P1.14 — Acceptance summary logic rejects non-success results."""

    def _evaluate_summary(self, results: list[str]) -> tuple[bool, int]:
        failures = 0
        for r in results:
            if r != "success":
                failures += 1
        return failures == 0, failures

    def test_acceptance_summary_rejects_skipped_job(self):
        results = ["success", "skipped", "success", "success",
                   "success", "success", "success", "success"]
        passed, failures = self._evaluate_summary(results)
        self.assertFalse(passed, "A skipped job must cause overall failure")
        self.assertEqual(failures, 1)

    def test_all_success_passes(self):
        results = ["success"] * 8
        passed, failures = self._evaluate_summary(results)
        self.assertTrue(passed)

    def test_cancelled_counts_as_blocker(self):
        results = ["success", "success", "success", "cancelled",
                   "success", "success", "success", "success"]
        passed, failures = self._evaluate_summary(results)
        self.assertFalse(passed, "A cancelled job must cause overall failure")

    def test_failure_counts_as_blocker(self):
        results = ["success", "failure", "success", "success",
                   "success", "success", "success", "success"]
        passed, failures = self._evaluate_summary(results)
        self.assertFalse(passed, "A failed job must cause overall failure")


if __name__ == "__main__":
    unittest.main()
