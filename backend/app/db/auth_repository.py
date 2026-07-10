"""P1.5.5 — Auth repository layer with DB implementations."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuthIdentity, AuthLinkTicket, AuthSession, CaseMember, Tenant, User

logger = logging.getLogger(__name__)


class UserRepository:
    @staticmethod
    async def get_by_email(session: AsyncSession, tenant_id: str, email_normalized: str) -> User | None:
        result = await session.execute(
            select(User).where(User.tenant_id == tenant_id, User.email_normalized == email_normalized, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def find_active_by_email(session: AsyncSession, email_normalized: str) -> list[User]:
        result = await session.execute(
            select(User).where(User.email_normalized == email_normalized, User.deleted_at.is_(None))
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_by_id(session: AsyncSession, tenant_id: str, user_id: str) -> User | None:
        result = await session.execute(
            select(User).where(User.id == user_id, User.tenant_id == tenant_id, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def update_login_failure(session: AsyncSession, user: User) -> None:
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= 5:
            user.locked_until = datetime.now(UTC) + timedelta(minutes=15)
            user.status = "locked"
        await session.flush()

    @staticmethod
    async def reset_login_failure(session: AsyncSession, user: User) -> None:
        user.failed_login_count = 0
        user.locked_until = None
        if user.status == "locked":
            user.status = "active"
        user.last_login_at = datetime.now(UTC)
        await session.flush()

    @staticmethod
    async def update_password(session: AsyncSession, user: User, password_hash: str) -> None:
        user.password_hash = password_hash
        user.token_version = (user.token_version or 0) + 1
        user.password_changed_at = datetime.now(UTC)
        await session.flush()

    @staticmethod
    async def increment_token_version(session: AsyncSession, user: User) -> None:
        user.token_version = (user.token_version or 0) + 1
        await session.flush()

    @staticmethod
    async def update_status(session: AsyncSession, user: User, status: str) -> None:
        user.status = status
        if status in ("disabled", "deleted"):
            user.deleted_at = datetime.now(UTC)
        await session.flush()


class TenantRepository:
    @staticmethod
    async def get_by_slug(session: AsyncSession, slug: str) -> Tenant | None:
        result = await session.execute(
            select(Tenant).where(Tenant.slug == slug, Tenant.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()


class AuthSessionRepository:
    @staticmethod
    async def create_session(session: AsyncSession, tenant_id: str, user_id: str, refresh_token_hash: str, token_family_id: str, user_agent_hash: str = "", ip_hash: str = "") -> AuthSession:
        now = datetime.now(UTC)
        s = AuthSession(
            tenant_id=tenant_id, user_id=user_id,
            refresh_token_hash=refresh_token_hash, token_family_id=token_family_id,
            user_agent_hash=user_agent_hash, ip_hash=ip_hash,
            created_at=now, last_used_at=now, expires_at=now + timedelta(days=7),
        )
        session.add(s)
        await session.flush()
        return s

    @staticmethod
    async def get_by_refresh_hash(session: AsyncSession, refresh_token_hash: str) -> AuthSession | None:
        result = await session.execute(
            select(AuthSession).where(AuthSession.refresh_token_hash == refresh_token_hash)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_active_session(session: AsyncSession, session_id: str) -> AuthSession | None:
        result = await session.execute(
            select(AuthSession).where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None), AuthSession.expires_at > datetime.now(UTC))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def revoke_session(db: AsyncSession, auth_session: AuthSession, reason: str = "") -> None:
        auth_session.revoked_at = datetime.now(UTC)
        auth_session.revoke_reason = reason
        await db.flush()

    @staticmethod
    async def revoke_user_sessions(db: AsyncSession, user_id: str) -> None:
        now = datetime.now(UTC)
        await db.execute(
            update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)).values(revoked_at=now, revoke_reason="logout_all")
        )

    @staticmethod
    async def revoke_token_family(db: AsyncSession, token_family_id: str) -> None:
        now = datetime.now(UTC)
        await db.execute(
            update(AuthSession).where(AuthSession.token_family_id == token_family_id, AuthSession.revoked_at.is_(None)).values(revoked_at=now, revoke_reason="reuse_detected")
        )

    @staticmethod
    async def replace_session(db: AsyncSession, old_session: AuthSession, new_session: AuthSession) -> None:
        old_session.revoked_at = datetime.now(UTC)
        old_session.replaced_by_session_id = new_session.id
        old_session.revoke_reason = "rotated"
        await db.flush()

    @staticmethod
    async def list_active_sessions(db: AsyncSession, user_id: str) -> list[AuthSession]:
        result = await db.execute(
            select(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None), AuthSession.expires_at > datetime.now(UTC))
        )
        return list(result.scalars().all())


class CaseMemberRepository:
    @staticmethod
    async def get_active_membership(db: AsyncSession, tenant_id: str, case_id: str, user_id: str) -> CaseMember | None:
        result = await db.execute(
            select(CaseMember).where(CaseMember.tenant_id == tenant_id, CaseMember.case_id == case_id, CaseMember.user_id == user_id, CaseMember.revoked_at.is_(None))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def add_member(db: AsyncSession, case_id: str, tenant_id: str, user_id: str, role: str = "viewer") -> CaseMember:
        m = CaseMember(case_id=case_id, tenant_id=tenant_id, user_id=user_id, membership_role=role, created_at=datetime.now(UTC))
        db.add(m)
        await db.flush()
        return m

    @staticmethod
    async def revoke_member(db: AsyncSession, member: CaseMember) -> None:
        member.revoked_at = datetime.now(UTC)
        await db.flush()

    @staticmethod
    async def list_members(db: AsyncSession, case_id: str) -> list[CaseMember]:
        result = await db.execute(select(CaseMember).where(CaseMember.case_id == case_id, CaseMember.revoked_at.is_(None)))
        return list(result.scalars().all())


class AuthAuditRepository:
    @staticmethod
    async def write_event(db: AsyncSession, tenant_id: str, actor_id: str, case_id: str, action: str, outcome: str = "success", safe_metadata: dict | None = None) -> None:
        from app.db.models import AuditEvent
        event = AuditEvent(
            tenant_id=tenant_id, actor_id=actor_id, case_id=case_id,
            action=action, outcome=outcome, safe_metadata=safe_metadata or {},
            created_at=datetime.now(UTC),
        )
        db.add(event)
        await db.flush()


class AuthIdentityRepository:
    @staticmethod
    async def find_by_provider(session: AsyncSession, provider: str, audience: str, subject_hash: str) -> AuthIdentity | None:
        result = await session.execute(
            select(AuthIdentity).where(
                AuthIdentity.provider == provider,
                AuthIdentity.provider_audience == audience,
                AuthIdentity.provider_subject_hash == subject_hash,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def find_by_user(session: AsyncSession, provider: str, user_id: str) -> AuthIdentity | None:
        result = await session.execute(
            select(AuthIdentity).where(
                AuthIdentity.provider == provider,
                AuthIdentity.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(session: AsyncSession, provider: str, subject_hash: str, audience: str, tenant_id: str, user_id: str) -> AuthIdentity:
        identity = AuthIdentity(
            provider=provider,
            provider_subject_hash=subject_hash,
            provider_audience=audience,
            tenant_id=tenant_id,
            user_id=user_id,
            created_at=datetime.now(UTC),
            last_used_at=datetime.now(UTC),
        )
        session.add(identity)
        await session.flush()
        return identity

    @staticmethod
    async def delete(session: AsyncSession, identity: AuthIdentity) -> None:
        await session.delete(identity)
        await session.flush()

    @staticmethod
    async def touch_last_used(session: AsyncSession, identity: AuthIdentity) -> None:
        identity.last_used_at = datetime.now(UTC)
        await session.flush()


class AuthLinkTicketRepository:
    @staticmethod
    async def create(session: AsyncSession, ticket_hash: str, provider: str, subject_hash: str, audience: str, ttl_seconds: int) -> AuthLinkTicket:
        now = datetime.now(UTC)
        ticket = AuthLinkTicket(
            ticket_hash=ticket_hash,
            provider=provider,
            provider_subject_hash=subject_hash,
            provider_audience=audience,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        session.add(ticket)
        await session.flush()
        return ticket

    @staticmethod
    async def get_by_hash(session: AsyncSession, ticket_hash: str) -> AuthLinkTicket | None:
        result = await session.execute(
            select(AuthLinkTicket).where(AuthLinkTicket.ticket_hash == ticket_hash)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def consume(session: AsyncSession, ticket: AuthLinkTicket) -> bool:
        """Atomically mark a ticket consumed.

        Uses a conditional UPDATE guarded on ``consumed_at IS NULL`` so that
        two concurrent link requests race on the database row and only one
        observes ``rowcount == 1``.  Returns True if this caller consumed the
        ticket, False if it had already been consumed.
        """
        now = datetime.now(UTC)
        result = await session.execute(
            update(AuthLinkTicket)
            .where(AuthLinkTicket.id == ticket.id, AuthLinkTicket.consumed_at.is_(None))
            .values(consumed_at=now)
        )
        await session.flush()
        consumed = getattr(result, "rowcount", 0) == 1
        if consumed:
            ticket.consumed_at = now
        return consumed
