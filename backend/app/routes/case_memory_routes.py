"""P2.4 — DB-backed structured case memory endpoints.

All routes are nested under an owned case: the first action is always
``_load_owned_case`` which enforces tenant + owner and returns 404 for
missing/foreign resources (no existence disclosure). Memory values are never
logged; audit ``safe_metadata`` carries only ids/type/action/verification
status.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.case_chat_repository import CaseRepository
from app.db.case_memory_repository import (
    CaseFactRepository,
    ContradictionRepository,
    MissingInformationRepository,
    RiskRepository,
    TimelineRepository,
    VersionConflictError,
    overall_risk_level,
)
from app.db.models import Case
from app.db.session import get_session
from app.models.case_memory_models import (
    CaseMemoryResponse,
    ContradictionResolveRequest,
    ContradictionResponse,
    FactCreateRequest,
    FactResponse,
    FactUpdateRequest,
    MessageResponse,
    MissingInfoCreateRequest,
    MissingInfoResponse,
    RiskCreateRequest,
    RiskResponse,
    TimelineCreateRequest,
    TimelineEventResponse,
)
from app.services.auth_service import SecurityContext, resolve_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cases/{case_id}/memory", tags=["Case Memory"])

CRITICAL_IMPORTANCE = frozenset({"critical", "high"})


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


async def _load_owned_case(
    db: AsyncSession, ctx: SecurityContext, case_id: str
) -> Case:
    case = await CaseRepository.get(db, ctx.tenant_id, case_id)
    if case is None or case.owner_user_id != ctx.actor_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Case not found"
        )
    return case


async def _audit(db, ctx, case_id, action, metadata):
    from app.db.auth_repository import AuthAuditRepository

    await AuthAuditRepository.write_event(
        db, ctx.tenant_id, ctx.actor_id, case_id, action, "success", metadata
    )


def _fact_resp(f) -> FactResponse:
    return FactResponse(
        id=f.id, case_id=f.case_id, fact_type=f.fact_type, value=f.value,
        importance=f.importance, source_type=f.source_type, source_id=f.source_id,
        confidence=f.confidence, verification_status=f.verification_status,
        version=f.version, created_at=_iso(f.created_at) or "",
        updated_at=_iso(f.updated_at) or "",
    )


def _timeline_resp(e) -> TimelineEventResponse:
    return TimelineEventResponse(
        id=e.id, case_id=e.case_id, event_type=e.event_type,
        description=e.description, event_date=e.event_date, event_time=e.event_time,
        is_approximate=e.is_approximate, party_reference=e.party_reference,
        legal_significance=e.legal_significance,
        verification_status=e.verification_status, version=e.version,
        created_at=_iso(e.created_at) or "",
    )


def _missing_resp(m) -> MissingInfoResponse:
    return MissingInfoResponse(
        id=m.id, case_id=m.case_id, field_key=m.field_key, label=m.label,
        reason_required=m.reason_required, importance=m.importance,
        related_legal_issue=m.related_legal_issue, expected_source=m.expected_source,
        status=m.status, resolved_by_fact_id=m.resolved_by_fact_id,
        resolved_at=_iso(m.resolved_at), version=m.version,
        created_at=_iso(m.created_at) or "",
    )


def _contradiction_resp(c) -> ContradictionResponse:
    return ContradictionResponse(
        id=c.id, case_id=c.case_id, contradiction_type=c.contradiction_type,
        subject_key=c.subject_key, description=c.description,
        fact_ids=list(c.fact_ids or []), severity=c.severity, status=c.status,
        resolution_fact_id=c.resolution_fact_id, resolution_note=c.resolution_note,
        version=c.version, created_at=_iso(c.created_at) or "",
        resolved_at=_iso(c.resolved_at),
    )


def _risk_resp(r) -> RiskResponse:
    return RiskResponse(
        id=r.id, case_id=r.case_id, risk_type=r.risk_type, severity=r.severity,
        title=r.title, rationale=r.rationale, affected_claim=r.affected_claim,
        supporting_reference=r.supporting_reference, mitigation=r.mitigation,
        related_missing_information=r.related_missing_information, status=r.status,
        version=r.version, created_at=_iso(r.created_at) or "",
    )


async def _compute_overall_risk(db, tenant_id, case_id) -> str:
    risks = await RiskRepository.list_for_case(db, tenant_id, case_id)
    contradictions = await ContradictionRepository.list_for_case(db, tenant_id, case_id)
    missing = await MissingInformationRepository.list_for_case(db, tenant_id, case_id)
    open_critical_contradiction = any(
        c.status == "open" and c.severity in ("high", "critical") for c in contradictions
    )
    critical_missing = any(
        m.status not in ("supplied", "verified", "waived")
        and m.importance in CRITICAL_IMPORTANCE
        for m in missing
    )
    return overall_risk_level(
        risks,
        open_critical_contradiction=open_critical_contradiction,
        critical_missing=critical_missing,
    )


# ---------------------------------------------------------------------------
# Aggregate memory
# ---------------------------------------------------------------------------
@router.get("", response_model=CaseMemoryResponse, operation_id="case_memory_get")
async def get_memory(
    case_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> CaseMemoryResponse:
    case = await _load_owned_case(db, ctx, case_id)
    facts = await CaseFactRepository.list_for_case(db, ctx.tenant_id, case.id)
    timeline = await TimelineRepository.list_for_case(db, ctx.tenant_id, case.id)
    missing = await MissingInformationRepository.list_for_case(db, ctx.tenant_id, case.id)
    contradictions = await ContradictionRepository.list_for_case(db, ctx.tenant_id, case.id)
    risks = await RiskRepository.list_for_case(db, ctx.tenant_id, case.id)
    overall = await _compute_overall_risk(db, ctx.tenant_id, case.id)
    return CaseMemoryResponse(
        case_id=case.id,
        overall_risk_level=overall,
        facts=[_fact_resp(f) for f in facts],
        timeline=[_timeline_resp(e) for e in timeline],
        missing_information=[_missing_resp(m) for m in missing],
        contradictions=[_contradiction_resp(c) for c in contradictions],
        risks=[_risk_resp(r) for r in risks],
        counts={
            "facts": len(facts),
            "timeline": len(timeline),
            "missing_information": len(missing),
            "contradictions": len(contradictions),
            "risks": len(risks),
        },
    )


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------
@router.post("/facts", response_model=FactResponse, status_code=201, operation_id="case_memory_fact_create")
async def create_fact(
    case_id: str,
    body: FactCreateRequest,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> FactResponse:
    case = await _load_owned_case(db, ctx, case_id)
    fact = await CaseFactRepository.create(
        db, tenant_id=ctx.tenant_id, case_id=case.id, fact_type=body.fact_type,
        value=body.value, created_by=ctx.actor_id, source_type=body.source_type,
        source_id=body.source_id, confidence=body.confidence, importance=body.importance,
        verification_status="suggested",
    )
    # Deterministic contradiction detection for this fact_type.
    await ContradictionRepository.detect_for_fact_type(
        db, ctx.tenant_id, case.id, body.fact_type, ctx.actor_id
    )
    await _audit(db, ctx, case.id, "case_fact_created",
                 {"resource": "case_fact", "fact_id": fact.id,
                  "fact_type": fact.fact_type, "verification_status": fact.verification_status})
    await db.commit()
    return _fact_resp(fact)


@router.patch("/facts/{fact_id}", response_model=FactResponse, operation_id="case_memory_fact_update")
async def update_fact(
    case_id: str,
    fact_id: str,
    body: FactUpdateRequest,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> FactResponse:
    case = await _load_owned_case(db, ctx, case_id)
    fact = await CaseFactRepository.get(db, ctx.tenant_id, case.id, fact_id)
    if fact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found")
    try:
        await CaseFactRepository.update(
            db, fact, body.version, value=body.value, importance=body.importance
        )
    except VersionConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version conflict: expected {e.expected}, current {e.current}",
        )
    if body.value is not None:
        await ContradictionRepository.detect_for_fact_type(
            db, ctx.tenant_id, case.id, fact.fact_type, ctx.actor_id
        )
    await _audit(db, ctx, case.id, "case_fact_updated",
                 {"resource": "case_fact", "fact_id": fact.id,
                  "verification_status": fact.verification_status})
    await db.commit()
    return _fact_resp(fact)


@router.post("/facts/{fact_id}/confirm", response_model=FactResponse, operation_id="case_memory_fact_confirm")
async def confirm_fact(
    case_id: str,
    fact_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> FactResponse:
    case = await _load_owned_case(db, ctx, case_id)
    fact = await CaseFactRepository.get(db, ctx.tenant_id, case.id, fact_id)
    if fact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found")
    await CaseFactRepository.set_status(db, fact, "user_confirmed")
    # Try to resolve any missing-information whose condition this fact satisfies.
    for item in await MissingInformationRepository.list_for_case(db, ctx.tenant_id, case.id):
        if item.status in ("supplied", "verified", "waived"):
            continue
        satisfied = MissingInformationRepository.completion_satisfied(item, [fact])
        if satisfied is not None:
            await MissingInformationRepository.resolve(db, item, satisfied)
    await _audit(db, ctx, case.id, "case_fact_confirmed",
                 {"resource": "case_fact", "fact_id": fact.id,
                  "verification_status": fact.verification_status})
    await db.commit()
    return _fact_resp(fact)


@router.post("/facts/{fact_id}/reject", response_model=FactResponse, operation_id="case_memory_fact_reject")
async def reject_fact(
    case_id: str,
    fact_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> FactResponse:
    case = await _load_owned_case(db, ctx, case_id)
    fact = await CaseFactRepository.get(db, ctx.tenant_id, case.id, fact_id)
    if fact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fact not found")
    # Reject preserves the record (soft state), never deletes.
    await CaseFactRepository.set_status(db, fact, "rejected")
    await _audit(db, ctx, case.id, "case_fact_rejected",
                 {"resource": "case_fact", "fact_id": fact.id,
                  "verification_status": fact.verification_status})
    await db.commit()
    return _fact_resp(fact)


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------
@router.post("/timeline", response_model=TimelineEventResponse, status_code=201, operation_id="case_memory_timeline_create")
async def create_timeline_event(
    case_id: str,
    body: TimelineCreateRequest,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> TimelineEventResponse:
    case = await _load_owned_case(db, ctx, case_id)
    event = await TimelineRepository.create(
        db, tenant_id=ctx.tenant_id, case_id=case.id, event_type=body.event_type,
        description=body.description, created_by=ctx.actor_id,
        event_date=body.event_date, event_time=body.event_time,
        is_approximate=body.is_approximate, party_reference=body.party_reference,
        legal_significance=body.legal_significance, source_type=body.source_type,
        source_id=body.source_id,
    )
    await _audit(db, ctx, case.id, "timeline_event_created",
                 {"resource": "timeline_event", "event_id": event.id})
    await db.commit()
    return _timeline_resp(event)


@router.get("/timeline", response_model=list[TimelineEventResponse], operation_id="case_memory_timeline_list")
async def list_timeline(
    case_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[TimelineEventResponse]:
    case = await _load_owned_case(db, ctx, case_id)
    events = await TimelineRepository.list_for_case(db, ctx.tenant_id, case.id)
    return [_timeline_resp(e) for e in events]


# ---------------------------------------------------------------------------
# Missing information
# ---------------------------------------------------------------------------
@router.post("/missing-information", response_model=MissingInfoResponse, status_code=201, operation_id="case_memory_missing_create")
async def create_missing_information(
    case_id: str,
    body: MissingInfoCreateRequest,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> MissingInfoResponse:
    case = await _load_owned_case(db, ctx, case_id)
    item = await MissingInformationRepository.create(
        db, tenant_id=ctx.tenant_id, case_id=case.id, field_key=body.field_key,
        label=body.label, created_by=ctx.actor_id, reason_required=body.reason_required,
        importance=body.importance, related_legal_issue=body.related_legal_issue,
        expected_source=body.expected_source, completion_condition=body.completion_condition,
    )
    await _audit(db, ctx, case.id, "missing_information_created",
                 {"resource": "missing_information", "item_id": item.id, "field_key": item.field_key})
    await db.commit()
    return _missing_resp(item)


@router.get("/missing-information", response_model=list[MissingInfoResponse], operation_id="case_memory_missing_list")
async def list_missing_information(
    case_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[MissingInfoResponse]:
    case = await _load_owned_case(db, ctx, case_id)
    items = await MissingInformationRepository.list_for_case(db, ctx.tenant_id, case.id)
    return [_missing_resp(m) for m in items]


@router.post("/missing-information/{item_id}/resolve", response_model=MissingInfoResponse, operation_id="case_memory_missing_resolve")
async def resolve_missing_information(
    case_id: str,
    item_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> MissingInfoResponse:
    case = await _load_owned_case(db, ctx, case_id)
    item = await MissingInformationRepository.get(db, ctx.tenant_id, case.id, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Missing information not found")
    # Completion requires a concrete verified value — never mere category presence.
    facts = await CaseFactRepository.list_for_case(db, ctx.tenant_id, case.id)
    satisfying = MissingInformationRepository.completion_satisfied(item, facts)
    if satisfying is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Completion condition not satisfied by a verified value.",
        )
    await MissingInformationRepository.resolve(db, item, satisfying)
    await _audit(db, ctx, case.id, "missing_information_resolved",
                 {"resource": "missing_information", "item_id": item.id,
                  "resolved_by_fact_id": item.resolved_by_fact_id})
    await db.commit()
    return _missing_resp(item)


# ---------------------------------------------------------------------------
# Contradictions
# ---------------------------------------------------------------------------
@router.get("/contradictions", response_model=list[ContradictionResponse], operation_id="case_memory_contradiction_list")
async def list_contradictions(
    case_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[ContradictionResponse]:
    case = await _load_owned_case(db, ctx, case_id)
    items = await ContradictionRepository.list_for_case(db, ctx.tenant_id, case.id)
    return [_contradiction_resp(c) for c in items]


@router.post("/contradictions/{contradiction_id}/resolve", response_model=ContradictionResponse, operation_id="case_memory_contradiction_resolve")
async def resolve_contradiction(
    case_id: str,
    contradiction_id: str,
    body: ContradictionResolveRequest,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> ContradictionResponse:
    case = await _load_owned_case(db, ctx, case_id)
    contradiction = await ContradictionRepository.get(db, ctx.tenant_id, case.id, contradiction_id)
    if contradiction is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contradiction not found")
    resolution_fact = await CaseFactRepository.get(
        db, ctx.tenant_id, case.id, body.resolution_fact_id
    )
    if resolution_fact is None or resolution_fact.id not in (contradiction.fact_ids or []):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resolution fact must be one of the conflicting facts.",
        )
    await ContradictionRepository.resolve(
        db, contradiction, resolution_fact=resolution_fact,
        resolved_by=ctx.actor_id, note=body.note,
    )
    await _audit(db, ctx, case.id, "contradiction_resolved",
                 {"resource": "contradiction", "contradiction_id": contradiction.id,
                  "resolution_fact_id": resolution_fact.id, "status": contradiction.status})
    await db.commit()
    return _contradiction_resp(contradiction)


# ---------------------------------------------------------------------------
# Risks
# ---------------------------------------------------------------------------
@router.post("/risks", response_model=RiskResponse, status_code=201, operation_id="case_memory_risk_create")
async def create_risk(
    case_id: str,
    body: RiskCreateRequest,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> RiskResponse:
    case = await _load_owned_case(db, ctx, case_id)
    risk = await RiskRepository.create(
        db, tenant_id=ctx.tenant_id, case_id=case.id, risk_type=body.risk_type,
        severity=body.severity, title=body.title, created_by=ctx.actor_id,
        rationale=body.rationale, affected_claim=body.affected_claim,
        supporting_reference=body.supporting_reference, mitigation=body.mitigation,
        related_missing_information=body.related_missing_information,
    )
    await _audit(db, ctx, case.id, "risk_created",
                 {"resource": "risk", "risk_id": risk.id, "risk_type": risk.risk_type,
                  "severity": risk.severity})
    await db.commit()
    return _risk_resp(risk)


@router.get("/risks", response_model=list[RiskResponse], operation_id="case_memory_risk_list")
async def list_risks(
    case_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[RiskResponse]:
    case = await _load_owned_case(db, ctx, case_id)
    risks = await RiskRepository.list_for_case(db, ctx.tenant_id, case.id)
    return [_risk_resp(r) for r in risks]
