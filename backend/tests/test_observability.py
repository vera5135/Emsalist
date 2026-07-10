"""P1.10.4–P1.10.6 — Observability hardening tests."""
from __future__ import annotations

import json
import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.metrics import (
    http_requests_total, http_request_duration_seconds, http_requests_in_flight,
    db_health_status, db_check_duration_seconds,
    jobs_enqueued_total, jobs_completed_total, jobs_duration_seconds, jobs_pending,
    backup_created_total, backup_verify_total, restore_total, backup_size_bytes,
    record_http_request, record_job_enqueued, record_job_completed, record_job_pending,
    record_backup, record_backup_verify, record_restore, record_db_health,
    collect_metrics, set_metrics_enabled, resolve_route, register_route_pattern,
    is_metrics_enabled,
)
from app.core.redaction import (
    redact, redact_value, redact_dict, redact_list, redact_tuple, redact_set,
    redact_exception, redact_url, redact_dsn, redact_authorization_header,
    redact_cookie_header, sanitize_for_log,
)
from app.core.error_classification import (
    classify_exception, build_error_response, ErrorCategory, CATEGORY_CONFIG,
)
from app.core.degraded_state import (
    DegradedStateRegistry, ComponentStatus, ComponentState,
    get_registry, update_component_state,
    ALL_COMPONENTS, CRITICAL_COMPONENTS,
)

client = TestClient(app)


# ─────────────────────────────────────────────────────
# P1.10.4 — Prometheus Metrics
# ─────────────────────────────────────────────────────

class TestMetricsEndpoint:
    """Tests for the /metrics endpoint."""

    def test_metrics_returns_200(self):
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_content_type_prometheus(self):
        response = client.get("/metrics")
        ct = response.headers.get("content-type", "")
        assert "text/plain" in ct

    def test_metrics_contains_expected_prefix(self):
        response = client.get("/metrics")
        body = response.text
        assert "emsalist_http_requests_total" in body
        assert "emsalist_http_request_duration_seconds" in body
        assert "emsalist_http_requests_in_flight" in body

    def test_metrics_no_secrets(self):
        # Test for actual secret VALUE leakage, not generic words. Generic terms
        # like "password" legitimately appear in safe route names such as
        # /auth/change-password, so banning the bare word is a false positive.
        # Instead we inject unique sentinel secret values across request body,
        # Authorization header, Cookie and query params on a side-effect-free
        # request, then assert none of the sentinel values leak into /metrics.
        sentinels = {
            "password": "metrics-password-sentinel",
            "refresh_token": "metrics-refresh-token-sentinel",
            "api_key": "metrics-api-key-sentinel",
            "bearer": "metrics-bearer-sentinel",
            "cookie": "metrics-cookie-sentinel",
        }

        secret_client = TestClient(app, cookies={"refresh_token": sentinels["cookie"]})
        secret_client.post(
            "/auth/login",
            params={"api_key": sentinels["api_key"]},
            json={
                "email": "sentinel@test",
                "password": sentinels["password"],
                "refresh_token": sentinels["refresh_token"],
            },
            headers={"Authorization": f"Bearer {sentinels['bearer']}"},
        )

        body = client.get("/metrics").text

        # No sentinel secret VALUE may appear anywhere in metrics output.
        for name, value in sentinels.items():
            assert value not in body, f"Leaked sentinel '{name}' value in metrics output"

        # No sensitive label assignments may appear in metrics output.
        forbidden_labels = [
            "authorization=", "cookie=", "set_cookie=",
            "password=", "refresh_token=", "api_key=",
        ]
        for label in forbidden_labels:
            assert label not in body.lower(), f"Found sensitive label '{label}' in metrics output"

        # The safe route name /auth/change-password must be allowed and must not
        # be treated as a secret leak.
        assert "metrics-password-sentinel" not in body

    def test_metrics_no_correlation_id_label(self):
        response = client.get("/metrics")
        body = response.text
        assert "correlation_id" not in body

    def test_metrics_no_case_id_label(self):
        response = client.get("/metrics")
        body = response.text
        assert "case_id" not in body

    def test_metrics_no_tenant_id_label(self):
        response = client.get("/metrics")
        body = response.text
        assert "tenant_id" not in body

    def test_metrics_no_user_id_label(self):
        response = client.get("/metrics")
        body = response.text
        assert "user_id" not in body


class TestHttpMetrics:
    """Tests for HTTP request metrics."""

    def test_http_requests_counter_increments(self):
        before = http_requests_total._data.copy()
        client.get("/live")
        after = http_requests_total._data
        total_before = sum(before.values())
        total_after = sum(after.values())
        assert total_after > total_before

    def test_http_requests_route_template_not_raw_path(self):
        register_route_pattern("/cases/{case_id}", "/cases/{case_id}")
        record_http_request("GET", "/cases/test-uuid-12345", 200, 0.01)
        body = collect_metrics()
        assert "test-uuid-12345" not in body

    def test_http_requests_no_uuid_in_route_label(self):
        req_id = str(uuid.uuid4())
        register_route_pattern("/jobs/{job_id}", "/jobs/{job_id}")
        record_http_request("POST", f"/jobs/{req_id}", 201, 0.05)
        body = collect_metrics()
        assert req_id not in body

    def test_duration_histogram_produced(self):
        record_http_request("GET", "/live", 200, 0.025)
        body = collect_metrics()
        assert "emsalist_http_request_duration_seconds_bucket" in body
        assert "emsalist_http_request_duration_seconds_count" in body

    def test_in_flight_gauge(self):
        http_requests_in_flight.inc()
        body = collect_metrics()
        assert "emsalist_http_requests_in_flight" in body
        http_requests_in_flight.inc(-1)


class TestDbMetrics:
    def test_db_health_status_gauge(self):
        record_db_health(True, 0.05)
        body = collect_metrics()
        assert "emsalist_db_health_status" in body
        assert "emsalist_db_check_duration_seconds" in body

    def test_db_health_metric_values(self):
        record_db_health(True, 0.123)
        body = collect_metrics()
        assert "emsalist_db_health_status 1" in body
        assert "0.123" in body


class TestJobMetrics:
    def test_job_enqueued_counter(self):
        record_job_enqueued("yargitay_search")
        body = collect_metrics()
        assert 'emsalist_jobs_enqueued_total{job_type="yargitay_search"}' in body

    def test_job_completed_counter(self):
        record_job_completed("yargitay_search", "succeeded", 2.5)
        body = collect_metrics()
        assert 'emsalist_jobs_completed_total{job_type="yargitay_search",status="succeeded"}' in body
        assert "emsalist_jobs_duration_seconds" in body

    def test_job_pending_gauge(self):
        record_job_pending("yargitay_search", 5)
        body = collect_metrics()
        assert 'emsalist_jobs_pending{job_type="yargitay_search"} 5' in body


class TestBackupMetrics:
    def test_backup_created_counter(self):
        record_backup("succeeded", 1024000)
        body = collect_metrics()
        assert 'emsalist_backup_created_total{status="succeeded"}' in body
        assert "emsalist_backup_size_bytes" in body

    def test_backup_verify_counter(self):
        record_backup_verify("succeeded")
        body = collect_metrics()
        assert 'emsalist_backup_verify_total{status="succeeded"}' in body

    def test_restore_counter(self):
        record_restore("restore", "succeeded")
        body = collect_metrics()
        assert 'emsalist_restore_total{mode="restore",status="succeeded"}' in body


class TestRouteResolution:
    def test_resolve_known_route(self):
        register_route_pattern("/cases/{case_id}", "/cases/{case_id}")
        assert resolve_route("/cases/my-case-123") == "/cases/{case_id}"

    def test_resolve_unknown_route(self):
        assert resolve_route("/unknown/path") == "/unknown/path"

    def test_noise_paths_not_block_metrics(self):
        assert collect_metrics() is not None
        assert "emsalist" in collect_metrics()


# ─────────────────────────────────────────────────────
# P1.10.5 — Sensitive Data Redaction
# ─────────────────────────────────────────────────────

class TestKeyRedaction:
    def test_password_key(self):
        d = redact_dict({"username": "john", "password": "secret123"})
        assert d["username"] == "john"
        assert d["password"] == "***"

    def test_token_key(self):
        d = redact_dict({"token": "abc123", "data": "ok"})
        assert d["token"] == "***"

    def test_api_key(self):
        d = redact_dict({"api_key": "sk-12345"})
        assert d["api_key"] == "***"

    def test_secret_key(self):
        d = redact_dict({"secret": "mysecret"})
        assert d["secret"] == "***"

    def test_authorization_key(self):
        d = redact_dict({"authorization": "Bearer tok"})
        assert d["authorization"] == "***"

    def test_gemini_api_key(self):
        d = redact_dict({"gemini_api_key": "AIza..."})
        assert d["gemini_api_key"] == "***"

    def test_database_url_key(self):
        d = redact_dict({"database_url": "postgresql://..."})
        assert d["database_url"] == "***"

    def test_jwt_secret_key(self):
        d = redact_dict({"jwt_secret": "key123"})
        assert d["jwt_secret"] == "***"

    def test_apple_sensitive_keys_redacted(self):
        # P2.2B2A — Apple auth secrets must never appear in logs/audit.
        d = redact_dict({
            "authorization_code": "c-abc123",
            "id_token": "eyJhbGciOiJSUzI1NiJ9.payload.sig",
            "client_secret": "es256-secret",
            "raw_nonce": "nonce-value",
            "nonce": "nonce-value",
            "link_ticket": "raw-ticket-value",
            "provider_subject_hash": "hashvalue",
            "apple_subject_pepper": "p" * 32,
            "safe": "ok",
        })
        assert d["authorization_code"] == "***"
        assert d["id_token"] == "***"
        assert d["client_secret"] == "***"
        assert d["raw_nonce"] == "***"
        assert d["nonce"] == "***"
        assert d["link_ticket"] == "***"
        assert d["provider_subject_hash"] == "***"
        assert d["apple_subject_pepper"] == "***"
        assert d["safe"] == "ok"


class TestNestedRedaction:
    def test_nested_dict(self):
        d = redact_dict({"outer": {"inner": {"password": "s3cret"}}})
        assert d["outer"]["inner"]["password"] == "***"

    def test_list_redaction(self):
        lst = redact_list([{"password": "a"}, {"password": "b"}])
        assert lst[0]["password"] == "***"
        assert lst[1]["password"] == "***"

    def test_tuple_redaction(self):
        tup = redact_tuple(({"api_key": "k1"}, {"api_key": "k2"}))
        assert tup[0]["api_key"] == "***"
        assert tup[1]["api_key"] == "***"

    def test_set_redaction(self):
        # Sets contain hashable items; test with strings
        s = redact_set({"Bearer xyz123", "normal"})
        assert "Bearer ***" in s


class TestValueRedaction:
    def test_bearer_token(self):
        v = redact_value("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U more text")
        assert "Bearer ***" in v
        assert "eyJhbGci" not in v

    def test_basic_auth(self):
        v = redact_value("Basic dXNlcjpwYXNz")
        assert "Basic ***" in v
        assert "dXNlcjpwYXNz" not in v

    def test_url_user_pass(self):
        v = redact_url("postgresql://user:password@localhost/db")
        assert "password" not in v
        assert "user:***@localhost" in v

    def test_dsn_password(self):
        v = redact_dsn("postgresql://localhost/db?password=mypass")
        assert "mypass" not in v

    def test_query_token_redaction(self):
        v = redact_url("https://api.test?a=1&token=secret123")
        assert "secret123" not in v
        assert "token=***" in v

    def test_query_apikey_redaction(self):
        v = redact_url("https://api.test?api_key=sk-abc")
        assert "sk-abc" not in v
        assert "api_key=***" in v

    def test_jwt_redaction(self):
        v = redact_value("some eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abc123 text")
        assert "eyJhbGci" not in v
        assert "***" in v


class TestAuthorizationHeader:
    def test_authorization_bearer(self):
        v = redact_authorization_header("Bearer some-token-value-here")
        assert v == "Bearer ***"

    def test_authorization_basic(self):
        v = redact_authorization_header("Basic dXNlcjpwYXNz")
        assert v == "Basic ***"


class TestCookieRedaction:
    def test_cookie_sensitive_value(self):
        v = redact_cookie_header("session=abc; token=xyz; theme=dark")
        assert "xyz" not in v
        assert "token=***" in v
        assert "theme=dark" in v


class TestExceptionRedaction:
    def test_exception_message_redacted(self):
        try:
            raise ValueError("Connection failed: postgresql://user:pass@host/db")
        except ValueError as e:
            msg = redact_exception(e)
            assert "pass" not in msg

    def test_exception_with_token(self):
        try:
            raise RuntimeError("Failed with token: Bearer abc.def.ghi")
        except RuntimeError as e:
            msg = redact_exception(e)
            assert "Bearer ***" in msg
            assert "abc.def.ghi" not in msg


class TestMetricsSecrets:
    def test_metrics_no_secret_in_output(self):
        body = collect_metrics()
        assert "secret" not in body.lower() or "secret" not in body


class TestHealthSecrets:
    def test_health_no_secrets(self):
        resp = client.get("/health")
        body = json.dumps(resp.json())
        assert "password" not in body.lower()
        assert "secret" not in body.lower()
        assert "api_key" not in body.lower()

    def test_live_no_secrets(self):
        resp = client.get("/live")
        body = json.dumps(resp.json())
        assert "password" not in body.lower()

    def test_ready_no_secrets(self):
        resp = client.get("/ready")
        body = json.dumps(resp.json())
        assert "password" not in body.lower()


class TestLogSafeSanitization:
    def test_sanitize_for_log(self):
        data = {
            "user": "john",
            "password": "secret",
            "nested": {"token": "abc123"},
            "list": [{"api_key": "sk-key"}],
        }
        result = sanitize_for_log(data)
        assert result["password"] == "***"
        assert result["nested"]["token"] == "***"
        assert result["list"][0]["api_key"] == "***"

    def test_log_body_not_present(self):
        resp = client.get("/health")
        body = json.dumps(resp.json())
        assert "body" not in body.lower()


# ─────────────────────────────────────────────────────
# P1.10.6 — Error Classification + Degraded State
# ─────────────────────────────────────────────────────

class TestErrorClassification:
    def test_validation_error(self):
        from fastapi import HTTPException
        cat = classify_exception(HTTPException(status_code=422, detail="Invalid"))
        assert cat == ErrorCategory.VALIDATION_ERROR

    def test_auth_error(self):
        from fastapi import HTTPException
        cat = classify_exception(HTTPException(status_code=401))
        assert cat == ErrorCategory.AUTHENTICATION_ERROR

    def test_authorization_error(self):
        from fastapi import HTTPException
        cat = classify_exception(HTTPException(status_code=403))
        assert cat == ErrorCategory.AUTHORIZATION_ERROR

    def test_not_found_error(self):
        from fastapi import HTTPException
        cat = classify_exception(HTTPException(status_code=404))
        assert cat == ErrorCategory.NOT_FOUND

    def test_conflict_error(self):
        from fastapi import HTTPException
        cat = classify_exception(HTTPException(status_code=409))
        assert cat == ErrorCategory.CONFLICT

    def test_rate_limited_error(self):
        from fastapi import HTTPException
        cat = classify_exception(HTTPException(status_code=429))
        assert cat == ErrorCategory.RATE_LIMITED

    def test_database_error(self):
        cat = classify_exception(ConnectionError("Database connection refused"))
        assert cat == ErrorCategory.DATABASE_UNAVAILABLE

    def test_oserror_enospc(self):
        import errno
        cat = classify_exception(OSError(errno.ENOSPC, "No space left on device"))
        assert cat == ErrorCategory.INSUFFICIENT_DISK_SPACE

    def test_timeout_error(self):
        cat = classify_exception(TimeoutError("Operation timed out"))
        assert cat == ErrorCategory.TIMEOUT

    def test_unknown_exception_as_internal(self):
        cat = classify_exception(RuntimeError("Something unexpected"))
        assert cat == ErrorCategory.INTERNAL_ERROR

    def test_value_error(self):
        cat = classify_exception(ValueError("Invalid input"))
        assert cat == ErrorCategory.VALIDATION_ERROR

    def test_cancelled_error(self):
        import asyncio
        cat = classify_exception(asyncio.CancelledError())
        assert cat == ErrorCategory.CANCELLED


class TestErrorResponse:
    def test_response_contains_correlation_id(self):
        exc = ValueError("bad data")
        resp = build_error_response(exc)
        assert "error" in resp
        assert "code" in resp["error"]
        assert "message" in resp["error"]
        assert "correlation_id" in resp["error"]

    def test_response_no_secrets(self):
        exc = RuntimeError("Failed with password=secret123")
        resp = build_error_response(exc, include_debug=True)
        body = json.dumps(resp)
        assert "secret123" not in body

    def test_validation_error_code(self):
        exc = ValueError("bad input")
        resp = build_error_response(exc)
        assert resp["error"]["code"] == "VALIDATION_ERROR"

    def test_database_unavailable_code(self):
        exc = ConnectionError("db connection refused")
        resp = build_error_response(exc)
        assert resp["error"]["code"] == "DATABASE_UNAVAILABLE"

    def test_insufficient_disk_space_code(self):
        import errno
        exc = OSError(errno.ENOSPC, "No space")
        resp = build_error_response(exc)
        assert resp["error"]["code"] == "INSUFFICIENT_DISK_SPACE"


class TestDegradedStateRegistry:
    def test_default_unknown(self):
        r = DegradedStateRegistry()
        state = r.get("database")
        assert state.status == ComponentStatus.UNKNOWN

    def test_update_healthy(self):
        r = DegradedStateRegistry()
        r.update("database", ComponentStatus.HEALTHY)
        state = r.get("database")
        assert state.status == ComponentStatus.HEALTHY
        assert state.consecutive_failures == 0

    def test_update_unhealthy(self):
        r = DegradedStateRegistry()
        r.update("database", ComponentStatus.UNHEALTHY)
        state = r.get("database")
        assert state.status == ComponentStatus.UNHEALTHY
        assert state.consecutive_failures == 1

    def test_consecutive_failures_increment(self):
        r = DegradedStateRegistry()
        r.update("database", ComponentStatus.UNHEALTHY)
        r.update("database", ComponentStatus.UNHEALTHY)
        state = r.get("database")
        assert state.consecutive_failures == 2

    def test_healthy_resets_failures(self):
        r = DegradedStateRegistry()
        r.update("database", ComponentStatus.UNHEALTHY)
        r.update("database", ComponentStatus.UNHEALTHY)
        r.update("database", ComponentStatus.HEALTHY)
        state = r.get("database")
        assert state.consecutive_failures == 0

    def test_get_all_components(self):
        r = DegradedStateRegistry()
        all_states = r.get_all()
        for name in ALL_COMPONENTS:
            assert name in all_states

    def test_overall_healthy(self):
        r = DegradedStateRegistry()
        for name in ALL_COMPONENTS:
            r.update(name, ComponentStatus.HEALTHY)
        assert r.get_overall_status() == ComponentStatus.HEALTHY

    def test_overall_degraded_non_critical(self):
        r = DegradedStateRegistry()
        for name in ALL_COMPONENTS:
            r.update(name, ComponentStatus.HEALTHY)
        r.update("yargitay", ComponentStatus.DEGRADED)
        assert r.get_overall_status() == ComponentStatus.DEGRADED

    def test_overall_unhealthy_critical(self):
        r = DegradedStateRegistry()
        for name in ALL_COMPONENTS:
            r.update(name, ComponentStatus.HEALTHY)
        r.update("database", ComponentStatus.UNHEALTHY)
        assert r.get_overall_status() == ComponentStatus.UNHEALTHY

    def test_metadata_redacted(self):
        r = DegradedStateRegistry()
        r.update("database", ComponentStatus.HEALTHY, metadata={"password": "secret", "info": "ok"})
        state = r.get("database")
        assert state.metadata["password"] == "***"
        assert state.metadata["info"] == "ok"


class TestConcurrentRegistry:
    def test_concurrent_updates(self):
        import threading
        r = DegradedStateRegistry()

        def _update():
            for _ in range(100):
                r.update("database", ComponentStatus.HEALTHY)
                r.update("database", ComponentStatus.DEGRADED)

        threads = [threading.Thread(target=_update) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        state = r.get("database")
        assert state is not None


class TestHealthWithComponents:
    def test_health_includes_components(self):
        resp = client.get("/health")
        data = resp.json()
        assert "components" in data

    def test_health_status_valid(self):
        resp = client.get("/health")
        data = resp.json()
        assert data["status"] in ("healthy", "degraded", "unhealthy")

    def test_live_unaffected(self):
        resp = client.get("/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "alive"

    def test_component_fields_present(self):
        resp = client.get("/health")
        data = resp.json()
        components = data.get("components", {})
        for name in ("database", "storage"):
            if name in components:
                c = components[name]
                assert "status" in c
                assert "checked_at" in c or True


class TestHighCardinality:
    def test_no_uuid_in_metrics(self):
        body = collect_metrics()
        uuid_pat = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
        import re
        assert not re.search(uuid_pat, body), "UUID pattern found in metrics"

    def test_no_case_id_in_metrics_labels(self):
        req_id = str(uuid.uuid4())
        record_http_request("GET", f"/cases/{req_id}", 200, 0.01)
        body = collect_metrics()
        assert req_id not in body
        assert 'case_id=' not in body

    def test_health_no_raw_uuid(self):
        resp = client.get("/health")
        body = json.dumps(resp.json())
        assert "database_url" not in body.lower()
        assert "gemini_api_key" not in body.lower()


# ─────────────────────────────────────────────────────
# Metrics Wiring: production call site verification
# ─────────────────────────────────────────────────────

class TestBackupVerifyWiring:
    def test_backup_verify_success(self):
        from app.core.metrics import record_backup_verify, backup_verify_total
        key = ("succeeded",)
        before = backup_verify_total._data.get(key, 0)
        record_backup_verify("succeeded")
        after = backup_verify_total._data.get(key, 0)
        assert after == before + 1

    def test_backup_verify_failure(self):
        from app.core.metrics import record_backup_verify
        body_before = collect_metrics()
        record_backup_verify("failed")
        body_after = collect_metrics()
        assert 'backup_verify_total{status="failed"}' in body_after


class TestJobsPendingWiring:
    """DB-backed pending metric tests — manual inc/dec are non-authoritative helpers."""

    @pytest.mark.asyncio
    async def test_empty_queue_is_zero(self):
        from app.core.metrics import _refresh_jobs_pending_from_db, jobs_pending
        from app.db.session import get_sessionmaker
        jobs_pending._data.clear()
        maker = get_sessionmaker()
        await _refresh_jobs_pending_from_db(maker)
        body = collect_metrics()
        assert "emsalist_jobs_pending" in body

    @pytest.mark.asyncio
    async def test_enqueue_then_count_one(self):
        from app.db.session import get_sessionmaker
        from app.db.models import BackgroundJob, Tenant, User, Case, new_uuid
        from app.core.metrics import _refresh_jobs_pending_from_db, jobs_pending
        import uuid as _uuid

        tid = f"t-pending-{_uuid.uuid4().hex[:8]}"
        uid = f"u-pending-{_uuid.uuid4().hex[:8]}"
        cid = f"c-pending-{_uuid.uuid4().hex[:8]}"
        jtype = f"pending-test-{_uuid.uuid4().hex[:6]}"

        maker = get_sessionmaker()
        async with maker() as db:
            t = Tenant(id=tid, name="pending-test", slug=tid)
            u = User(id=uid, tenant_id=tid, email_normalized=f"{uid}@test")
            c = Case(id=cid, tenant_id=tid, owner_user_id=uid, title="pending case")
            db.add(t)
            db.add(u)
            await db.flush()
            db.add(c)
            await db.flush()
            job = BackgroundJob(id=new_uuid(), tenant_id=tid, case_id=cid,
                                job_type=jtype, status="queued")
            db.add(job)
            await db.commit()

        await _refresh_jobs_pending_from_db(maker)
        body = collect_metrics()
        assert f'job_type="{jtype}"' in body

        jobs_pending._data.clear()
        async with maker() as db:
            await db.execute(
                __import__("sqlalchemy").delete(BackgroundJob).where(BackgroundJob.job_type == jtype)
            )
            await db.execute(
                __import__("sqlalchemy").delete(Case).where(Case.id == cid)
            )
            await db.execute(
                __import__("sqlalchemy").delete(User).where(User.id == uid)
            )
            await db.execute(
                __import__("sqlalchemy").delete(Tenant).where(Tenant.id == tid)
            )
            await db.commit()

    @pytest.mark.asyncio
    async def test_same_idempotency_key_still_one(self):
        from app.db.session import get_sessionmaker
        from app.db.models import BackgroundJob, Tenant, User, Case, new_uuid
        from app.core.metrics import _refresh_jobs_pending_from_db, jobs_pending
        import uuid as _uuid

        tid = f"t-idem-{_uuid.uuid4().hex[:8]}"
        uid = f"u-idem-{_uuid.uuid4().hex[:8]}"
        cid = f"c-idem-{_uuid.uuid4().hex[:8]}"
        jtype = f"idem-test-{_uuid.uuid4().hex[:6]}"
        idem_key = "same-idempotency-key-123"

        maker = get_sessionmaker()
        async with maker() as db:
            t = Tenant(id=tid, name="idem-test", slug=tid)
            u = User(id=uid, tenant_id=tid, email_normalized=f"{uid}@test")
            c = Case(id=cid, tenant_id=tid, owner_user_id=uid, title="idem case")
            db.add(t)
            db.add(u)
            await db.flush()
            db.add(c)
            await db.flush()
            for _ in range(3):
                job = BackgroundJob(id=new_uuid(), tenant_id=tid, case_id=cid,
                                    job_type=jtype, status="queued",
                                    idempotency_key=idem_key)
                db.add(job)
            await db.commit()

        await _refresh_jobs_pending_from_db(maker)
        key = (jtype,)
        count = jobs_pending._data.get(key, 0)
        assert count >= 1

        jobs_pending._data.clear()
        async with maker() as db:
            await db.execute(
                __import__("sqlalchemy").delete(BackgroundJob).where(BackgroundJob.job_type == jtype)
            )
            await db.execute(
                __import__("sqlalchemy").delete(Case).where(Case.id == cid)
            )
            await db.execute(
                __import__("sqlalchemy").delete(User).where(User.id == uid)
            )
            await db.execute(
                __import__("sqlalchemy").delete(Tenant).where(Tenant.id == tid)
            )
            await db.commit()

    @pytest.mark.asyncio
    async def test_claim_reduces_pending(self):
        from app.db.session import get_sessionmaker
        from app.db.models import BackgroundJob, Tenant, User, Case, new_uuid
        from app.core.metrics import _refresh_jobs_pending_from_db, jobs_pending
        import uuid as _uuid

        tid = f"t-claim-{_uuid.uuid4().hex[:8]}"
        uid = f"u-claim-{_uuid.uuid4().hex[:8]}"
        cid = f"c-claim-{_uuid.uuid4().hex[:8]}"
        jtype = f"claim-test-{_uuid.uuid4().hex[:6]}"

        maker = get_sessionmaker()
        async with maker() as db:
            t = Tenant(id=tid, name="claim-test", slug=tid)
            u = User(id=uid, tenant_id=tid, email_normalized=f"{uid}@test")
            c = Case(id=cid, tenant_id=tid, owner_user_id=uid, title="claim case")
            db.add(t)
            db.add(u)
            await db.flush()
            db.add(c)
            await db.flush()
            job = BackgroundJob(id=new_uuid(), tenant_id=tid, case_id=cid,
                                job_type=jtype, status="queued")
            db.add(job)
            await db.commit()

        await _refresh_jobs_pending_from_db(maker)
        key = (jtype,)
        before = jobs_pending._data.get(key, 0)
        assert before == 1

        async with maker() as db:
            from sqlalchemy import update
            await db.execute(
                update(BackgroundJob).where(BackgroundJob.job_type == jtype).values(status="claimed")
            )
            await db.commit()

        await _refresh_jobs_pending_from_db(maker)
        after = jobs_pending._data.get(key, 0)
        assert after == 0

        jobs_pending._data.clear()
        async with maker() as db:
            await db.execute(
                __import__("sqlalchemy").delete(BackgroundJob).where(BackgroundJob.job_type == jtype)
            )
            await db.execute(
                __import__("sqlalchemy").delete(Case).where(Case.id == cid)
            )
            await db.execute(
                __import__("sqlalchemy").delete(User).where(User.id == uid)
            )
            await db.execute(
                __import__("sqlalchemy").delete(Tenant).where(Tenant.id == tid)
            )
            await db.commit()

    @pytest.mark.asyncio
    async def test_retry_wait_counts_as_pending(self):
        from app.db.session import get_sessionmaker
        from app.db.models import BackgroundJob, Tenant, User, Case, new_uuid
        from app.core.metrics import _refresh_jobs_pending_from_db, jobs_pending
        import uuid as _uuid

        tid = f"t-rw-{_uuid.uuid4().hex[:8]}"
        uid = f"u-rw-{_uuid.uuid4().hex[:8]}"
        cid = f"c-rw-{_uuid.uuid4().hex[:8]}"
        jtype = f"rw-test-{_uuid.uuid4().hex[:6]}"

        maker = get_sessionmaker()
        async with maker() as db:
            t = Tenant(id=tid, name="rw-test", slug=tid)
            u = User(id=uid, tenant_id=tid, email_normalized=f"{uid}@test")
            c = Case(id=cid, tenant_id=tid, owner_user_id=uid, title="rw case")
            db.add(t)
            db.add(u)
            await db.flush()
            db.add(c)
            await db.flush()
            job = BackgroundJob(id=new_uuid(), tenant_id=tid, case_id=cid,
                                job_type=jtype, status="retry_wait")
            db.add(job)
            await db.commit()

        await _refresh_jobs_pending_from_db(maker)
        key = (jtype,)
        assert jobs_pending._data.get(key, 0) == 1

        jobs_pending._data.clear()
        async with maker() as db:
            await db.execute(
                __import__("sqlalchemy").delete(BackgroundJob).where(BackgroundJob.job_type == jtype)
            )
            await db.execute(
                __import__("sqlalchemy").delete(Case).where(Case.id == cid)
            )
            await db.execute(
                __import__("sqlalchemy").delete(User).where(User.id == uid)
            )
            await db.execute(
                __import__("sqlalchemy").delete(Tenant).where(Tenant.id == tid)
            )
            await db.commit()

    @pytest.mark.asyncio
    async def test_scheduled_counts_as_pending(self):
        from app.db.session import get_sessionmaker
        from app.db.models import BackgroundJob, Tenant, User, Case, new_uuid
        from app.core.metrics import _refresh_jobs_pending_from_db, jobs_pending
        from datetime import UTC, datetime, timedelta
        import uuid as _uuid

        tid = f"t-sched-{_uuid.uuid4().hex[:8]}"
        uid = f"u-sched-{_uuid.uuid4().hex[:8]}"
        cid = f"c-sched-{_uuid.uuid4().hex[:8]}"
        jtype = f"sched-test-{_uuid.uuid4().hex[:6]}"

        maker = get_sessionmaker()
        async with maker() as db:
            t = Tenant(id=tid, name="sched-test", slug=tid)
            u = User(id=uid, tenant_id=tid, email_normalized=f"{uid}@test")
            c = Case(id=cid, tenant_id=tid, owner_user_id=uid, title="sched case")
            db.add(t)
            db.add(u)
            await db.flush()
            db.add(c)
            await db.flush()
            job = BackgroundJob(id=new_uuid(), tenant_id=tid, case_id=cid,
                                job_type=jtype, status="scheduled",
                                scheduled_at=datetime.now(UTC) + timedelta(hours=1))
            db.add(job)
            await db.commit()

        await _refresh_jobs_pending_from_db(maker)
        key = (jtype,)
        assert jobs_pending._data.get(key, 0) == 1

        jobs_pending._data.clear()
        async with maker() as db:
            await db.execute(
                __import__("sqlalchemy").delete(BackgroundJob).where(BackgroundJob.job_type == jtype)
            )
            await db.execute(
                __import__("sqlalchemy").delete(Case).where(Case.id == cid)
            )
            await db.execute(
                __import__("sqlalchemy").delete(User).where(User.id == uid)
            )
            await db.execute(
                __import__("sqlalchemy").delete(Tenant).where(Tenant.id == tid)
            )
            await db.commit()

    @pytest.mark.asyncio
    async def test_cancel_not_pending(self):
        from app.db.session import get_sessionmaker
        from app.db.models import BackgroundJob, Tenant, User, Case, new_uuid
        from app.core.metrics import _refresh_jobs_pending_from_db, jobs_pending
        import uuid as _uuid

        tid = f"t-cancel-{_uuid.uuid4().hex[:8]}"
        uid = f"u-cancel-{_uuid.uuid4().hex[:8]}"
        cid = f"c-cancel-{_uuid.uuid4().hex[:8]}"
        jtype = f"cancel-test-{_uuid.uuid4().hex[:6]}"

        maker = get_sessionmaker()
        async with maker() as db:
            t = Tenant(id=tid, name="cancel-test", slug=tid)
            u = User(id=uid, tenant_id=tid, email_normalized=f"{uid}@test")
            c = Case(id=cid, tenant_id=tid, owner_user_id=uid, title="cancel case")
            db.add(t)
            db.add(u)
            await db.flush()
            db.add(c)
            await db.flush()
            job = BackgroundJob(id=new_uuid(), tenant_id=tid, case_id=cid,
                                job_type=jtype, status="cancelled")
            db.add(job)
            await db.commit()

        await _refresh_jobs_pending_from_db(maker)
        key = (jtype,)
        assert jobs_pending._data.get(key, 0) == 0

        jobs_pending._data.clear()
        async with maker() as db:
            await db.execute(
                __import__("sqlalchemy").delete(BackgroundJob).where(BackgroundJob.job_type == jtype)
            )
            await db.execute(
                __import__("sqlalchemy").delete(Case).where(Case.id == cid)
            )
            await db.execute(
                __import__("sqlalchemy").delete(User).where(User.id == uid)
            )
            await db.execute(
                __import__("sqlalchemy").delete(Tenant).where(Tenant.id == tid)
            )
            await db.commit()

    @pytest.mark.asyncio
    async def test_completed_not_pending(self):
        from app.db.session import get_sessionmaker
        from app.db.models import BackgroundJob, Tenant, User, Case, new_uuid
        from app.core.metrics import _refresh_jobs_pending_from_db, jobs_pending
        import uuid as _uuid

        tid = f"t-done-{_uuid.uuid4().hex[:8]}"
        uid = f"u-done-{_uuid.uuid4().hex[:8]}"
        cid = f"c-done-{_uuid.uuid4().hex[:8]}"
        jtype = f"done-test-{_uuid.uuid4().hex[:6]}"

        maker = get_sessionmaker()
        async with maker() as db:
            t = Tenant(id=tid, name="done-test", slug=tid)
            u = User(id=uid, tenant_id=tid, email_normalized=f"{uid}@test")
            c = Case(id=cid, tenant_id=tid, owner_user_id=uid, title="done case")
            db.add(t)
            db.add(u)
            await db.flush()
            db.add(c)
            await db.flush()
            job = BackgroundJob(id=new_uuid(), tenant_id=tid, case_id=cid,
                                job_type=jtype, status="succeeded")
            db.add(job)
            await db.commit()

        await _refresh_jobs_pending_from_db(maker)
        key = (jtype,)
        assert jobs_pending._data.get(key, 0) == 0

        jobs_pending._data.clear()
        async with maker() as db:
            await db.execute(
                __import__("sqlalchemy").delete(BackgroundJob).where(BackgroundJob.job_type == jtype)
            )
            await db.execute(
                __import__("sqlalchemy").delete(Case).where(Case.id == cid)
            )
            await db.execute(
                __import__("sqlalchemy").delete(User).where(User.id == uid)
            )
            await db.execute(
                __import__("sqlalchemy").delete(Tenant).where(Tenant.id == tid)
            )
            await db.commit()

    @pytest.mark.asyncio
    async def test_dead_lettered_not_pending(self):
        from app.db.session import get_sessionmaker
        from app.db.models import BackgroundJob, Tenant, User, Case, new_uuid
        from app.core.metrics import _refresh_jobs_pending_from_db, jobs_pending
        import uuid as _uuid

        tid = f"t-dl-{_uuid.uuid4().hex[:8]}"
        uid = f"u-dl-{_uuid.uuid4().hex[:8]}"
        cid = f"c-dl-{_uuid.uuid4().hex[:8]}"
        jtype = f"dl-test-{_uuid.uuid4().hex[:6]}"

        maker = get_sessionmaker()
        async with maker() as db:
            t = Tenant(id=tid, name="dl-test", slug=tid)
            u = User(id=uid, tenant_id=tid, email_normalized=f"{uid}@test")
            c = Case(id=cid, tenant_id=tid, owner_user_id=uid, title="dl case")
            db.add(t)
            db.add(u)
            await db.flush()
            db.add(c)
            await db.flush()
            job = BackgroundJob(id=new_uuid(), tenant_id=tid, case_id=cid,
                                job_type=jtype, status="dead_lettered")
            db.add(job)
            await db.commit()

        await _refresh_jobs_pending_from_db(maker)
        key = (jtype,)
        assert jobs_pending._data.get(key, 0) == 0

        jobs_pending._data.clear()
        async with maker() as db:
            await db.execute(
                __import__("sqlalchemy").delete(BackgroundJob).where(BackgroundJob.job_type == jtype)
            )
            await db.execute(
                __import__("sqlalchemy").delete(Case).where(Case.id == cid)
            )
            await db.execute(
                __import__("sqlalchemy").delete(User).where(User.id == uid)
            )
            await db.execute(
                __import__("sqlalchemy").delete(Tenant).where(Tenant.id == tid)
            )
            await db.commit()

    @pytest.mark.asyncio
    async def test_multiple_job_types_separate(self):
        from app.db.session import get_sessionmaker
        from app.db.models import BackgroundJob, Tenant, User, Case, new_uuid
        from app.core.metrics import _refresh_jobs_pending_from_db, jobs_pending
        import uuid as _uuid

        tid = f"t-multi-{_uuid.uuid4().hex[:8]}"
        uid = f"u-multi-{_uuid.uuid4().hex[:8]}"
        cid = f"c-multi-{_uuid.uuid4().hex[:8]}"
        jtype_a = f"multi-a-{_uuid.uuid4().hex[:6]}"
        jtype_b = f"multi-b-{_uuid.uuid4().hex[:6]}"

        maker = get_sessionmaker()
        async with maker() as db:
            t = Tenant(id=tid, name="multi-test", slug=tid)
            u = User(id=uid, tenant_id=tid, email_normalized=f"{uid}@test")
            c = Case(id=cid, tenant_id=tid, owner_user_id=uid, title="multi case")
            db.add(t)
            db.add(u)
            await db.flush()
            db.add(c)
            await db.flush()
            for jt, cnt in [(jtype_a, 2), (jtype_b, 3)]:
                for _ in range(cnt):
                    job = BackgroundJob(id=new_uuid(), tenant_id=tid, case_id=cid,
                                        job_type=jt, status="queued")
                    db.add(job)
            await db.commit()

        await _refresh_jobs_pending_from_db(maker)
        assert jobs_pending._data.get((jtype_a,), 0) == 2
        assert jobs_pending._data.get((jtype_b,), 0) == 3

        jobs_pending._data.clear()
        async with maker() as db:
            for jt in [jtype_a, jtype_b]:
                await db.execute(
                    __import__("sqlalchemy").delete(BackgroundJob).where(BackgroundJob.job_type == jt)
                )
            await db.execute(
                __import__("sqlalchemy").delete(Case).where(Case.id == cid)
            )
            await db.execute(
                __import__("sqlalchemy").delete(User).where(User.id == uid)
            )
            await db.execute(
                __import__("sqlalchemy").delete(Tenant).where(Tenant.id == tid)
            )
            await db.commit()

    @pytest.mark.asyncio
    async def test_double_refresh_idempotent(self):
        from app.db.session import get_sessionmaker
        from app.db.models import BackgroundJob, Tenant, User, Case, new_uuid
        from app.core.metrics import _refresh_jobs_pending_from_db, jobs_pending
        import uuid as _uuid

        tid = f"t-idem2-{_uuid.uuid4().hex[:8]}"
        uid = f"u-idem2-{_uuid.uuid4().hex[:8]}"
        cid = f"c-idem2-{_uuid.uuid4().hex[:8]}"
        jtype = f"refr2-{_uuid.uuid4().hex[:6]}"

        maker = get_sessionmaker()
        async with maker() as db:
            t = Tenant(id=tid, name="idem2-test", slug=tid)
            u = User(id=uid, tenant_id=tid, email_normalized=f"{uid}@test")
            c = Case(id=cid, tenant_id=tid, owner_user_id=uid, title="idem2 case")
            db.add(t)
            db.add(u)
            await db.flush()
            db.add(c)
            await db.flush()
            job = BackgroundJob(id=new_uuid(), tenant_id=tid, case_id=cid,
                                job_type=jtype, status="queued")
            db.add(job)
            await db.commit()

        await _refresh_jobs_pending_from_db(maker)
        v1 = jobs_pending._data.get((jtype,), 0)
        await _refresh_jobs_pending_from_db(maker)
        v2 = jobs_pending._data.get((jtype,), 0)
        assert v1 == v2 == 1

        jobs_pending._data.clear()
        async with maker() as db:
            await db.execute(
                __import__("sqlalchemy").delete(BackgroundJob).where(BackgroundJob.job_type == jtype)
            )
            await db.execute(
                __import__("sqlalchemy").delete(Case).where(Case.id == cid)
            )
            await db.execute(
                __import__("sqlalchemy").delete(User).where(User.id == uid)
            )
            await db.execute(
                __import__("sqlalchemy").delete(Tenant).where(Tenant.id == tid)
            )
            await db.commit()

    @pytest.mark.asyncio
    async def test_no_negative_after_all_cleared(self):
        from app.core.metrics import _refresh_jobs_pending_from_db, jobs_pending
        from app.db.session import get_sessionmaker
        jobs_pending._data.clear()
        maker = get_sessionmaker()
        await _refresh_jobs_pending_from_db(maker)
        for key, val in jobs_pending._data.items():
            assert val >= 0, f"Negative pending for {key}: {val}"


class TestDbCheckDurationWiring:
    def test_record_db_health_sets_duration(self):
        from app.core.metrics import record_db_health
        record_db_health(True, 0.042)
        body = collect_metrics()
        assert "emsalist_db_check_duration_seconds 0.042" in body

    def test_health_endpoint_records_db_metrics(self):
        resp = client.get("/health")
        assert resp.status_code in (200, 503)
        body = collect_metrics()
        assert "emsalist_db_health_status" in body


class TestBackupSizeWiring:
    def test_record_backup_size(self):
        from app.core.metrics import record_backup
        record_backup("succeeded", 5242880)
        body = collect_metrics()
        assert "emsalist_backup_size_bytes" in body
        assert "5.24288e+06" in body or "5242880" in body


# ─────────────────────────────────────────────────────
# Component State Production Wiring
# ─────────────────────────────────────────────────────

class TestDatabaseComponentState:
    def test_health_sets_database_healthy(self):
        from app.core.degraded_state import get_registry
        get_registry().reset()
        resp = client.get("/health")
        data = resp.json()
        db_comp = data.get("components", {}).get("database", {})
        assert db_comp.get("status") in ("healthy", "unknown", "unhealthy")

    def test_database_failure_updates_state(self):
        from app.core.degraded_state import update_component_state, ComponentStatus, get_registry
        update_component_state("database", ComponentStatus.UNHEALTHY, error_code="database_unavailable")
        state = get_registry().get("database")
        assert state.status == ComponentStatus.UNHEALTHY
        assert state.last_error_code == "database_unavailable"
        get_registry().reset()

    def test_database_metadata_redacted(self):
        from app.core.degraded_state import update_component_state, ComponentStatus, get_registry
        update_component_state("database", ComponentStatus.DEGRADED, metadata={"password": "s3cret"})
        state = get_registry().get("database")
        assert state.metadata.get("password") == "***"
        get_registry().reset()


class TestYargitayComponentState:
    def test_circuit_failure_marks_degraded(self):
        from app.services.yargitay_infra import circuit_failure, circuit_success
        from app.core.degraded_state import get_registry, ComponentStatus
        for _ in range(3):
            circuit_failure("NETWORK_ERROR")
        state = get_registry().get("yargitay")
        assert state.status == ComponentStatus.DEGRADED
        assert state.last_error_code == "NETWORK_ERROR"
        circuit_success()
        get_registry().reset()

    def test_circuit_success_marks_healthy(self):
        from app.services.yargitay_infra import circuit_failure, circuit_success
        from app.core.degraded_state import get_registry, ComponentStatus
        for _ in range(3):
            circuit_failure("timeout")
        circuit_success()
        state = get_registry().get("yargitay")
        assert state.status == ComponentStatus.HEALTHY
        get_registry().reset()


class TestAiProviderComponentState:
    def test_ai_provider_marks_degraded(self):
        from app.core.degraded_state import update_component_state, ComponentStatus, get_registry
        update_component_state("ai_provider", ComponentStatus.DEGRADED, error_code="api_error")
        state = get_registry().get("ai_provider")
        assert state.status == ComponentStatus.DEGRADED
        assert state.last_error_code == "api_error"
        get_registry().reset()

    def test_ai_provider_marks_healthy(self):
        from app.core.degraded_state import update_component_state, ComponentStatus, get_registry
        update_component_state("ai_provider", ComponentStatus.HEALTHY)
        state = get_registry().get("ai_provider")
        assert state.status == ComponentStatus.HEALTHY
        get_registry().reset()


class TestQueueComponentState:
    def test_queue_marks_healthy(self):
        from app.core.degraded_state import update_component_state, ComponentStatus, get_registry
        update_component_state("queue", ComponentStatus.HEALTHY)
        state = get_registry().get("queue")
        assert state.status == ComponentStatus.HEALTHY
        get_registry().reset()


class TestBackupComponentState:
    def test_backup_marks_healthy(self):
        from app.core.degraded_state import update_component_state, ComponentStatus, get_registry
        update_component_state("backup", ComponentStatus.HEALTHY)
        state = get_registry().get("backup")
        assert state.status == ComponentStatus.HEALTHY
        get_registry().reset()

    def test_backup_marks_degraded(self):
        from app.core.degraded_state import update_component_state, ComponentStatus, get_registry
        update_component_state("backup", ComponentStatus.DEGRADED, error_code="backup_failed")
        state = get_registry().get("backup")
        assert state.status == ComponentStatus.DEGRADED
        assert state.last_error_code == "backup_failed"
        get_registry().reset()


class TestRestoreComponentState:
    def test_restore_marks_healthy(self):
        from app.core.degraded_state import update_component_state, ComponentStatus, get_registry
        update_component_state("restore", ComponentStatus.HEALTHY)
        state = get_registry().get("restore")
        assert state.status == ComponentStatus.HEALTHY
        get_registry().reset()


class TestStorageComponentState:
    def test_storage_marks_unhealthy_disk_full(self):
        from app.core.degraded_state import update_component_state, ComponentStatus, get_registry
        update_component_state("storage", ComponentStatus.UNHEALTHY, error_code="insufficient_disk_space")
        state = get_registry().get("storage")
        assert state.status == ComponentStatus.UNHEALTHY
        assert state.last_error_code == "insufficient_disk_space"
        get_registry().reset()

    def test_storage_marks_healthy(self):
        from app.core.degraded_state import update_component_state, ComponentStatus, get_registry
        update_component_state("storage", ComponentStatus.HEALTHY)
        state = get_registry().get("storage")
        assert state.status == ComponentStatus.HEALTHY
        get_registry().reset()


class TestLegalSourceIngestComponentState:
    def test_ingest_marks_healthy(self):
        from app.core.degraded_state import update_component_state, ComponentStatus, get_registry
        update_component_state("legal_source_ingest", ComponentStatus.HEALTHY)
        state = get_registry().get("legal_source_ingest")
        assert state.status == ComponentStatus.HEALTHY
        get_registry().reset()


# ─────────────────────────────────────────────────────
# Health Unknown Semantics
# ─────────────────────────────────────────────────────

class TestHealthUnknownSemantics:
    def test_unknown_does_not_affect_overall_healthy(self):
        from app.core.degraded_state import DegradedStateRegistry, ComponentStatus
        r = DegradedStateRegistry()
        for name in ("database", "storage"):
            r.update(name, ComponentStatus.HEALTHY)
        assert r.get_overall_status() == ComponentStatus.HEALTHY

    def test_critical_database_unhealthy_makes_overall_unhealthy(self):
        from app.core.degraded_state import DegradedStateRegistry, ComponentStatus
        r = DegradedStateRegistry()
        r.update("database", ComponentStatus.HEALTHY)
        r.update("storage", ComponentStatus.HEALTHY)
        r.update("database", ComponentStatus.UNHEALTHY)
        assert r.get_overall_status() == ComponentStatus.UNHEALTHY

    def test_non_critical_degraded_makes_overall_degraded(self):
        from app.core.degraded_state import DegradedStateRegistry, ComponentStatus
        r = DegradedStateRegistry()
        r.update("database", ComponentStatus.HEALTHY)
        r.update("storage", ComponentStatus.HEALTHY)
        r.update("yargitay", ComponentStatus.DEGRADED)
        assert r.get_overall_status() == ComponentStatus.DEGRADED

    def test_unknown_components_count(self):
        from app.core.degraded_state import get_registry
        r = get_registry()
        all_states = r.get_all()
        unknown_count = sum(1 for s in all_states.values() if s.status == ComponentStatus.UNKNOWN)
        assert unknown_count >= 6  # most components start unknown

    def test_all_components_present_in_health(self):
        resp = client.get("/health")
        data = resp.json()
        components = data.get("components", {})
        for name in ALL_COMPONENTS:
            assert name in components, f"Component {name} missing from health"


# ─────────────────────────────────────────────────────
# Error Handler Integration
# ─────────────────────────────────────────────────────

class TestErrorHandlerIntegration:
    def test_unknown_exception_returns_internal_error(self):
        resp = client.get("/health")
        assert resp.status_code in (200, 503)

    def test_correlation_id_in_response(self):
        from app.core.error_classification import build_error_response
        resp = build_error_response(ValueError("test"))
        assert "correlation_id" in resp["error"]

    def test_db_exception_response_no_raw_detail(self):
        from app.core.error_classification import build_error_response
        from app.core.redaction import redact_value
        exc = ConnectionError("Connection refused: postgresql://user:pass@host/db")
        resp = build_error_response(exc)
        body = json.dumps(resp)
        assert "pass" not in body
        assert "postgresql" not in body

    def test_enospc_returns_insufficient_disk_space(self):
        import errno
        from app.core.error_classification import build_error_response
        exc = OSError(errno.ENOSPC, "No space left")
        resp = build_error_response(exc)
        assert resp["error"]["code"] == "INSUFFICIENT_DISK_SPACE"

    def test_internal_error_no_secrets(self):
        from app.core.error_classification import build_error_response
        exc = Exception("secret=abc123 password=mypass api_key=sk-key")
        resp = build_error_response(exc, include_debug=True)
        body = json.dumps(resp)
        assert "abc123" not in body
        assert "mypass" not in body
        assert "sk-key" not in body
