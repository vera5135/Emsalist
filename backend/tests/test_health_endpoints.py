
from __future__ import annotations

import json
import os
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _normalize_health(data: dict) -> dict:
    """Strip timestamps and volatile fields from health response for comparison."""
    if "components" in data:
        for comp in data["components"].values():
            comp.pop("checked_at", None)
    return data


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
            assert data["checks"]["database"]["code"] == "database_unavailable"

    def test_ready_with_db_exception_returns_503(self):
        with patch("app.main.check_db_health", new_callable=AsyncMock) as mock_health:
            mock_health.side_effect = Exception("timeout")
            response = client.get("/ready")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "not_ready"
            assert data["checks"]["database"]["status"] == "failed"
            assert data["checks"]["database"]["code"] == "database_unavailable"

    def test_health_returns_200_when_healthy(self):
        with patch("app.main.check_db_health", new_callable=AsyncMock) as mock_health:
            mock_health.return_value = {
                "backend": "sqlalchemy",
                "connected": True,
                "latency_ms": 3,
                "migration_head": "abc",
            }
            response = client.get("/health")
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
            response = client.get("/health")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "unhealthy"

    def test_health_comprehensive_response(self):
        with patch("app.main.check_db_health", new_callable=AsyncMock) as mock_health:
            mock_health.return_value = {
                "backend": "sqlalchemy",
                "connected": True,
                "latency_ms": 5,
                "migration_head": "abc123",
            }
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert "checks" in data
            assert "database" in data["checks"]
            assert "configuration" in data["checks"]
            assert data["checks"]["database"]["status"] == "ok"
            assert data["checks"]["configuration"]["status"] == "ok"

    def test_system_health_aliases_health(self):
        with patch("app.main.check_db_health", new_callable=AsyncMock) as mock_health:
            mock_health.return_value = {
                "backend": "sqlalchemy",
                "connected": True,
                "latency_ms": 3,
                "migration_head": "abc",
            }
            r1 = client.get("/health")
            r2 = client.get("/system-health")
            d1 = _normalize_health(r1.json())
            d2 = _normalize_health(r2.json())
            assert d1 == d2


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
            response = client.get("/health")
            data = response.json()
            body = json.dumps(data)
            assert "password" not in body.lower()
            assert "secret" not in body.lower()

    def test_no_db_exception_text_in_ready_response(self):
        with patch("app.main.check_db_health", new_callable=AsyncMock) as mock_health:
            mock_health.side_effect = Exception("OperationalError: connection refused at 127.0.0.1:5432")
            response = client.get("/ready")
            data = response.json()
            body = json.dumps(data)
            assert "OperationalError" not in body
            assert "connection refused" not in body
            assert "127.0.0.1" not in body
            assert "5432" not in body
            assert data["checks"]["database"]["code"] == "database_unavailable"

    def test_no_db_exception_text_in_health_response(self):
        with patch("app.main.check_db_health", new_callable=AsyncMock) as mock_health:
            mock_health.side_effect = Exception("OperationalError: connection timeout")
            response = client.get("/health")
            data = response.json()
            body = json.dumps(data)
            assert "OperationalError" not in body
            assert "connection timeout" not in body
            assert data["checks"]["database"]["code"] == "database_unavailable"

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
                response = client.get("/health")
                assert response.status_code == 200
