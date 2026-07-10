"""P2.2B2A — Apple auth DB-backed integration tests.

Exercises AuthManager against a self-contained migrated SQLite database.
Apple network calls (authorization-code exchange and ID-token verification)
are mocked; no real Apple network access occurs. Each test builds its own
async engine and sessionmaker and patches ``app.db.session.get_sessionmaker``
so the global engine/config are never mutated.
"""
from __future__ import annotations

import tempfile
import types
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models import Base, Tenant, User
from app.services.auth_service import decode_token, hash_password


def _fake_settings(**overrides):
    base = dict(
        apple_sign_in_enabled=True,
        apple_client_id="com.test.emsalist",
        apple_subject_pepper="p" * 32,
        apple_link_ticket_seconds=300,
        auth_mode="jwt",
        jwt_secret_key="",
        jwt_audience="emsalist-api",
    )
    base.update(overrides)
    return types.SimpleNamespace(**base)


class AppleAuthIntegrationBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._tmpdir = tempfile.TemporaryDirectory(prefix="emsalist-apple-it-")
        db_path = Path(self._tmpdir.name) / "apple.db"
        self._engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path.as_posix()}", poolclass=NullPool
        )
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self._maker = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

        self._settings = _fake_settings()
        self._patchers = [
            patch("app.db.session.get_sessionmaker", return_value=self._maker),
            patch("app.services.auth_manager.get_settings", return_value=self._settings),
            patch("app.services.apple_auth_service.get_settings", return_value=self._settings),
        ]
        for p in self._patchers:
            p.start()

        from app.services.auth_manager import AuthManager
        self.mgr = AuthManager()

    async def asyncTearDown(self):
        for p in self._patchers:
            p.stop()
        await self._engine.dispose()
        self._tmpdir.cleanup()

    async def _seed_user(self, *, tenant_id="t1", slug="acme", user_id=None,
                         email="lawyer@example.com", password="Secret123!",
                         status="active", role="lawyer") -> str:
        uid = user_id or uuid.uuid4().hex[:16]
        async with self._maker() as db:
            existing = await db.get(Tenant, tenant_id)
            if not existing:
                db.add(Tenant(id=tenant_id, name=tenant_id, slug=slug, status="active"))
            db.add(User(
                id=uid, tenant_id=tenant_id,
                email_normalized=email.strip().casefold(),
                display_name="Test", status=status, role=role,
                password_hash=hash_password(password) if password else None,
            ))
            await db.commit()
        return uid

    def _ctx(self, actor_id, tenant_id="t1", role="lawyer"):
        from app.services.auth_service import SecurityContext
        ctx = SecurityContext()
        ctx.authenticated = True
        ctx.actor_id = actor_id
        ctx.tenant_id = tenant_id
        ctx.role = role
        return ctx

    def _mock_apple(self, apple_sub="apple-sub-001"):
        """Return patchers that make Apple exchange/verify succeed for a subject."""
        return [
            patch(
                "app.services.apple_auth_service.exchange_authorization_code",
                new=AsyncMock(return_value={"id_token": "fake.jwt.token"}),
            ),
            patch(
                "app.services.apple_auth_service.verify_apple_id_token",
                return_value={"sub": apple_sub, "iss": "https://appleid.apple.com"},
            ),
        ]


# ---------------------------------------------------------------------------
# F) Email-only / legacy tenant_slug login resolution
# ---------------------------------------------------------------------------
class EmailOnlyLoginTests(AppleAuthIntegrationBase):
    async def test_single_user_login_success(self):
        uid = await self._seed_user()
        result = await self.mgr.login(None, "lawyer@example.com", "Secret123!")
        self.assertIn("access_token", result)
        self.assertEqual(result["user"]["id"], uid)
        self.assertEqual(result["user"]["tenant"], "t1")

    async def test_zero_users_generic_failure(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as e:
            await self.mgr.login(None, "nobody@example.com", "whatever")
        self.assertEqual(e.exception.status_code, 401)
        self.assertEqual(e.exception.detail, "Giriş bilgileri doğrulanamadı.")

    async def test_duplicate_users_generic_failure(self):
        from fastapi import HTTPException
        await self._seed_user(tenant_id="t1", slug="acme", email="dup@example.com")
        await self._seed_user(tenant_id="t2", slug="beta", email="dup@example.com")
        with self.assertRaises(HTTPException) as e:
            await self.mgr.login(None, "dup@example.com", "Secret123!")
        self.assertEqual(e.exception.status_code, 401)
        self.assertEqual(e.exception.detail, "Giriş bilgileri doğrulanamadı.")

    async def test_legacy_tenant_slug_resolves_canonical_id(self):
        uid = await self._seed_user(tenant_id="tenant-canonical-1", slug="acme-slug")
        result = await self.mgr.login("acme-slug", "lawyer@example.com", "Secret123!")
        self.assertEqual(result["user"]["tenant"], "tenant-canonical-1")
        self.assertNotEqual(result["user"]["tenant"], "acme-slug")

    async def test_session_and_jwt_use_canonical_tenant_id(self):
        await self._seed_user(tenant_id="tenant-canonical-2", slug="beta-slug")
        result = await self.mgr.login("beta-slug", "lawyer@example.com", "Secret123!")
        claims = decode_token(result["access_token"], "access")
        self.assertEqual(claims["tenant_id"], "tenant-canonical-2")

    async def test_wrong_password_generic_failure(self):
        from fastapi import HTTPException
        await self._seed_user()
        with self.assertRaises(HTTPException) as e:
            await self.mgr.login(None, "lawyer@example.com", "WRONG")
        self.assertEqual(e.exception.detail, "Giriş bilgileri doğrulanamadı.")


# ---------------------------------------------------------------------------
# E) Apple login / account linking
# ---------------------------------------------------------------------------
class AppleLinkTests(AppleAuthIntegrationBase):
    async def test_unlinked_login_returns_link_required(self):
        await self._seed_user()
        mocks = self._mock_apple()
        for p in mocks:
            p.start()
        try:
            result = await self.mgr.apple_login("authcode", "raw-nonce")
        finally:
            for p in mocks:
                p.stop()
        self.assertEqual(result["state"], "link_required")
        self.assertIn("link_ticket", result)
        self.assertNotIn("access_token", result)
        self.assertNotIn("refresh_token", result)

    async def _get_link_ticket(self, apple_sub="apple-sub-001"):
        mocks = self._mock_apple(apple_sub)
        for p in mocks:
            p.start()
        try:
            result = await self.mgr.apple_login("authcode", "raw-nonce")
        finally:
            for p in mocks:
                p.stop()
        return result["link_ticket"]

    async def test_link_success_returns_login_response(self):
        uid = await self._seed_user()
        ticket = await self._get_link_ticket()
        result = await self.mgr.apple_link(ticket, "lawyer@example.com", "Secret123!")
        self.assertIn("access_token", result)
        self.assertIn("refresh_token", result)
        self.assertEqual(result["user"]["id"], uid)

    async def test_link_wrong_password_generic(self):
        from fastapi import HTTPException
        await self._seed_user()
        ticket = await self._get_link_ticket()
        with self.assertRaises(HTTPException) as e:
            await self.mgr.apple_link(ticket, "lawyer@example.com", "WRONG")
        self.assertEqual(e.exception.detail, "Giriş bilgileri doğrulanamadı.")

    async def test_link_zero_user_generic(self):
        from fastapi import HTTPException
        ticket = await self._get_link_ticket()
        with self.assertRaises(HTTPException) as e:
            await self.mgr.apple_link(ticket, "ghost@example.com", "Secret123!")
        self.assertEqual(e.exception.detail, "Giriş bilgileri doğrulanamadı.")

    async def test_link_duplicate_user_generic(self):
        from fastapi import HTTPException
        await self._seed_user(tenant_id="t1", slug="acme", email="dup@example.com")
        await self._seed_user(tenant_id="t2", slug="beta", email="dup@example.com")
        ticket = await self._get_link_ticket()
        with self.assertRaises(HTTPException) as e:
            await self.mgr.apple_link(ticket, "dup@example.com", "Secret123!")
        self.assertEqual(e.exception.detail, "Giriş bilgileri doğrulanamadı.")

    async def test_inactive_user_cannot_link(self):
        from fastapi import HTTPException
        await self._seed_user(status="disabled")
        ticket = await self._get_link_ticket()
        with self.assertRaises(HTTPException) as e:
            await self.mgr.apple_link(ticket, "lawyer@example.com", "Secret123!")
        self.assertEqual(e.exception.detail, "Giriş bilgileri doğrulanamadı.")

    async def test_linked_login_returns_authenticated(self):
        await self._seed_user()
        ticket = await self._get_link_ticket()
        await self.mgr.apple_link(ticket, "lawyer@example.com", "Secret123!")
        mocks = self._mock_apple()
        for p in mocks:
            p.start()
        try:
            result = await self.mgr.apple_login("authcode", "raw-nonce")
        finally:
            for p in mocks:
                p.stop()
        self.assertEqual(result["state"], "authenticated")
        self.assertIn("access_token", result)
        self.assertNotIn("link_ticket", result)

    async def test_same_apple_identity_cannot_link_second_user(self):
        from fastapi import HTTPException
        await self._seed_user(user_id="userA", email="a@example.com")
        await self._seed_user(tenant_id="t2", slug="beta", user_id="userB", email="b@example.com")
        # Mint two tickets for the same Apple subject while still unlinked.
        ticket_a = await self._get_link_ticket("apple-shared")
        ticket_b = await self._get_link_ticket("apple-shared")
        # First ticket links the Apple subject to user A.
        await self.mgr.apple_link(ticket_a, "a@example.com", "Secret123!")
        # Second ticket (same subject) attempting user B must conflict.
        with self.assertRaises(HTTPException) as e:
            await self.mgr.apple_link(ticket_b, "b@example.com", "Secret123!")
        self.assertEqual(e.exception.status_code, 409)

    async def test_same_user_cannot_link_second_identity(self):
        from fastapi import HTTPException
        await self._seed_user(user_id="userA", email="a@example.com")
        ticket1 = await self._get_link_ticket("apple-sub-1")
        await self.mgr.apple_link(ticket1, "a@example.com", "Secret123!")
        ticket2 = await self._get_link_ticket("apple-sub-2")
        with self.assertRaises(HTTPException) as e:
            await self.mgr.apple_link(ticket2, "a@example.com", "Secret123!")
        self.assertEqual(e.exception.status_code, 409)

    async def test_link_then_refresh_works(self):
        await self._seed_user()
        ticket = await self._get_link_ticket()
        result = await self.mgr.apple_link(ticket, "lawyer@example.com", "Secret123!")
        refreshed = await self.mgr.refresh(result["refresh_token"])
        self.assertIn("access_token", refreshed)
        self.assertNotEqual(refreshed["refresh_token"], result["refresh_token"])

    async def test_refresh_reuse_detected_after_link(self):
        from fastapi import HTTPException
        await self._seed_user()
        ticket = await self._get_link_ticket()
        result = await self.mgr.apple_link(ticket, "lawyer@example.com", "Secret123!")
        await self.mgr.refresh(result["refresh_token"])
        with self.assertRaises(HTTPException):
            await self.mgr.refresh(result["refresh_token"])


# ---------------------------------------------------------------------------
# D) Link ticket lifecycle
# ---------------------------------------------------------------------------
class LinkTicketLifecycleTests(AppleAuthIntegrationBase):
    async def test_expired_ticket_rejected(self):
        from fastapi import HTTPException
        from app.db.auth_repository import AuthLinkTicketRepository
        import hashlib
        await self._seed_user()
        raw = "raw-ticket-value-123456"
        thash = hashlib.sha256(raw.encode()).hexdigest()
        async with self._maker() as db:
            t = await AuthLinkTicketRepository.create(db, thash, "apple", "sub-hash", "aud", 300)
            t.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await db.commit()
        with self.assertRaises(HTTPException) as e:
            await self.mgr.apple_link(raw, "lawyer@example.com", "Secret123!")
        self.assertIn("expired", e.exception.detail.lower())

    async def test_consumed_ticket_cannot_reuse(self):
        from fastapi import HTTPException
        await self._seed_user()
        # generate + consume via a real link, then reuse
        mocks = self._mock_apple()
        for p in mocks:
            p.start()
        try:
            login = await self.mgr.apple_login("authcode", "raw-nonce")
        finally:
            for p in mocks:
                p.stop()
        raw = login["link_ticket"]
        await self.mgr.apple_link(raw, "lawyer@example.com", "Secret123!")
        with self.assertRaises(HTTPException) as e:
            await self.mgr.apple_link(raw, "lawyer@example.com", "Secret123!")
        self.assertEqual(e.exception.status_code, 400)

    async def test_malformed_ticket_rejected(self):
        from fastapi import HTTPException
        await self._seed_user()
        with self.assertRaises(HTTPException) as e:
            await self.mgr.apple_link("no-such-ticket", "lawyer@example.com", "Secret123!")
        self.assertEqual(e.exception.status_code, 400)

    async def test_double_consume_only_one_succeeds(self):
        import hashlib
        from app.db.auth_repository import AuthLinkTicketRepository
        raw = "raw-double-consume-987654"
        thash = hashlib.sha256(raw.encode()).hexdigest()
        async with self._maker() as db:
            await AuthLinkTicketRepository.create(db, thash, "apple", "sub-hash", "aud", 300)
            await db.commit()
        async with self._maker() as db:
            t = await AuthLinkTicketRepository.get_by_hash(db, thash)
            assert t is not None
            first = await AuthLinkTicketRepository.consume(db, t)
            second = await AuthLinkTicketRepository.consume(db, t)
            await db.commit()
        self.assertTrue(first)
        self.assertFalse(second)

    async def test_only_hash_stored_not_raw(self):
        import hashlib
        from app.db.auth_repository import AuthLinkTicketRepository
        await self._seed_user()
        mocks = self._mock_apple()
        for p in mocks:
            p.start()
        try:
            login = await self.mgr.apple_login("authcode", "raw-nonce")
        finally:
            for p in mocks:
                p.stop()
        raw = login["link_ticket"]
        thash = hashlib.sha256(raw.encode()).hexdigest()
        async with self._maker() as db:
            t = await AuthLinkTicketRepository.get_by_hash(db, thash)
            self.assertIsNotNone(t)
            assert t is not None
            self.assertNotEqual(t.ticket_hash, raw)
            self.assertEqual(t.ticket_hash, thash)


# ---------------------------------------------------------------------------
# G) Status / unlink
# ---------------------------------------------------------------------------
class AppleStatusUnlinkTests(AppleAuthIntegrationBase):
    async def _seed_and_link(self, apple_sub="apple-sub-001"):
        uid = await self._seed_user()
        mocks = self._mock_apple(apple_sub)
        for p in mocks:
            p.start()
        try:
            login = await self.mgr.apple_login("authcode", "raw-nonce")
        finally:
            for p in mocks:
                p.stop()
        await self.mgr.apple_link(login["link_ticket"], "lawyer@example.com", "Secret123!")
        return uid

    async def test_status_linked_true(self):
        uid = await self._seed_and_link()
        status = await self.mgr.apple_status(self._ctx(uid))
        self.assertTrue(status["linked"])
        self.assertEqual(status["provider"], "apple")

    async def test_status_unlinked_false(self):
        uid = await self._seed_user()
        status = await self.mgr.apple_status(self._ctx(uid))
        self.assertFalse(status["linked"])

    async def test_unlink_wrong_password_rejected(self):
        from fastapi import HTTPException
        uid = await self._seed_and_link()
        with self.assertRaises(HTTPException) as e:
            await self.mgr.apple_unlink(self._ctx(uid), "WRONG")
        self.assertEqual(e.exception.status_code, 400)

    async def test_unlink_removes_identity_and_bumps_token_version(self):
        uid = await self._seed_and_link()
        async with self._maker() as db:
            u0 = await db.get(User, uid)
            assert u0 is not None
            before = u0.token_version
        result = await self.mgr.apple_unlink(self._ctx(uid), "Secret123!")
        self.assertIn("removed", result["message"].lower())
        async with self._maker() as db:
            user = await db.get(User, uid)
            assert user is not None
            self.assertGreater(user.token_version, before)
        status = await self.mgr.apple_status(self._ctx(uid))
        self.assertFalse(status["linked"])

    async def test_unlink_revokes_sessions(self):
        from fastapi import HTTPException
        uid = await self._seed_user()
        mocks = self._mock_apple()
        for p in mocks:
            p.start()
        try:
            login = await self.mgr.apple_login("authcode", "raw-nonce")
        finally:
            for p in mocks:
                p.stop()
        linked = await self.mgr.apple_link(login["link_ticket"], "lawyer@example.com", "Secret123!")
        await self.mgr.apple_unlink(self._ctx(uid), "Secret123!")
        with self.assertRaises(HTTPException):
            await self.mgr.refresh(linked["refresh_token"])

    async def test_unlink_idempotent_second_time(self):
        uid = await self._seed_and_link()
        await self.mgr.apple_unlink(self._ctx(uid), "Secret123!")
        result = await self.mgr.apple_unlink(self._ctx(uid), "Secret123!")
        self.assertEqual(result["message"], "Apple account is not linked.")

    async def test_password_login_works_after_unlink(self):
        uid = await self._seed_and_link()
        await self.mgr.apple_unlink(self._ctx(uid), "Secret123!")
        result = await self.mgr.login(None, "lawyer@example.com", "Secret123!")
        self.assertEqual(result["user"]["id"], uid)


if __name__ == "__main__":
    unittest.main()
