"""P2.2B2A — Apple authentication service.

Handles Apple Sign-In client secret generation, authorization code exchange,
ID token verification, nonce validation, and subject privacy via HMAC.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from app.config import get_settings

logger = logging.getLogger(__name__)


class AppleAuthError(Exception):
    """Safe Apple auth error with machine-readable code and user-safe message."""
    def __init__(self, code: str, message: str, http_status: int = 503):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


# ---------------------------------------------------------------------------
# Subject privacy
# ---------------------------------------------------------------------------

def hash_apple_subject(audience: str, subject: str) -> str:
    """Deterministic HMAC-SHA256 hash of an Apple subject.

    The raw Apple subject is never stored or logged.  Only this hex digest
    is persisted in auth_identities.provider_subject_hash.
    """
    settings = get_settings()
    pepper = settings.apple_subject_pepper
    if not pepper:
        raise AppleAuthError("apple_sign_in_unavailable", "Apple Sign-In is not configured")
    message = f"apple|{audience}|{subject}"
    return hmac.new(pepper.encode(), message.encode(), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Client secret (ES256 JWT)
# ---------------------------------------------------------------------------

_client_secret_cache: tuple[str, str, float] | None = None
_client_secret_lock = threading.Lock()


def _load_private_key() -> bytes:
    settings = get_settings()
    path = settings.apple_private_key_path
    if not path:
        raise AppleAuthError("apple_sign_in_unavailable", "Apple private key path not configured")
    try:
        return open(path, "rb").read()
    except Exception:
        raise AppleAuthError("apple_sign_in_unavailable", "Cannot read Apple private key")


def generate_client_secret() -> str:
    """Generate an ES256-signed client secret JWT for Apple token endpoint.

    The secret is cached in memory for a short lifetime to avoid
    re-reading the key file and re-signing on every request.
    """
    global _client_secret_cache
    settings = get_settings()
    now = int(time.time())

    with _client_secret_lock:
        if _client_secret_cache:
            cached_secret, _, cached_at = _client_secret_cache
            if now - cached_at < 120:
                return cached_secret

        private_key_bytes = _load_private_key()
        private_key = serialization.load_pem_private_key(
            private_key_bytes, password=None, backend=default_backend()
        )

        exp = now + 300  # 5 minutes max, per Apple recommendation
        payload = {
            "iss": settings.apple_team_id,
            "sub": settings.apple_client_id,
            "aud": "https://appleid.apple.com",
            "iat": now,
            "exp": exp,
        }
        headers = {
            "kid": settings.apple_key_id,
            "alg": "ES256",
        }
        token = pyjwt.encode(payload, private_key, algorithm="ES256", headers=headers)
        _client_secret_cache = (token, "", now)
        return token


# ---------------------------------------------------------------------------
# Authorization code exchange
# ---------------------------------------------------------------------------

def _apple_http_client() -> httpx.Client:
    settings = get_settings()
    return httpx.Client(timeout=settings.apple_http_timeout_seconds)


async def exchange_authorization_code(code: str, client_secret: str | None = None) -> dict:
    """Exchange an Apple authorization code for tokens.

    Returns the decoded response dict including id_token.
    Does NOT log the authorization code, client secret, or any tokens.
    Raises AppleAuthError on any failure.
    """
    settings = get_settings()
    if not settings.apple_sign_in_enabled:
        raise AppleAuthError("apple_sign_in_unavailable", "Apple Sign-In is currently unavailable")

    secret = client_secret or generate_client_secret()

    data = {
        "client_id": settings.apple_client_id,
        "client_secret": secret,
        "code": code,
        "grant_type": "authorization_code",
    }

    try:
        async with httpx.AsyncClient(timeout=settings.apple_http_timeout_seconds) as client:
            response = await client.post(
                settings.apple_token_endpoint,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
    except httpx.TimeoutException:
        raise AppleAuthError("apple_authorization_failed", "Apple token request timed out")
    except httpx.RequestError:
        raise AppleAuthError("apple_authorization_failed", "Cannot reach Apple token endpoint")

    if response.status_code != 200:
        _safe_log_apple_error(response)
        raise AppleAuthError("apple_authorization_failed", "Apple authorization could not be completed")

    try:
        body = response.json()
    except Exception:
        raise AppleAuthError("apple_authorization_failed", "Invalid response from Apple")

    if not body.get("id_token"):
        raise AppleAuthError("apple_authorization_failed", "No identity token in Apple response")

    return body


def _safe_log_apple_error(response: httpx.Response) -> None:
    try:
        body = response.json()
        error_code = body.get("error", "unknown")
        logger.warning("apple_token_error", extra={"status": response.status_code, "error_code": error_code})
    except Exception:
        logger.warning("apple_token_error", extra={"status": response.status_code})


# ---------------------------------------------------------------------------
# JWKS cache
# ---------------------------------------------------------------------------

_jwks_cache: tuple[dict, float] | None = None
_jwks_lock = threading.Lock()


def _get_jwks() -> dict:
    """Fetch Apple JWKS with caching."""
    global _jwks_cache
    settings = get_settings()
    now = time.time()

    with _jwks_lock:
        if _jwks_cache:
            keys, cached_at = _jwks_cache
            if now - cached_at < settings.apple_jwks_cache_seconds:
                return keys

        try:
            with httpx.Client(timeout=settings.apple_http_timeout_seconds) as client:
                response = client.get(settings.apple_jwks_url)
            response.raise_for_status()
            jwks = response.json()
        except Exception:
            if _jwks_cache:
                return _jwks_cache[0]
            raise AppleAuthError("apple_authorization_failed", "Cannot fetch Apple signing keys")

        _jwks_cache = (jwks, now)
        return jwks


def _refresh_jwks_cache() -> dict:
    """Force-refresh the JWKS cache (used when kid not found)."""
    global _jwks_cache
    settings = get_settings()
    with _jwks_lock:
        try:
            with httpx.Client(timeout=settings.apple_http_timeout_seconds) as client:
                response = client.get(settings.apple_jwks_url)
            response.raise_for_status()
            jwks = response.json()
        except Exception:
            if _jwks_cache:
                return _jwks_cache[0]
            raise AppleAuthError("apple_authorization_failed", "Cannot refresh Apple signing keys")
        _jwks_cache = (jwks, time.time())
        return jwks


# ---------------------------------------------------------------------------
# ID token verification
# ---------------------------------------------------------------------------

def verify_apple_id_token(id_token: str, raw_nonce: str) -> dict:
    """Verify an Apple ID token (RS256, claims, nonce).

    Returns the decoded claims dict on success.
    The raw Apple 'sub' claim is NOT logged — it is returned only for
    immediate hashing in the caller.
    """
    settings = get_settings()

    try:
        unverified_header = pyjwt.get_unverified_header(id_token)
    except Exception:
        raise AppleAuthError("apple_authorization_failed", "Malformed Apple ID token")

    if unverified_header.get("alg") != "RS256":
        raise AppleAuthError("apple_authorization_failed", "Unexpected Apple token algorithm")

    kid = unverified_header.get("kid")
    if not kid:
        raise AppleAuthError("apple_authorization_failed", "Missing key ID in Apple token")

    def _try_decode(use_fresh_jwks: bool = False) -> dict:
        jwks = _refresh_jwks_cache() if use_fresh_jwks else _get_jwks()
        matching_key = None
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                matching_key = key
                break

        if not matching_key:
            if not use_fresh_jwks:
                return _try_decode(use_fresh_jwks=True)
            raise AppleAuthError("apple_authorization_failed", "Unknown Apple signing key")

        try:
            public_key = pyjwt.algorithms.RSAAlgorithm.from_jwk(matching_key)
        except Exception:
            raise AppleAuthError("apple_authorization_failed", "Cannot parse Apple public key")

        try:
            payload = pyjwt.decode(
                id_token,
                public_key,
                algorithms=["RS256"],
                issuer=settings.apple_issuer,
                audience=settings.apple_client_id,
                options={"require": ["exp", "iss", "sub", "aud", "iat"]},
                leeway=30,
            )
        except pyjwt.ExpiredSignatureError:
            raise AppleAuthError("apple_authorization_failed", "Apple token expired")
        except pyjwt.InvalidIssuerError:
            raise AppleAuthError("apple_authorization_failed", "Invalid Apple token issuer")
        except pyjwt.InvalidAudienceError:
            raise AppleAuthError("apple_authorization_failed", "Invalid Apple token audience")
        except pyjwt.ImmatureSignatureError:
            raise AppleAuthError("apple_authorization_failed", "Apple token not yet valid")
        except pyjwt.InvalidTokenError:
            raise AppleAuthError("apple_authorization_failed", "Invalid Apple token")

        return payload

    payload = _try_decode()

    if not payload.get("sub"):
        raise AppleAuthError("apple_authorization_failed", "Missing subject in Apple token")

    token_nonce = payload.get("nonce", "")
    if not token_nonce:
        raise AppleAuthError("apple_authorization_failed", "Missing nonce in Apple token")

    expected_nonce = hashlib.sha256(raw_nonce.encode()).hexdigest()
    if not hmac.compare_digest(token_nonce, expected_nonce):
        raise AppleAuthError("apple_authorization_failed", "Nonce verification failed")

    return payload


# ---------------------------------------------------------------------------
# Link ticket
# ---------------------------------------------------------------------------

def generate_link_ticket() -> tuple[str, str]:
    """Generate a cryptographically secure link ticket.

    Returns (raw_ticket, ticket_hash).  Only the hash is persisted.
    The raw ticket is returned once to the caller.
    """
    raw = uuid.uuid4().hex + uuid.uuid4().hex + uuid.uuid4().hex  # 96 hex chars
    ticket_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, ticket_hash
