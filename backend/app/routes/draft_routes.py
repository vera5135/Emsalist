"""P2.9A — Grounded draft persistence endpoints (case-scoped, member-authorized).

Persistence and provenance backbone only: no LLM generation, no export.
Every route resolves the case with member-based authorization (foreign
tenant/case → 404, non-members → 404, viewers cannot write). Draft paragraph
text and source quotes are never written to logs or audit metadata.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
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
    DraftParagraphSourceLinkRepository,
    EDITABLE_DRAFT_STATUSES,
    InvalidDraftTransitionError,
)
from app.db.models import (
    DRAFT_DOCUMENT_TYPES,
    DRAFT_PARAGRAPH_TYPES,
    DRAFT_PARAGRAPH_VERIFICATION_STATUSES,
    DRAFT_SOURCE_USAGE_TYPES,
    DraftDocument,
    DraftParagraph,
    LegalIssue,
    SourceParagraph,
    SourceRecord,
    SourceUsage,
    SourceVersion,
)
from app.db.session import get_session
from app.models.draft_models import (
    DraftCreateRequest,
    DraftDetailResponse,
    DraftFinalizeRequest,
    DraftFinalizeResponse,
    DraftListResponse,
    DraftParagraphCreateRequest,
    DraftParagraphIssueLinkRequest,
    DraftParagraphIssueLinkResponse,
    DraftParagraphResponse,
    DraftParagraphSourceLinkRequest,
    DraftParagraphSourceLinkResponse,
    DraftParagraphUpdateRequest,
    DraftResponse,
    DraftUpdateRequest,
)
from app.services.auth_manager import require_case_read, require_case_write
from app.services.auth_service import SecurityContext, get_auth_mode
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
    if (body.verification_status is not None
            and body.verification_status not in DRAFT_PARAGRAPH_VERIFICATION_STATUSES):
        raise HTTPException(status_code=422, detail="Invalid paragraph verification status")
    if body.paragraph_order is not None and body.paragraph_order != paragraph.paragraph_order:
        if await DraftParagraphRepository.active_order_exists(db, draft.id, body.paragraph_order):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bu sırada aktif bir paragraf zaten var.",
            )
        paragraph.paragraph_order = body.paragraph_order
    if body.paragraph_type is not None:
        paragraph.paragraph_type = body.paragraph_type
    if body.text is not None:
        paragraph.text = body.text
        # Text changed by the user: grounding must be re-reviewed.
        if body.verification_status is None:
            paragraph.verification_status = "pending_review"
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
