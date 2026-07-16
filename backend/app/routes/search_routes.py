"""Search profile, dynamic precedent pool and P2.7 hybrid search endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.case_models import (
    CaseSearchProfileRequest,
    CaseSearchProfileResponse,
    SearchBuildRequest,
    SearchBuildResponse,
)
from app.models.search_models import (
    DynamicPrecedentPoolRequest,
    DynamicPrecedentPoolResponse,
    LegalSearchRequest,
    LegalSearchResponse,
    OpposingSearchRequest,
    OpposingSearchResponse,
    SearchFeedbackRequest,
    SearchFeedbackResponse,
    SearchSuggestionResponse,
    SimilarSearchRequest,
    SimilarSearchResponse,
)
from app.services.auth_service import SecurityContext, resolve_current_user
from app.services.case_search_profile import case_search_profile_provider
from app.services.dynamic_precedent_pool_service import build_dynamic_precedent_pool
from app.services.hybrid_search_service import (
    execute_legal_search,
    execute_opposing_search,
    execute_similar_search,
    get_search_suggestions,
    submit_feedback,
)
from app.services.search_builder import search_builder

router = APIRouter(prefix="/search", tags=["Search"])


@router.post("/build", response_model=SearchBuildResponse)
def build_search_queries(request: SearchBuildRequest) -> SearchBuildResponse:
    return search_builder.build(request)


@router.post(
    "/profile",
    response_model=CaseSearchProfileResponse,
    operation_id="search_build_case_profile",
)
def build_case_search_profile(
    request: CaseSearchProfileRequest,
    ctx: SecurityContext = Depends(resolve_current_user),
) -> CaseSearchProfileResponse:
    # Authentication is required because the narrative may contain privileged
    # client information. The raw narrative and provider queries are not stored.
    _ = ctx
    return case_search_profile_provider.build(request)


@router.post(
    "/dynamic-pool",
    response_model=DynamicPrecedentPoolResponse,
    operation_id="search_build_dynamic_precedent_pool",
)
async def create_dynamic_precedent_pool(
    request: DynamicPrecedentPoolRequest,
    db: AsyncSession = Depends(get_session),
    ctx: SecurityContext = Depends(resolve_current_user),
) -> DynamicPrecedentPoolResponse:
    return await build_dynamic_precedent_pool(db, request, ctx)


@router.post("/legal", response_model=LegalSearchResponse)
async def search_legal(
    request: LegalSearchRequest,
    db: AsyncSession = Depends(get_session),
    ctx: SecurityContext = Depends(resolve_current_user),
) -> LegalSearchResponse:
    return await execute_legal_search(db, request, ctx)


@router.post("/similar", response_model=SimilarSearchResponse)
async def search_similar(
    request: SimilarSearchRequest,
    db: AsyncSession = Depends(get_session),
    ctx: SecurityContext = Depends(resolve_current_user),
) -> SimilarSearchResponse:
    return await execute_similar_search(db, request, ctx)


@router.post("/opposing", response_model=OpposingSearchResponse)
async def search_opposing(
    request: OpposingSearchRequest,
    db: AsyncSession = Depends(get_session),
    ctx: SecurityContext = Depends(resolve_current_user),
) -> OpposingSearchResponse:
    return await execute_opposing_search(db, request, ctx)


@router.get("/suggestions", response_model=SearchSuggestionResponse)
async def search_suggestions(
    q: str = Query(..., min_length=1, max_length=200, description="Sorgu on eki"),
    limit: int = Query(10, ge=1, le=20, description="Maksimum oneri sayisi"),
) -> SearchSuggestionResponse:
    return await get_search_suggestions(q, limit)


@router.post("/results/{result_id}/feedback", response_model=SearchFeedbackResponse)
async def search_feedback(
    result_id: str,
    feedback_request: SearchFeedbackRequest,
    db: AsyncSession = Depends(get_session),
    ctx: SecurityContext = Depends(resolve_current_user),
) -> SearchFeedbackResponse:
    return await submit_feedback(db, result_id, feedback_request, ctx)
