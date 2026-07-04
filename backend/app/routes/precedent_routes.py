"""P0.5 — Precedent authority endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.models.precedent_models import (
    PrecedentAuditRequest,
    PrecedentAuthorityResponse,
    PrecedentSelectRequest,
)
from app.services.case_session_service import case_session_service
from app.services.precedent_authority_service import precedent_authority_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/precedents", tags=["Emsal Otoritesi"])


@router.get("/authority/{case_id}", response_model=PrecedentAuthorityResponse)
def get_precedent_authority(case_id: str) -> PrecedentAuthorityResponse:
    case_session_service.require_existing_case(case_id)
    stored = case_session_service.get_case_state(case_id)
    authority_data = stored.get("precedent_authority") or {}
    from app.models.precedent_models import PrecedentAuthority
    authority = PrecedentAuthority(**authority_data) if authority_data else PrecedentAuthority()
    return precedent_authority_service.to_response(authority, case_id)


@router.post("/select", response_model=PrecedentAuthorityResponse)
def select_precedent(request: PrecedentSelectRequest) -> PrecedentAuthorityResponse:
    case_session_service.require_existing_case(request.case_id)
    stored = case_session_service.get_case_state(request.case_id)
    authority_data = stored.get("precedent_authority") or {}

    if not authority_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Emsal otoritesi bulunamadı. Önce inceleme yapın.")

    try:
        updated = precedent_authority_service.select_precedent(
            authority=authority_data,
            precedent_id=request.precedent_id,
            selected=request.selected,
            reason=request.reason,
        )
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Emsal kaydı bulunamadı: {request.precedent_id}")

    case_session_service.update_case(request.case_id, precedent_authority=updated)
    from app.models.precedent_models import PrecedentAuthority
    return precedent_authority_service.to_response(PrecedentAuthority(**updated), request.case_id)
