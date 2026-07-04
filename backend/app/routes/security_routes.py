"""P0.7 — Security and KVKK compliance endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.services.case_session_service import case_session_service
from app.services.security_service import compliance_delete_case, security_fingerprint

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/security", tags=["Güvenlik"])


@router.delete("/case/{case_id}")
def delete_case(case_id: str) -> dict:
    case_session_service.require_existing_case(case_id)
    return compliance_delete_case(case_id)


@router.get("/fingerprint")
def get_fingerprint() -> dict:
    return {"fingerprint": security_fingerprint(), "compliance_ready": True}
