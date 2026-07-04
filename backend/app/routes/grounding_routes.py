"""P0.6 — Claim grounding endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.models.claim_models import GroundingAnalyzeRequest, GroundingAnalyzeResponse
from app.services.case_session_service import case_session_service
from app.services.claim_grounding_service import claim_grounding_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/grounding", tags=["Claim Grounding"])


@router.post("/analyze", response_model=GroundingAnalyzeResponse)
def analyze_grounding(request: GroundingAnalyzeRequest) -> GroundingAnalyzeResponse:
    case_session_service.require_existing_case(request.case_id)
    stored = case_session_service.get_case_state(request.case_id)
    existing = stored.get("claim_grounding")
    result = claim_grounding_service.analyze(
        case_id=request.case_id,
        petition_text=request.petition_text,
        case_state=stored,
        existing=existing,
    )
    case_session_service.update_case(request.case_id, claim_grounding=result.model_dump(mode="json"))
    return claim_grounding_service.to_response(result, request.case_id, request.petition_text)


@router.get("/{case_id}", response_model=GroundingAnalyzeResponse)
def get_grounding(case_id: str) -> GroundingAnalyzeResponse:
    case_session_service.require_existing_case(case_id)
    stored = case_session_service.get_case_state(case_id)
    grounding_data = stored.get("claim_grounding") or {}
    from app.models.claim_models import ClaimGroundingResult
    result = ClaimGroundingResult(**grounding_data) if grounding_data else ClaimGroundingResult()
    return claim_grounding_service.to_response(result, case_id)
