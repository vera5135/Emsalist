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
    from app.services.source_ingestion_service import resolve_version_verification_status

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

    # ── Authoritative exact-version effective-trust fingerprint ────────────
    current_records = await session.execute(
        select(SourceRecord).where(
            SourceRecord.current_version_id.isnot(None),
            SourceRecord.deleted_at.is_(None),
        ).order_by(SourceRecord.id)
    )
    records = current_records.scalars().all()

    trust_payload = []
    for rec in records:
        resolved = await resolve_version_verification_status(
            session, rec.id, rec.current_version_id, rec.verification_status
        )
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
            ).where(
                SourceVerification.source_record_id == rec.id,
                SourceVerification.source_version_id == rec.current_version_id,
            ).order_by(
                SourceVerification.source_record_id,
                SourceVerification.source_version_id,
                SourceVerification.id,
            )
        )
        verifications = []
        for row in verif_rows.all():
            verifications.append([
                row[0], row[1], row[2], row[3], row[4], row[5],
                row[6] or "", row[7] or "",
            ])
        trust_payload.append({
            "rid": rec.id,
            "cvid": rec.current_version_id,
            "rec_st": rec.verification_status,
            "eff_st": resolved,
            "verifs": verifications,
        })

    trust_fingerprint = hashlib.sha256(
        json.dumps(trust_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()[:16]

    # ── Current-version embedding fingerprint ──────────────────────────────
    emb_rows = await session.execute(
        select(
            SourceRecord.id,
            SourceParagraph.source_version_id,
            SourceParagraph.id,
            SourceParagraph.embedding_status,
            SourceParagraph.embedding_model,
            SourceParagraph.embedding_version,
            SourceParagraph.embedding_dimension,
            SourceParagraph.embedding_vector_json,
            SourceParagraph.embedding_updated_at,
        )
        .join(SourceRecord, SourceParagraph.source_version_id == SourceRecord.current_version_id)
        .where(SourceRecord.deleted_at.is_(None))
        .order_by(
            SourceRecord.id,
            SourceParagraph.source_version_id,
            SourceParagraph.id,
        )
    )
    emb_payload = []
    for row in emb_rows.all():
        raw_vec = row[7] or ""
        vec_hash = hashlib.sha256(raw_vec.encode()).hexdigest()
        upd = row[8].isoformat() if row[8] is not None else ""
        emb_payload.append({
            "rid": row[0],
            "svid": row[1],
            "pid": row[2],
            "status": row[3] or "",
            "model": row[4] or "",
            "version": row[5] or "",
            "dim": row[6],
            "vh": vec_hash,
            "upd": upd,
        })
    emb_fingerprint = hashlib.sha256(
        json.dumps(emb_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()[:16]

    settings = get_settings()
    components = [
        trust_fingerprint,
        emb_fingerprint,
        settings.search_embedding_model,
        settings.search_embedding_version,
        "p2.7-v8",
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
