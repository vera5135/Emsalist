from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from types import SimpleNamespace

from app.main import app


def test_chrome_draft_patch_preflight_allowed():
    client = TestClient(app)
    response = client.options(
        "/api/v1/cases/case-1/drafts/draft-1",
        headers={
            "Origin": "http://127.0.0.1:4096",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:4096"
    assert "PATCH" in response.headers["access-control-allow-methods"]


def test_web_demo_seed_requires_explicit_development_opt_in(monkeypatch):
    from app.config import get_settings
    from app.scripts import seed_web_demo

    monkeypatch.setenv("EMSALIST_ENVIRONMENT", "development")
    monkeypatch.delenv("EMSALIST_DEMO_SEED_ENABLED", raising=False)
    get_settings.cache_clear()

    with pytest.raises(SystemExit, match="EMSALIST_DEMO_SEED_ENABLED=1"):
        seed_web_demo._guard()


def test_web_demo_seed_refuses_production(monkeypatch):
    from app.scripts import seed_web_demo

    monkeypatch.setenv("EMSALIST_DEMO_SEED_ENABLED", "1")
    monkeypatch.setattr(
        seed_web_demo,
        "get_settings",
        lambda: SimpleNamespace(environment="production"),
    )

    with pytest.raises(SystemExit, match="outside_development"):
        seed_web_demo._guard()
