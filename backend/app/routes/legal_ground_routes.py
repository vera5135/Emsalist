"""P0.4 — Legal grounds validation endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.models.legal_issue_graph_models import (
    LegalGroundValidationRequest,
    LegalGroundValidationResponse,
)
from app.services.case_session_service import case_session_service
from app.services.legal_ground_validator_service import legal_ground_validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/legal-grounds", tags=["Hukuki Dayanak"])


@router.post("/validate", response_model=LegalGroundValidationResponse)
def validate_legal_grounds(request: LegalGroundValidationRequest) -> LegalGroundValidationResponse:
    case_session_service.require_existing_case(request.case_id)
    return legal_ground_validator.validate_response(
        case_id=request.case_id,
        legal_grounds=request.legal_grounds,
        event_date=request.event_date,
    )
