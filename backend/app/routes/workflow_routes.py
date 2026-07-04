"""P0.2 — Backend review workflow endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.models.ai_models import WorkflowReviewRequest, WorkflowReviewResponse
from app.services.case_session_service import case_session_service
from app.services.review_workflow_service import review_workflow_service

router = APIRouter(prefix="/workflow", tags=["İş Akışı"])


@router.post("/review", response_model=WorkflowReviewResponse)
async def workflow_review(request: WorkflowReviewRequest) -> WorkflowReviewResponse:
    case_id = case_session_service.require_existing_case(request.case_id)

    existing_runs = (
        case_session_service._state.get("cases", {})
        .get(case_id, {})
        .get("workflow_runs", {})
    )
    if request.request_id in existing_runs:
        run = existing_runs[request.request_id]
        current_fingerprint = review_workflow_service._fingerprint(request)

        if run.get("fingerprint") != current_fingerprint:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Aynı request_id farklı parametrelerle kullanılamaz.",
            )
        if run.get("status") == "running":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Bu request_id için iş akışı devam ediyor.",
            )

    return await review_workflow_service.execute(request)
