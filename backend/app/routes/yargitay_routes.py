"""Yargıtay decision search endpoint."""

from fastapi import APIRouter

from app.models.yargitay_models import YargitaySearchRequest, YargitaySearchResponse
from app.services.yargitay_scraper import yargitay_scraper

router = APIRouter(prefix="/yargitay", tags=["Yargıtay"])


@router.post("/search", response_model=YargitaySearchResponse)
async def search_yargitay(request: YargitaySearchRequest) -> YargitaySearchResponse:
    return await yargitay_scraper.search(
        queries=request.queries,
        max_results=request.max_results,
    )
