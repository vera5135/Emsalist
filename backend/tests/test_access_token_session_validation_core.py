from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from app.services import auth_service


class _DbContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Sessionmaker:
    def __call__(self):
        return _DbContext()


def _request() -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/auth/me",
        "headers": [],
        "query_string": b"",
        "server": ("test", 80),
        "client": ("test", 1234),
        "scheme": "http",
    })


def _credentials() -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")


def _payload(**overrides):
    value = {
        "sub": "user-1",
        "tenant_id": "tenant-1",
        "role": "lawyer",
        "session_id": "session-1",
        "token_version": 2,
    }
    value.update(overrides)
    return value


@pytest.fixture
def auth_dependencies(monkeypatch):
    user = SimpleNamespace(
        id="user-1",
        tenant_id="tenant-1",
        role="lawyer",
        status="active",
        token_version=2,
    )
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        tenant_id="tenant-1",
    )

    monkeypatch.setattr(auth_service, "get_auth_mode", lambda: "jwt")
    monkeypatch.setattr(auth_service, "decode_token", lambda *_: _payload())

    from app.db import auth_repository
    from app.db import session as session_module

    get_user = AsyncMock(return_value=user)
    get_session = AsyncMock(return_value=session)
    monkeypatch.setattr(auth_repository.UserRepository, "get_by_id", get_user)
    monkeypatch.setattr(
        auth_repository.AuthSessionRepository,
        "get_active_session",
        get_session,
    )
    monkeypatch.setattr(session_module, "get_sessionmaker", lambda: _Sessionmaker())

    return SimpleNamespace(
        user=user,
        auth_session=session,
        get_user=get_user,
        get_session=get_session,
    )


@pytest.mark.asyncio
async def test_active_canonical_user_and_session_are_accepted(auth_dependencies):
    ctx = await auth_service.resolve_current_user(_request(), _credentials())

    assert ctx.authenticated is True
    assert ctx.actor_id == "user-1"
    assert ctx.tenant_id == "tenant-1"
    assert ctx.role == "lawyer"
    assert ctx.session_id == "session-1"
    auth_dependencies.get_user.assert_awaited_once()
    auth_dependencies.get_session.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "claim,value",
    [
        ("sub", ""),
        ("tenant_id", None),
        ("role", 42),
        ("session_id", ""),
        ("token_version", True),
        ("token_version", "2"),
    ],
)
async def test_malformed_session_claims_fail_closed(
    monkeypatch,
    auth_dependencies,
    claim,
    value,
):
    monkeypatch.setattr(
        auth_service,
        "decode_token",
        lambda *_: _payload(**{claim: value}),
    )

    with pytest.raises(HTTPException) as exc:
        await auth_service.resolve_current_user(_request(), _credentials())

    assert exc.value.status_code == 401
    assert exc.value.detail == "Authentication session is no longer valid"


@pytest.mark.asyncio
async def test_missing_or_revoked_session_rejects_existing_jwt(auth_dependencies):
    auth_dependencies.get_session.return_value = None

    with pytest.raises(HTTPException) as exc:
        await auth_service.resolve_current_user(_request(), _credentials())

    assert exc.value.status_code == 401
    assert exc.value.detail == "Authentication session is no longer valid"


@pytest.mark.asyncio
async def test_token_version_mismatch_rejects_existing_jwt(auth_dependencies):
    auth_dependencies.user.token_version = 3

    with pytest.raises(HTTPException) as exc:
        await auth_service.resolve_current_user(_request(), _credentials())

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_role_claim_must_match_canonical_user(monkeypatch, auth_dependencies):
    monkeypatch.setattr(
        auth_service,
        "decode_token",
        lambda *_: _payload(role="admin"),
    )

    with pytest.raises(HTTPException) as exc:
        await auth_service.resolve_current_user(_request(), _credentials())

    assert exc.value.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_id,tenant_id",
    [
        ("other-user", "tenant-1"),
        ("user-1", "other-tenant"),
    ],
)
async def test_session_binding_must_match_token_subject_and_tenant(
    auth_dependencies,
    user_id,
    tenant_id,
):
    auth_dependencies.auth_session.user_id = user_id
    auth_dependencies.auth_session.tenant_id = tenant_id

    with pytest.raises(HTTPException) as exc:
        await auth_service.resolve_current_user(_request(), _credentials())

    assert exc.value.status_code == 401
