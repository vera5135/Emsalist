"""P1.5.3 — JWT aud/nbf enforcement, rate limit, production checks."""
from __future__ import annotations
import hashlib, logging, time, uuid
from datetime import UTC, datetime, timedelta
from typing import Any
import jwt as pyjwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.config import get_settings

logger = logging.getLogger(__name__)
_ph = PasswordHasher()
_bearer = HTTPBearer(auto_error=False)
ACCESS_TOKEN_MINUTES = 30; REFRESH_TOKEN_DAYS = 7; CLOCK_SKEW = 30

def _get_jwt_secret() -> str:
    s = get_settings()
    return s.jwt_secret_key or "emsalist-local-dev-key-change-in-production"

def _get_audience() -> str:
    return get_settings().jwt_audience or "emsalist-api"

# -- Security Context --
class SecurityContext:
    def __init__(self):
        self.authenticated = False; self.actor_id = "local-user"
        self.tenant_id = "local"; self.role = "lawyer"
        self.permissions: list[str] = []; self.session_id = ""; self.request_id = ""
_security_context: SecurityContext | None = None
def get_security_context() -> SecurityContext:
    global _security_context
    if _security_context is None: _security_context = SecurityContext()
    return _security_context
def set_security_context(ctx): global _security_context; _security_context = ctx

# -- JWT --
def create_access_token(user_id: str, tenant_id: str, role: str, session_id: str = "", token_version: int = 0, token_type_value: str = "access") -> str:
    now = datetime.now(UTC)
    return pyjwt.encode({
        "sub": user_id, "tenant_id": tenant_id, "role": role, "session_id": session_id,
        "token_version": token_version, "jti": uuid.uuid4().hex[:12], "iss": "emsalist",
        "aud": _get_audience(), "iat": now, "nbf": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES), "token_type": token_type_value,
    }, _get_jwt_secret(), algorithm="HS256")

def create_refresh_token(user_id: str, session_id: str, token_family_id: str) -> str:
    now = datetime.now(UTC)
    return pyjwt.encode({
        "sub": user_id, "session_id": session_id, "token_family_id": token_family_id,
        "jti": uuid.uuid4().hex[:12], "iss": "emsalist", "aud": _get_audience(),
        "iat": now, "nbf": now, "exp": now + timedelta(days=REFRESH_TOKEN_DAYS), "token_type": "refresh",
    }, _get_jwt_secret(), algorithm="HS256")

def decode_token(token: str, token_type: str = "access") -> dict:
    try:
        payload = pyjwt.decode(
            token, _get_jwt_secret(), algorithms=["HS256"],
            issuer="emsalist", audience=_get_audience(),
            options={"require": ["exp", "iss", "sub", "token_type", "aud", "nbf"], "verify_signature": True},
            leeway=CLOCK_SKEW,
        )
        if payload.get("token_type") != token_type:
            raise pyjwt.InvalidTokenError("wrong token_type")
        return payload
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except pyjwt.ImmatureSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token not yet valid")
    except pyjwt.InvalidAudienceError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid audience")
    except pyjwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

# -- Password --
def hash_password(pw: str) -> str: return _ph.hash(pw)
def verify_password(pw: str, h: str) -> bool:
    try: return _ph.verify(h, pw)
    except VerifyMismatchError: return False
def needs_rehash(h: str) -> bool: return _ph.check_needs_rehash(h)

# -- Rate Limiter --
_LOGIN_ATTEMPTS: dict[str, list[float]] = {}
LOGIN_MAX_FAILURES = 5; LOGIN_LOCK_MINUTES = 15; LOGIN_WINDOW = 300.0
def check_login_rate(key: str) -> tuple[bool, int]:
    now = time.time()
    _LOGIN_ATTEMPTS.setdefault(key, [])
    _LOGIN_ATTEMPTS[key] = [t for t in _LOGIN_ATTEMPTS[key] if t > now - LOGIN_WINDOW]
    if len(_LOGIN_ATTEMPTS[key]) >= LOGIN_MAX_FAILURES:
        return True, int(_LOGIN_ATTEMPTS[key][0] + LOGIN_WINDOW - now) + 1
    _LOGIN_ATTEMPTS[key].append(now)
    return False, 0
def reset_login_rate(key: str) -> None: _LOGIN_ATTEMPTS.pop(key, None)

# -- Auth dependency --
def get_auth_mode() -> str: return get_settings().auth_mode or "local"
async def resolve_current_user(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> SecurityContext:
    ctx = SecurityContext(); ctx.request_id = request.headers.get("X-Request-Id", uuid.uuid4().hex[:8])
    if get_auth_mode() == "local": ctx.authenticated = True; return ctx
    if not credentials: raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    payload = decode_token(credentials.credentials, "access")
    ctx.authenticated = True; ctx.actor_id = payload["sub"]; ctx.tenant_id = payload["tenant_id"]
    ctx.role = payload["role"]; ctx.session_id = payload.get("session_id", "")
    set_security_context(ctx); return ctx
def require_authenticated(ctx: SecurityContext = Depends(resolve_current_user)) -> SecurityContext: return ctx

# -- Production checks --
def check_production_safety() -> list[str]:
    s = get_settings(); issues = []
    if s.auth_mode == "local":
        issues.append("AUTH_MODE=local productionda kullanilamaz")
    if s.jwt_secret_key in ("", "emsalist-local-dev-key-change-in-production"):
        issues.append("Varsayilan JWT secret productionda kullanilamaz")
    return issues
