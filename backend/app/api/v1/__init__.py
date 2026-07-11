"""P1.12 — Versioned API router aggregation."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.config import get_settings
from app.core.correlation import get_correlation_id
from app.models.api_models import CapabilitiesResponse


api_v1_router = APIRouter(prefix="/api/v1")


@api_v1_router.get(
    "/meta/version",
    response_model=dict,
    tags=["Meta"],
    operation_id="get_version",
    summary="Application version and build metadata",
)
def get_version() -> dict:
    import os as _os
    from app.config import get_settings
    settings = get_settings()
    return {
        "application": "emsalist",
        "version": settings.app_version,
        "api_version": "v1",
        "commit": _os.environ.get("EMSALIST_COMMIT", "unknown"),
        "build_timestamp": _os.environ.get("EMSALIST_BUILD_TIMESTAMP", ""),
        "environment": settings.environment,
    }


# ── Sub-routers mounted under /api/v1 ───────────────────────────
from app.routes.case_routes import router as _case_router
from app.routes.document_routes import router as _document_router
from app.routes.auth_routes_new import router as _auth_router
from app.routes.auth_routes_new import apple_router as _apple_auth_router
from app.routes.job_routes import router as _job_router
from app.routes.lifecycle_routes import router as _lifecycle_router
from app.routes.ai_routes import router as _ai_router
from app.routes.petition_routes import router as _petition_router
from app.routes.search_routes import router as _search_router
from app.routes.decision_routes import router as _decision_router
from app.routes.yargitay_routes import router as _yargitay_router
from app.routes.research_routes import router as _research_router
from app.routes.legal_brain_routes import router as _legal_brain_router
from app.routes.workflow_routes import router as _workflow_router
from app.routes.legal_ground_routes import router as _legal_ground_router
from app.routes.precedent_routes import router as _precedent_router
from app.routes.grounding_routes import router as _grounding_router
from app.routes.ai_run_routes import router as _ai_run_router
from app.routes.legal_issue_graph_routes import router as _legal_issue_graph_router
from app.routes.security_routes import router as _security_router
from app.routes.case_chat_routes import router as _case_chat_router
from app.routes.case_chat_routes import conversation_router as _conversation_router
from app.routes.case_memory_routes import router as _case_memory_router
from app.routes.document_pipeline_routes import router as _document_pipeline_router

api_v1_router.include_router(_case_router, include_in_schema=True)
api_v1_router.include_router(_document_router, include_in_schema=True)
api_v1_router.include_router(_auth_router, include_in_schema=True)
api_v1_router.include_router(_apple_auth_router, include_in_schema=True)
api_v1_router.include_router(_job_router, include_in_schema=True)
api_v1_router.include_router(_lifecycle_router, include_in_schema=True)
api_v1_router.include_router(_ai_router, include_in_schema=True)
api_v1_router.include_router(_petition_router, include_in_schema=True)
api_v1_router.include_router(_search_router, include_in_schema=True)
api_v1_router.include_router(_decision_router, include_in_schema=True)
api_v1_router.include_router(_yargitay_router, include_in_schema=True)
api_v1_router.include_router(_research_router, include_in_schema=True)
api_v1_router.include_router(_legal_brain_router, include_in_schema=True)
api_v1_router.include_router(_workflow_router, include_in_schema=True)
api_v1_router.include_router(_legal_ground_router, include_in_schema=True)
api_v1_router.include_router(_precedent_router, include_in_schema=True)
api_v1_router.include_router(_grounding_router, include_in_schema=True)
api_v1_router.include_router(_ai_run_router, include_in_schema=True)
api_v1_router.include_router(_legal_issue_graph_router, include_in_schema=True)
api_v1_router.include_router(_security_router, include_in_schema=True)
api_v1_router.include_router(_case_chat_router, include_in_schema=True)
api_v1_router.include_router(_conversation_router, include_in_schema=True)
api_v1_router.include_router(_case_memory_router, include_in_schema=True)
api_v1_router.include_router(_document_pipeline_router, include_in_schema=True)


@api_v1_router.get(
    "/meta/capabilities",
    response_model=CapabilitiesResponse,
    tags=["Meta"],
    operation_id="get_capabilities",
    summary="API capabilities and feature flags",
)
def get_capabilities() -> CapabilitiesResponse:
    settings = get_settings()
    return CapabilitiesResponse(
        api_version="v1",
        features={
            "document_upload": True,
            "document_analysis": True,
            "background_jobs": True,
            "ai_enrichment": settings.gemini_enabled,
            "legal_brain": True,
            "yargitay_search": True,
            "petition_drafting": True,
            "case_lifecycle": True,
            "backup_restore": True,
            "metrics": settings.metrics_enabled,
        },
        limits={
            "max_upload_size_bytes": settings.max_upload_size_bytes,
            "supported_extensions": [".pdf", ".txt", ".docx", ".udf", ".jpg", ".jpeg", ".png"],
        },
    )
