"""P2.9A — Grounded draft persistence endpoints (case-scoped, member-authorized).

Persistence and provenance backbone only: no LLM generation, no export.
Every route resolves the case with member-based authorization (foreign
tenant/case → 404, non-members → 404, viewers cannot write). Draft paragraph
text and source quotes are never written to logs or audit metadata.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.auth_repository import CaseMemberRepository
from app.db.case_chat_repository import CaseRepository
from app.db.draft_repository import (
    DRAFT_STATUS_DELETED,
    DRAFT_STATUS_DRAFT,
    DRAFT_STATUS_FINALIZED,
    DRAFT_STATUS_REVIEWING,
    DRAFT_STATUS_SUPERSEDED,
    DraftDocumentRepository,
    DraftParagraphIssueLinkRepository,
    DraftParagraphRepository,
    DraftParagraphReviewEventRepository,
    DraftParagraphRevisionRepository,
    DraftParagraphSourceLinkRepository,
    EDITABLE_DRAFT_STATUSES,
    InvalidDraftTransitionError,
)
from app.db.models import (
    DRAFT_DOCUMENT_TYPES,
    DRAFT_PARAGRAPH_TYPES,
    DRAFT_PARAGRAPH_VERIFICATION_STATUSES,
    DRAFT_REVIEW_REASON_CODES,
    DRAFT_SOURCE_USAGE_TYPES,
    DraftDocument,
    DraftParagraph,
    LegalIssue,
    LegalIssueSourceLink,
    SourceParagraph,
    SourceRecord,
    SourceUsage,
    SourceVersion,
    new_uuid,
)
from app.db.session import get_session
from app.models.draft_models import (
    DraftCreateRequest,
    DraftDetailResponse,
    DraftFinalizeRequest,
    DraftFinalizeResponse,
    DraftGenerateRequest,
    DraftGenerateResponse,
    DraftListResponse,
    DraftParagraphAcceptRequest,
    DraftParagraphCreateRequest,
    DraftParagraphEditRequest,
    DraftParagraphIssueLinkRequest,
    DraftParagraphIssueLinkResponse,
    DraftParagraphRequestChangesRequest,
    DraftParagraphResponse,
    DraftParagraphRestoreRequest,
    DraftParagraphRevisionActionResponse,
    DraftParagraphRevisionResponse,
    DraftParagraphSourceLinkRequest,
    DraftParagraphSourceLinkResponse,
    DraftParagraphUpdateRequest,
    DraftPlanResponse,
    DraftReadinessResponse,
    DraftResponse,
    DraftReviewActionResponse,
    DraftReviewEventResponse,
    DraftUpdateRequest,
    DraftValidateResponse,
    SectionPlanEntry,
)
from app.services.auth_manager import require_case_read, require_case_write
from app.services.auth_service import SecurityContext, get_auth_mode
from app.services.draft_citation_renderer import render_citation
from app.services.draft_generation_input import (
    UnknownSelectionError,
    build_generation_input,
)
from app.services.draft_generation_provider import (
    DraftGenerationError,
    create_configured_draft_generation_provider,
    generation_input_fingerprint,
)
from app.services.draft_readiness import compute_draft_readiness
from app.services.draft_section_plan import SECTION_PLAN_BY_DRAFT_TYPE, build_section_plan
from app.services.source_ingestion_service import resolve_version_verification_status
from app.services.source_paragraphs import text_hash as source_text_hash
from app.services.source_verification import BLOCKED_FOR_USAGE, TRUSTED_STATUSES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cases/{case_id}/drafts", tags=["Drafts"])

# PATCH may only move a draft between these workflow statuses; finalized is
# reachable only through /finalize and superseded only through a superseding
# draft creation.
_PATCHABLE_STATUSES = frozenset({DRAFT_STATUS_DRAFT, DRAFT_STATUS_REVIEWING})


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


async def _authorized_case(db: AsyncSession, ctx: SecurityContext, case_id: str, *, write: bool):
    case = await CaseRepository.get(db, ctx.tenant_id, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if get_auth_mode() != "local" and ctx.role != "tenant_admin":
        membership = await CaseMemberRepository.get_active_membership(
            db, ctx.tenant_id, case_id, ctx.actor_id,
        )
        if membership is None or (write and membership.membership_role == "viewer"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return case


async def _load_draft(
    db: AsyncSession, ctx: SecurityContext, case_id: str, draft_id: str,
) -> DraftDocument:
    draft = await DraftDocumentRepository.get(db, ctx.tenant_id, case_id, draft_id)
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")
    return draft


def _require_editable(draft: DraftDocument) -> None:
    if draft.status not in EDITABLE_DRAFT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{draft.status}' durumundaki taslak düzenlenemez.",
        )


def _require_version(expected: int, current: int) -> None:
    if expected != current:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Version conflict")


async def _load_paragraph(
    db: AsyncSession, ctx: SecurityContext, case_id: str, draft_id: str, paragraph_id: str,
) -> DraftParagraph:
    paragraph = await DraftParagraphRepository.get(
        db, ctx.tenant_id, case_id, draft_id, paragraph_id,
    )
    if paragraph is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paragraph not found")
    return paragraph


async def _audit(db, ctx, case_id, action, metadata):
    # Safe metadata only: ids, counts, statuses, versions — never draft or
    # source text.
    from app.db.auth_repository import AuthAuditRepository

    await AuthAuditRepository.write_event(
        db, ctx.tenant_id, ctx.actor_id, case_id, action, "success", metadata
    )


def _draft_resp(draft: DraftDocument, paragraph_count: int = 0) -> DraftResponse:
    return DraftResponse(
        id=draft.id, case_id=draft.case_id, title=draft.title,
        draft_type=draft.draft_type, status=draft.status,
        supersedes_draft_id=draft.supersedes_draft_id,
        paragraph_count=paragraph_count, created_by=draft.created_by,
        created_at=_iso(draft.created_at) or "", updated_at=_iso(draft.updated_at) or "",
        finalized_at=_iso(draft.finalized_at), version=draft.version,
    )


def _issue_link_resp(link) -> DraftParagraphIssueLinkResponse:
    return DraftParagraphIssueLinkResponse(
        id=link.id, draft_paragraph_id=link.draft_paragraph_id,
        legal_issue_id=link.legal_issue_id, relation_type=link.relation_type,
        created_at=_iso(link.created_at) or "", version=link.version,
    )


def _source_link_resp(link, effective_trust: str = "") -> DraftParagraphSourceLinkResponse:
    return DraftParagraphSourceLinkResponse(
        id=link.id, draft_paragraph_id=link.draft_paragraph_id,
        source_record_id=link.source_record_id,
        source_version_id=link.source_version_id,
        source_paragraph_id=link.source_paragraph_id,
        usage_type=link.usage_type, quote_hash=link.quote_hash,
        verification_status=link.verification_status,
        effective_trust=effective_trust,
        created_at=_iso(link.created_at) or "", version=link.version,
    )


def _paragraph_resp(paragraph: DraftParagraph, issue_links, source_links) -> DraftParagraphResponse:
    return DraftParagraphResponse(
        id=paragraph.id, draft_document_id=paragraph.draft_document_id,
        paragraph_order=paragraph.paragraph_order,
        paragraph_type=paragraph.paragraph_type, text=paragraph.text,
        verification_status=paragraph.verification_status,
        generated_by=paragraph.generated_by, model_name=paragraph.model_name,
        issue_links=[_issue_link_resp(link) for link in issue_links],
        source_links=[_source_link_resp(link) for link in source_links],
        created_at=_iso(paragraph.created_at) or "",
        updated_at=_iso(paragraph.updated_at) or "", version=paragraph.version,
    )


def _revision_resp(revision, *, current: bool) -> DraftParagraphRevisionResponse:
    # Revision text may be returned to the user; it must never be logged or
    # placed in audit metadata.
    return DraftParagraphRevisionResponse(
        id=revision.id, draft_paragraph_id=revision.draft_paragraph_id,
        revision_number=revision.revision_number, change_type=revision.change_type,
        created_by=revision.created_by, created_at=_iso(revision.created_at) or "",
        text_hash=revision.text_hash, current_revision=current, text=revision.text,
    )


def _review_event_resp(event) -> DraftReviewEventResponse:
    return DraftReviewEventResponse(
        id=event.id, draft_paragraph_id=event.draft_paragraph_id,
        paragraph_revision_id=event.paragraph_revision_id, decision=event.decision,
        reason_code=event.reason_code, reviewer_user_id=event.reviewer_user_id,
        paragraph_version=event.paragraph_version,
        created_at=_iso(event.created_at) or "",
    )


async def _mark_source_links_needs_review(
    db: AsyncSession, ctx: SecurityContext, paragraph: DraftParagraph,
) -> int:
    """Paragraph text changed: grounding must be re-verified by the user."""
    links = await DraftParagraphSourceLinkRepository.list_for_paragraphs(
        db, ctx.tenant_id, [paragraph.id])
    marked = 0
    for link in links:
        if link.verification_status != "needs_review":
            link.verification_status = "needs_review"
            link.version += 1
            marked += 1
    return marked


async def _append_paragraph_revision(
    db: AsyncSession, ctx: SecurityContext, draft: DraftDocument,
    paragraph: DraftParagraph, *, new_text: str, change_type: str,
):
    """Bootstrap-if-needed + append one immutable revision (same transaction)."""
    await DraftParagraphRevisionRepository.ensure_bootstrap(db, paragraph)
    latest = await DraftParagraphRevisionRepository.latest_for_paragraph(
        db, ctx.tenant_id, paragraph.id)
    return await DraftParagraphRevisionRepository.create(
        db, tenant_id=ctx.tenant_id, case_id=paragraph.case_id,
        draft_document_id=draft.id, draft_paragraph_id=paragraph.id,
        revision_number=(latest.revision_number + 1) if latest else 1,
        base_paragraph_version=paragraph.version,
        text=new_text, change_type=change_type, created_by=ctx.actor_id,
    )


# ---------------------------------------------------------------------------
# Draft CRUD
# ---------------------------------------------------------------------------
@router.post("", response_model=DraftResponse, status_code=201, operation_id="draft_create")
async def create_draft(
    case_id: str,
    body: DraftCreateRequest,
    ctx: SecurityContext = Depends(require_case_write),
    db: AsyncSession = Depends(get_session),
) -> DraftResponse:
    await _authorized_case(db, ctx, case_id, write=True)
    if body.draft_type not in DRAFT_DOCUMENT_TYPES:
        raise HTTPException(status_code=422, detail="Invalid draft type")
    superseded = None
    if body.supersedes_draft_id:
        superseded = await _load_draft(db, ctx, case_id, body.supersedes_draft_id)
        if superseded.status != DRAFT_STATUS_FINALIZED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Yalnızca finalize edilmiş bir taslak yerine yeni taslak açılabilir.",
            )
    draft = await DraftDocumentRepository.create(
        db, tenant_id=ctx.tenant_id, case_id=case_id, title=body.title,
        draft_type=body.draft_type, created_by=ctx.actor_id,
        supersedes_draft_id=body.supersedes_draft_id,
    )
    if superseded is not None:
        try:
            DraftDocumentRepository.transition(superseded, DRAFT_STATUS_SUPERSEDED)
        except InvalidDraftTransitionError:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Taslak devralınamadı.")
        superseded.version += 1
    await _audit(db, ctx, case_id, "draft_created",
                 {"resource": "draft", "draft_id": draft.id,
                  "draft_type": draft.draft_type, "status": draft.status,
                  "supersedes_draft_id": draft.supersedes_draft_id or ""})
    await db.commit()
    return _draft_resp(draft)


@router.get("", response_model=DraftListResponse, operation_id="draft_list")
async def list_drafts(
    case_id: str,
    ctx: SecurityContext = Depends(require_case_read),
    db: AsyncSession = Depends(get_session),
) -> DraftListResponse:
    await _authorized_case(db, ctx, case_id, write=False)
    drafts = await DraftDocumentRepository.list_for_case(db, ctx.tenant_id, case_id)
    items = []
    for draft in drafts:
        paragraphs = await DraftParagraphRepository.list_for_draft(db, ctx.tenant_id, draft.id)
        items.append(_draft_resp(draft, paragraph_count=len(paragraphs)))
    return DraftListResponse(items=items, total=len(items))


@router.get("/{draft_id}", response_model=DraftDetailResponse, operation_id="draft_get")
async def get_draft(
    case_id: str,
    draft_id: str,
    ctx: SecurityContext = Depends(require_case_read),
    db: AsyncSession = Depends(get_session),
) -> DraftDetailResponse:
    await _authorized_case(db, ctx, case_id, write=False)
    draft = await _load_draft(db, ctx, case_id, draft_id)
    paragraphs = await DraftParagraphRepository.list_for_draft(db, ctx.tenant_id, draft.id)
    paragraph_ids = [p.id for p in paragraphs]
    issue_links = await DraftParagraphIssueLinkRepository.list_for_paragraphs(
        db, ctx.tenant_id, paragraph_ids)
    source_links = await DraftParagraphSourceLinkRepository.list_for_paragraphs(
        db, ctx.tenant_id, paragraph_ids)
    issues_by_paragraph: dict[str, list] = {}
    for link in issue_links:
        issues_by_paragraph.setdefault(link.draft_paragraph_id, []).append(link)
    sources_by_paragraph: dict[str, list] = {}
    for link in source_links:
        sources_by_paragraph.setdefault(link.draft_paragraph_id, []).append(link)
    base = _draft_resp(draft, paragraph_count=len(paragraphs))
    return DraftDetailResponse(
        **base.model_dump(),
        paragraphs=[
            _paragraph_resp(
                p, issues_by_paragraph.get(p.id, []), sources_by_paragraph.get(p.id, []))
            for p in paragraphs
        ],
    )


@router.patch("/{draft_id}", response_model=DraftResponse, operation_id="draft_update")
async def update_draft(
    case_id: str,
    draft_id: str,
    body: DraftUpdateRequest,
    ctx: SecurityContext = Depends(require_case_write),
    db: AsyncSession = Depends(get_session),
) -> DraftResponse:
    await _authorized_case(db, ctx, case_id, write=True)
    draft = await _load_draft(db, ctx, case_id, draft_id)
    _require_editable(draft)
    _require_version(body.version, draft.version)
    if body.status is not None:
        if body.status not in _PATCHABLE_STATUSES:
            raise HTTPException(status_code=422, detail="Invalid draft status")
        if body.status != draft.status:
            try:
                DraftDocumentRepository.transition(draft, body.status)
            except InvalidDraftTransitionError:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invalid status transition")
    if body.title is not None:
        draft.title = body.title
    draft.version += 1
    await _audit(db, ctx, case_id, "draft_updated",
                 {"resource": "draft", "draft_id": draft.id,
                  "status": draft.status, "version": draft.version})
    await db.commit()
    paragraphs = await DraftParagraphRepository.list_for_draft(db, ctx.tenant_id, draft.id)
    return _draft_resp(draft, paragraph_count=len(paragraphs))


@router.delete("/{draft_id}", status_code=204, operation_id="draft_delete")
async def delete_draft(
    case_id: str,
    draft_id: str,
    ctx: SecurityContext = Depends(require_case_write),
    db: AsyncSession = Depends(get_session),
) -> None:
    await _authorized_case(db, ctx, case_id, write=True)
    draft = await _load_draft(db, ctx, case_id, draft_id)
    try:
        DraftDocumentRepository.transition(draft, DRAFT_STATUS_DELETED)
    except InvalidDraftTransitionError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{draft.status}' durumundaki taslak silinemez.",
        )
    draft.version += 1
    await _audit(db, ctx, case_id, "draft_deleted",
                 {"resource": "draft", "draft_id": draft.id, "status": draft.status})
    await db.commit()
    return None


# ---------------------------------------------------------------------------
# Paragraphs
# ---------------------------------------------------------------------------
@router.post("/{draft_id}/paragraphs", response_model=DraftParagraphResponse,
             status_code=201, operation_id="draft_paragraph_create")
async def create_paragraph(
    case_id: str,
    draft_id: str,
    body: DraftParagraphCreateRequest,
    ctx: SecurityContext = Depends(require_case_write),
    db: AsyncSession = Depends(get_session),
) -> DraftParagraphResponse:
    await _authorized_case(db, ctx, case_id, write=True)
    draft = await _load_draft(db, ctx, case_id, draft_id)
    _require_editable(draft)
    if body.paragraph_type not in DRAFT_PARAGRAPH_TYPES:
        raise HTTPException(status_code=422, detail="Invalid paragraph type")
    if await DraftParagraphRepository.active_order_exists(db, draft.id, body.paragraph_order):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu sırada aktif bir paragraf zaten var.",
        )
    paragraph = await DraftParagraphRepository.create(
        db, tenant_id=ctx.tenant_id, case_id=case_id, draft_document_id=draft.id,
        paragraph_order=body.paragraph_order, paragraph_type=body.paragraph_type,
        text=body.text, generated_by="user", model_name="",
    )
    await DraftParagraphRevisionRepository.create(
        db, tenant_id=ctx.tenant_id, case_id=case_id, draft_document_id=draft.id,
        draft_paragraph_id=paragraph.id, revision_number=1,
        base_paragraph_version=paragraph.version, text=body.text,
        change_type="manual_creation", created_by=ctx.actor_id,
    )
    draft.version += 1
    await _audit(db, ctx, case_id, "draft_paragraph_added",
                 {"resource": "draft_paragraph", "draft_id": draft.id,
                  "paragraph_id": paragraph.id,
                  "paragraph_order": paragraph.paragraph_order,
                  "paragraph_type": paragraph.paragraph_type})
    await db.commit()
    return _paragraph_resp(paragraph, [], [])


@router.patch("/{draft_id}/paragraphs/{paragraph_id}", response_model=DraftParagraphResponse,
              operation_id="draft_paragraph_update")
async def update_paragraph(
    case_id: str,
    draft_id: str,
    paragraph_id: str,
    body: DraftParagraphUpdateRequest,
    ctx: SecurityContext = Depends(require_case_write),
    db: AsyncSession = Depends(get_session),
) -> DraftParagraphResponse:
    await _authorized_case(db, ctx, case_id, write=True)
    draft = await _load_draft(db, ctx, case_id, draft_id)
    _require_editable(draft)
    paragraph = await _load_paragraph(db, ctx, case_id, draft.id, paragraph_id)
    _require_version(body.version, paragraph.version)
    if body.paragraph_type is not None and body.paragraph_type not in DRAFT_PARAGRAPH_TYPES:
        raise HTTPException(status_code=422, detail="Invalid paragraph type")
    if body.verification_status is not None:
        if body.verification_status not in DRAFT_PARAGRAPH_VERIFICATION_STATUSES:
            raise HTTPException(status_code=422, detail="Invalid paragraph verification status")
        if body.verification_status == "accepted":
            # P2.9C1: accepted is only reachable through the review accept
            # endpoint (revision + source verification barriers).
            raise HTTPException(
                status_code=422,
                detail="Paragraph acceptance requires the review accept endpoint",
            )
    if body.paragraph_order is not None and body.paragraph_order != paragraph.paragraph_order:
        if await DraftParagraphRepository.active_order_exists(db, draft.id, body.paragraph_order):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bu sırada aktif bir paragraf zaten var.",
            )
        paragraph.paragraph_order = body.paragraph_order
    if body.paragraph_type is not None:
        paragraph.paragraph_type = body.paragraph_type
    marked_links = 0
    if body.text is not None and body.text != paragraph.text:
        # Manual edit: append an immutable revision and force re-review.
        await _append_paragraph_revision(
            db, ctx, draft, paragraph, new_text=body.text, change_type="user_edit")
        paragraph.text = body.text
        marked_links = await _mark_source_links_needs_review(db, ctx, paragraph)
        if body.verification_status is None:
            paragraph.verification_status = "pending_review"
        draft.version += 1
    if body.verification_status is not None:
        paragraph.verification_status = body.verification_status
    paragraph.version += 1
    await _audit(db, ctx, case_id, "draft_paragraph_updated",
                 {"resource": "draft_paragraph", "draft_id": draft.id,
                  "paragraph_id": paragraph.id,
                  "paragraph_order": paragraph.paragraph_order,
                  "verification_status": paragraph.verification_status,
                  "version": paragraph.version})
    await db.commit()
    issue_links = await DraftParagraphIssueLinkRepository.list_for_paragraphs(
        db, ctx.tenant_id, [paragraph.id])
    source_links = await DraftParagraphSourceLinkRepository.list_for_paragraphs(
        db, ctx.tenant_id, [paragraph.id])
    return _paragraph_resp(paragraph, issue_links, source_links)


@router.delete("/{draft_id}/paragraphs/{paragraph_id}", status_code=204,
               operation_id="draft_paragraph_delete")
async def delete_paragraph(
    case_id: str,
    draft_id: str,
    paragraph_id: str,
    ctx: SecurityContext = Depends(require_case_write),
    db: AsyncSession = Depends(get_session),
) -> None:
    await _authorized_case(db, ctx, case_id, write=True)
    draft = await _load_draft(db, ctx, case_id, draft_id)
    _require_editable(draft)
    paragraph = await _load_paragraph(db, ctx, case_id, draft.id, paragraph_id)
    issue_links = await DraftParagraphIssueLinkRepository.list_for_paragraphs(
        db, ctx.tenant_id, [paragraph.id])
    source_links = await DraftParagraphSourceLinkRepository.list_for_paragraphs(
        db, ctx.tenant_id, [paragraph.id])
    DraftParagraphRepository.soft_delete(paragraph)
    for link in issue_links + source_links:
        link.deleted_at = paragraph.deleted_at
    draft.version += 1
    await _audit(db, ctx, case_id, "draft_paragraph_deleted",
                 {"resource": "draft_paragraph", "draft_id": draft.id,
                  "paragraph_id": paragraph.id,
                  "issue_link_count": len(issue_links),
                  "source_link_count": len(source_links)})
    await db.commit()
    return None


# ---------------------------------------------------------------------------
# Issue links (issue_drafted_in_paragraph — owned by P2.9)
# ---------------------------------------------------------------------------
@router.post("/{draft_id}/paragraphs/{paragraph_id}/issues",
             response_model=DraftParagraphIssueLinkResponse, status_code=201,
             operation_id="draft_paragraph_issue_link_create")
async def create_paragraph_issue_link(
    case_id: str,
    draft_id: str,
    paragraph_id: str,
    body: DraftParagraphIssueLinkRequest,
    ctx: SecurityContext = Depends(require_case_write),
    db: AsyncSession = Depends(get_session),
) -> DraftParagraphIssueLinkResponse:
    await _authorized_case(db, ctx, case_id, write=True)
    draft = await _load_draft(db, ctx, case_id, draft_id)
    _require_editable(draft)
    paragraph = await _load_paragraph(db, ctx, case_id, draft.id, paragraph_id)
    issue = (await db.execute(select(LegalIssue).where(
        LegalIssue.id == body.legal_issue_id,
        LegalIssue.tenant_id == ctx.tenant_id,
        LegalIssue.case_id == case_id,
        LegalIssue.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if issue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Legal issue not found")
    if await DraftParagraphIssueLinkRepository.active_exists(
            db, ctx.tenant_id, case_id, paragraph.id, issue.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu paragraf bu hukuki meseleye zaten bağlı.",
        )
    link = await DraftParagraphIssueLinkRepository.create(
        db, tenant_id=ctx.tenant_id, case_id=case_id,
        draft_paragraph_id=paragraph.id, legal_issue_id=issue.id,
        created_by=ctx.actor_id,
    )
    await _audit(db, ctx, case_id, "draft_paragraph_issue_linked",
                 {"resource": "draft_paragraph_issue_link", "draft_id": draft.id,
                  "paragraph_id": paragraph.id, "issue_id": issue.id,
                  "relation_type": link.relation_type})
    await db.commit()
    return _issue_link_resp(link)


@router.delete("/{draft_id}/paragraphs/{paragraph_id}/issues/{link_id}", status_code=204,
               operation_id="draft_paragraph_issue_link_delete")
async def delete_paragraph_issue_link(
    case_id: str,
    draft_id: str,
    paragraph_id: str,
    link_id: str,
    ctx: SecurityContext = Depends(require_case_write),
    db: AsyncSession = Depends(get_session),
) -> None:
    await _authorized_case(db, ctx, case_id, write=True)
    draft = await _load_draft(db, ctx, case_id, draft_id)
    _require_editable(draft)
    paragraph = await _load_paragraph(db, ctx, case_id, draft.id, paragraph_id)
    link = await DraftParagraphIssueLinkRepository.get(
        db, ctx.tenant_id, case_id, paragraph.id, link_id)
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue link not found")
    from app.db.draft_repository import _now

    link.deleted_at = _now()
    await _audit(db, ctx, case_id, "draft_paragraph_issue_unlinked",
                 {"resource": "draft_paragraph_issue_link", "draft_id": draft.id,
                  "paragraph_id": paragraph.id, "issue_id": link.legal_issue_id})
    await db.commit()
    return None


# ---------------------------------------------------------------------------
# Source links (exact SourceRecord + SourceVersion + SourceParagraph)
# ---------------------------------------------------------------------------
async def _resolve_exact_source(
    db: AsyncSession, source_record_id: str, source_version_id: str, source_paragraph_id: str,
):
    """Load the exact provenance chain; 404 when any part does not match."""
    row = (await db.execute(
        select(SourceRecord, SourceVersion, SourceParagraph)
        .join(SourceVersion, SourceVersion.source_record_id == SourceRecord.id)
        .join(SourceParagraph, SourceParagraph.source_version_id == SourceVersion.id)
        .where(
            SourceRecord.id == source_record_id,
            SourceVersion.id == source_version_id,
            SourceParagraph.id == source_paragraph_id,
            SourceRecord.current_version_id == source_version_id,
            SourceRecord.deleted_at.is_(None),
        )
    )).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Source provenance not found")
    return row


async def _require_draft_trust_eligible(db: AsyncSession, record, version) -> str:
    """Only verified, trust-eligible sources may be cited in a draft."""
    if record.verification_status in BLOCKED_FOR_USAGE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu kaynak doğrulanmadığı için taslakta kullanılamaz.",
        )
    trust = await resolve_version_verification_status(
        db, record.id, version.id, record.verification_status)
    if trust not in TRUSTED_STATUSES:
        raise HTTPException(
            status_code=422,
            detail="Source is not trust-eligible for drafting",
        )
    return trust


def _require_exact_quote_hash(provided: str, source_paragraph) -> None:
    expected = source_paragraph.text_hash or source_text_hash(source_paragraph.text or "")
    recomputed = source_text_hash(source_paragraph.text or "")
    if provided != expected or provided != recomputed:
        raise HTTPException(
            status_code=422,
            detail="Quote hash does not match the source paragraph",
        )


@router.post("/{draft_id}/paragraphs/{paragraph_id}/sources",
             response_model=DraftParagraphSourceLinkResponse, status_code=201,
             operation_id="draft_paragraph_source_link_create")
async def create_paragraph_source_link(
    case_id: str,
    draft_id: str,
    paragraph_id: str,
    body: DraftParagraphSourceLinkRequest,
    ctx: SecurityContext = Depends(require_case_write),
    db: AsyncSession = Depends(get_session),
) -> DraftParagraphSourceLinkResponse:
    await _authorized_case(db, ctx, case_id, write=True)
    draft = await _load_draft(db, ctx, case_id, draft_id)
    _require_editable(draft)
    paragraph = await _load_paragraph(db, ctx, case_id, draft.id, paragraph_id)
    if body.usage_type not in DRAFT_SOURCE_USAGE_TYPES:
        raise HTTPException(status_code=422, detail="Invalid source usage type")
    record, version, source_paragraph = await _resolve_exact_source(
        db, body.source_record_id, body.source_version_id, body.source_paragraph_id)
    trust = await _require_draft_trust_eligible(db, record, version)
    _require_exact_quote_hash(body.quote_hash, source_paragraph)
    if await DraftParagraphSourceLinkRepository.active_exists(
            db, ctx.tenant_id, case_id, paragraph.id,
            record.id, version.id, source_paragraph.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu paragraf bu kaynak paragrafına zaten bağlı.",
        )
    link = await DraftParagraphSourceLinkRepository.create(
        db, tenant_id=ctx.tenant_id, case_id=case_id,
        draft_paragraph_id=paragraph.id,
        source_record_id=record.id, source_version_id=version.id,
        source_paragraph_id=source_paragraph.id,
        usage_type=body.usage_type, quote_hash=body.quote_hash,
        created_by=ctx.actor_id, verification_status="verified",
    )
    await _audit(db, ctx, case_id, "draft_paragraph_source_linked",
                 {"resource": "draft_paragraph_source_link", "draft_id": draft.id,
                  "paragraph_id": paragraph.id,
                  "source_record_id": record.id, "source_version_id": version.id,
                  "source_paragraph_id": source_paragraph.id,
                  "usage_type": link.usage_type})
    await db.commit()
    return _source_link_resp(link, effective_trust=trust)


@router.delete("/{draft_id}/paragraphs/{paragraph_id}/sources/{link_id}", status_code=204,
               operation_id="draft_paragraph_source_link_delete")
async def delete_paragraph_source_link(
    case_id: str,
    draft_id: str,
    paragraph_id: str,
    link_id: str,
    ctx: SecurityContext = Depends(require_case_write),
    db: AsyncSession = Depends(get_session),
) -> None:
    await _authorized_case(db, ctx, case_id, write=True)
    draft = await _load_draft(db, ctx, case_id, draft_id)
    _require_editable(draft)
    paragraph = await _load_paragraph(db, ctx, case_id, draft.id, paragraph_id)
    link = await DraftParagraphSourceLinkRepository.get(
        db, ctx.tenant_id, case_id, paragraph.id, link_id)
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source link not found")
    from app.db.draft_repository import _now

    link.deleted_at = _now()
    await _audit(db, ctx, case_id, "draft_paragraph_source_unlinked",
                 {"resource": "draft_paragraph_source_link", "draft_id": draft.id,
                  "paragraph_id": paragraph.id, "source_record_id": link.source_record_id})
    await db.commit()
    return None


# ---------------------------------------------------------------------------
# Finalize (atomic: status + used_in_final_draft + audit)
# ---------------------------------------------------------------------------
@router.post("/{draft_id}/finalize", response_model=DraftFinalizeResponse,
             operation_id="draft_finalize")
async def finalize_draft(
    case_id: str,
    draft_id: str,
    body: DraftFinalizeRequest,
    ctx: SecurityContext = Depends(require_case_write),
    db: AsyncSession = Depends(get_session),
) -> DraftFinalizeResponse:
    await _authorized_case(db, ctx, case_id, write=True)
    draft = await _load_draft(db, ctx, case_id, draft_id)
    _require_editable(draft)
    _require_version(body.version, draft.version)

    paragraphs = await DraftParagraphRepository.list_for_draft(db, ctx.tenant_id, draft.id)
    if not paragraphs:
        raise HTTPException(status_code=422, detail="Draft has no paragraphs")
    orders = sorted(p.paragraph_order for p in paragraphs)
    if orders != list(range(1, len(paragraphs) + 1)):
        raise HTTPException(
            status_code=422,
            detail="Paragraph order must be unique and contiguous starting at 1",
        )
    not_accepted = [p.id for p in paragraphs if p.verification_status != "accepted"]
    if not_accepted:
        raise HTTPException(
            status_code=422,
            detail="All paragraphs must be accepted before finalize",
        )

    # P2.9C1 additive barriers: acceptance must cover the CURRENT text of the
    # latest immutable revision; an accepted-then-edited paragraph blocks
    # finalize until it is re-reviewed.
    for entry in paragraphs:
        latest_revision = await DraftParagraphRevisionRepository.latest_for_paragraph(
            db, ctx.tenant_id, entry.id)
        if latest_revision is None:
            raise HTTPException(
                status_code=422,
                detail="Draft has paragraphs without revision history",
            )
        if latest_revision.text_hash != source_text_hash(entry.text or ""):
            raise HTTPException(
                status_code=422,
                detail="Paragraph was modified after its latest revision",
            )
        latest_event = await DraftParagraphReviewEventRepository.latest_for_paragraph(
            db, ctx.tenant_id, entry.id)
        if (latest_event is None or latest_event.decision != "accepted"
                or latest_event.paragraph_revision_id != latest_revision.id):
            raise HTTPException(
                status_code=422,
                detail="Paragraph acceptance does not cover its latest revision",
            )

    paragraph_ids = [p.id for p in paragraphs]
    issue_links = await DraftParagraphIssueLinkRepository.list_for_paragraphs(
        db, ctx.tenant_id, paragraph_ids)
    for link in issue_links:
        issue = (await db.execute(select(LegalIssue).where(
            LegalIssue.id == link.legal_issue_id,
            LegalIssue.tenant_id == ctx.tenant_id,
            LegalIssue.case_id == case_id,
            LegalIssue.deleted_at.is_(None),
        ))).scalar_one_or_none()
        if issue is None:
            raise HTTPException(
                status_code=422,
                detail="A linked legal issue is no longer available in this case",
            )

    source_links = await DraftParagraphSourceLinkRepository.list_for_paragraphs(
        db, ctx.tenant_id, paragraph_ids)
    for link in source_links:
        if link.verification_status != "verified":
            raise HTTPException(
                status_code=422,
                detail="Draft has unresolved source provenance",
            )
        record, version, source_paragraph = await _resolve_exact_source(
            db, link.source_record_id, link.source_version_id, link.source_paragraph_id)
        await _require_draft_trust_eligible(db, record, version)
        _require_exact_quote_hash(link.quote_hash, source_paragraph)

    try:
        DraftDocumentRepository.transition(draft, DRAFT_STATUS_FINALIZED)
        draft.version += 1

        marked_usage_count = 0
        if source_links:
            usages = list((await db.execute(select(SourceUsage).where(
                SourceUsage.tenant_id == ctx.tenant_id,
                SourceUsage.case_id == case_id,
                SourceUsage.deleted_at.is_(None),
            ))).scalars().all())
            link_keys = {
                (link.source_record_id, link.source_version_id, link.source_paragraph_id)
                for link in source_links
            }
            for usage in usages:
                used = any(
                    usage.source_record_id == record_id
                    and usage.source_version_id == version_id
                    and (not usage.source_paragraph_id
                         or usage.source_paragraph_id == paragraph_ref)
                    for record_id, version_id, paragraph_ref in link_keys
                )
                if used and not usage.used_in_final_draft:
                    usage.used_in_final_draft = True
                    marked_usage_count += 1

        await _audit(db, ctx, case_id, "draft_finalized",
                     {"resource": "draft", "draft_id": draft.id,
                      "status": draft.status, "version": draft.version,
                      "paragraph_count": len(paragraphs),
                      "issue_link_count": len(issue_links),
                      "source_link_count": len(source_links),
                      "marked_source_usage_count": marked_usage_count})
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except InvalidDraftTransitionError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Draft cannot be finalized from its current status")
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "draft_finalized draft_id=%s case_id=%s paragraph_count=%d "
        "source_link_count=%d marked_source_usage_count=%d",
        draft.id, case_id, len(paragraphs), len(source_links), marked_usage_count,
    )
    return DraftFinalizeResponse(
        id=draft.id, case_id=case_id, status=draft.status,
        finalized_at=_iso(draft.finalized_at), version=draft.version,
        paragraph_count=len(paragraphs),
        issue_link_count=len(issue_links),
        source_link_count=len(source_links),
        marked_source_usage_count=marked_usage_count,
    )


# ---------------------------------------------------------------------------
# P2.9B — Deterministic readiness + section plan (no LLM, no persistence)
# ---------------------------------------------------------------------------
@router.post("/{draft_id}/readiness", response_model=DraftReadinessResponse,
             operation_id="draft_readiness_check")
async def draft_readiness_check(
    case_id: str,
    draft_id: str,
    ctx: SecurityContext = Depends(require_case_read),
    db: AsyncSession = Depends(get_session),
) -> DraftReadinessResponse:
    await _authorized_case(db, ctx, case_id, write=False)
    draft = await _load_draft(db, ctx, case_id, draft_id)
    result = await compute_draft_readiness(db, ctx.tenant_id, case_id, draft)
    return DraftReadinessResponse(
        status=result.status,
        blocked_reasons=result.blocked_reasons,
        warnings=result.warnings,
        metrics=result.metrics,
    )


@router.post("/{draft_id}/plan", response_model=DraftPlanResponse,
             operation_id="draft_section_plan")
async def draft_section_plan(
    case_id: str,
    draft_id: str,
    ctx: SecurityContext = Depends(require_case_read),
    db: AsyncSession = Depends(get_session),
) -> DraftPlanResponse:
    await _authorized_case(db, ctx, case_id, write=False)
    draft = await _load_draft(db, ctx, case_id, draft_id)
    result = await compute_draft_readiness(db, ctx.tenant_id, case_id, draft)
    if result.status == "blocked":
        raise HTTPException(status_code=422, detail="readiness_blocked")
    sections = build_section_plan(draft.draft_type, result.active_issue_ids)
    return DraftPlanResponse(
        draft_id=draft.id,
        draft_type=draft.draft_type,
        draft_version=draft.version,
        readiness_status=result.status,
        sections=[SectionPlanEntry(**section) for section in sections],
        warnings=result.warnings,
    )


# ---------------------------------------------------------------------------
# P2.9B — Grounded generation (single atomic transaction)
# ---------------------------------------------------------------------------
def _draft_generation_provider():
    """Route-local factory; tests monkeypatch this to inject a fake provider."""
    return create_configured_draft_generation_provider()


_GENERATION_UNAVAILABLE_CODES = frozenset({
    "draft_generation_unavailable", "draft_generation_disabled",
    "deepseek_api_key_missing",
})


def _safe_provider_metrics(metrics: dict) -> dict:
    allowed = (
        "provider", "model", "status", "safe_error_code", "logical_call_count",
        "request_attempt_count", "latency_ms", "prompt_tokens",
        "completion_tokens", "total_tokens", "reasoning_tokens",
        "finish_reasons", "section_count", "source_count",
    )
    return {key: metrics[key] for key in allowed if key in metrics}


@router.post("/{draft_id}/generate", response_model=DraftGenerateResponse,
             operation_id="draft_generate")
async def generate_draft(
    case_id: str,
    draft_id: str,
    body: DraftGenerateRequest,
    ctx: SecurityContext = Depends(require_case_write),
    db: AsyncSession = Depends(get_session),
) -> DraftGenerateResponse:
    await _authorized_case(db, ctx, case_id, write=True)
    draft = await _load_draft(db, ctx, case_id, draft_id)
    if draft.status not in EDITABLE_DRAFT_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="draft_not_editable")
    if body.version != draft.version:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="draft_version_conflict")
    existing = await DraftParagraphRepository.list_for_draft(db, ctx.tenant_id, draft.id)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="draft_not_empty")

    readiness = await compute_draft_readiness(db, ctx.tenant_id, case_id, draft)
    if readiness.status == "blocked":
        raise HTTPException(status_code=422, detail="readiness_blocked")

    sections = build_section_plan(draft.draft_type, readiness.active_issue_ids)
    try:
        payload, provenance_context = await build_generation_input(
            db, ctx.tenant_id, case_id, draft, sections,
            readiness.trusted_sources, readiness.active_issue_ids,
            selected_legal_issue_ids=body.selected_legal_issue_ids,
            selected_source_usage_ids=body.selected_source_usage_ids,
        )
    except UnknownSelectionError as exc:
        raise HTTPException(status_code=422, detail=exc.code)

    input_fingerprint = generation_input_fingerprint(payload)
    provider = _draft_generation_provider()
    try:
        result = await provider.generate(payload)
    except DraftGenerationError as exc:
        logger.warning(
            "draft_generation_failed draft_id=%s case_id=%s provider=%s model=%s "
            "safe_error_code=%s",
            draft.id, case_id, provider.provider_name, provider.model_version, exc.code,
        )
        status_code = 503 if exc.code in _GENERATION_UNAVAILABLE_CODES else 502
        raise HTTPException(status_code=status_code, detail=exc.code)

    run_id = new_uuid()
    paragraphs = result["paragraphs"]
    issue_link_count = 0
    source_link_count = 0
    try:
        for entry in paragraphs:
            # Re-validate exact provenance inside the transaction.
            for reference in entry["source_references"]:
                key = (reference["source_record_id"], reference["source_version_id"],
                       reference["source_paragraph_id"])
                context_item = provenance_context.get(key)
                if context_item is None:
                    raise HTTPException(status_code=502,
                                        detail="draft_generation_unknown_source")
                record, version, source_paragraph = await _resolve_exact_source(
                    db, key[0], key[1], key[2])
                await _require_draft_trust_eligible(db, record, version)
                if (source_paragraph.text_hash or "") != context_item.text_hash or \
                        source_text_hash(source_paragraph.text or "") != context_item.text_hash:
                    raise HTTPException(status_code=502,
                                        detail="draft_generation_provenance_mismatch")

        created_paragraphs = []
        for entry in paragraphs:
            paragraph = await DraftParagraphRepository.create(
                db, tenant_id=ctx.tenant_id, case_id=case_id,
                draft_document_id=draft.id,
                paragraph_order=entry["section_order"],
                paragraph_type=entry["paragraph_type"],
                text=entry["text"], generated_by="ai",
                model_name=provider.model_version,
            )
            paragraph.generation_run_id = run_id
            paragraph.generation_input_fingerprint = input_fingerprint
            created_paragraphs.append(paragraph)
            # P2.9C1: every generated paragraph starts its immutable history
            # with revision 1 inside the same atomic transaction.
            await DraftParagraphRevisionRepository.create(
                db, tenant_id=ctx.tenant_id, case_id=case_id,
                draft_document_id=draft.id, draft_paragraph_id=paragraph.id,
                revision_number=1, base_paragraph_version=paragraph.version,
                text=entry["text"], change_type="initial_generation",
                created_by=ctx.actor_id,
            )
            for issue_id in entry["legal_issue_ids"]:
                if await DraftParagraphIssueLinkRepository.active_exists(
                        db, ctx.tenant_id, case_id, paragraph.id, issue_id):
                    continue
                await DraftParagraphIssueLinkRepository.create(
                    db, tenant_id=ctx.tenant_id, case_id=case_id,
                    draft_paragraph_id=paragraph.id, legal_issue_id=issue_id,
                    created_by=ctx.actor_id,
                )
                issue_link_count += 1
            for reference in entry["source_references"]:
                key = (reference["source_record_id"], reference["source_version_id"],
                       reference["source_paragraph_id"])
                context_item = provenance_context[key]
                if await DraftParagraphSourceLinkRepository.active_exists(
                        db, ctx.tenant_id, case_id, paragraph.id, *key):
                    continue
                await DraftParagraphSourceLinkRepository.create(
                    db, tenant_id=ctx.tenant_id, case_id=case_id,
                    draft_paragraph_id=paragraph.id,
                    source_record_id=key[0], source_version_id=key[1],
                    source_paragraph_id=key[2],
                    usage_type="citation", quote_hash=context_item.text_hash,
                    created_by=ctx.actor_id, verification_status="verified",
                )
                source_link_count += 1

        draft.version += 1
        metrics = _safe_provider_metrics(getattr(provider, "last_metrics", {}) or {})
        await _audit(db, ctx, case_id, "draft_generated",
                     {"resource": "draft", "draft_id": draft.id,
                      "generation_run_id": run_id,
                      "provider": provider.provider_name,
                      "model": provider.model_version,
                      "paragraph_count": len(created_paragraphs),
                      "issue_link_count": issue_link_count,
                      "source_link_count": source_link_count,
                      "version": draft.version})
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise

    logger.info(
        "draft_generated draft_id=%s case_id=%s run_id=%s provider=%s model=%s "
        "paragraph_count=%d issue_link_count=%d source_link_count=%d",
        draft.id, case_id, run_id, provider.provider_name, provider.model_version,
        len(created_paragraphs), issue_link_count, source_link_count,
    )
    return DraftGenerateResponse(
        draft_id=draft.id, status=draft.status, version=draft.version,
        generation_run_id=run_id, provider=provider.provider_name,
        model_name=provider.model_version,
        paragraph_count=len(created_paragraphs),
        issue_link_count=issue_link_count,
        source_link_count=source_link_count,
        metrics=metrics,
    )


# ---------------------------------------------------------------------------
# P2.9B — Deterministic post-generation validation (no LLM)
# ---------------------------------------------------------------------------
@router.post("/{draft_id}/validate", response_model=DraftValidateResponse,
             operation_id="draft_validate")
async def validate_draft(
    case_id: str,
    draft_id: str,
    ctx: SecurityContext = Depends(require_case_read),
    db: AsyncSession = Depends(get_session),
) -> DraftValidateResponse:
    await _authorized_case(db, ctx, case_id, write=False)
    draft = await _load_draft(db, ctx, case_id, draft_id)
    blocking: set[str] = set()
    warnings: set[str] = set()

    paragraphs = await DraftParagraphRepository.list_for_draft(db, ctx.tenant_id, draft.id)
    orders = sorted(p.paragraph_order for p in paragraphs)
    if orders != list(range(1, len(paragraphs) + 1)):
        blocking.add("paragraph_order_not_contiguous")

    plan_types = [entry[0] for entry in SECTION_PLAN_BY_DRAFT_TYPE[draft.draft_type]]
    required_types = {
        entry[0] for entry in SECTION_PLAN_BY_DRAFT_TYPE[draft.draft_type] if entry[1]
    }
    present_types = [p.paragraph_type for p in paragraphs]
    if required_types - set(present_types):
        blocking.add("required_section_missing")
    single_instance_types = {t for t in plan_types if plan_types.count(t) == 1}
    duplicated = {
        t for t in single_instance_types if present_types.count(t) > 1
    }
    if duplicated:
        blocking.add("duplicate_section")

    pending = [p for p in paragraphs if p.verification_status == "pending_review"]
    if any(p.verification_status == "needs_review" for p in paragraphs):
        blocking.add("paragraph_needs_review")
    if pending:
        warnings.add("paragraph_pending_review")

    paragraph_ids = [p.id for p in paragraphs]
    issue_links = await DraftParagraphIssueLinkRepository.list_for_paragraphs(
        db, ctx.tenant_id, paragraph_ids)
    for link in issue_links:
        issue = (await db.execute(select(LegalIssue).where(
            LegalIssue.id == link.legal_issue_id,
            LegalIssue.tenant_id == ctx.tenant_id,
            LegalIssue.case_id == case_id,
            LegalIssue.deleted_at.is_(None),
        ))).scalar_one_or_none()
        if issue is None:
            blocking.add("issue_link_invalid")

    source_links = await DraftParagraphSourceLinkRepository.list_for_paragraphs(
        db, ctx.tenant_id, paragraph_ids)
    citation_incomplete = False
    for link in source_links:
        row = (await db.execute(
            select(SourceRecord, SourceVersion, SourceParagraph)
            .join(SourceVersion, SourceVersion.source_record_id == SourceRecord.id)
            .join(SourceParagraph, SourceParagraph.source_version_id == SourceVersion.id)
            .where(
                SourceRecord.id == link.source_record_id,
                SourceVersion.id == link.source_version_id,
                SourceParagraph.id == link.source_paragraph_id,
                SourceRecord.current_version_id == link.source_version_id,
                SourceRecord.deleted_at.is_(None),
            )
        )).first()
        if row is None:
            blocking.add("source_link_provenance_invalid")
            continue
        record, version, source_paragraph = row
        trust = await resolve_version_verification_status(
            db, record.id, version.id, record.verification_status)
        if record.verification_status in BLOCKED_FOR_USAGE or trust not in TRUSTED_STATUSES:
            blocking.add("source_link_trust_lost")
        if link.quote_hash != (source_paragraph.text_hash or "") or \
                link.quote_hash != source_text_hash(source_paragraph.text or ""):
            blocking.add("source_link_quote_hash_mismatch")
        citation = render_citation(
            court=record.court or "", chamber=record.chamber or "",
            case_number=record.case_number or "",
            decision_number=record.decision_number or "",
            decision_date=record.decision_date or "",
            article_number=source_paragraph.article_number or "",
            paragraph_index=source_paragraph.paragraph_index,
        )
        if not citation:
            citation_incomplete = True
    if citation_incomplete:
        warnings.add("citation_metadata_incomplete")

    readiness = await compute_draft_readiness(db, ctx.tenant_id, case_id, draft)
    residual_blockers = [
        reason for reason in readiness.blocked_reasons
        if reason not in {"draft_not_empty"}
    ]
    if residual_blockers:
        blocking.add("readiness_blocked")
    if readiness.metrics.get("unsupported_claim_count", 0) > 0:
        warnings.add("unsupported_claim")

    linked_issue_ids = {link.legal_issue_id for link in issue_links}
    issue_ids_with_sources = set((await db.execute(select(LegalIssueSourceLink.issue_id).where(
        LegalIssueSourceLink.tenant_id == ctx.tenant_id,
        LegalIssueSourceLink.case_id == case_id,
        LegalIssueSourceLink.deleted_at.is_(None),
    ))).scalars().all())
    paragraphs_with_sources = {link.draft_paragraph_id for link in source_links}
    for link in issue_links:
        if link.legal_issue_id not in issue_ids_with_sources and \
                link.draft_paragraph_id not in paragraphs_with_sources:
            warnings.add("legal_issue_without_source")
            break

    return DraftValidateResponse(
        valid=not blocking,
        blocking_errors=sorted(blocking),
        warnings=sorted(warnings),
        metrics={
            "paragraph_count": len(paragraphs),
            "pending_paragraph_count": len(pending),
            "issue_link_count": len(issue_links),
            "source_link_count": len(source_links),
            "linked_issue_count": len(linked_issue_ids),
        },
    )


# ---------------------------------------------------------------------------
# P2.9C1 — Immutable revision history + manual editing
# ---------------------------------------------------------------------------
async def _load_editable_paragraph(
    db: AsyncSession, ctx: SecurityContext, case_id: str, draft_id: str,
    paragraph_id: str, *, draft_version: int, paragraph_version: int,
):
    draft = await _load_draft(db, ctx, case_id, draft_id)
    _require_editable(draft)
    _require_version(draft_version, draft.version)
    paragraph = await _load_paragraph(db, ctx, case_id, draft.id, paragraph_id)
    _require_version(paragraph_version, paragraph.version)
    return draft, paragraph


@router.post("/{draft_id}/paragraphs/{paragraph_id}/revisions",
             response_model=DraftParagraphRevisionActionResponse, status_code=201,
             operation_id="draft_paragraph_edit_revision")
async def create_paragraph_edit_revision(
    case_id: str,
    draft_id: str,
    paragraph_id: str,
    body: DraftParagraphEditRequest,
    ctx: SecurityContext = Depends(require_case_write),
    db: AsyncSession = Depends(get_session),
) -> DraftParagraphRevisionActionResponse:
    await _authorized_case(db, ctx, case_id, write=True)
    draft, paragraph = await _load_editable_paragraph(
        db, ctx, case_id, draft_id, paragraph_id,
        draft_version=body.draft_version, paragraph_version=body.paragraph_version)
    try:
        revision = await _append_paragraph_revision(
            db, ctx, draft, paragraph, new_text=body.text, change_type="user_edit")
        paragraph.text = body.text
        paragraph.verification_status = "pending_review"
        paragraph.version += 1
        marked = await _mark_source_links_needs_review(db, ctx, paragraph)
        draft.version += 1
        await _audit(db, ctx, case_id, "draft_paragraph_revised",
                     {"resource": "draft_paragraph_revision", "draft_id": draft.id,
                      "paragraph_id": paragraph.id, "revision_id": revision.id,
                      "revision_number": revision.revision_number,
                      "change_type": revision.change_type,
                      "paragraph_version": paragraph.version,
                      "draft_version": draft.version,
                      "source_links_marked_needs_review": marked})
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise
    return DraftParagraphRevisionActionResponse(
        paragraph_id=paragraph.id,
        revision=_revision_resp(revision, current=True),
        verification_status=paragraph.verification_status,
        paragraph_version=paragraph.version,
        draft_version=draft.version,
        source_links_marked_needs_review=marked,
    )


@router.get("/{draft_id}/paragraphs/{paragraph_id}/revisions",
            response_model=list[DraftParagraphRevisionResponse],
            operation_id="draft_paragraph_revisions")
async def list_paragraph_revisions(
    case_id: str,
    draft_id: str,
    paragraph_id: str,
    ctx: SecurityContext = Depends(require_case_read),
    db: AsyncSession = Depends(get_session),
) -> list[DraftParagraphRevisionResponse]:
    await _authorized_case(db, ctx, case_id, write=False)
    draft = await _load_draft(db, ctx, case_id, draft_id)
    paragraph = await _load_paragraph(db, ctx, case_id, draft.id, paragraph_id)
    revisions = await DraftParagraphRevisionRepository.list_for_paragraph(
        db, ctx.tenant_id, paragraph.id)
    latest_number = revisions[-1].revision_number if revisions else 0
    return [
        _revision_resp(revision, current=revision.revision_number == latest_number)
        for revision in revisions
    ]


@router.post("/{draft_id}/paragraphs/{paragraph_id}/revisions/{revision_id}/restore",
             response_model=DraftParagraphRevisionActionResponse, status_code=201,
             operation_id="draft_paragraph_revision_restore")
async def restore_paragraph_revision(
    case_id: str,
    draft_id: str,
    paragraph_id: str,
    revision_id: str,
    body: DraftParagraphRestoreRequest,
    ctx: SecurityContext = Depends(require_case_write),
    db: AsyncSession = Depends(get_session),
) -> DraftParagraphRevisionActionResponse:
    await _authorized_case(db, ctx, case_id, write=True)
    draft, paragraph = await _load_editable_paragraph(
        db, ctx, case_id, draft_id, paragraph_id,
        draft_version=body.draft_version, paragraph_version=body.paragraph_version)
    source = await DraftParagraphRevisionRepository.get(
        db, ctx.tenant_id, case_id, paragraph.id, revision_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Revision not found")
    try:
        # The old row is never mutated or re-pointed; restoring appends a NEW
        # immutable revision carrying the old text forward.
        revision = await _append_paragraph_revision(
            db, ctx, draft, paragraph, new_text=source.text,
            change_type="restored_revision")
        paragraph.text = source.text
        paragraph.verification_status = "pending_review"
        paragraph.version += 1
        marked = await _mark_source_links_needs_review(db, ctx, paragraph)
        draft.version += 1
        await _audit(db, ctx, case_id, "draft_paragraph_revision_restored",
                     {"resource": "draft_paragraph_revision", "draft_id": draft.id,
                      "paragraph_id": paragraph.id, "revision_id": revision.id,
                      "restored_from_revision_id": source.id,
                      "revision_number": revision.revision_number,
                      "paragraph_version": paragraph.version,
                      "draft_version": draft.version,
                      "source_links_marked_needs_review": marked})
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise
    return DraftParagraphRevisionActionResponse(
        paragraph_id=paragraph.id,
        revision=_revision_resp(revision, current=True),
        verification_status=paragraph.verification_status,
        paragraph_version=paragraph.version,
        draft_version=draft.version,
        source_links_marked_needs_review=marked,
    )

# ---------------------------------------------------------------------------
# P2.9C1 — Review decisions (accept / request-changes)
# ---------------------------------------------------------------------------
async def _load_latest_revision_for_review(
    db: AsyncSession, ctx: SecurityContext, case_id: str,
    paragraph, revision_id: str,
):
    """Bootstrap if needed and require ``revision_id`` to be the latest."""
    await DraftParagraphRevisionRepository.ensure_bootstrap(db, paragraph)
    latest = await DraftParagraphRevisionRepository.latest_for_paragraph(
        db, ctx.tenant_id, paragraph.id)
    revision = await DraftParagraphRevisionRepository.get(
        db, ctx.tenant_id, case_id, paragraph.id, revision_id)
    if revision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Revision not found")
    if latest is None or revision.id != latest.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Revision is not the latest revision")
    if revision.text_hash != source_text_hash(paragraph.text or ""):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Revision does not match the current paragraph text")
    return revision


@router.post("/{draft_id}/paragraphs/{paragraph_id}/accept",
             response_model=DraftReviewActionResponse,
             operation_id="draft_paragraph_accept")
async def accept_paragraph(
    case_id: str,
    draft_id: str,
    paragraph_id: str,
    body: DraftParagraphAcceptRequest,
    ctx: SecurityContext = Depends(require_case_write),
    db: AsyncSession = Depends(get_session),
) -> DraftReviewActionResponse:
    await _authorized_case(db, ctx, case_id, write=True)
    draft, paragraph = await _load_editable_paragraph(
        db, ctx, case_id, draft_id, paragraph_id,
        draft_version=body.draft_version, paragraph_version=body.paragraph_version)
    if paragraph.verification_status not in {"pending_review", "needs_review"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Paragraph is not awaiting review")
    revision = await _load_latest_revision_for_review(
        db, ctx, case_id, paragraph, body.revision_id)

    source_links = await DraftParagraphSourceLinkRepository.list_for_paragraphs(
        db, ctx.tenant_id, [paragraph.id])
    for link in source_links:
        if link.verification_status != "verified":
            raise HTTPException(
                status_code=422,
                detail="All source links must be re-verified before acceptance",
            )
        record, version, source_paragraph = await _resolve_exact_source(
            db, link.source_record_id, link.source_version_id, link.source_paragraph_id)
        await _require_draft_trust_eligible(db, record, version)
        _require_exact_quote_hash(link.quote_hash, source_paragraph)
    issue_links = await DraftParagraphIssueLinkRepository.list_for_paragraphs(
        db, ctx.tenant_id, [paragraph.id])
    for link in issue_links:
        issue = (await db.execute(select(LegalIssue).where(
            LegalIssue.id == link.legal_issue_id,
            LegalIssue.tenant_id == ctx.tenant_id,
            LegalIssue.case_id == case_id,
            LegalIssue.deleted_at.is_(None),
        ))).scalar_one_or_none()
        if issue is None:
            raise HTTPException(
                status_code=422,
                detail="A linked legal issue is no longer available in this case",
            )

    try:
        paragraph.verification_status = "accepted"
        paragraph.version += 1
        draft.version += 1
        event = await DraftParagraphReviewEventRepository.create(
            db, tenant_id=ctx.tenant_id, case_id=case_id,
            draft_document_id=draft.id, draft_paragraph_id=paragraph.id,
            paragraph_revision_id=revision.id, decision="accepted",
            reviewer_user_id=ctx.actor_id, paragraph_version=paragraph.version,
        )
        await _audit(db, ctx, case_id, "draft_paragraph_accepted",
                     {"resource": "draft_paragraph_review", "draft_id": draft.id,
                      "paragraph_id": paragraph.id, "revision_id": revision.id,
                      "revision_number": revision.revision_number,
                      "decision": "accepted",
                      "paragraph_version": paragraph.version,
                      "draft_version": draft.version})
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise
    return DraftReviewActionResponse(
        paragraph_id=paragraph.id, verification_status=paragraph.verification_status,
        paragraph_version=paragraph.version, draft_version=draft.version,
        review_event=_review_event_resp(event),
    )


@router.post("/{draft_id}/paragraphs/{paragraph_id}/request-changes",
             response_model=DraftReviewActionResponse,
             operation_id="draft_paragraph_request_changes")
async def request_paragraph_changes(
    case_id: str,
    draft_id: str,
    paragraph_id: str,
    body: DraftParagraphRequestChangesRequest,
    ctx: SecurityContext = Depends(require_case_write),
    db: AsyncSession = Depends(get_session),
) -> DraftReviewActionResponse:
    await _authorized_case(db, ctx, case_id, write=True)
    if body.reason_code not in DRAFT_REVIEW_REASON_CODES:
        raise HTTPException(status_code=422, detail="Invalid review reason code")
    draft, paragraph = await _load_editable_paragraph(
        db, ctx, case_id, draft_id, paragraph_id,
        draft_version=body.draft_version, paragraph_version=body.paragraph_version)
    revision = await _load_latest_revision_for_review(
        db, ctx, case_id, paragraph, body.revision_id)
    try:
        # Text and revisions stay untouched; only the review state changes.
        paragraph.verification_status = "needs_review"
        paragraph.version += 1
        draft.version += 1
        event = await DraftParagraphReviewEventRepository.create(
            db, tenant_id=ctx.tenant_id, case_id=case_id,
            draft_document_id=draft.id, draft_paragraph_id=paragraph.id,
            paragraph_revision_id=revision.id, decision="changes_requested",
            reason_code=body.reason_code, reviewer_user_id=ctx.actor_id,
            paragraph_version=paragraph.version,
        )
        await _audit(db, ctx, case_id, "draft_paragraph_changes_requested",
                     {"resource": "draft_paragraph_review", "draft_id": draft.id,
                      "paragraph_id": paragraph.id, "revision_id": revision.id,
                      "revision_number": revision.revision_number,
                      "decision": "changes_requested",
                      "reason_code": body.reason_code,
                      "paragraph_version": paragraph.version,
                      "draft_version": draft.version})
        await db.commit()
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise
    return DraftReviewActionResponse(
        paragraph_id=paragraph.id, verification_status=paragraph.verification_status,
        paragraph_version=paragraph.version, draft_version=draft.version,
        review_event=_review_event_resp(event),
    )


@router.get("/{draft_id}/paragraphs/{paragraph_id}/reviews",
            response_model=list[DraftReviewEventResponse],
            operation_id="draft_paragraph_reviews")
async def list_paragraph_reviews(
    case_id: str,
    draft_id: str,
    paragraph_id: str,
    ctx: SecurityContext = Depends(require_case_read),
    db: AsyncSession = Depends(get_session),
) -> list[DraftReviewEventResponse]:
    await _authorized_case(db, ctx, case_id, write=False)
    draft = await _load_draft(db, ctx, case_id, draft_id)
    paragraph = await _load_paragraph(db, ctx, case_id, draft.id, paragraph_id)
    events = await DraftParagraphReviewEventRepository.list_for_paragraph(
        db, ctx.tenant_id, paragraph.id)
    return [_review_event_resp(event) for event in events]


# ---------------------------------------------------------------------------
# P2.9C2 — Deterministic export (finalized drafts only, read-only)
# ---------------------------------------------------------------------------
async def _build_export_document(
    db: AsyncSession, ctx: SecurityContext, case_id: str, draft: DraftDocument,
):
    """Re-validate every finalize/provenance barrier and assemble the export.

    Read-only: never mutates the draft, never writes audit rows. Citations
    come exclusively from the deterministic server-side renderer.
    """
    from app.services.draft_export import (
        DRAFT_TYPE_LABELS,
        ExportDocument,
        ExportParagraph,
        TURKISH_SECTION_HEADINGS,
    )

    if draft.status != DRAFT_STATUS_FINALIZED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="draft_export_requires_finalized_draft")

    paragraphs = await DraftParagraphRepository.list_for_draft(db, ctx.tenant_id, draft.id)
    if not paragraphs:
        raise HTTPException(status_code=422, detail="draft_export_no_paragraphs")
    orders = sorted(p.paragraph_order for p in paragraphs)
    if orders != list(range(1, len(paragraphs) + 1)):
        raise HTTPException(status_code=422, detail="draft_export_order_invalid")

    export_paragraphs: list[ExportParagraph] = []
    for paragraph in paragraphs:
        if paragraph.verification_status != "accepted":
            raise HTTPException(status_code=422,
                                detail="draft_export_paragraph_not_accepted")
        latest_revision = await DraftParagraphRevisionRepository.latest_for_paragraph(
            db, ctx.tenant_id, paragraph.id)
        if latest_revision is None or \
                latest_revision.text_hash != source_text_hash(paragraph.text or ""):
            raise HTTPException(status_code=422,
                                detail="draft_export_revision_mismatch")
        latest_event = await DraftParagraphReviewEventRepository.latest_for_paragraph(
            db, ctx.tenant_id, paragraph.id)
        if (latest_event is None or latest_event.decision != "accepted"
                or latest_event.paragraph_revision_id != latest_revision.id):
            raise HTTPException(status_code=422,
                                detail="draft_export_revision_mismatch")

        source_links = await DraftParagraphSourceLinkRepository.list_for_paragraphs(
            db, ctx.tenant_id, [paragraph.id])
        source_links.sort(key=lambda link: (
            link.source_record_id, link.source_version_id, link.source_paragraph_id))
        citations: list[str] = []
        for link in source_links:
            if link.verification_status != "verified":
                raise HTTPException(status_code=422,
                                    detail="draft_export_provenance_invalid")
            row = (await db.execute(
                select(SourceRecord, SourceVersion, SourceParagraph)
                .join(SourceVersion, SourceVersion.source_record_id == SourceRecord.id)
                .join(SourceParagraph,
                      SourceParagraph.source_version_id == SourceVersion.id)
                .where(
                    SourceRecord.id == link.source_record_id,
                    SourceVersion.id == link.source_version_id,
                    SourceParagraph.id == link.source_paragraph_id,
                    SourceRecord.current_version_id == link.source_version_id,
                    SourceRecord.deleted_at.is_(None),
                )
            )).first()
            if row is None:
                raise HTTPException(status_code=422,
                                    detail="draft_export_provenance_invalid")
            record, version, source_paragraph = row
            trust = await resolve_version_verification_status(
                db, record.id, version.id, record.verification_status)
            if record.verification_status in BLOCKED_FOR_USAGE or \
                    trust not in TRUSTED_STATUSES:
                raise HTTPException(status_code=422,
                                    detail="draft_export_provenance_invalid")
            if link.quote_hash != (source_paragraph.text_hash or "") or \
                    link.quote_hash != source_text_hash(source_paragraph.text or ""):
                raise HTTPException(status_code=422,
                                    detail="draft_export_provenance_invalid")
            citation = render_citation(
                court=record.court or "", chamber=record.chamber or "",
                case_number=record.case_number or "",
                decision_number=record.decision_number or "",
                decision_date=record.decision_date or "",
                article_number=source_paragraph.article_number or "",
                paragraph_index=source_paragraph.paragraph_index,
            )
            if citation:
                citations.append(citation)
        export_paragraphs.append(ExportParagraph(
            order=paragraph.paragraph_order,
            heading=TURKISH_SECTION_HEADINGS.get(paragraph.paragraph_type, ""),
            text=paragraph.text,
            citations=tuple(citations),
        ))

    label = DRAFT_TYPE_LABELS.get(draft.draft_type, draft.draft_type)
    return ExportDocument(
        title=f"{label} — Emsalist Taslak {draft.id[:8]}",
        draft_type=draft.draft_type,
        draft_type_label=label,
        draft_id_short=draft.id[:8],
        version=draft.version,
        paragraphs=tuple(export_paragraphs),
    )


def _export_response(content: bytes, filename: str, media_type: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/{draft_id}/export/docx", operation_id="draft_export_docx",
            response_class=Response)
async def export_draft_docx(
    case_id: str,
    draft_id: str,
    ctx: SecurityContext = Depends(require_case_read),
    db: AsyncSession = Depends(get_session),
) -> Response:
    from app.services.draft_export import export_filename, render_docx

    await _authorized_case(db, ctx, case_id, write=False)
    draft = await _load_draft(db, ctx, case_id, draft_id)
    document = await _build_export_document(db, ctx, case_id, draft)
    content = render_docx(document)
    logger.info(
        "draft_exported draft_id=%s case_id=%s export_format=docx size_bytes=%d",
        draft.id, case_id, len(content),
    )
    return _export_response(
        content, export_filename(draft.draft_type, draft.id, "docx"),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
