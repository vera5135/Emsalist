"""Optional AI legal intelligence endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.models.ai_models import (
    CaseEnrichmentRequest,
    CaseEnrichmentResponse,
    DraftAuditRequest,
    DraftAuditResponse,
    DraftRefineRequest,
    DraftRefineResponse,
    LegalQuestionRequest,
    LegalQuestionResponse,
    PrecedentAuditRequest,
    PrecedentAuditResponse,
    SearchQualityRequest,
    SearchQualityResponse,
    SourceAuditRequest,
    SourceAuditResponse,
)
from app.services.case_enrichment_agent import case_enrichment_agent
from app.services.legal_question_agent import legal_question_agent
from app.services.petition_quality_agent import petition_quality_agent
from app.services.petition_refine_agent import petition_refine_agent
from app.services.precedent_quality_agent import precedent_quality_agent
from app.services.search_quality_agent import search_quality_agent
from app.services.source_relevance_agent import source_relevance_agent

router = APIRouter(prefix="/ai", tags=["Hukuki Zekâ"])


@router.post("/enrich-case", response_model=CaseEnrichmentResponse)
def enrich_case(request: CaseEnrichmentRequest) -> CaseEnrichmentResponse:
    return case_enrichment_agent.enrich(
        case_text=request.case_text,
        practice_area=request.practice_area,
        use_gemini=request.use_gemini,
    )


@router.post("/generate-legal-questions", response_model=LegalQuestionResponse)
def generate_legal_questions(request: LegalQuestionRequest) -> LegalQuestionResponse:
    return legal_question_agent.generate(
        case_text=request.case_text,
        case_enrichment=request.case_enrichment,
        use_gemini=request.use_gemini,
    )


@router.post("/build-better-searches", response_model=SearchQualityResponse)
def build_better_searches(request: SearchQualityRequest) -> SearchQualityResponse:
    return search_quality_agent.build(
        case_text=request.case_text,
        case_enrichment=request.case_enrichment,
        use_gemini=request.use_gemini,
    )


@router.post("/audit-sources", response_model=SourceAuditResponse)
def audit_sources(request: SourceAuditRequest) -> SourceAuditResponse:
    return source_relevance_agent.audit(
        case_enrichment=request.case_enrichment,
        sources=request.sources,
        use_gemini=request.use_gemini,
    )


@router.post("/audit-precedents", response_model=PrecedentAuditResponse)
def audit_precedents(request: PrecedentAuditRequest) -> PrecedentAuditResponse:
    return precedent_quality_agent.audit(
        case_text=request.case_text,
        case_enrichment=request.case_enrichment,
        precedents=request.precedents,
        use_gemini=request.use_gemini,
    )


@router.post("/audit-draft", response_model=DraftAuditResponse)
def audit_draft(request: DraftAuditRequest) -> DraftAuditResponse:
    return petition_quality_agent.audit(
        draft_text=request.draft_text,
        case_text=request.case_text,
        case_enrichment=request.case_enrichment,
        selected_decisions=request.selected_decisions,
        use_gemini=request.use_gemini,
    )


@router.post("/refine-draft", response_model=DraftRefineResponse)
def refine_draft(request: DraftRefineRequest) -> DraftRefineResponse:
    return petition_refine_agent.refine(
        draft_text=request.draft_text,
        case_text=request.case_text,
        case_enrichment=request.case_enrichment,
        selected_decisions=request.selected_decisions,
        use_gemini=request.use_gemini,
    )
