"""Case analysis endpoints."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.models.case_models import (
    CaseAnalyzeRequest,
    CaseAnalyzeResponse,
    CaseStateRequest,
    DynamicReasonerRequest,
)
from app.services.case_analyzer import case_analyzer
from app.services.case_session_service import case_session_service
from app.services.case_state_service import case_state_service
from app.services.dynamic_legal_reasoner_service import dynamic_legal_reasoner_service
from app.services.legal_issue_graph_service import legal_issue_graph_service
from app.services.petition_profile_service import get_petition_profile

router = APIRouter(prefix="/case", tags=["Case Analysis"])


@router.post("/new")
def create_new_case() -> dict[str, str]:
    payload = case_session_service.new_case()
    return {
        "case_id": payload["case_id"],
        "message": "Yeni dosya baÅŸlatÄ±ldÄ±.",
    }


@router.get("/current")
def get_current_case() -> dict[str, str]:
    payload = case_session_service.get_current_case(create_if_missing=True)
    if not payload:
        raise HTTPException(status_code=404, detail="Aktif dosya bulunamadÄ±.")
    return {
        "case_id": payload["case_id"],
        "message": "Aktif dosya hazÄ±r.",
    }


@router.get("/state")
def get_case_state(case_id: Annotated[str | None, Query()] = None) -> dict:
    resolved_case_id = case_session_service.resolve_case_id(case_id)
    return case_session_service.get_case_state(resolved_case_id)


@router.post("/analyze", response_model=CaseAnalyzeResponse)
def analyze_case(request: CaseAnalyzeRequest) -> CaseAnalyzeResponse:
    resolved_case_id = case_session_service.resolve_case_id(request.case_id)
    case_text = request.enriched_case_text or request.case_text
    analysis = case_analyzer.analyze(case_text)
    profile = get_petition_profile(case_text)
    existing = case_session_service.get_case_state(resolved_case_id)
    reasoning = dynamic_legal_reasoner_service.analyze(
        event_text=case_text,
        document_facts=list(existing.get("document_facts") or []),
        question_answers=dict(existing.get("question_answers") or {}),
    )
    case_state = case_state_service.build(
        case_id=resolved_case_id,
        event_text=case_text,
        area=analysis.legal_topic,
        case_type=profile.key,
        document_facts=list(existing.get("document_facts") or []),
        question_answers=dict(existing.get("question_answers") or {}),
        legal_sources=reasoning.get("research_queries", []),
        precedent_candidates=list(existing.get("final_precedents") or []),
        drafting_package=dict(existing.get("drafting_package") or {}),
        analysis_context={
            "warnings": reasoning.get("warnings", []),
            "documents": [{"document_type": item.get("document_type", "")} for item in existing.get("documents", []) if isinstance(item, dict)],
        },
    )
    case_session_service.update_case(
        resolved_case_id,
        event_text=case_text,
        title=(case_text[:80] + "...") if len(case_text) > 80 else case_text,
        legal_topic=analysis.legal_topic,
        case_state=case_state,
        dynamic_reasoning=reasoning,
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
    resolved_case_id = case_session_service.resolve_case_id(request.case_id)
    case_state = case_state_service.build(
        case_id=resolved_case_id,
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
    case_session_service.update_case(
        resolved_case_id,
        event_text=request.event_text,
        question_answers=request.question_answers,
        case_state=case_state,
        drafting_package=request.drafting_package,
    )
    return case_state


@router.post("/reason")
def run_dynamic_reasoner(request: DynamicReasonerRequest) -> dict:
    resolved_case_id = case_session_service.resolve_case_id(request.case_id)
    reasoning = dynamic_legal_reasoner_service.analyze(
        event_text=request.event_text,
        document_facts=request.document_facts,
        question_answers=request.question_answers,
    )
    case_state = case_state_service.build(
        case_id=resolved_case_id,
        event_text=request.event_text,
        area=str(request.analysis_context.get("area") or ""),
        case_type=str(request.analysis_context.get("case_type") or ""),
        document_facts=request.document_facts,
        question_answers=request.question_answers,
        legal_sources=reasoning.get("research_queries", []),
        precedent_candidates=[],
        drafting_package={},
        analysis_context=request.analysis_context,
    )
    case_session_service.update_case(
        resolved_case_id,
        event_text=request.event_text,
        question_answers=request.question_answers,
        case_state=case_state,
        dynamic_reasoning=reasoning,
    )
    return {**reasoning, "case_state": case_state}


@router.get("/legal-issue-graph")
def get_legal_issue_graph(case_id: Annotated[str | None, Query()] = None) -> dict:
    """Build and return the Legal Issue Graph for the current case."""
    resolved_case_id = case_session_service.resolve_case_id(case_id)
    case_state = case_session_service.get_case_state(resolved_case_id)
    graph = legal_issue_graph_service.build(case_state)
    graph_dict = graph.model_dump(mode="json")
    case_session_service.update_case(
        resolved_case_id,
        legal_issue_graph=graph_dict,
    )
    return graph_dict
