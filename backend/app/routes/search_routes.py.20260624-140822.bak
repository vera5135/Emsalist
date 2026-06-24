"""Search query builder endpoints."""

from fastapi import APIRouter

from app.models.case_models import SearchBuildRequest, SearchBuildResponse
from app.services.search_builder import search_builder

router = APIRouter(prefix="/search", tags=["Search"])


@router.post("/build", response_model=SearchBuildResponse)
def build_search_queries(request: SearchBuildRequest) -> SearchBuildResponse:
    return search_builder.build(request)
