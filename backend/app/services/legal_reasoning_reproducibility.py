"""Deterministic P2.8 legal-reasoning reproducibility helpers.

The helpers bind reasoning runs to persisted case-memory state and exact source
provenance. They do not persist or expose hidden model reasoning.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    CaseFact,
    Claim,
    Contradiction,
    Defense,
    Evidence,
    LegalIssue,
    LegalIssueSourceLink,
    MissingInformation,
    Risk,
    SourceParagraph,
    SourceRecord,
    SourceVersion,
    TimelineEvent,
)
from app.services.source_ingestion_service import resolve_version_verification_status


P2_8_PROMPT_VERSION = "p2.8b-legal-reasoning-1"

_HIDDEN_REASONING_KEYS = frozenset({
    "chain_of_thought",
    "thinking",
    "reasoning_trace",
    "hidden_reasoning",
    "scratchpad",
})


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def assert_no_hidden_reasoning_keys(value: Any) -> None:
    found = _find_hidden_reasoning_keys(value)
    if found:
        raise ValueError(f"hidden_reasoning_fields_not_allowed:{','.join(sorted(found))}")


def output_hash(value: Any) -> str:
    assert_no_hidden_reasoning_keys(value)
    return canonical_hash(value)


async def compute_memory_fingerprint(
    session: AsyncSession, *, tenant_id: str, case_id: str
) -> str:
    payload: list[dict[str, Any]] = []
    for model, label, columns in (
        (CaseFact, "case_facts", (
            "id", "fact_type", "value", "normalized_value", "unit", "source_type",
            "source_id", "verification_status", "importance", "supersedes_fact_id",
            "version", "deleted_at",
        )),
        (TimelineEvent, "timeline_events", (
            "id", "event_type", "description", "event_date", "event_time",
            "is_approximate", "party_reference", "legal_significance",
            "source_type", "source_id", "verification_status", "version", "deleted_at",
        )),
        (Claim, "claims", (
            "id", "claim_type", "title", "description", "requested_relief",
            "amount", "currency", "status", "source_type", "source_id",
            "verification_status", "version", "deleted_at",
        )),
        (Defense, "defenses", (
            "id", "claim_type", "title", "description", "responds_to_claim_id",
            "status", "source_type", "source_id", "verification_status",
            "version", "deleted_at",
        )),
        (Evidence, "evidence", (
            "id", "evidence_type", "title", "description", "document_id",
            "supports_claim_id", "supports_event_id", "reliability_status",
            "admissibility_status", "source_type", "source_id",
            "verification_status", "version", "deleted_at",
        )),
        (MissingInformation, "missing_information", (
            "id", "field_key", "label", "reason_required", "importance",
            "related_legal_issue", "expected_source", "completion_condition",
            "status", "resolved_by_fact_id", "version", "deleted_at",
        )),
        (Contradiction, "contradictions", (
            "id", "contradiction_type", "subject_key", "description", "fact_ids",
            "severity", "status", "resolution_fact_id", "resolution_note",
            "version", "deleted_at",
        )),
        (Risk, "risks", (
            "id", "risk_type", "severity", "title", "rationale",
            "affected_claim", "supporting_reference", "mitigation",
            "related_missing_information", "status", "source_type", "source_id",
            "version", "deleted_at",
        )),
        (LegalIssue, "legal_issues", (
            "id", "parent_issue_id", "issue_code", "title", "description",
            "status", "confidence", "version", "deleted_at",
        )),
    ):
        payload.append({
            "table": label,
            "rows": await _rows(session, model, tenant_id, case_id, columns),
        })
    return canonical_hash(payload)


async def next_memory_revision_number(
    session: AsyncSession, *, tenant_id: str, case_id: str
) -> int:
    from app.db.models import MemoryRevision

    result = await session.execute(
        select(func.max(MemoryRevision.revision_number)).where(
            MemoryRevision.tenant_id == tenant_id,
            MemoryRevision.case_id == case_id,
        )
    )
    current = result.scalar_one_or_none()
    return int(current or 0) + 1


async def compute_case_source_fingerprint(
    session: AsyncSession, *, tenant_id: str, case_id: str
) -> str:
    result = await session.execute(
        select(LegalIssueSourceLink, SourceRecord, SourceVersion, SourceParagraph)
        .join(SourceRecord, LegalIssueSourceLink.source_record_id == SourceRecord.id)
        .join(
            SourceVersion,
            (LegalIssueSourceLink.source_record_id == SourceVersion.source_record_id)
            & (LegalIssueSourceLink.source_version_id == SourceVersion.id),
        )
        .join(
            SourceParagraph,
            (LegalIssueSourceLink.source_version_id == SourceParagraph.source_version_id)
            & (LegalIssueSourceLink.source_paragraph_id == SourceParagraph.id),
        )
        .where(
            LegalIssueSourceLink.tenant_id == tenant_id,
            LegalIssueSourceLink.case_id == case_id,
            LegalIssueSourceLink.deleted_at.is_(None),
            SourceRecord.deleted_at.is_(None),
        )
        .order_by(
            LegalIssueSourceLink.issue_id,
            LegalIssueSourceLink.source_record_id,
            LegalIssueSourceLink.source_version_id,
            LegalIssueSourceLink.source_paragraph_id,
        )
    )
    payload = []
    for link, record, version, paragraph in result.all():
        effective_trust = await resolve_version_verification_status(
            session, record.id, version.id, record.verification_status
        )
        payload.append({
            "issue_id": link.issue_id,
            "relation_type": link.relation_type,
            "source_record_id": record.id,
            "source_version_id": version.id,
            "source_paragraph_id": paragraph.id,
            "record_verification_status": record.verification_status,
            "effective_trust": effective_trust,
            "record_current_version_id": record.current_version_id or "",
            "version_status": version.status,
            "content_hash": version.content_hash,
            "paragraph_text_hash": paragraph.text_hash,
            "article_number": paragraph.article_number,
            "locator_json": _normalize(paragraph.locator_json),
        })
    return canonical_hash(payload)


async def _rows(
    session: AsyncSession,
    model,
    tenant_id: str,
    case_id: str,
    columns: Iterable[str],
) -> list[dict[str, Any]]:
    result = await session.execute(
        select(model).where(
            model.tenant_id == tenant_id,
            model.case_id == case_id,
        ).order_by(model.id)
    )
    rows = []
    for item in result.scalars().all():
        rows.append({column: _normalize(getattr(item, column)) for column in columns})
    return rows


def _normalize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    return value


def _find_hidden_reasoning_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key) in _HIDDEN_REASONING_KEYS:
                found.add(str(key))
            found.update(_find_hidden_reasoning_keys(nested))
    elif isinstance(value, list):
        for nested in value:
            found.update(_find_hidden_reasoning_keys(nested))
    return found
