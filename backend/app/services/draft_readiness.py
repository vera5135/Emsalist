"""P2.9B — Deterministic draft readiness computation.

Pure DB reads; no LLM call, no persistence, no draft mutation. All reason and
warning codes are allowlisted; raw fact values, paragraph text or provider
text never appear in the result. The same inputs always produce the same
output (sorted, canonical ordering).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    CaseFact,
    Claim,
    Contradiction,
    DraftDocument,
    DraftParagraph,
    EvidenceClaimLink,
    EvidenceSufficiencyAssessment,
    LegalIssue,
    LegalIssueSourceLink,
    MissingInformation,
    SourceRecord,
    SourceUsage,
    TimelineEvent,
)
from app.services.source_ingestion_service import resolve_version_verification_status
from app.services.source_verification import TRUSTED_STATUSES

# Facts only count when a human/system verification chain confirmed them.
CONFIRMED_FACT_STATUSES = frozenset({
    "user_confirmed", "document_verified", "uyap_verified",
})

# ── Central fact-type vocabulary (P2_CASE_MEMORY_MODEL §3.1-3.2) ────────────
# court_name is the canonical CaseProfile field name; party_* mirror the
# canonical CaseParty roles. No aliases, no substring heuristics.
COURT_AUTHORITY_FACT_TYPES = frozenset({"court_name"})

PARTY_FACT_TYPES = frozenset({
    "party_client",
    "party_opponent",
    "party_plaintiff",
    "party_defendant",
    "party_recipient",
})

# Judicial draft types must know the court/authority they address.
COURT_REQUIRED_DRAFT_TYPES = frozenset({
    "dava_dilekcesi", "cevap_dilekcesi", "cevaba_cevap", "ikinci_cevap",
    "istinaf", "temyiz", "itiraz", "ihtiyati_tedbir", "beyan", "delil_listesi",
})

# Notice-like draft types must know the recipient party instead.
_RECIPIENT_PARTY_TYPES = frozenset({"party_recipient"})
RECIPIENT_REQUIRED_DRAFT_TYPES = frozenset({"ihtarname", "arabuluculuk_basvurusu"})

# Judicial drafts accept any adversarial/client party fact.
_JUDICIAL_PARTY_TYPES = frozenset({
    "party_client", "party_opponent", "party_plaintiff", "party_defendant",
})

BLOCKED_REASON_CODES = frozenset({
    "draft_not_editable",
    "draft_not_empty",
    "no_confirmed_facts",
    "court_or_authority_missing",
    "required_party_missing",
    "critical_contradiction_open",
    "critical_information_missing",
    "no_active_legal_issue",
    "no_trusted_source",
    "source_provenance_invalid",
    "critical_evidence_authenticity_risk",
})

WARNING_CODES = frozenset({
    "noncritical_contradiction_open",
    "important_information_missing",
    "unsupported_claim",
    "weak_evidence_coverage",
    "source_coverage_incomplete",
    "party_information_incomplete",
    "chronology_incomplete",
})

_WEAK_EVIDENCE_STATUSES = frozenset({
    "unsupported", "contradicted", "inadmissibility_risk",
})


@dataclass(frozen=True)
class TrustedSourceSelection:
    """One case source usage resolved to exact, trusted provenance."""
    usage_id: str
    source_record_id: str
    source_version_id: str
    source_paragraph_id: str  # "" for case-level usages
    effective_trust: str


@dataclass
class ReadinessResult:
    status: str  # ready | ready_with_warnings | blocked
    blocked_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, int] = field(default_factory=dict)
    trusted_sources: list[TrustedSourceSelection] = field(default_factory=list)
    active_issue_ids: list[str] = field(default_factory=list)


async def resolve_trusted_case_sources(
    db: AsyncSession, tenant_id: str, case_id: str,
) -> tuple[list[TrustedSourceSelection], int]:
    """Resolve active case source usages to exact trusted provenance.

    Returns (trusted selections in stable order, invalid_provenance_count).
    """
    usages = list((await db.execute(select(SourceUsage).where(
        SourceUsage.tenant_id == tenant_id,
        SourceUsage.case_id == case_id,
        SourceUsage.deleted_at.is_(None),
    ).order_by(SourceUsage.created_at.asc(), SourceUsage.id.asc()))).scalars().all())
    trusted: list[TrustedSourceSelection] = []
    invalid = 0
    for usage in usages:
        record = (await db.execute(select(SourceRecord).where(
            SourceRecord.id == usage.source_record_id,
            SourceRecord.deleted_at.is_(None),
        ))).scalar_one_or_none()
        if record is None or record.current_version_id != usage.source_version_id:
            invalid += 1
            continue
        trust = await resolve_version_verification_status(
            db, record.id, usage.source_version_id, record.verification_status)
        if trust not in TRUSTED_STATUSES:
            continue
        trusted.append(TrustedSourceSelection(
            usage_id=usage.id,
            source_record_id=usage.source_record_id,
            source_version_id=usage.source_version_id,
            source_paragraph_id=usage.source_paragraph_id or "",
            effective_trust=trust,
        ))
    return trusted, invalid


async def compute_draft_readiness(
    db: AsyncSession, tenant_id: str, case_id: str, draft: DraftDocument,
) -> ReadinessResult:
    blocked: set[str] = set()
    warnings: set[str] = set()

    if draft.status not in {"draft", "reviewing"}:
        blocked.add("draft_not_editable")

    active_paragraphs = (await db.execute(select(DraftParagraph.id).where(
        DraftParagraph.tenant_id == tenant_id,
        DraftParagraph.draft_document_id == draft.id,
        DraftParagraph.deleted_at.is_(None),
    ))).scalars().all()
    if active_paragraphs:
        blocked.add("draft_not_empty")

    facts = list((await db.execute(select(CaseFact).where(
        CaseFact.tenant_id == tenant_id,
        CaseFact.case_id == case_id,
        CaseFact.deleted_at.is_(None),
        CaseFact.verification_status.in_(sorted(CONFIRMED_FACT_STATUSES)),
    ))).scalars().all())
    confirmed_fact_count = len(facts)
    if confirmed_fact_count == 0:
        blocked.add("no_confirmed_facts")

    confirmed_fact_types = {f.fact_type for f in facts}
    if draft.draft_type in COURT_REQUIRED_DRAFT_TYPES:
        if not (confirmed_fact_types & COURT_AUTHORITY_FACT_TYPES):
            blocked.add("court_or_authority_missing")
        judicial_parties = confirmed_fact_types & _JUDICIAL_PARTY_TYPES
        if not judicial_parties:
            blocked.add("required_party_missing")
        elif len(judicial_parties) < 2:
            warnings.add("party_information_incomplete")
    if draft.draft_type in RECIPIENT_REQUIRED_DRAFT_TYPES:
        if not (confirmed_fact_types & _RECIPIENT_PARTY_TYPES):
            blocked.add("required_party_missing")

    contradictions = list((await db.execute(select(Contradiction).where(
        Contradiction.tenant_id == tenant_id,
        Contradiction.case_id == case_id,
        Contradiction.status == "open",
        Contradiction.deleted_at.is_(None),
    ))).scalars().all())
    open_critical_contradictions = [c for c in contradictions if c.severity == "critical"]
    if open_critical_contradictions:
        blocked.add("critical_contradiction_open")
    if len(contradictions) > len(open_critical_contradictions):
        warnings.add("noncritical_contradiction_open")

    missing = list((await db.execute(select(MissingInformation).where(
        MissingInformation.tenant_id == tenant_id,
        MissingInformation.case_id == case_id,
        MissingInformation.status == "open",
        MissingInformation.deleted_at.is_(None),
    ))).scalars().all())
    open_critical_missing = [m for m in missing if m.importance == "critical"]
    if open_critical_missing:
        blocked.add("critical_information_missing")
    if any(m.importance in {"high", "medium"} for m in missing):
        warnings.add("important_information_missing")

    issues = list((await db.execute(select(LegalIssue).where(
        LegalIssue.tenant_id == tenant_id,
        LegalIssue.case_id == case_id,
        LegalIssue.deleted_at.is_(None),
    ).order_by(LegalIssue.created_at.asc(), LegalIssue.id.asc()))).scalars().all())
    if not issues:
        blocked.add("no_active_legal_issue")

    trusted_sources, invalid_provenance = await resolve_trusted_case_sources(
        db, tenant_id, case_id)
    if not trusted_sources:
        blocked.add("no_trusted_source")
        if invalid_provenance:
            blocked.add("source_provenance_invalid")

    assessments = list((await db.execute(select(EvidenceSufficiencyAssessment).where(
        EvidenceSufficiencyAssessment.tenant_id == tenant_id,
        EvidenceSufficiencyAssessment.case_id == case_id,
        EvidenceSufficiencyAssessment.deleted_at.is_(None),
    ))).scalars().all())
    if any(a.status == "authenticity_risk" for a in assessments):
        blocked.add("critical_evidence_authenticity_risk")
    if any(a.status in _WEAK_EVIDENCE_STATUSES for a in assessments):
        warnings.add("weak_evidence_coverage")

    claims = list((await db.execute(select(Claim).where(
        Claim.tenant_id == tenant_id,
        Claim.case_id == case_id,
        Claim.deleted_at.is_(None),
    ))).scalars().all())
    supporting_claim_ids = set((await db.execute(select(EvidenceClaimLink.claim_id).where(
        EvidenceClaimLink.tenant_id == tenant_id,
        EvidenceClaimLink.case_id == case_id,
        EvidenceClaimLink.deleted_at.is_(None),
        EvidenceClaimLink.relation_type == "evidence_supports_claim",
    ))).scalars().all())
    unsupported_claims = [c for c in claims if c.id not in supporting_claim_ids]
    if unsupported_claims:
        warnings.add("unsupported_claim")

    if issues:
        linked_issue_ids = set((await db.execute(select(LegalIssueSourceLink.issue_id).where(
            LegalIssueSourceLink.tenant_id == tenant_id,
            LegalIssueSourceLink.case_id == case_id,
            LegalIssueSourceLink.deleted_at.is_(None),
        ))).scalars().all())
        if any(issue.id not in linked_issue_ids for issue in issues):
            warnings.add("source_coverage_incomplete")

    events = (await db.execute(select(TimelineEvent.id).where(
        TimelineEvent.tenant_id == tenant_id,
        TimelineEvent.case_id == case_id,
        TimelineEvent.deleted_at.is_(None),
    ))).scalars().all()
    if not events:
        warnings.add("chronology_incomplete")

    if blocked:
        status = "blocked"
    elif warnings:
        status = "ready_with_warnings"
    else:
        status = "ready"

    assert blocked <= BLOCKED_REASON_CODES
    assert warnings <= WARNING_CODES
    return ReadinessResult(
        status=status,
        blocked_reasons=sorted(blocked),
        warnings=sorted(warnings),
        metrics={
            "confirmed_fact_count": confirmed_fact_count,
            "trusted_source_count": len(trusted_sources),
            "open_critical_contradiction_count": len(open_critical_contradictions),
            "open_critical_missing_information_count": len(open_critical_missing),
            "unsupported_claim_count": len(unsupported_claims),
        },
        trusted_sources=trusted_sources,
        active_issue_ids=[issue.id for issue in issues],
    )
