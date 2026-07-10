"""P1.10.5 — Centralized sensitive data redaction."""
from __future__ import annotations

import re
from typing import Any

_SENSITIVE_KEY_PATTERNS = frozenset({
    "authorization", "cookie", "set-cookie", "token", "access_token",
    "refresh_token", "api_key", "apikey", "secret", "password", "passwd",
    "credential", "credentials", "private_key", "database_url", "db_url",
    "dsn", "connection_string", "gemini_api_key", "openai_api_key",
    "jwt_secret", "backup_encryption_key", "x-api-key",
    "authorization_code", "id_token", "client_secret", "raw_nonce",
    "nonce", "link_ticket", "ticket_hash", "provider_subject_hash",
    "apple_subject_pepper", "apple_private_key_path",
})


def _is_sensitive_key(key: str) -> bool:
    lower = key.lower().replace("-", "_").replace(" ", "_")
    return lower in _SENSITIVE_KEY_PATTERNS


_BEARER_RE = re.compile(r"Bearer\s+\S+", re.IGNORECASE)
_BASIC_RE = re.compile(r"Basic\s+\S+", re.IGNORECASE)
_JWT_RE = re.compile(
    r"(?:^|[^\w.\-])eyJ[A-Za-z0-9\-_]+\.eyJ[A-Za-z0-9\-_]+"
    r"\.[A-Za-z0-9\-_]+(?:[^\w.\-]|$)",
)
_URL_USER_PASS_RE = re.compile(
    r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+\-.]*://)"
    r"(?P<user>[^:@/\s]+):(?P<pass>[^@/\s]+)@"
)

_DSN_PASSWORD_RE = re.compile(
    r"(password|pwd)=[^;&\s]+",
    re.IGNORECASE,
)

_QUERY_SECRET_RE = re.compile(
    r"([?&](?:token|api_key|apikey|secret|password|passwd|access_token"
    r"|refresh_token|api\-key|x\-api\-key))=[^&\s#]+",
    re.IGNORECASE,
)

_PEM_LIKE_RE = re.compile(
    r"-----BEGIN\s(?:RSA\s|EC\s|DSA\s|OPENSSH\s|ENCRYPTED\s)?PRIVATE\sKEY-----.*?"
    r"-----END\s(?:RSA\s|EC\s|DSA\s|OPENSSH\s|ENCRYPTED\s)?PRIVATE\sKEY-----",
    re.DOTALL,
)

_REDACTED = "***"
_MAX_STRING_LENGTH = 500

_PLAIN_SECRET_RE = re.compile(
    r"((?:secret|password|api_key|apikey|passwd)\s*[:=]\s*)\S+",
    re.IGNORECASE,
)


def redact_value(value: str) -> str:
    """Apply value-level redaction patterns to a string."""
    if not isinstance(value, str):
        return value
    value = _BEARER_RE.sub("Bearer ***", value)
    value = _BASIC_RE.sub("Basic ***", value)
    value = _JWT_RE.sub(" *** ", value)
    value = _URL_USER_PASS_RE.sub(r"\g<scheme>\g<user>:***@", value)
    value = _DSN_PASSWORD_RE.sub(r"\1=***", value)
    value = _QUERY_SECRET_RE.sub(r"\1=***", value)
    value = _PEM_LIKE_RE.sub("[PRIVATE KEY REDACTED]", value)
    value = _PLAIN_SECRET_RE.sub(r"\1***", value)
    return value


def redact_exception(exc: BaseException) -> str:
    """Return a sanitized string representation of an exception."""
    raw = str(exc)
    if not raw:
        return f"{type(exc).__name__}"
    redacted = redact_value(raw)
    if len(redacted) > _MAX_STRING_LENGTH:
        redacted = redacted[:_MAX_STRING_LENGTH] + "..."
    return redacted


def redact_dict(data: dict[str, Any], depth: int = 10) -> dict[str, Any]:
    """Recursively redact sensitive keys and values in a dict."""
    if depth <= 0:
        return {"_truncated": True}
    result: dict[str, Any] = {}
    for key, value in data.items():
        if _is_sensitive_key(str(key)):
            result[key] = _REDACTED
            continue
        result[key] = _redact_any(value, depth - 1)
    return result


def redact_list(data: list[Any], depth: int = 10) -> list[Any]:
    if depth <= 0:
        return ["_truncated"]
    return [_redact_any(item, depth - 1) for item in data]


def redact_tuple(data: tuple[Any, ...], depth: int = 10) -> tuple[Any, ...]:
    if depth <= 0:
        return ("_truncated",)
    return tuple(_redact_any(item, depth - 1) for item in data)


def redact_set(data: set[Any], depth: int = 10) -> set[Any]:
    if depth <= 0:
        return {"_truncated"}
    return {_redact_any(item, depth - 1) for item in data}


def _redact_any(value: Any, depth: int = 10) -> Any:
    if isinstance(value, dict):
        return redact_dict(value, depth)
    if isinstance(value, list):
        return redact_list(value, depth)
    if isinstance(value, tuple):
        return redact_tuple(value, depth)
    if isinstance(value, set):
        return redact_set(value, depth)
    if isinstance(value, str):
        return redact_value(value)
    return value


def redact(data: Any) -> Any:
    """Top-level redaction entry point. Handles any nested structure."""
    return _redact_any(data)


def redact_url(url: str) -> str:
    """Redact user:password in URL and sensitive query parameters."""
    if not isinstance(url, str):
        return url
    result = _URL_USER_PASS_RE.sub(r"\g<scheme>\g<user>:***@", url)
    result = _QUERY_SECRET_RE.sub(r"\1=***", result)
    return result


def redact_dsn(dsn: str) -> str:
    """Redact password in database connection strings."""
    if not isinstance(dsn, str):
        return dsn
    result = _URL_USER_PASS_RE.sub(r"\g<scheme>\g<user>:***@", dsn)
    result = _DSN_PASSWORD_RE.sub(r"\1=***", result)
    return result


def redact_authorization_header(value: str) -> str:
    """Redact the credential portion of an Authorization header."""
    if not isinstance(value, str):
        return value
    value = _BEARER_RE.sub("Bearer ***", value)
    value = _BASIC_RE.sub("Basic ***", value)
    return value


def redact_cookie_header(value: str) -> str:
    """Redact sensitive cookie values while preserving structure."""
    if not isinstance(value, str):
        return value
    parts = value.split(";")
    redacted_parts = []
    for part in parts:
        part = part.strip()
        if "=" in part:
            key, val = part.split("=", 1)
            if _is_sensitive_key(key.strip()):
                redacted_parts.append(f"{key.strip()}=***")
            else:
                redacted_parts.append(part)
        else:
            redacted_parts.append(part)
    return "; ".join(redacted_parts)


def sanitize_for_log(data: dict[str, Any]) -> dict[str, Any]:
    """Apply redaction and remove known large/noisy fields for logging."""
    result = redact_dict(data)
    for key in list(result.keys()):
        if _is_sensitive_key(str(key)):
            result[key] = _REDACTED
    return result
