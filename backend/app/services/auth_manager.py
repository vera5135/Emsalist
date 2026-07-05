"""P1.5.6 — DB-backed auth operations with repository integration."""
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

# -- Auth session manager (DB-backed) --
class AuthManager:
    def __init__(self):
        self._settings = get_settings()

    async def _get_session(self):
        from app.db.session import get_sessionmaker
        sm = get_sessionmaker()
        async with sm() as s:
            yield s

    async def login(self, tenant_slug: str, email: str, password: str, ip_hash: str = "", user_agent_hash: str = "") -> dict:
        from app.db.auth_repository import UserRepository, AuthSessionRepository, AuthAuditRepository
        from app.db.session import get_sessionmaker
        sm = get_sessionmaker()
        async with sm() as db:
            email_norm = email.strip().casefold()
            user = await UserRepository.get_by_email(db, tenant_slug, email_norm)

            if not user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

            if user.status in ("disabled", "deleted"):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account disabled")
            if user.status == "locked" and user.locked_until and user.locked_until > datetime.now(UTC):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account locked")
            if not user.password_hash:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

            if not verify_password(password, user.password_hash):
                await UserRepository.update_login_failure(db, user)
                await AuthAuditRepository.write_event(db, tenant_slug, user.id, "", "login_failed", "failure", {"ip_hash": ip_hash})
                await db.commit()
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

            await UserRepository.reset_login_failure(db, user)
            token_family = uuid.uuid4().hex[:16]
            refresh_raw = uuid.uuid4().hex + uuid.uuid4().hex
            refresh_hash = hashlib.sha256(refresh_raw.encode()).hexdigest()
            auth_session = await AuthSessionRepository.create_session(
                db, tenant_slug, user.id, refresh_hash, token_family, user_agent_hash, ip_hash,
            )
            await AuthAuditRepository.write_event(db, tenant_slug, user.id, "", "login_success", "success")
            await db.commit()

            access = create_access_token(user.id, tenant_slug, user.role or "lawyer", auth_session.id, user.token_version or 0)
            refresh = create_refresh_token(user.id, auth_session.id, token_family)
            return {"access_token": access, "refresh_token": refresh_raw, "token_type": "bearer",
                    "user": {"id": user.id, "tenant": tenant_slug, "role": user.role or "lawyer"}}

    async def refresh(self, refresh_token: str) -> dict:
        from app.db.auth_repository import UserRepository, AuthSessionRepository, AuthAuditRepository
        from app.db.session import get_sessionmaker
        sm = get_sessionmaker()
        async with sm() as db:
            refresh_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
            auth_session = await AuthSessionRepository.get_by_refresh_hash(db, refresh_hash)
            if not auth_session or auth_session.expires_at < datetime.now(UTC):
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
