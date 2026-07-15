"""P2.8B13D — DB-backed access token session validation executable proof."""
from __future__ import annotations

import hashlib
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch

from app.db.models import AuthSession, Tenant, User
from app.db.session import get_sessionmaker
from app.main import app
from app.services.auth_service import create_access_token, _get_jwt_secret


def _make_tenant(tid): return Tenant(id=tid, name="T", slug=tid, status="active")
def _make_user(uid, tid, role="lawyer", tv=0, pw=None):
    from app.services.auth_service import hash_password
    return User(id=uid, tenant_id=tid, email_normalized=f"{uid}@t", display_name="U",
                status="active", role=role, token_version=tv,
                password_hash=hash_password(pw) if pw else None)
def _make_session(sid, uid, tid):
    now = datetime.now(UTC)
    return AuthSession(id=sid, tenant_id=tid, user_id=uid,
        refresh_token_hash=hashlib.sha256(f"rt-{sid}".encode()).hexdigest(),
        token_family_id=f"tf-{sid}", created_at=now, last_used_at=now,
        expires_at=now + timedelta(days=7))

_JWT_PATCH = ["app.services.auth_service.get_auth_mode",
              "app.services.auth_manager.get_auth_mode",
              "app.routes.auth_routes_new.get_auth_mode"]
@contextmanager
def _jm():
    ps = [patch(p, return_value="jwt") for p in _JWT_PATCH]
    for p in ps: p.start()
    try: yield
    finally:
        for p in ps: p.stop()

async def _http(method, path, token=None, json=None):
    h = {"Authorization": f"Bearer {token}"} if token else {}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        return await ac.request(method, path, json=json, headers=h)

def _unique(*prefixes):
    return [f"{p}-{uuid.uuid4().hex[:6]}" for p in prefixes]

async def _seed(tid, uid, sid, u_kw=None):
    session_kw = {} if u_kw is None else dict(u_kw)
    async with get_sessionmaker()() as s:
        s.add(_make_tenant(tid))
        await s.flush()
        s.add(_make_user(uid, tid, **session_kw))
        await s.flush()
        s.add(_make_session(sid, uid, tid))
        await s.commit()

def _tok(uid, tid, sid, role="lawyer", tv=0):
    return create_access_token(uid, tid, role, sid, tv)


@pytest.mark.asyncio
async def test_active_token_accepted():
    tid, uid, sid = _unique("t-a", "u-a", "s-a")
    await _seed(tid, uid, sid)
    t = _tok(uid, tid, sid)
    with _jm():
        assert (await _http("GET", "/auth/me", token=t)).status_code == 200

@pytest.mark.asyncio
async def test_revoked_session_rejects():
    tid, uid, sid = _unique("t-r", "u-r", "s-r")
    await _seed(tid, uid, sid)
    t = _tok(uid, tid, sid)
    async with get_sessionmaker()() as s:
        a = await s.get(AuthSession, sid)
        a.revoked_at = datetime.now(UTC)
        await s.commit()
    with _jm():
        assert (await _http("GET", "/auth/me", token=t)).status_code == 401

@pytest.mark.asyncio
async def test_expired_session_rejects():
    tid, uid, sid = _unique("t-e", "u-e", "s-e")
    await _seed(tid, uid, sid)
    t = _tok(uid, tid, sid)
    async with get_sessionmaker()() as s:
        a = await s.get(AuthSession, sid)
        a.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await s.commit()
    with _jm():
        assert (await _http("GET", "/auth/me", token=t)).status_code == 401

@pytest.mark.asyncio
async def test_token_version_mismatch():
    tid, uid, sid = _unique("t-tv", "u-tv", "s-tv")
    await _seed(tid, uid, sid)
    t = _tok(uid, tid, sid)
    async with get_sessionmaker()() as s:
        u = await s.get(User, uid)
        u.token_version = 1
        await s.commit()
    with _jm():
        assert (await _http("GET", "/auth/me", token=t)).status_code == 401

@pytest.mark.asyncio
async def test_logout_invalidates():
    tid, uid, sid = _unique("t-lo", "u-lo", "s-lo")
    await _seed(tid, uid, sid)
    t = _tok(uid, tid, sid)
    with _jm():
        assert (await _http("POST", "/auth/logout", token=t)).status_code == 200
        assert (await _http("GET", "/auth/me", token=t)).status_code == 401

@pytest.mark.asyncio
async def test_logout_all_invalidates_both():
    tid, uid, s1, s2 = _unique("t-lo2", "u-lo2", "s1-lo2", "s2-lo2")
    async with get_sessionmaker()() as s:
        s.add(_make_tenant(tid))
        await s.flush()
        s.add(_make_user(uid, tid))
        await s.flush()
        s.add(_make_session(s1, uid, tid))
        s.add(_make_session(s2, uid, tid))
        await s.commit()
    ta = _tok(uid, tid, s1)
    tb = _tok(uid, tid, s2)
    with _jm():
        assert (await _http("POST", "/auth/logout-all", token=ta)).status_code == 200
        assert (await _http("GET", "/auth/me", token=ta)).status_code == 401
        assert (await _http("GET", "/auth/me", token=tb)).status_code == 401

@pytest.mark.asyncio
async def test_password_change_invalidates():
    tid, uid, sid = _unique("t-pw", "u-pw", "s-pw")
    async with get_sessionmaker()() as s:
        s.add(_make_tenant(tid))
        await s.flush()
        s.add(_make_user(uid, tid, pw="oldpass"))
        await s.flush()
        s.add(_make_session(sid, uid, tid))
        await s.commit()
    t = _tok(uid, tid, sid)
    with _jm():
        r = await _http("POST", "/auth/change-password", token=t,
                         json={"current_password": "oldpass", "new_password": "NewPass123!"})
        assert r.status_code == 200
        assert (await _http("GET", "/auth/me", token=t)).status_code == 401

@pytest.mark.asyncio
async def test_session_user_mismatch():
    tid, uid_a, uid_b, sid = _unique("t-sm", "ua-sm", "ub-sm", "s-sm")
    async with get_sessionmaker()() as s:
        s.add(_make_tenant(tid))
        await s.flush()
        s.add(_make_user(uid_a, tid))
        s.add(_make_user(uid_b, tid))
        await s.flush()
        s.add(_make_session(sid, uid_a, tid))
        await s.commit()
    t = _tok(uid_b, tid, sid)
    with _jm():
        assert (await _http("GET", "/auth/me", token=t)).status_code == 401

@pytest.mark.asyncio
async def test_session_tenant_mismatch():
    tid_a, tid_b, uid, sid = _unique("ta-stm", "tb-stm", "u-stm", "s-stm")
    async with get_sessionmaker()() as s:
        s.add(_make_tenant(tid_a))
        s.add(_make_tenant(tid_b))
        await s.flush()
        s.add(_make_user(uid, tid_a))
        await s.flush()
        s.add(_make_session(sid, uid, tid_a))
        await s.commit()
    t = _tok(uid, tid_b, sid)
    with _jm():
        assert (await _http("GET", "/auth/me", token=t)).status_code == 401

@pytest.mark.asyncio
async def test_inactive_user_rejected():
    tid, uid, sid = _unique("t-iu", "u-iu", "s-iu")
    await _seed(tid, uid, sid)
    t = _tok(uid, tid, sid)
    async with get_sessionmaker()() as s:
        u = await s.get(User, uid)
        u.status = "disabled"
        await s.commit()
    with _jm():
        assert (await _http("GET", "/auth/me", token=t)).status_code == 401

@pytest.mark.asyncio
async def test_stale_role_rejected():
    tid, uid, sid = _unique("t-sr", "u-sr", "s-sr")
    await _seed(tid, uid, sid)
    t = _tok(uid, tid, sid)
    async with get_sessionmaker()() as s:
        u = await s.get(User, uid)
        u.role = "tenant_admin"
        await s.commit()
    with _jm():
        assert (await _http("GET", "/auth/me", token=t)).status_code == 401

@pytest.mark.asyncio
async def test_missing_session_id_rejected():
    tid, uid, sid = _unique("t-ms", "u-ms", "s-ms")
    await _seed(tid, uid, sid)
    t = _tok(uid, tid, "")
    with _jm():
        assert (await _http("GET", "/auth/me", token=t)).status_code == 401

@pytest.mark.asyncio
async def test_invalid_token_version_type_rejected():
    tid, uid, sid = _unique("t-itv", "u-itv", "s-itv")
    await _seed(tid, uid, sid)
    now = datetime.now(UTC)
    payload = {"sub": uid, "tenant_id": tid, "role": "lawyer", "session_id": sid,
               "token_version": "not_an_int", "jti": uuid.uuid4().hex[:12],
               "iss": "emsalist", "aud": "emsalist-api", "iat": now, "nbf": now,
               "exp": now + timedelta(minutes=30), "token_type": "access"}
    t = pyjwt.encode(payload, _get_jwt_secret(), algorithm="HS256")
    with _jm():
        assert (await _http("GET", "/auth/me", token=t)).status_code == 401
