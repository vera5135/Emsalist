"""P2.8B13D — DB-backed access token session validation executable proof."""
from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch

from sqlalchemy import delete, select

from app.db.models import AuthSession, Tenant, User
from app.db.session import get_sessionmaker
from app.main import app
from app.services.auth_service import create_access_token

TENANT = "tenant-b13d"
USER_ID = "user-b13d"
USER_ID_B = "user-b13d-b"
SESSION_ID_1 = "session-1-b13d"
SESSION_ID_2 = "session-2-b13d"


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _make_session(sid: str, uid: str = USER_ID, tid: str = TENANT,
                  expires_in: int = 3600, revoked: bool = False):
    now = datetime.now(UTC)
    return AuthSession(
        id=sid, tenant_id=tid, user_id=uid,
        refresh_token_hash=_hash(f"rt-{sid}"),
        token_family_id=f"tf-{sid}", created_at=now, last_used_at=now,
        expires_at=now + timedelta(seconds=expires_in),
        revoked_at=now - timedelta(seconds=1) if revoked else None,
        revoke_reason="test" if revoked else "",
    )


_JWT_MODULES = [
    "app.services.auth_service.get_auth_mode",
    "app.services.auth_manager.get_auth_mode",
    "app.routes.auth_routes_new.get_auth_mode",
]


def _jwt_mode():
    return contextmanager(
        lambda: (patch(p, return_value="jwt") for p in _JWT_MODULES)
    )


# Hack: inline context manager
import contextlib as _cl
@_cl.contextmanager
def _jm():
    ps = [patch(p, return_value="jwt") for p in _JWT_MODULES]
    for p in ps: p.start()
    try: yield
    finally:
        for p in ps: p.stop()


async def _http(method, path, token=None, json=None):
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        return await ac.request(method, path, json=json, headers=headers)


async def _seed(tv=0):
    async with get_sessionmaker()() as session:
        for tbl in (AuthSession, User, Tenant):
            await session.execute(delete(tbl))
        session.add(Tenant(id=TENANT, name="T", slug=TENANT, status="active"))
        session.add(User(id=USER_ID, tenant_id=TENANT,
                         email_normalized="u@t", display_name="U",
                         status="active", role="lawyer", token_version=tv))
        await session.flush()
        s = _make_session(SESSION_ID_1)
        session.add(s)
        await session.flush()
        await session.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 1 — active real session token accepted
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_active_session_token_accepted():
    await _seed()
    token = create_access_token(USER_ID, TENANT, "lawyer", SESSION_ID_1, 0)
    with _jm():
        r = await _http("GET", "/auth/me", token=token)
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 2 — revoked session rejects existing token
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_revoked_session_rejects():
    await _seed()
    token = create_access_token(USER_ID, TENANT, "lawyer", SESSION_ID_1, 0)
    # Revoke session
    async with get_sessionmaker()() as session:
        s = await session.get(AuthSession, SESSION_ID_1)
        s.revoked_at = datetime.now(UTC)
        await session.commit()
    with _jm():
        r = await _http("GET", "/auth/me", token=token)
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 3 — expired session rejects unexpired JWT
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_expired_session_rejects():
    await _seed()
    token = create_access_token(USER_ID, TENANT, "lawyer", SESSION_ID_1, 0)
    async with get_sessionmaker()() as session:
        s = await session.get(AuthSession, SESSION_ID_1)
        s.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    with _jm():
        r = await _http("GET", "/auth/me", token=token)
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 4 — token_version mismatch rejects
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_token_version_mismatch_rejects():
    await _seed(tv=0)
    token = create_access_token(USER_ID, TENANT, "lawyer", SESSION_ID_1, 0)
    async with get_sessionmaker()() as session:
        user = await session.get(User, USER_ID)
        user.token_version = 1
        await session.commit()
    with _jm():
        r = await _http("GET", "/auth/me", token=token)
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 5 — logout invalidates same access token
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_logout_invalidates_token():
    await _seed()
    token = create_access_token(USER_ID, TENANT, "lawyer", SESSION_ID_1, 0)
    with _jm():
        r = await _http("POST", "/auth/logout", token=token)
        assert r.status_code == 200
        r = await _http("GET", "/auth/me", token=token)
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 6 — logout-all invalidates all tokens
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_logout_all_invalidates_both_tokens():
    async with get_sessionmaker()() as session:
        await session.execute(delete(AuthSession))
        await session.execute(delete(User))
        await session.execute(delete(Tenant))
        session.add(Tenant(id=TENANT, name="T", slug=TENANT, status="active"))
        session.add(User(id=USER_ID, tenant_id=TENANT,
                         email_normalized="u@t", display_name="U",
                         status="active", role="lawyer", token_version=0))
        session.add(_make_session(SESSION_ID_1))
        session.add(_make_session(SESSION_ID_2))
        await session.commit()

    token_a = create_access_token(USER_ID, TENANT, "lawyer", SESSION_ID_1, 0)
    token_b = create_access_token(USER_ID, TENANT, "lawyer", SESSION_ID_2, 0)
    with _jm():
        # logout-all
        r = await _http("POST", "/auth/logout-all", token=token_a)
        assert r.status_code == 200
        # both tokens now rejected
        r = await _http("GET", "/auth/me", token=token_a)
        assert r.status_code == 401
        r = await _http("GET", "/auth/me", token=token_b)
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 7 — password change invalidates old token
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_password_change_invalidates_token():
    async with get_sessionmaker()() as session:
        await session.execute(delete(AuthSession))
        await session.execute(delete(User))
        await session.execute(delete(Tenant))
        from app.services.auth_service import hash_password
        session.add(Tenant(id=TENANT, name="T", slug=TENANT, status="active"))
        session.add(User(id=USER_ID, tenant_id=TENANT,
                         email_normalized="u@t", display_name="U",
                         status="active", role="lawyer", token_version=0,
                         password_hash=hash_password("oldpass")))
        session.add(_make_session(SESSION_ID_1))
        await session.commit()

    token = create_access_token(USER_ID, TENANT, "lawyer", SESSION_ID_1, 0)
    with _jm():
        r = await _http("POST", "/auth/change-password",
                         token=token, json={"current_password": "oldpass",
                                            "new_password": "NewPass123!"})
        assert r.status_code == 200
        r = await _http("GET", "/auth/me", token=token)
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 8 — session user mismatch rejected
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_session_user_mismatch_rejected():
    async with get_sessionmaker()() as session:
        await session.execute(delete(AuthSession))
        await session.execute(delete(User))
        await session.execute(delete(Tenant))
        session.add(Tenant(id=TENANT, name="T", slug=TENANT, status="active"))
        session.add(User(id=USER_ID, tenant_id=TENANT,
                         email_normalized="u@t", display_name="U",
                         status="active", role="lawyer", token_version=0))
        session.add(User(id=USER_ID_B, tenant_id=TENANT,
                         email_normalized="b@t", display_name="B",
                         status="active", role="lawyer", token_version=0))
        session.add(_make_session(SESSION_ID_1))  # belongs to USER_ID
        await session.commit()

    # token claims sub=USER_ID_B but session belongs to USER_ID
    token = create_access_token(USER_ID_B, TENANT, "lawyer", SESSION_ID_1, 0)
    with _jm():
        r = await _http("GET", "/auth/me", token=token)
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 9 — session tenant mismatch rejected
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_session_tenant_mismatch_rejected():
    T2 = "tenant-b13d-2"
    async with get_sessionmaker()() as session:
        await session.execute(delete(AuthSession))
        await session.execute(delete(User))
        await session.execute(delete(Tenant))
        session.add(Tenant(id=TENANT, name="T1", slug=TENANT, status="active"))
        session.add(Tenant(id=T2, name="T2", slug=T2, status="active"))
        session.add(User(id=USER_ID, tenant_id=TENANT,
                         email_normalized="u@t", display_name="U",
                         status="active", role="lawyer", token_version=0))
        # Session in TENANT, but token claims tenant T2
        session.add(_make_session(SESSION_ID_1, uid=USER_ID, tid=TENANT))
        await session.commit()

    token = create_access_token(USER_ID, T2, "lawyer", SESSION_ID_1, 0)
    with _jm():
        r = await _http("GET", "/auth/me", token=token)
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 10 — inactive user rejected
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_inactive_user_rejected():
    await _seed()
    token = create_access_token(USER_ID, TENANT, "lawyer", SESSION_ID_1, 0)
    async with get_sessionmaker()() as session:
        user = await session.get(User, USER_ID)
        user.status = "disabled"
        await session.commit()
    with _jm():
        r = await _http("GET", "/auth/me", token=token)
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 11 — stale role claim rejected
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_stale_role_rejected():
    await _seed()
    token = create_access_token(USER_ID, TENANT, "lawyer", SESSION_ID_1, 0)
    async with get_sessionmaker()() as session:
        user = await session.get(User, USER_ID)
        user.role = "tenant_admin"
        await session.commit()
    with _jm():
        r = await _http("GET", "/auth/me", token=token)
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 12 — missing/invalid session_id claim rejected
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_missing_session_id_claim_rejected():
    await _seed()
    token = create_access_token(USER_ID, TENANT, "lawyer", "", 0)
    with _jm():
        r = await _http("GET", "/auth/me", token=token)
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# TEST 13 — invalid token_version type rejected
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_invalid_token_version_type_rejected():
    await _seed()
    # Manually craft JWT with string token_version
    import jwt as pyjwt
    from datetime import UTC, datetime, timedelta
    now = datetime.now(UTC)
    payload = {
        "sub": USER_ID, "tenant_id": TENANT, "role": "lawyer",
        "session_id": SESSION_ID_1, "token_version": "not_an_int",
        "jti": uuid.uuid4().hex[:12], "iss": "emsalist",
        "aud": "emsalist-api", "iat": now, "nbf": now,
        "exp": now + timedelta(minutes=30), "token_type": "access",
    }
    from app.services.auth_service import _get_jwt_secret
    token = pyjwt.encode(payload, _get_jwt_secret(), algorithm="HS256")
    with _jm():
        r = await _http("GET", "/auth/me", token=token)
        assert r.status_code == 401
