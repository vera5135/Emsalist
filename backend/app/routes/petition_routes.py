"""Petition strategy and draft endpoints."""

from fastapi import APIRouter

from app.models.petition_models import (
    PetitionDraftRequest,
    PetitionDraftResponse,
    PetitionStrategyRequest,
    PetitionStrategyResponse,
)
from app.services.petition_draft_service import petition_draft_service
from app.services.petition_strategy_service import petition_strategy_service


router = APIRouter(prefix="/petition", tags=["Dilekçe"])


@router.post("/strategy", response_model=PetitionStrategyResponse)
def build_petition_strategy(request: PetitionStrategyRequest) -> PetitionStrategyResponse:
    return petition_strategy_service.build_strategy(
        case_text=request.case_text,
        top_decisions=request.top_decisions,
    )


@router.post("/draft", response_model=PetitionDraftResponse)
def build_petition_draft(request: PetitionDraftRequest) -> PetitionDraftResponse:
    selected_decisions = request.audited_precedents or request.selected_decisions
    # AI enrichment fields are internal signals for search, questions and quality checks.
    # They must not be appended to the petition narrative as raw analysis text.
    case_text = request.case_text
    return petition_draft_service.build_draft(
        case_text=case_text,
        answers=request.answers,
        selected_decisions=selected_decisions,
        tone=request.tone,
        request_type=request.request_type,
        use_legal_brain=request.use_legal_brain,
        legal_language_level=request.legal_language_level,
    )
