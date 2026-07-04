"""P1.5 — JWT authentication, authorization, and security context."""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings

logger = logging.getLogger(__name__)
_ph = PasswordHasher()
_bearer = HTTPBearer(auto_error=False)

# -- Config --
ACCESS_TOKEN_MINUTES = 30
REFRESH_TOKEN_DAYS = 7


def _get_jwt_secret() -> str:
    s = get_settings()
    key = s.jwt_secret_key or "emsalist-local-dev-key-change-in-production"
    if len(key) < 16:
        logger.warning("jwt_secret_too_short")
    return key


# -- Security Context --
class SecurityContext:
    def __init__(self):
        self.authenticated = False
        self.actor_id = "local-user"
        self.tenant_id = "local"
        self.role = "lawyer"
        self.permissions: list[str] = []
        self.session_id = ""
        self.request_id = ""


_security_context: SecurityContext | None = None


def get_security_context() -> SecurityContext:
    global _security_context
    if _security_context is None:
        _security_context = SecurityContext()
    return _security_context


def set_security_context(ctx: SecurityContext) -> None:
    global _security_context
    _security_context = ctx


# -- JWT --
def create_access_token(user_id: str, tenant_id: str, role: str, session_id: str = "", token_version: int = 0) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": user_id, "tenant_id": tenant_id, "role": role,
            "session_id": session_id, "token_version": token_version,
            "jti": uuid.uuid4().hex[:12], "iss": "emsalist",
            "iat": now, "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES),
            "token_type": "access",
        },
        _get_jwt_secret(), algorithm="HS256",
    )


def create_refresh_token(user_id: str, session_id: str, token_family_id: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": user_id, "session_id": session_id, "token_family_id": token_family_id,
            "jti": uuid.uuid4().hex[:12], "iss": "emsalist",
            "iat": now, "exp": now + timedelta(days=REFRESH_TOKEN_DAYS),
            "token_type": "refresh",
        },
        _get_jwt_secret(), algorithm="HS256",
    )


def decode_token(token: str, token_type: str = "access") -> dict:
    try:
        payload = jwt.decode(
            token, _get_jwt_secret(), algorithms=["HS256"],
            issuer="emsalist", options={"require": ["exp", "iss", "sub", "token_type"]},
        )
        if payload.get("token_type") != token_type:
            raise jwt.InvalidTokenError("wrong token_type")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# -- Password --
def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def needs_rehash(password_hash: str) -> bool:
    return _ph.check_needs_rehash(password_hash)


# -- Auth dependency --
def get_auth_mode() -> str:
    return get_settings().auth_mode or "local"


async def resolve_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> SecurityContext:
    ctx = SecurityContext()
    ctx.request_id = request.headers.get("X-Request-Id", uuid.uuid4().hex[:8])

    if get_auth_mode() == "local":
        ctx.authenticated = True
        return ctx

    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")

    payload = decode_token(credentials.credentials, "access")
    ctx.authenticated = True
    ctx.actor_id = payload["sub"]
    ctx.tenant_id = payload["tenant_id"]
    ctx.role = payload["role"]
    ctx.session_id = payload.get("session_id", "")
    set_security_context(ctx)
    return ctx


def require_permission(permission: str):
    async def checker(ctx: SecurityContext = Depends(resolve_current_user)) -> SecurityContext:
        if get_auth_mode() == "local":
            return ctx
        if permission in ctx.permissions or ctx.role == "tenant_admin":
            return ctx
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    return checker


def require_authenticated(ctx: SecurityContext = Depends(resolve_current_user)) -> SecurityContext:
    return ctx
