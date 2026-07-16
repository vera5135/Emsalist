"""P2.9B — Bounded, deterministic generation input assembly.

Builds the provider payload from canonical case memory only: confirmed
facts, confirmed chronology, active legal issues, claim/evidence summaries
and the exact trusted source paragraphs selected for the case. Applies the
bounded limits with deterministic rank/filter (issue-linked sources first,
stable ordering, head truncation) — never random truncation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    CaseFact,
    Claim,
    EvidenceClaimLink,
    LegalIssue,
    LegalIssueSourceLink,
    SourceParagraph,
    SourceRecord,
    TimelineEvent,
)
from app.services.draft_generation_provider import (
    MAX_CHRONOLOGY_EVENTS,
    MAX_CLAIMS,
    MAX_CONFIRMED_FACTS,
    MAX_LEGAL_ISSUES,
    MAX_SOURCE_PARAGRAPH_CHARS,
    MAX_SOURCE_PARAGRAPHS,
    MAX_TOTAL_SOURCE_CHARS,
)
from app.services.draft_readiness import (
    CONFIRMED_FACT_STATUSES,
    TrustedSourceSelection,
)


@dataclass(frozen=True)
class SelectedSourceParagraph:
    """One exact trusted source paragraph offered to the provider."""
    source_record_id: str
    source_version_id: str
    source_paragraph_id: str
    paragraph_index: int | None
    text_hash: str
    court: str
    chamber: str
    case_number: str
    decision_number: str
    decision_date: str
    article_number: str
    effective_trust: str


class UnknownSelectionError(ValueError):
    """A client-selected id does not belong to this case's eligible set."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


async def build_generation_input(
    db: AsyncSession,
    tenant_id: str,
    case_id: str,
    draft: Any,
    sections: list[dict[str, Any]],
    trusted_sources: list[TrustedSourceSelection],
    active_issue_ids: list[str],
    *,
    selected_legal_issue_ids: list[str],
    selected_source_usage_ids: list[str],
    max_source_paragraphs: int = MAX_SOURCE_PARAGRAPHS,
    max_total_source_chars: int = MAX_TOTAL_SOURCE_CHARS,
) -> tuple[dict[str, Any], dict[tuple[str, str, str], SelectedSourceParagraph]]:
    """Returns (provider payload, provenance context by exact source key)."""
    # ── Issues ──────────────────────────────────────────────────────────
    active_issue_set = set(active_issue_ids)
    if selected_legal_issue_ids:
        unknown = [i for i in selected_legal_issue_ids if i not in active_issue_set]
        if unknown:
            raise UnknownSelectionError("draft_generation_unknown_issue")
        issue_ids = [i for i in active_issue_ids if i in set(selected_legal_issue_ids)]
    else:
        issue_ids = list(active_issue_ids)
    issue_ids = issue_ids[:MAX_LEGAL_ISSUES]
    issues = list((await db.execute(select(LegalIssue).where(
        LegalIssue.tenant_id == tenant_id,
        LegalIssue.case_id == case_id,
        LegalIssue.id.in_(issue_ids) if issue_ids else LegalIssue.id.is_(None),
        LegalIssue.deleted_at.is_(None),
    ).order_by(LegalIssue.created_at.asc(), LegalIssue.id.asc()))).scalars().all())

    # ── Source usages ───────────────────────────────────────────────────
    if selected_source_usage_ids:
        by_usage_id = {s.usage_id: s for s in trusted_sources}
        unknown = [u for u in selected_source_usage_ids if u not in by_usage_id]
        if unknown:
            raise UnknownSelectionError("draft_generation_unknown_source")
        selections = [s for s in trusted_sources
                      if s.usage_id in set(selected_source_usage_ids)]
    else:
        selections = list(trusted_sources)

    # ── Expand usages to exact paragraphs (stable order) ────────────────
    issue_linked_keys = {
        (link.source_record_id, link.source_version_id, link.source_paragraph_id)
        for link in (await db.execute(select(LegalIssueSourceLink).where(
            LegalIssueSourceLink.tenant_id == tenant_id,
            LegalIssueSourceLink.case_id == case_id,
            LegalIssueSourceLink.deleted_at.is_(None),
        ))).scalars().all()
    }

    candidates: list[tuple[tuple[int, str, int, str], SelectedSourceParagraph, str]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for selection in selections:
        record = (await db.execute(select(SourceRecord).where(
            SourceRecord.id == selection.source_record_id,
            SourceRecord.deleted_at.is_(None),
        ))).scalar_one_or_none()
        if record is None:
            continue
        paragraph_query = select(SourceParagraph).where(
            SourceParagraph.source_version_id == selection.source_version_id,
        )
        if selection.source_paragraph_id:
            paragraph_query = paragraph_query.where(
                SourceParagraph.id == selection.source_paragraph_id)
        paragraphs = list((await db.execute(
            paragraph_query.order_by(SourceParagraph.paragraph_index.asc(),
                                     SourceParagraph.id.asc()))).scalars().all())
        for paragraph in paragraphs:
            key = (selection.source_record_id, selection.source_version_id, paragraph.id)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            item = SelectedSourceParagraph(
                source_record_id=selection.source_record_id,
                source_version_id=selection.source_version_id,
                source_paragraph_id=paragraph.id,
                paragraph_index=paragraph.paragraph_index,
                text_hash=paragraph.text_hash or "",
                court=record.court or "",
                chamber=record.chamber or "",
                case_number=record.case_number or "",
                decision_number=record.decision_number or "",
                decision_date=record.decision_date or "",
                article_number=paragraph.article_number or "",
                effective_trust=selection.effective_trust,
            )
            rank = (
                0 if key in issue_linked_keys else 1,
                selection.source_record_id,
                paragraph.paragraph_index if paragraph.paragraph_index is not None else 1 << 30,
                paragraph.id,
            )
            candidates.append((rank, item, paragraph.text or ""))
    candidates.sort(key=lambda entry: entry[0])

    source_items: list[dict[str, Any]] = []
    context: dict[tuple[str, str, str], SelectedSourceParagraph] = {}
    budget = max_total_source_chars
    for _rank, item, text in candidates:
        if len(source_items) >= max_source_paragraphs or budget <= 0:
            break
        excerpt = text[:min(MAX_SOURCE_PARAGRAPH_CHARS, budget)]
        if not excerpt:
            continue
        budget -= len(excerpt)
        key = (item.source_record_id, item.source_version_id, item.source_paragraph_id)
        context[key] = item
        source_items.append({
            "source_record_id": item.source_record_id,
            "source_version_id": item.source_version_id,
            "source_paragraph_id": item.source_paragraph_id,
            "court": item.court,
            "chamber": item.chamber,
            "case_number": item.case_number,
            "decision_number": item.decision_number,
            "decision_date": item.decision_date,
            "article_number": item.article_number,
            "paragraph_index": item.paragraph_index,
            "text_hash": item.text_hash,
            "paragraph_excerpt": excerpt,
        })

    # ── Confirmed facts / chronology / claims ───────────────────────────
    facts = list((await db.execute(select(CaseFact).where(
        CaseFact.tenant_id == tenant_id,
        CaseFact.case_id == case_id,
        CaseFact.deleted_at.is_(None),
        CaseFact.verification_status.in_(sorted(CONFIRMED_FACT_STATUSES)),
    ).order_by(CaseFact.created_at.asc(), CaseFact.id.asc()))).scalars().all())
    facts = facts[:MAX_CONFIRMED_FACTS]

    events = list((await db.execute(select(TimelineEvent).where(
        TimelineEvent.tenant_id == tenant_id,
        TimelineEvent.case_id == case_id,
        TimelineEvent.deleted_at.is_(None),
        TimelineEvent.verification_status.in_(sorted(CONFIRMED_FACT_STATUSES)),
    ).order_by(TimelineEvent.event_date.asc(), TimelineEvent.id.asc()))).scalars().all())
    events = events[:MAX_CHRONOLOGY_EVENTS]

    claims = list((await db.execute(select(Claim).where(
        Claim.tenant_id == tenant_id,
        Claim.case_id == case_id,
        Claim.deleted_at.is_(None),
    ).order_by(Claim.created_at.asc(), Claim.id.asc()))).scalars().all())
    claims = claims[:MAX_CLAIMS]
    supported_claim_ids = set((await db.execute(select(EvidenceClaimLink.claim_id).where(
        EvidenceClaimLink.tenant_id == tenant_id,
        EvidenceClaimLink.case_id == case_id,
        EvidenceClaimLink.deleted_at.is_(None),
        EvidenceClaimLink.relation_type == "evidence_supports_claim",
    ))).scalars().all())

    payload = {
        "draft": {"id": draft.id, "draft_type": draft.draft_type},
        "sections": sections,
        "case_memory": {
            "confirmed_facts": [
                {"fact_type": f.fact_type, "value": f.value, "unit": f.unit}
                for f in facts
            ],
            "chronology": [
                {"event_date": e.event_date, "description": e.description}
                for e in events
            ],
        },
        "legal_issues": [
            {"id": i.id, "title": i.title, "description": i.description,
             "status": i.status}
            for i in issues
        ],
        "claims": [
            {"id": c.id, "title": c.title, "requested_relief": c.requested_relief,
             "amount": c.amount, "currency": c.currency,
             "support_status": "supported" if c.id in supported_claim_ids
             else "unsupported"}
            for c in claims
        ],
        "sources": source_items,
    }
    return payload, context
