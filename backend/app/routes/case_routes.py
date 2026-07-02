"""Case analysis endpoints."""

from fastapi import APIRouter

from app.models.case_models import (
    CaseAnalyzeRequest,
    CaseAnalyzeResponse,
    CaseStateRequest,
    DynamicReasonerRequest,
)
from app.services.case_analyzer import case_analyzer
from app.services.case_state_service import case_state_service
from app.services.dynamic_legal_reasoner_service import dynamic_legal_reasoner_service
from app.services.petition_profile_service import get_petition_profile

router = APIRouter(prefix="/case", tags=["Case Analysis"])


@router.post("/analyze", response_model=CaseAnalyzeResponse)
def analyze_case(request: CaseAnalyzeRequest) -> CaseAnalyzeResponse:
    case_text = request.enriched_case_text or request.case_text
    analysis = case_analyzer.analyze(case_text)
    profile = get_petition_profile(case_text)
    reasoning = dynamic_legal_reasoner_service.analyze(
        event_text=case_text,
        document_facts=[],
        question_answers={},
    )
    case_state = case_state_service.build(
        event_text=case_text,
        area=analysis.legal_topic,
        case_type=profile.key,
        document_facts=[],
        question_answers={},
        legal_sources=reasoning.get("research_queries", []),
        precedent_candidates=[],
        drafting_package={},
        analysis_context={"warnings": reasoning.get("warnings", [])},
    )
    return CaseAnalyzeResponse(
        legal_topic=analysis.legal_topic,
        case_facts=analysis.case_facts,
        legal_keywords=analysis.legal_keywords,
        case_state=case_state,
        dynamic_reasoning=reasoning,
    )


@router.post("/state")
def build_case_state(request: CaseStateRequest) -> dict:
    return case_state_service.build(
        event_text=request.event_text,
        area=request.area,
        case_type=request.case_type,
        document_facts=request.document_facts,
        question_answers=request.question_answers,
        legal_sources=request.legal_sources,
        precedent_candidates=request.precedent_candidates,
        drafting_package=request.drafting_package,
        analysis_context=request.analysis_context,
    )


@router.post("/reason")
def run_dynamic_reasoner(request: DynamicReasonerRequest) -> dict:
    reasoning = dynamic_legal_reasoner_service.analyze(
        event_text=request.event_text,
        document_facts=request.document_facts,
        question_answers=request.question_answers,
    )
    return {
        **reasoning,
        "case_state": case_state_service.build(
            event_text=request.event_text,
            area=str(request.analysis_context.get("area") or ""),
            case_type=str(request.analysis_context.get("case_type") or ""),
            document_facts=request.document_facts,
            question_answers=request.question_answers,
            legal_sources=reasoning.get("research_queries", []),
            precedent_candidates=[],
            drafting_package={},
            analysis_context=request.analysis_context,
        ),
    }
