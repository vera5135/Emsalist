"""P1.5.6 / P2.2B2A — DB-backed auth operations with Apple Sign-In support."""
from __future__ import annotations
import hashlib, logging, uuid
from datetime import UTC, datetime, timedelta
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.config import get_settings
from app.services.auth_service import (
    create_access_token, create_refresh_token, decode_token,
    hash_password, verify_password, get_auth_mode, SecurityContext,
    resolve_current_user, get_security_context, set_security_context, check_production_safety,
)

logger = logging.getLogger(__name__)
_bearer = HTTPBearer(auto_error=False)

GENERIC_INVALID = "Giriş bilgileri doğrulanamadı."


def _as_aware_utc(value: datetime) -> datetime:
    """Coerce a possibly naive datetime to timezone-aware UTC.

    PostgreSQL returns timezone-aware datetimes for ``DateTime(timezone=True)``
    columns, but SQLite (used in tests) returns naive values.  Normalising here
    keeps expiry comparisons correct on both backends.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


# -- Auth session manager (DB-backed) --
class AuthManager:
    def __init__(self):
        self._settings = get_settings()

    # ------------------------------------------------------------------
    # Shared session issuance helper
    # ------------------------------------------------------------------
    async def _issue_session_for_user(
        self, db, user, tenant_id: str, auth_method: str,
        ip_hash: str = "", user_agent_hash: str = "",
    ) -> dict:
        from app.db.auth_repository import AuthSessionRepository, UserRepository

        await UserRepository.reset_login_failure(db, user)
        token_family = uuid.uuid4().hex[:16]
        refresh_raw = uuid.uuid4().hex + uuid.uuid4().hex
        refresh_hash = hashlib.sha256(refresh_raw.encode()).hexdigest()
        auth_session = await AuthSessionRepository.create_session(
            db, tenant_id, user.id, refresh_hash, token_family,
            user_agent_hash, ip_hash,
        )
        access = create_access_token(
            user.id, tenant_id, user.role or "lawyer", auth_session.id,
            user.token_version or 0,
        )
        refresh = create_refresh_token(user.id, auth_session.id, token_family)
        return {
            "access_token": access,
            "refresh_token": refresh_raw,
            "token_type": "bearer",
            "user": {"id": user.id, "tenant": tenant_id, "role": user.role or "lawyer"},
        }

    # ------------------------------------------------------------------
    # Email-only login (primary path, no tenant_slug needed)
    # ------------------------------------------------------------------
    async def _resolve_user_by_email(self, db, email: str) -> tuple:
        """Returns (user, canonical_tenant_id) or raises generic 401."""
        from app.db.auth_repository import UserRepository

        email_norm = email.strip().casefold()
        users = await UserRepository.find_active_by_email(db, email_norm)

        if not users:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_INVALID)

        if len(users) > 1:
            logger.warning("account_resolution_ambiguous", extra={"match_count": len(users)})
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_INVALID)

        user = users[0]
        return user, user.tenant_id

    # ------------------------------------------------------------------
    # Login (password)
    # ------------------------------------------------------------------
    async def login(self, tenant_slug: str | None, email: str, password: str,
                    ip_hash: str = "", user_agent_hash: str = "") -> dict:
        from app.db.auth_repository import UserRepository, TenantRepository, AuthAuditRepository
        from app.db.session import get_sessionmaker
        sm = get_sessionmaker()
        async with sm() as db:
            email_norm = email.strip().casefold()

            if tenant_slug:
                tenant = await TenantRepository.get_by_slug(db, tenant_slug)
                if not tenant:
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_INVALID)
                canonical_tenant_id = tenant.id
                user = await UserRepository.get_by_email(db, canonical_tenant_id, email_norm)
                if not user:
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_INVALID)
            else:
                user, canonical_tenant_id = await self._resolve_user_by_email(db, email)

            if user.status in ("disabled", "deleted"):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_INVALID)
            if user.status == "locked" and user.locked_until and user.locked_until > datetime.now(UTC):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_INVALID)
            if not user.password_hash:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_INVALID)

            if not verify_password(password, user.password_hash):
                await UserRepository.update_login_failure(db, user)
                await AuthAuditRepository.write_event(
                    db, canonical_tenant_id, user.id, "", "login_failed", "failure",
                    {"auth_method": "password", "ip_hash": ip_hash},
                )
                await db.commit()
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_INVALID)

            result = await self._issue_session_for_user(
                db, user, canonical_tenant_id, "password", ip_hash, user_agent_hash,
            )
            await AuthAuditRepository.write_event(
                db, canonical_tenant_id, user.id, "", "login_success", "success",
                {"auth_method": "password"},
            )
            await db.commit()
            return result

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------
    async def refresh(self, refresh_token: str) -> dict:
        from app.db.auth_repository import UserRepository, AuthSessionRepository, AuthAuditRepository
        from app.db.session import get_sessionmaker
        sm = get_sessionmaker()
        async with sm() as db:
            refresh_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
            auth_session = await AuthSessionRepository.get_by_refresh_hash(db, refresh_hash)
            if not auth_session or _as_aware_utc(auth_session.expires_at) < datetime.now(UTC):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

            if auth_session.revoked_at:
                await AuthSessionRepository.revoke_token_family(db, auth_session.token_family_id)
                await AuthAuditRepository.write_event(db, auth_session.tenant_id, auth_session.user_id, "", "refresh_reuse_detected", "failure")
                await db.commit()
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token reused — all sessions revoked")

            user = await UserRepository.get_by_id(db, auth_session.tenant_id, auth_session.user_id)
            if not user or user.status not in ("active",):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User inactive")

            token_family = auth_session.token_family_id
            await AuthSessionRepository.revoke_session(db, auth_session, "rotated")
            refresh_raw = uuid.uuid4().hex + uuid.uuid4().hex
            new_hash = hashlib.sha256(refresh_raw.encode()).hexdigest()
            new_session = await AuthSessionRepository.create_session(db, auth_session.tenant_id, auth_session.user_id, new_hash, token_family)
            auth_session.replaced_by_session_id = new_session.id
            await AuthAuditRepository.write_event(db, auth_session.tenant_id, user.id, "", "token_refreshed", "success")
            await db.commit()

            access = create_access_token(user.id, auth_session.tenant_id, user.role or "lawyer", new_session.id, user.token_version or 0)
            return {"access_token": access, "refresh_token": refresh_raw, "token_type": "bearer"}

    # ------------------------------------------------------------------
    # Logout / Logout-all
    # ------------------------------------------------------------------
    async def logout(self, ctx: SecurityContext) -> None:
        from app.db.auth_repository import AuthSessionRepository, AuthAuditRepository
        from app.db.session import get_sessionmaker
        sm = get_sessionmaker()
        async with sm() as db:
            if ctx.session_id:
                sess = await AuthSessionRepository.get_active_session(db, ctx.session_id)
                if sess:
                    await AuthSessionRepository.revoke_session(db, sess, "logout")
                    await AuthAuditRepository.write_event(db, ctx.tenant_id, ctx.actor_id, "", "logout", "success")
                    await db.commit()

    async def logout_all(self, ctx: SecurityContext) -> None:
        from app.db.auth_repository import AuthSessionRepository, AuthAuditRepository
        from app.db.session import get_sessionmaker
        sm = get_sessionmaker()
        async with sm() as db:
            await AuthSessionRepository.revoke_user_sessions(db, ctx.actor_id)
            await AuthAuditRepository.write_event(db, ctx.tenant_id, ctx.actor_id, "", "logout_all", "success")
            await db.commit()

    # ------------------------------------------------------------------
    # Change password
    # ------------------------------------------------------------------
    async def change_password(self, ctx: SecurityContext, current_password: str, new_password: str) -> None:
        from app.db.auth_repository import UserRepository, AuthSessionRepository, AuthAuditRepository
        from app.db.session import get_sessionmaker
        sm = get_sessionmaker()
        async with sm() as db:
            user = await UserRepository.get_by_id(db, ctx.tenant_id, ctx.actor_id)
            if not user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
            if not user.password_hash:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password not set")
            if not verify_password(current_password, user.password_hash):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
            hashed = hash_password(new_password)
            await UserRepository.update_password(db, user, hashed)
            await AuthSessionRepository.revoke_user_sessions(db, ctx.actor_id)
            await AuthAuditRepository.write_event(db, ctx.tenant_id, ctx.actor_id, "", "password_changed", "success")
            await db.commit()

    # ------------------------------------------------------------------
    # Apple login
    # ------------------------------------------------------------------
    async def apple_login(self, authorization_code: str, raw_nonce: str,
                          ip_hash: str = "", user_agent_hash: str = "") -> dict:
        from app.db.auth_repository import (
            UserRepository, AuthIdentityRepository, AuthLinkTicketRepository,
            AuthAuditRepository,
        )
        from app.services.apple_auth_service import (
            exchange_authorization_code, verify_apple_id_token,
            hash_apple_subject, generate_link_ticket, AppleAuthError,
        )
        from app.db.session import get_sessionmaker

        settings = get_settings()
        if not settings.apple_sign_in_enabled:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail="Apple Sign-In is currently unavailable")

        try:
            token_response = await exchange_authorization_code(authorization_code)
        except AppleAuthError as e:
            raise HTTPException(status_code=e.http_status, detail=e.message)

        try:
            id_claims = verify_apple_id_token(token_response["id_token"], raw_nonce)
        except AppleAuthError as e:
            raise HTTPException(status_code=e.http_status, detail=e.message)

        apple_sub = id_claims["sub"]
        audience = settings.apple_client_id
        subject_hash = hash_apple_subject(audience, apple_sub)

        sm = get_sessionmaker()
        async with sm() as db:
            identity = await AuthIdentityRepository.find_by_provider(db, "apple", audience, subject_hash)

            if identity:
                user = await UserRepository.get_by_id(db, identity.tenant_id, identity.user_id)
                if not user or user.status != "active":
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_INVALID)

                await AuthIdentityRepository.touch_last_used(db, identity)
                result = await self._issue_session_for_user(
                    db, user, identity.tenant_id, "apple", ip_hash, user_agent_hash,
                )
                await AuthAuditRepository.write_event(
                    db, identity.tenant_id, user.id, "", "apple_login_success", "success",
                    {"provider": "apple", "auth_method": "apple"},
                )
                await db.commit()
                return {"state": "authenticated", **result}

            raw_ticket, ticket_hash = generate_link_ticket()
            await AuthLinkTicketRepository.create(
                db, ticket_hash, "apple", subject_hash, audience, settings.apple_link_ticket_seconds,
            )
            await AuthAuditRepository.write_event(
                db, "", "", "", "apple_link_required", "pending",
                {"provider": "apple"},
            )
            await db.commit()

            return {
                "state": "link_required",
                "link_ticket": raw_ticket,
                "link_expires_in": settings.apple_link_ticket_seconds,
            }

    # ------------------------------------------------------------------
    # Apple link
    # ------------------------------------------------------------------
    async def apple_link(self, link_ticket: str, email: str, password: str,
                         ip_hash: str = "", user_agent_hash: str = "") -> dict:
        from app.db.auth_repository import (
            UserRepository, AuthIdentityRepository, AuthLinkTicketRepository,
            AuthAuditRepository,
        )
        from app.db.session import get_sessionmaker

        settings = get_settings()
        if not settings.apple_sign_in_enabled:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail="Apple Sign-In is currently unavailable")

        ticket_hash = hashlib.sha256(link_ticket.encode()).hexdigest()
        sm = get_sessionmaker()
        async with sm() as db:
            ticket = await AuthLinkTicketRepository.get_by_hash(db, ticket_hash)
            if not ticket:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="Invalid link ticket")
            if _as_aware_utc(ticket.expires_at) < datetime.now(UTC):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="Link ticket expired")
            if ticket.consumed_at:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="Link ticket already used")

            email_norm = email.strip().casefold()
            users = await UserRepository.find_active_by_email(db, email_norm)

            if not users:
                await AuthAuditRepository.write_event(
                    db, "", "", "", "apple_link_failed", "failure",
                    {"provider": "apple", "failure_category": "no_user"},
                )
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_INVALID)

            if len(users) > 1:
                logger.warning("account_resolution_ambiguous", extra={"match_count": len(users)})
                await AuthAuditRepository.write_event(
                    db, "", "", "", "apple_link_failed", "failure",
                    {"provider": "apple", "failure_category": "ambiguous", "match_count": len(users)},
                )
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_INVALID)

            user = users[0]
            canonical_tenant_id = user.tenant_id

            if not user.password_hash or not verify_password(password, user.password_hash):
                await UserRepository.update_login_failure(db, user)
                await AuthAuditRepository.write_event(
                    db, canonical_tenant_id, user.id, "", "apple_link_failed", "failure",
                    {"provider": "apple", "failure_category": "wrong_password"},
                )
                await db.commit()
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_INVALID)

            if user.status != "active":
                await AuthAuditRepository.write_event(
                    db, canonical_tenant_id, user.id, "", "apple_link_failed", "failure",
                    {"provider": "apple", "failure_category": "inactive"},
                )
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_INVALID)

            existing_identity = await AuthIdentityRepository.find_by_user(db, "apple", user.id)
            if existing_identity:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                    detail="Apple account already linked")

            existing_provider = await AuthIdentityRepository.find_by_provider(
                db, ticket.provider, ticket.provider_audience, ticket.provider_subject_hash,
            )
            if existing_provider:
                await AuthAuditRepository.write_event(
                    db, "", "", "", "apple_identity_conflict", "failure",
                    {"provider": "apple"},
                )
                raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                    detail="Apple identity already linked to another account")

            await AuthIdentityRepository.create(
                db, ticket.provider, ticket.provider_subject_hash,
                ticket.provider_audience, canonical_tenant_id, user.id,
            )
            consumed = await AuthLinkTicketRepository.consume(db, ticket)
            if not consumed:
                await db.rollback()
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="Link ticket already used")

            result = await self._issue_session_for_user(
                db, user, canonical_tenant_id, "apple", ip_hash, user_agent_hash,
            )
            await AuthAuditRepository.write_event(
                db, canonical_tenant_id, user.id, "", "apple_account_linked", "success",
                {"provider": "apple"},
            )
            await db.commit()
            return result

    # ------------------------------------------------------------------
    # Apple status
    # ------------------------------------------------------------------
    async def apple_status(self, ctx: SecurityContext) -> dict:
        from app.db.auth_repository import AuthIdentityRepository
        from app.db.session import get_sessionmaker
        sm = get_sessionmaker()
        async with sm() as db:
            identity = await AuthIdentityRepository.find_by_user(db, "apple", ctx.actor_id)
            return {"linked": identity is not None, "provider": "apple"}

    # ------------------------------------------------------------------
    # Apple unlink
    # ------------------------------------------------------------------
    async def apple_unlink(self, ctx: SecurityContext, current_password: str) -> dict:
        from app.db.auth_repository import (
            UserRepository, AuthIdentityRepository, AuthSessionRepository, AuthAuditRepository,
        )
        from app.db.session import get_sessionmaker
        sm = get_sessionmaker()
        async with sm() as db:
            user = await UserRepository.get_by_id(db, ctx.tenant_id, ctx.actor_id)
            if not user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
            if not user.password_hash or not verify_password(current_password, user.password_hash):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

            identity = await AuthIdentityRepository.find_by_user(db, "apple", ctx.actor_id)
            if not identity:
                return {"message": "Apple account is not linked."}

            await AuthIdentityRepository.delete(db, identity)
            user.token_version = (user.token_version or 0) + 1
            await AuthSessionRepository.revoke_user_sessions(db, ctx.actor_id)
            await AuthAuditRepository.write_event(
                db, ctx.tenant_id, ctx.actor_id, "", "apple_account_unlinked", "success",
            )
            await db.commit()
            return {"message": "Apple account link removed."}


auth_manager = AuthManager()


# -- Authorization dependencies --
async def require_case_read(ctx: SecurityContext = Depends(resolve_current_user), case_id: str = "") -> SecurityContext:
    if get_auth_mode() == "local": return ctx
    from app.db.auth_repository import CaseMemberRepository
    from app.db.session import get_sessionmaker
    sm = get_sessionmaker()
    async with sm() as db:
        m = await CaseMemberRepository.get_active_membership(db, ctx.tenant_id, case_id, ctx.actor_id)
        if not m and ctx.role != "tenant_admin":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return ctx


async def require_case_write(ctx: SecurityContext = Depends(resolve_current_user), case_id: str = "") -> SecurityContext:
    if get_auth_mode() == "local": return ctx
    from app.db.auth_repository import CaseMemberRepository
    from app.db.session import get_sessionmaker
    sm = get_sessionmaker()
    async with sm() as db:
        m = await CaseMemberRepository.get_active_membership(db, ctx.tenant_id, case_id, ctx.actor_id)
        if not m or m.membership_role == "viewer":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
        if ctx.role == "tenant_admin": return ctx
    return ctx


async def require_authenticated(ctx: SecurityContext = Depends(resolve_current_user)) -> SecurityContext:
    return ctx