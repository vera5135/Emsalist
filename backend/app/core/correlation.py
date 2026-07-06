
from __future__ import annotations

import re
import uuid
from contextvars import ContextVar

MAX_CORRELATION_ID_LENGTH = 256
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")
_request_id: ContextVar[str] = ContextVar("request_id", default="")


def generate_correlation_id() -> str:
    return uuid.uuid4().hex


def get_correlation_id() -> str:
    return _correlation_id.get()


def set_correlation_id(cid: str) -> None:
    _correlation_id.set(sanitize_correlation_id(cid))


def clear_correlation_id() -> None:
    _correlation_id.set("")


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(rid: str) -> None:
    _request_id.set(rid)


def clear_request_id() -> None:
    _request_id.set("")


def sanitize_correlation_id(raw: str) -> str:
    if not raw or not isinstance(raw, str):
        return generate_correlation_id()
    raw = raw.strip()
    if not raw or len(raw) > MAX_CORRELATION_ID_LENGTH:
        return generate_correlation_id()
    if _CONTROL_CHARS_RE.search(raw):
        return generate_correlation_id()
    if "\n" in raw or "\r" in raw:
        return generate_correlation_id()
    return raw


def extract_or_create_correlation_id(header_value: str | None) -> str:
    cid = sanitize_correlation_id(header_value) if header_value else generate_correlation_id()
    _correlation_id.set(cid)
    _request_id.set(uuid.uuid4().hex)
    return cid
