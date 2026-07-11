"""P2.6 — Trusted legal source backbone endpoints.

Two authorization tiers:
- Global source READ: any authenticated user (lawyer) may read.
- Editor/admin actions (ingest, verify, quarantine, review, resolve-conflict):
  gated by ``require_editor`` — a normal lawyer tenant user cannot make a global
  source verified_official/editor_verified or quarantine it.
- Case SourceUsage: tenant + case-owner scoped (IDOR-guarded, 404 no-disclosure).

Full source text, paragraph text and verification notes are never logged/audited.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.case_chat_repository import CaseRepository
from app.db.models import Case
from app.db.session import get_session
from app.db.source_repository import (
    SourceParagraphRepository,
    SourceRecordRepository,
    SourceRelationshipRepository,
    SourceUsageRepository,
    SourceVerificationRepository,
    SourceVersionRepository,
)
from app.models.source_models import (
    OfficialTrackingItem,
    OfficialTrackingResponse,
    ResolveConflictRequest,
    SourceIngestRequest,
    SourceIngestResponse,
    SourceParagraphResponse,
    SourceRecordListResponse,
    SourceRecordResponse,
    SourceRelationshipCreateRequest,
    SourceRelationshipResponse,
    SourceReviewItem,
    SourceReviewListResponse,
    SourceUsageCreateRequest,
    SourceUsageListResponse,
    SourceUsageResponse,
    SourceVerifyRequest,
    SourceVersionResponse,
)
from app.services.auth_service import SecurityContext, get_auth_mode, resolve_current_user
from app.services.source_ingestion_service import ingest_editor_candidate, get_version_official_evidence, resolve_version_verification_status
from app.services.source_verification import (
    BLOCKED_FOR_USAGE,
    EDITOR_VERIFIED,
    InvalidVerificationTransition,
    QUARANTINED,
    VERIFICATION_STATUSES,
    VERIFIED_OFFICIAL,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/legal-sources", tags=["Legal Sources"])
case_source_router = APIRouter(prefix="/cases/{case_id}/sources", tags=["Case Sources"])
tracking_router = APIRouter(prefix="/official-source-tracking", tags=["Official Source Tracking"])
review_router = APIRouter(prefix="/source-review", tags=["Source Review"])

# P2.6 trust boundary: only editor/admin may mutate global legal sources.
# tenant_admin is a per-tenant role that cannot ingest/verify/quarantine/review
# global canonical sources — it operates only within its own tenant/case scope.
_EDITOR_ROLES = frozenset({"editor", "admin"})


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


def require_editor(ctx: SecurityContext = Depends(resolve_current_user)) -> SecurityContext:
    """Editor/admin boundary for global source mutation.

    In local dev/test mode auth is bypassed (matches the rest of the codebase).
    In production (jwt mode) a normal lawyer role is rejected with 403 — the
    boundary is NOT loosened to 'everyone is editor'.
    """
    if get_auth_mode() == "local":
        return ctx
    if ctx.role not in _EDITOR_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu işlem için editör yetkisi gerekir.",
        )
    return ctx


async def _audit(db, ctx, action, metadata):
    from app.db.auth_repository import AuthAuditRepository

    await AuthAuditRepository.write_event(
        db, ctx.tenant_id, ctx.actor_id, metadata.get("case_id", ""), action, "success", metadata
    )


async def _record_resp(db: AsyncSession, r) -> SourceRecordResponse:
    effective_status = await resolve_version_verification_status(
        db, r.id, r.current_version_id, r.verification_status,
    )
    return SourceRecordResponse(
        id=r.id, source_type=r.source_type, canonical_key=r.canonical_key, title=r.title,
        issuing_authority=r.issuing_authority, court=r.court, chamber=r.chamber,
        case_number=r.case_number, decision_number=r.decision_number,
        decision_date=r.decision_date, publication_date=r.publication_date,
        effective_date=r.effective_date, repeal_date=r.repeal_date,
        official_url=r.official_url, jurisdiction=r.jurisdiction,
        verification_status=effective_status, temporal_status=r.temporal_status,
        current_version_id=r.current_version_id, version=r.version,
        created_at=_iso(r.created_at) or "", updated_at=_iso(r.updated_at) or "",
    )


def _version_resp(v) -> SourceVersionResponse:
    return SourceVersionResponse(
        id=v.id, source_record_id=v.source_record_id, version_label=v.version_label,
        content_hash=v.content_hash, retrieval_method=v.retrieval_method,
        parser_version=v.parser_version, valid_from=v.valid_from, valid_to=v.valid_to,
        supersedes_version_id=v.supersedes_version_id, status=v.status,
        retrieved_at=_iso(v.retrieved_at) or "",
    )


def _paragraph_resp(p) -> SourceParagraphResponse:
    return SourceParagraphResponse(
        id=p.id, source_version_id=p.source_version_id, paragraph_index=p.paragraph_index,
        heading_path=p.heading_path, text=p.text, page=p.page,
        article_number=p.article_number, embedding_status=p.embedding_status,
    )


# ---------------------------------------------------------------------------
# Global source read (any authenticated user)
# ---------------------------------------------------------------------------
@router.get("", response_model=SourceRecordListResponse, operation_id="legal_source_list")
async def list_sources(
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
    source_type: str | None = Query(default=None),
    verification_status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> SourceRecordListResponse:
    records, total = await SourceRecordRepository.list(
        db, source_type=source_type, verification_status=verification_status,
        limit=limit, offset=offset,
    )
    return SourceRecordListResponse(
        items=[await _record_resp(db, r) for r in records], total=total, limit=limit, offset=offset,
        has_more=(offset + len(records)) < total,
    )


async def _load_source(db, source_id: str):
    record = await SourceRecordRepository.get(db, source_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return record


@router.get("/{source_id}", response_model=SourceRecordResponse, operation_id="legal_source_get")
async def get_source(
    source_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> SourceRecordResponse:
    return await _record_resp(db, await _load_source(db, source_id))


@router.get("/{source_id}/versions", response_model=list[SourceVersionResponse], operation_id="legal_source_versions")
async def list_versions(
    source_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[SourceVersionResponse]:
    await _load_source(db, source_id)
    versions = await SourceVersionRepository.list_for_record(db, source_id)
    return [_version_resp(v) for v in versions]


@router.get("/{source_id}/paragraphs", response_model=list[SourceParagraphResponse], operation_id="legal_source_paragraphs")
async def list_paragraphs(
    source_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
    version_id: str | None = Query(default=None),
) -> list[SourceParagraphResponse]:
    record = await _load_source(db, source_id)
    target_version = version_id or record.current_version_id
    if not target_version:
        return []
    version = await SourceVersionRepository.get(db, target_version)
    if version is None or version.source_record_id != record.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
    paragraphs = await SourceParagraphRepository.list_for_version(db, version.id)
    return [_paragraph_resp(p) for p in paragraphs]


@router.get("/{source_id}/relationships", response_model=list[SourceRelationshipResponse], operation_id="legal_source_relationships")
async def list_relationships(
    source_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[SourceRelationshipResponse]:
    await _load_source(db, source_id)
    rels = await SourceRelationshipRepository.list_for_record(db, source_id)
    return [
        SourceRelationshipResponse(
            id=r.id, source_record_id=r.source_record_id,
            related_source_record_id=r.related_source_record_id,
            relationship_type=r.relationship_type,
            verification_status=r.verification_status,
            created_at=_iso(r.created_at) or "",
        )
        for r in rels
    ]


# ---------------------------------------------------------------------------
# Editor/admin actions
# ---------------------------------------------------------------------------
@router.post("/ingest", response_model=SourceIngestResponse, status_code=201, operation_id="legal_source_ingest")
async def ingest(
    body: SourceIngestRequest,
    ctx: SecurityContext = Depends(require_editor),
    db: AsyncSession = Depends(get_session),
) -> SourceIngestResponse:
    from app.services.source_canonical_key import CanonicalKeyError

    metadata = body.model_dump()
    try:
        result = await ingest_editor_candidate(
            db, metadata=metadata, raw_text=body.raw_text, official_url=body.official_url,
        )
    except CanonicalKeyError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    await _audit(db, ctx, "legal_source_ingested",
                 {"resource": "source_record", "source_id": result.source_record_id,
                  "source_type": body.source_type, "outcome": result.outcome,
                  "verification_status": result.verification_status})
    await db.commit()
    return SourceIngestResponse(
        source_record_id=result.source_record_id, source_version_id=result.source_version_id,
        canonical_key=result.canonical_key, verification_status=result.verification_status,
        outcome=result.outcome,
    )


@router.post("/{source_id}/verify", response_model=SourceRecordResponse, operation_id="legal_source_verify")
async def verify_source(
    source_id: str,
    body: SourceVerifyRequest,
    ctx: SecurityContext = Depends(require_editor),
    db: AsyncSession = Depends(get_session),
) -> SourceRecordResponse:
    record = await _load_source(db, source_id)
    if body.target_status not in VERIFICATION_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid status")
    # verified_official requires version-scoped official-match evidence.
    # An editor click alone is insufficient; only the official_fetch path
    # produces the required evidence with exact content_hash match.
    if body.target_status == VERIFIED_OFFICIAL:
        evidence = await get_version_official_evidence(
            db, record.id, record.current_version_id or ""
        )
        if not evidence.valid:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"verified_official yalnız resmî fetch kanıtıyla verilebilir. {evidence.failure_reason}",
            )
    try:
        await SourceRecordRepository.transition_status(db, record, body.target_status)
    except InvalidVerificationTransition as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Geçersiz doğrulama geçişi: {e.current} -> {e.target}",
        )
    verifier_type = "editor" if body.target_status == EDITOR_VERIFIED else "editor"
    await SourceVerificationRepository.create(
        db, source_record_id=record.id, source_version_id=record.current_version_id,
        verification_method="editor_action", verifier_type=verifier_type,
        verifier_user_id=ctx.actor_id, result=body.target_status,
        evidence_url=body.evidence_url, notes=body.notes,
    )
    await _audit(db, ctx, "legal_source_verified",
                 {"resource": "source_record", "source_id": record.id,
                  "verification_status": record.verification_status})
    await db.commit()
    return await _record_resp(db, record)


@router.post("/{source_id}/quarantine", response_model=SourceRecordResponse, operation_id="legal_source_quarantine")
async def quarantine_source(
    source_id: str,
    ctx: SecurityContext = Depends(require_editor),
    db: AsyncSession = Depends(get_session),
) -> SourceRecordResponse:
    record = await _load_source(db, source_id)
    try:
        await SourceRecordRepository.transition_status(db, record, QUARANTINED)
    except InvalidVerificationTransition as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Geçersiz geçiş: {e.current} -> {e.target}",
        )
    await SourceVerificationRepository.create(
        db, source_record_id=record.id, verification_method="editor_action",
        verifier_type="editor", verifier_user_id=ctx.actor_id, result=QUARANTINED,
    )
    await _audit(db, ctx, "legal_source_quarantined",
                 {"resource": "source_record", "source_id": record.id,
                  "verification_status": record.verification_status})
    await db.commit()
    return await _record_resp(db, record)


@router.post("/{source_id}/relationships", response_model=SourceRelationshipResponse, status_code=201, operation_id="legal_source_add_relationship")
async def add_relationship(
    source_id: str,
    body: SourceRelationshipCreateRequest,
    ctx: SecurityContext = Depends(require_editor),
    db: AsyncSession = Depends(get_session),
) -> SourceRelationshipResponse:
    record = await _load_source(db, source_id)
    related = await SourceRecordRepository.get(db, body.related_source_record_id)
    if related is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Related source not found")
    try:
        rel = await SourceRelationshipRepository.create(
            db, source_record_id=record.id,
            related_source_record_id=body.related_source_record_id,
            relationship_type=body.relationship_type, evidence=body.evidence,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    await _audit(db, ctx, "legal_source_relationship_added",
                 {"resource": "source_relationship", "source_id": record.id,
                  "relationship_type": body.relationship_type})
    await db.commit()
    return SourceRelationshipResponse(
        id=rel.id, source_record_id=rel.source_record_id,
        related_source_record_id=rel.related_source_record_id,
        relationship_type=rel.relationship_type, verification_status=rel.verification_status,
        created_at=_iso(rel.created_at) or "",
    )


# ---------------------------------------------------------------------------
# Case source usage (tenant + case-owner scoped)
# ---------------------------------------------------------------------------
async def _load_owned_case(db: AsyncSession, ctx: SecurityContext, case_id: str) -> Case:
    case = await CaseRepository.get(db, ctx.tenant_id, case_id)
    if case is None or case.owner_user_id != ctx.actor_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return case


def _usage_resp(usage, record, version, paragraph, verif_status: str) -> SourceUsageResponse:
    return SourceUsageResponse(
        id=usage.id, case_id=usage.case_id, source_record_id=usage.source_record_id,
        source_version_id=usage.source_version_id, source_paragraph_id=usage.source_paragraph_id,
        usage_type=usage.usage_type, reason=usage.reason, relevance_score=usage.relevance_score,
        used_in_final_draft=usage.used_in_final_draft,
        source_title=record.title if record else "",
        source_type=record.source_type if record else "",
        court=record.court if record else "",
        decision_date=record.decision_date if record else "",
        case_number=record.case_number if record else "",
        decision_number=record.decision_number if record else "",
        verification_status=verif_status,
        temporal_status=record.temporal_status if record else "",
        official_url=record.official_url if record else "",
        selected_paragraph=(paragraph.text[:500] if paragraph else ""),
        created_at=_iso(usage.created_at) or "",
    )


@case_source_router.post("", response_model=SourceUsageResponse, status_code=201, operation_id="case_source_add")
async def add_case_source(
    case_id: str,
    body: SourceUsageCreateRequest,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> SourceUsageResponse:
    case = await _load_owned_case(db, ctx, case_id)
    record = await SourceRecordRepository.get(db, body.source_record_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    version = await SourceVersionRepository.get(db, body.source_version_id)
    if version is None or version.source_record_id != record.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Version does not belong to source")
    paragraph = None
    if body.source_paragraph_id:
        paragraph = await SourceParagraphRepository.get(db, body.source_paragraph_id)
        if paragraph is None or paragraph.source_version_id != version.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Paragraph does not belong to version")
    # A conflicting/quarantined source cannot be added as trusted usage by a user.
    if record.verification_status in BLOCKED_FOR_USAGE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu kaynak doğrulanmadığı için dosyaya eklenemez.",
        )
    usage = await SourceUsageRepository.create(
        db, tenant_id=ctx.tenant_id, case_id=case.id,
        source_record_id=record.id, source_version_id=version.id,
        source_paragraph_id=(paragraph.id if paragraph else None),
        usage_type=body.usage_type, reason=body.reason, selected_by=ctx.actor_id,
    )
    await _audit(db, ctx, "case_source_added",
                 {"resource": "source_usage", "usage_id": usage.id, "case_id": case.id,
                  "source_id": record.id, "verification_status": record.verification_status})
    await db.commit()
    verif_status = await resolve_version_verification_status(
        db, record.id, usage.source_version_id, record.verification_status)
    return _usage_resp(usage, record, version, paragraph, verif_status)


@case_source_router.get("", response_model=SourceUsageListResponse, operation_id="case_source_list")
async def list_case_sources(
    case_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> SourceUsageListResponse:
    case = await _load_owned_case(db, ctx, case_id)
    usages = await SourceUsageRepository.list_for_case(db, ctx.tenant_id, case.id)
    items: list[SourceUsageResponse] = []
    for usage in usages:
        record = await SourceRecordRepository.get(db, usage.source_record_id)
        paragraph = None
        if usage.source_paragraph_id:
            paragraph = await SourceParagraphRepository.get(db, usage.source_paragraph_id)
        verif_status = await resolve_version_verification_status(
            db, (record.id if record else ""), usage.source_version_id,
            (record.verification_status if record else "needs_review"))
        items.append(_usage_resp(usage, record, None, paragraph, verif_status))
    return SourceUsageListResponse(items=items)


@case_source_router.delete("/{usage_id}", status_code=204, operation_id="case_source_remove")
async def remove_case_source(
    case_id: str,
    usage_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> None:
    await _load_owned_case(db, ctx, case_id)
    usage = await SourceUsageRepository.get(db, ctx.tenant_id, case_id, usage_id)
    if usage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usage not found")
    await SourceUsageRepository.soft_delete(db, usage)
    await _audit(db, ctx, "case_source_removed",
                 {"resource": "source_usage", "usage_id": usage.id, "case_id": case_id})
    await db.commit()
    return None


# ---------------------------------------------------------------------------
# Official source tracking (read; any authenticated user)
# ---------------------------------------------------------------------------
@tracking_router.get("", response_model=OfficialTrackingResponse, operation_id="official_source_tracking")
async def official_tracking(
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=200),
) -> OfficialTrackingResponse:
    records, _ = await SourceRecordRepository.list(db, limit=limit, offset=0)
    items: list[OfficialTrackingItem] = []
    for r in records:
        if not r.official_url:
            continue
        usages = await SourceUsageRepository.list_for_source(db, r.id)
        affected_cases = {u.case_id for u in usages}
        versions = await SourceVersionRepository.list_for_record(db, r.id)
        new_version = len(versions) > 1 and (
            r.current_version_id == (versions[-1].id if versions else None)
        )
        fingerprint = ""
        if r.current_version_id:
            cur = await SourceVersionRepository.get(db, r.current_version_id)
            fingerprint = (cur.content_hash[:12] if cur else "")
        items.append(OfficialTrackingItem(
            source_id=r.id, title=r.title, source_type=r.source_type,
            official_url=r.official_url, last_checked_at=_iso(r.last_checked_at),
            last_successful_check_at=_iso(r.last_successful_check_at),
            content_fingerprint=fingerprint, temporal_status=r.temporal_status,
            verification_status=r.verification_status,
            new_version_detected=new_version,
            latest_version_id=(versions[-1].id if versions else None),
            change_summary=None,
            affected_case_count=len(affected_cases),
            affected_draft_count=0,  # drafting (P2.9) not implemented
            affected_draft_supported=False,
            requires_review=r.verification_status in ("needs_review", "conflicting"),
        ))
    return OfficialTrackingResponse(items=items)


# ---------------------------------------------------------------------------
# Editor/admin review queue
# ---------------------------------------------------------------------------
@review_router.get("", response_model=SourceReviewListResponse, operation_id="source_review_list")
async def review_list(
    ctx: SecurityContext = Depends(require_editor),
    db: AsyncSession = Depends(get_session),
) -> SourceReviewListResponse:
    records = await SourceRecordRepository.list_needs_review(db)
    return SourceReviewListResponse(items=[
        SourceReviewItem(
            source_id=r.id, title=r.title, source_type=r.source_type,
            verification_status=r.verification_status, canonical_key=r.canonical_key,
            updated_at=_iso(r.updated_at) or "",
        )
        for r in records
    ])


@review_router.get("/{source_id}", response_model=SourceRecordResponse, operation_id="source_review_get")
async def review_get(
    source_id: str,
    ctx: SecurityContext = Depends(require_editor),
    db: AsyncSession = Depends(get_session),
) -> SourceRecordResponse:
    return await _record_resp(db, await _load_source(db, source_id))


@review_router.post("/{source_id}/approve", response_model=SourceRecordResponse, operation_id="source_review_approve")
async def review_approve(
    source_id: str,
    ctx: SecurityContext = Depends(require_editor),
    db: AsyncSession = Depends(get_session),
) -> SourceRecordResponse:
    record = await _load_source(db, source_id)
    try:
        await SourceRecordRepository.transition_status(db, record, EDITOR_VERIFIED)
    except InvalidVerificationTransition as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{e.current} -> {e.target}")
    await SourceVerificationRepository.create(
        db, source_record_id=record.id, verification_method="editor_review",
        verifier_type="editor", verifier_user_id=ctx.actor_id, result=EDITOR_VERIFIED,
    )
    await _audit(db, ctx, "source_review_approved",
                 {"resource": "source_record", "source_id": record.id,
                  "verification_status": record.verification_status})
    await db.commit()
    return await _record_resp(db, record)


@review_router.post("/{source_id}/quarantine", response_model=SourceRecordResponse, operation_id="source_review_quarantine")
async def review_quarantine(
    source_id: str,
    ctx: SecurityContext = Depends(require_editor),
    db: AsyncSession = Depends(get_session),
) -> SourceRecordResponse:
    record = await _load_source(db, source_id)
    try:
        await SourceRecordRepository.transition_status(db, record, QUARANTINED)
    except InvalidVerificationTransition as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{e.current} -> {e.target}")
    await SourceVerificationRepository.create(
        db, source_record_id=record.id, verification_method="editor_review",
        verifier_type="editor", verifier_user_id=ctx.actor_id, result=QUARANTINED,
    )
    await _audit(db, ctx, "source_review_quarantined",
                 {"resource": "source_record", "source_id": record.id,
                  "verification_status": record.verification_status})
    await db.commit()
    return await _record_resp(db, record)


@review_router.post("/{source_id}/resolve-conflict", response_model=SourceRecordResponse, operation_id="source_review_resolve_conflict")
async def review_resolve_conflict(
    source_id: str,
    body: ResolveConflictRequest,
    ctx: SecurityContext = Depends(require_editor),
    db: AsyncSession = Depends(get_session),
) -> SourceRecordResponse:
    record = await _load_source(db, source_id)
    if record.verification_status != "conflicting":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kaynak çelişkili durumda değil.")
    target = body.target_status if body.target_status in VERIFICATION_STATUSES else EDITOR_VERIFIED
    try:
        await SourceRecordRepository.transition_status(db, record, target)
    except InvalidVerificationTransition as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"{e.current} -> {e.target}")
    await SourceVerificationRepository.create(
        db, source_record_id=record.id, verification_method="conflict_resolution",
        verifier_type="editor", verifier_user_id=ctx.actor_id, result=target, notes=body.notes,
    )
    await _audit(db, ctx, "source_conflict_resolved",
                 {"resource": "source_record", "source_id": record.id,
                  "verification_status": record.verification_status})
    await db.commit()
    return await _record_resp(db, record)
