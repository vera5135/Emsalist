"""Canonical P2.8 legal issue and reasoning endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.auth_repository import CaseMemberRepository
from app.db.case_chat_repository import CaseRepository
from app.db.legal_reasoning_repository import LegalReasoningRepository, iso
from app.db.models import (
    COUNTERARGUMENT_STATUSES, EVIDENCE_CLAIM_RELATIONS, LEGAL_ISSUE_STATUSES,
    Claim, EvidenceClaimLink, MissingInformation, SourceParagraph, SourceRecord, SourceVersion,
)
from app.db.session import get_session
from app.models.legal_reasoning_models import (
    EvidenceLinkRequest, GraphResponse, LegalIssueResponse, LegalIssueUpdateRequest,
    ReasoningRunResponse, RebuildRequest, SourceLinkRequest,
)
from app.services.auth_manager import require_case_read, require_case_write
from app.services.auth_service import SecurityContext, get_auth_mode, resolve_current_user
from app.services.legal_reasoning_service import legal_reasoning_service
from app.services.source_ingestion_service import resolve_version_verification_status
from app.services.source_verification import index_eligibility


router = APIRouter(tags=["Legal Reasoning"])


async def _authorized_case(db: AsyncSession, ctx: SecurityContext, case_id: str, *, write: bool):
    case = await CaseRepository.get(db, ctx.tenant_id, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    if get_auth_mode() != "local" and ctx.role != "tenant_admin":
        membership = await CaseMemberRepository.get_active_membership(
            db, ctx.tenant_id, case_id, ctx.actor_id,
        )
        if membership is None or (write and membership.membership_role == "viewer"):
            raise HTTPException(status_code=404, detail="Case not found")
    return case


async def _authorized_issue(db: AsyncSession, ctx: SecurityContext, issue_id: str, *, write: bool):
    issue = await LegalReasoningRepository.issue_by_id(db, ctx.tenant_id, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Legal issue not found")
    case = await CaseRepository.get(db, ctx.tenant_id, issue.case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Legal issue not found")
    if get_auth_mode() != "local" and ctx.role != "tenant_admin":
        membership = await CaseMemberRepository.get_active_membership(
            db, ctx.tenant_id, issue.case_id, ctx.actor_id,
        )
        if membership is None or (write and membership.membership_role == "viewer"):
            raise HTTPException(status_code=404, detail="Legal issue not found")
    return issue


def _support(issue_id: str, graph) -> str:
    assessments = [a.status for a in graph["assessments"] if a.issue_id == issue_id]
    if "contradicted" in assessments:
        return "contradictory"
    if any(s in {"inadmissibility_risk", "authenticity_risk", "unsupported"} for s in assessments):
        return "uncertain"
    if "partially_supported" in assessments:
        return "partial"
    if "supported" in assessments:
        return "strong"
    if not any(s.issue_id == issue_id for s in graph["source_links"]):
        return "source_missing"
    return "uncertain"


async def _issues(db, tenant_id, case_id):
    graph = await LegalReasoningRepository.graph(db, tenant_id, case_id)
    stale, _, _ = await legal_reasoning_service.current_state(db, tenant_id, case_id)
    return [LegalIssueResponse(
        id=i.id, case_id=i.case_id, parent_issue_id=i.parent_issue_id,
        issue_code=i.issue_code, title=i.title, description=i.description,
        status=i.status, confidence=i.confidence, support_state=_support(i.id, graph),
        stale=stale, version=i.version,
    ) for i in graph["issues"]]


@router.get("/cases/{case_id}/legal-issues", response_model=list[LegalIssueResponse], operation_id="list_case_legal_issues")
async def list_case_legal_issues(case_id: str, ctx: SecurityContext = Depends(require_case_read),
                                 db: AsyncSession = Depends(get_session)):
    await _authorized_case(db, ctx, case_id, write=False)
    return await _issues(db, ctx.tenant_id, case_id)


@router.post("/cases/{case_id}/legal-issues/rebuild", response_model=ReasoningRunResponse,
             operation_id="rebuild_case_legal_issues")
async def rebuild_case_legal_issues(case_id: str, body: RebuildRequest,
                                    ctx: SecurityContext = Depends(require_case_write),
                                    db: AsyncSession = Depends(get_session)):
    await _authorized_case(db, ctx, case_id, write=True)
    try:
        run = await legal_reasoning_service.rebuild(
            db, tenant_id=ctx.tenant_id, case_id=case_id, actor_id=ctx.actor_id,
            prompt_version=body.prompt_version,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return _run(run, False)


@router.patch("/legal-issues/{issue_id}", response_model=LegalIssueResponse, operation_id="update_legal_issue")
async def update_legal_issue(issue_id: str, body: LegalIssueUpdateRequest,
                             ctx: SecurityContext = Depends(resolve_current_user),
                             db: AsyncSession = Depends(get_session)):
    issue = await _authorized_issue(db, ctx, issue_id, write=True)
    if issue.version != body.version:
        raise HTTPException(status_code=409, detail="Version conflict")
    if body.status is not None:
        if body.status not in LEGAL_ISSUE_STATUSES:
            raise HTTPException(status_code=422, detail="Invalid legal issue status")
        issue.status = body.status
    if body.title is not None: issue.title = body.title
    if body.description is not None: issue.description = body.description
    issue.version += 1
    await db.commit()
    graph = await LegalReasoningRepository.graph(db, ctx.tenant_id, issue.case_id, issue.id)
    stale, _, _ = await legal_reasoning_service.current_state(db, ctx.tenant_id, issue.case_id)
    return LegalIssueResponse(id=issue.id, case_id=issue.case_id, parent_issue_id=issue.parent_issue_id,
        issue_code=issue.issue_code, title=issue.title, description=issue.description,
        status=issue.status, confidence=issue.confidence, support_state=_support(issue.id, graph),
        stale=stale, version=issue.version)


@router.get("/legal-issues/{issue_id}/graph", response_model=GraphResponse, operation_id="get_legal_issue_graph")
async def get_legal_issue_graph(issue_id: str, ctx: SecurityContext = Depends(resolve_current_user),
                                db: AsyncSession = Depends(get_session)):
    issue = await _authorized_issue(db, ctx, issue_id, write=False)
    return await _graph_response(db, ctx.tenant_id, issue.case_id, issue.id)


@router.post("/legal-issues/{issue_id}/evidence-links", operation_id="create_legal_issue_evidence_link")
async def create_legal_issue_evidence_link(issue_id: str, body: EvidenceLinkRequest,
                                           ctx: SecurityContext = Depends(resolve_current_user),
                                           db: AsyncSession = Depends(get_session)):
    issue = await _authorized_issue(db, ctx, issue_id, write=True)
    link = await LegalReasoningRepository.add_evidence_link(
        db, tenant_id=ctx.tenant_id, case_id=issue.case_id, issue_id=issue.id,
        claim_id=body.claim_id, evidence_id=body.evidence_id, relation_type=body.relation_type,
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    await db.commit()
    return {"id": link.id, "claim_id": link.claim_id, "evidence_id": link.evidence_id,
            "relation_type": link.relation_type}


@router.post("/legal-issues/{issue_id}/source-links", operation_id="create_legal_issue_source_link")
async def create_legal_issue_source_link(issue_id: str, body: SourceLinkRequest,
                                         ctx: SecurityContext = Depends(resolve_current_user),
                                         db: AsyncSession = Depends(get_session)):
    issue = await _authorized_issue(db, ctx, issue_id, write=True)
    row = (await db.execute(select(SourceRecord, SourceVersion, SourceParagraph)
        .join(SourceVersion, SourceVersion.source_record_id == SourceRecord.id)
        .join(SourceParagraph, SourceParagraph.source_version_id == SourceVersion.id)
        .where(SourceRecord.id == body.source_record_id,
               SourceVersion.id == body.source_version_id,
               SourceParagraph.id == body.source_paragraph_id,
               SourceRecord.current_version_id == body.source_version_id,
               SourceRecord.deleted_at.is_(None)))).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Source provenance not found")
    record, version, _ = row
    trust = await resolve_version_verification_status(db, record.id, version.id, record.verification_status)
    if not index_eligibility(trust).eligible:
        raise HTTPException(status_code=422, detail="Source is not eligible for legal reasoning")
    link = await LegalReasoningRepository.add_source_link(db, tenant_id=ctx.tenant_id,
        case_id=issue.case_id, issue_id=issue.id, source_record_id=body.source_record_id,
        source_version_id=body.source_version_id, source_paragraph_id=body.source_paragraph_id,
        relation_type=body.relation_type)
    await db.commit()
    return {"id": link.id, "source_record_id": link.source_record_id,
            "source_version_id": link.source_version_id,
            "source_paragraph_id": link.source_paragraph_id,
            "relation_type": link.relation_type, "effective_trust": trust}


@router.get("/cases/{case_id}/reasoning-runs", response_model=list[ReasoningRunResponse],
            operation_id="list_case_reasoning_runs")
async def list_case_reasoning_runs(case_id: str, ctx: SecurityContext = Depends(require_case_read),
                                   db: AsyncSession = Depends(get_session)):
    await _authorized_case(db, ctx, case_id, write=False)
    stale, _, _ = await legal_reasoning_service.current_state(db, ctx.tenant_id, case_id)
    return [_run(run, stale if run.status == "succeeded" else False)
            for run in await LegalReasoningRepository.list_runs(db, ctx.tenant_id, case_id)]


def _run(run, stale):
    return ReasoningRunResponse(id=run.id, case_id=run.case_id,
        memory_revision_id=run.memory_revision_id, source_fingerprint=run.source_fingerprint,
        provider=run.provider, model_version=run.model_version, prompt_version=run.prompt_version,
        output_hash=run.output_hash, status=run.status, stale=stale,
        safe_summary=run.safe_summary_json or {}, created_at=iso(run.created_at) or "")


async def _graph_response(db, tenant_id, case_id, issue_id=None):
    graph = await LegalReasoningRepository.graph(db, tenant_id, case_id, issue_id)
    stale, _, _ = await legal_reasoning_service.current_state(db, tenant_id, case_id)
    def base(row): return {"id": row.id, "issue_id": getattr(row, "issue_id", None)}
    missing = list((await db.execute(select(MissingInformation).where(
        MissingInformation.tenant_id == tenant_id,
        MissingInformation.case_id == case_id,
        MissingInformation.deleted_at.is_(None),
    ))).scalars().all())
    claims = list((await db.execute(select(Claim).where(
        Claim.tenant_id == tenant_id, Claim.case_id == case_id,
        Claim.deleted_at.is_(None),
    ))).scalars().all())
    linked_claim_ids = set((await db.execute(select(EvidenceClaimLink.claim_id).where(
        EvidenceClaimLink.tenant_id == tenant_id, EvidenceClaimLink.case_id == case_id,
        EvidenceClaimLink.deleted_at.is_(None),
    ))).scalars().all())
    return GraphResponse(case_id=case_id, stale=stale,
        issues=[{"id": i.id, "parent_issue_id": i.parent_issue_id, "title": i.title,
                 "description": i.description, "status": i.status,
                 "support_state": _support(i.id, graph), "version": i.version} for i in graph["issues"]],
        fact_links=[{**base(x), "fact_id": x.fact_id, "relation_type": x.relation_type} for x in graph["fact_links"]],
        evidence_links=[{**base(x), "claim_id": x.claim_id, "evidence_id": x.evidence_id,
                         "status": x.status, "notes": x.notes} for x in graph["assessments"]],
        source_links=[{**base(x), "source_record_id": x.source_record_id,
                       "source_version_id": x.source_version_id, "source_paragraph_id": x.source_paragraph_id,
                       "relation_type": x.relation_type} for x in graph["source_links"]],
        risk_links=[{**base(x), "risk_id": x.risk_id, "relation_type": x.relation_type} for x in graph["risk_links"]],
        dependencies=[{**base(x), "required_issue_id": x.required_issue_id} for x in graph["dependencies"]],
        burdens=[{**base(x), "burden_party_id": x.burden_party_id, "burden_type": x.burden_type,
                  "required_standard": x.required_standard, "evidence_status": x.evidence_status,
                  "status": x.status, "legal_source_refs": x.legal_source_refs, "notes": x.notes} for x in graph["burdens"]],
        counterarguments=[{**base(x), "category": x.category, "title": x.title,
                           "rationale": x.rationale, "basis": x.basis, "status": x.status,
                           "source_refs": x.source_refs} for x in graph["counterarguments"]],
        missing_information=[{"id": x.id, "label": x.label, "status": x.status,
                              "importance": x.importance} for x in missing],
        unsupported_claims=[{"id": x.id, "title": x.title, "status": "unsupported",
                             "reason": "linked_evidence_missing"}
                            for x in claims if x.id not in linked_claim_ids])
