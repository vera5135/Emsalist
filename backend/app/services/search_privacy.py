"""P2.7 — Search privacy: query hash, safe summary, cursor signing."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
import base64
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SourceParagraph

_DOMAIN_QUERY_HASH = b"emsalist-query-hash|v1"
_DOMAIN_RESULT_ID = b"emsalist-result-id|v1"
_DOMAIN_CURSOR = b"emsalist-cursor|v1"


def compute_query_hash(query_plan, tenant_id: str, secret: str) -> str:
    clauses = sorted(query_plan.positive_clauses())
    payload = tenant_id + ":" + " ".join(clauses)
    return _hmac_hex(_DOMAIN_QUERY_HASH, payload, secret)


async def compute_index_version(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.max(SourceParagraph.created_at))
    )
    max_ts = result.scalar_one_or_none()
    if max_ts is None:
        return 0
    return int(max_ts.timestamp())


def sign_result_id(
    query_id: str,
    source_id: str,
    source_version_id: str,
    paragraph_id: str,
    index_version: int,
    secret: str,
) -> str:
    payload = json.dumps({
        "qid": query_id,
        "sid": source_id,
        "svid": source_version_id,
        "pid": paragraph_id,
        "iv": index_version,
    }, sort_keys=True)
    sig = _hmac_hex(_DOMAIN_RESULT_ID, payload, secret)
    encoded = base64.urlsafe_b64encode((payload + "|" + sig).encode()).rstrip(b"=").decode()
    return encoded


def verify_result_id(result_id: str, query_id: str, secret: str) -> dict | None:
    try:
        padded = result_id + "=" * (-len(result_id) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode()
        parts = decoded.rsplit("|", 1)
        if len(parts) != 2:
            return None
        payload, sig = parts
        expected = _hmac_hex(_DOMAIN_RESULT_ID, payload, secret)
        if not hmac.compare_digest(expected, sig):
            return None
        data = json.loads(payload)
        if data.get("qid") != query_id:
            return None
        return data
    except Exception:
        return None


def sign_cursor(payload: dict, secret: str) -> str:
    raw = json.dumps(payload, sort_keys=True)
    sig = _hmac_hex(_DOMAIN_CURSOR, raw, secret)
    encoded = base64.urlsafe_b64encode((raw + "|" + sig).encode()).rstrip(b"=").decode()
    return encoded


def verify_cursor(cursor: str, secret: str) -> dict | None:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode()
        parts = decoded.rsplit("|", 1)
        if len(parts) != 2:
            return None
        payload, sig = parts
        expected = _hmac_hex(_DOMAIN_CURSOR, payload, secret)
        if not hmac.compare_digest(expected, sig):
            return None
        return json.loads(payload)
    except Exception:
        return None


def compute_filter_hash(filters: dict) -> str:
    raw = json.dumps(filters, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _hmac_hex(domain: bytes, message: str, secret: str) -> str:
    return hmac.new(
        secret.encode(),
        domain + message.encode(),
        hashlib.sha256,
    ).hexdigest()
