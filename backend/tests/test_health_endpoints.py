
from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


class TestHealthEndpoints:

    def test_live_returns_200(self):
        response = client.get("/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        assert "service" in data

    def test_live_returns_fast(self):
        t0 = time.time()
        response = client.get("/live")
        duration = time.time() - t0
        assert response.status_code == 200
        assert duration < 1.0

    def test_live_does_not_query_database(self):
        with patch("app.main.check_db_health", side_effect=Exception("should not be called")):
            response = client.get("/live")
            assert response.status_code == 200

    def test_ready_with_healthy_db(self):
        with patch("app.main.check_db_health", new_callable=AsyncMock) as mock_health:
            mock_health.return_value = {
                "backend": "sqlalchemy",
                "connected": True,
                "latency_ms": 5,
                "migration_head": "abc123",
            }
            response = client.get("/ready")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert data["checks"]["database"]["status"] == "ok"
            assert data["checks"]["configuration"]["status"] == "ok"

    def test_ready_with_db_down_returns_503(self):
        with patch("app.main.check_db_health", new_callable=AsyncMock) as mock_health:
            mock_health.return_value = {
                "backend": "sqlalchemy",
                "connected": False,
                "error": "connection refused",
            }
            response = client.get("/ready")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "not_ready"
            assert data["checks"]["database"]["status"] == "failed"

    def test_ready_with_db_exception_returns_503(self):
        with patch("app.main.check_db_health", new_callable=AsyncMock) as mock_health:
            mock_health.side_effect = Exception("timeout")
            response = client.get("/ready")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "not_ready"
            assert data["checks"]["database"]["status"] == "failed"

    def test_health_returns_200_when_healthy(self):
        with patch("app.main.check_db_health", new_callable=AsyncMock) as mock_health:
            mock_health.return_value = {
                "backend": "sqlalchemy",
                "connected": True,
                "latency_ms": 3,
                "migration_head": "abc",
            }
            response = client.get("/system-health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"

    def test_health_returns_503_when_unhealthy(self):
        with patch("app.main.check_db_health", new_callable=AsyncMock) as mock_health:
            mock_health.return_value = {
                "backend": "sqlalchemy",
                "connected": False,
                "error": "down",
            }
            response = client.get("/system-health")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "unhealthy"

    def test_legacy_health_returns_200(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestHealthEndpointSecurity:

    def test_no_credentials_in_live_response(self):
        response = client.get("/live")
        data = response.json()
        body = json.dumps(data)
        for sensitive in ("password", "secret", "token", "api_key", "dsn", "connection_string"):
            assert sensitive not in body.lower()

    def test_no_credentials_in_ready_response(self):
        with patch("app.main.check_db_health", new_callable=AsyncMock) as mock_health:
            mock_health.return_value = {
                "backend": "sqlalchemy",
                "connected": True,
                "latency_ms": 2,
                "migration_head": "abc",
            }
            response = client.get("/ready")
            data = response.json()
            body = json.dumps(data)
            assert "password" not in body.lower()
            assert "secret" not in body.lower()
            assert "stack_trace" not in body.lower()

    def test_no_credentials_in_health_response(self):
        with patch("app.main.check_db_health", new_callable=AsyncMock) as mock_health:
            mock_health.return_value = {
                "backend": "sqlalchemy",
                "connected": True,
                "latency_ms": 2,
                "migration_head": "abc",
            }
            response = client.get("/system-health")
            data = response.json()
            body = json.dumps(data)
            assert "password" not in body.lower()
            assert "secret" not in body.lower()

    def test_db_error_detail_is_truncated(self):
        with patch("app.main.check_db_health", new_callable=AsyncMock) as mock_health:
            mock_health.return_value = {
                "backend": "sqlalchemy",
                "connected": False,
                "error": "a" * 200,
            }
            response = client.get("/ready")
            data = response.json()
            detail = data["checks"]["database"].get("detail", "")
            assert len(detail) <= 100

    def test_readiness_does_not_modify_data(self):
        with patch("app.main.check_db_health", new_callable=AsyncMock) as mock_health:
            mock_health.return_value = {
                "backend": "sqlalchemy",
                "connected": True,
                "latency_ms": 1,
                "migration_head": "abc",
            }
            response1 = client.get("/ready")
            response2 = client.get("/ready")
            assert response1.status_code == 200
            assert response2.status_code == 200
            assert response1.json() == response2.json()


class TestHealthEndpointsBypassRateLimit:

    def test_live_bypasses_rate_limit(self):
        for _ in range(10):
            response = client.get("/live")
            assert response.status_code == 200

    def test_ready_bypasses_rate_limit(self):
        with patch("app.main.check_db_health", new_callable=AsyncMock) as mock_health:
            mock_health.return_value = {
                "backend": "sqlalchemy",
                "connected": True,
                "latency_ms": 1,
                "migration_head": "abc",
            }
            for _ in range(10):
                response = client.get("/ready")
                assert response.status_code == 200

    def test_health_bypasses_rate_limit(self):
        with patch("app.main.check_db_health", new_callable=AsyncMock) as mock_health:
            mock_health.return_value = {
                "backend": "sqlalchemy",
                "connected": True,
                "latency_ms": 1,
                "migration_head": "abc",
            }
            for _ in range(10):
                response = client.get("/system-health")
                assert response.status_code == 200
