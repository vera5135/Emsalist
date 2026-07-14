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
    parts = [
        "opt_terms:" + ",".join(sorted(query_plan.optional_terms)),
        "opt_phrases:" + ",".join(sorted(query_plan.optional_phrases)),
        "req_terms:" + ",".join(sorted(query_plan.required_terms)),
        "req_phrases:" + ",".join(sorted(query_plan.required_phrases)),
        "exc_terms:" + ",".join(sorted(query_plan.excluded_terms)),
        "exc_phrases:" + ",".join(sorted(query_plan.excluded_phrases)),
        "citations:" + ",".join(sorted(query_plan.exact_citation_candidates)),
        "legislation:" + ",".join(sorted(query_plan.legislation_number_candidates)),
        "articles:" + ",".join(sorted(query_plan.article_candidates)),
        "tenant:" + tenant_id,
    ]
    payload = "|".join(parts)
    return _hmac_hex(_DOMAIN_QUERY_HASH, payload, secret)


async def compute_index_version(session: AsyncSession) -> str:
    from app.db.models import SourceRecord, SourceVersion, SourceVerification
    from app.config import get_settings

    result = await session.execute(
        select(func.max(SourceRecord.updated_at))
    )
    max_rec = result.scalar_one_or_none()

    result = await session.execute(
        select(func.max(SourceParagraph.embedding_updated_at))
    )
    max_emb = result.scalar_one_or_none()

    result = await session.execute(
        select(func.count(SourceParagraph.id)).where(
            SourceParagraph.embedding_status == "indexed"
        )
    )
    indexed_paragraphs = result.scalar_one()

    result = await session.execute(
        select(func.count(SourceVersion.id)).where(SourceVersion.status == "active")
    )
    active_versions = result.scalar_one()

    # ── Exact-version trust fingerprint ───────────────────────────────────
    # Hash current-version verification provenance rows
    verif_rows = await session.execute(
        select(
            SourceVerification.id,
            SourceVerification.source_record_id,
            SourceVerification.source_version_id,
            SourceVerification.verification_method,
            SourceVerification.verifier_type,
            SourceVerification.result,
            SourceVerification.evidence_url,
            SourceVerification.evidence_hash,
        )
        .join(SourceRecord, SourceVerification.source_record_id == SourceRecord.id)
        .where(
            SourceVerification.source_version_id == SourceRecord.current_version_id,
            SourceRecord.deleted_at.is_(None),
        )
        .order_by(SourceVerification.source_record_id, SourceVerification.source_version_id)
    )
    verif_parts = []
    for row in verif_rows.all():
        verif_parts.append(
            f"{row[1]}|{row[2]}|{row[3]}|{row[4]}|{row[5]}|{row[6] or ''}|{row[7] or ''}"
        )
    verif_hash = hashlib.sha256(";;".join(verif_parts).encode()).hexdigest()[:12]

    settings = get_settings()
    components = [
        str(int(max_rec.timestamp()) if max_rec else 0),
        str(int(max_emb.timestamp()) if max_emb else 0),
        str(indexed_paragraphs),
        str(active_versions),
        verif_hash,
        settings.search_embedding_model,
        settings.search_embedding_version,
        "p2.7-v6",
    ]
    fingerprint = hashlib.sha256("|".join(components).encode()).hexdigest()[:16]
    return fingerprint


def sign_result_id(
    query_id: str,
    source_id: str,
    source_version_id: str,
    paragraph_id: str,
    index_version: str,
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
