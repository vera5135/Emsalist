"""P1.1 — AI run tracking endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from app.models.ai_models import AIRunSummary
from app.services.ai_run_service import ai_run_service
from app.services.case_session_service import case_session_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai-runs", tags=["AI Run Logs"])


@router.get("/cases/{case_id}")
def list_runs(
    case_id: str,
    operation: str = Query(default=""),
    status: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    case_session_service.require_existing_case(case_id)
    records, total = ai_run_service.list_case_runs(case_id, operation=operation, status=status, limit=limit, offset=offset)
    return {"case_id": case_id, "runs": records, "total": total, "limit": limit, "offset": offset}


@router.get("/cases/{case_id}/summary")
def summary(case_id: str) -> AIRunSummary:
    case_session_service.require_existing_case(case_id)
    return ai_run_service.summarize_case(case_id)


@router.get("/{run_id}")
def get_run(run_id: str) -> dict:
    record = ai_run_service.get_run(run_id)
    if not record:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run kaydı bulunamadı")
    return record
