"""Mock decision ranking endpoints."""

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.models.decision_models import DecisionRankRequest, DecisionRankResponse
from app.services.decision_ranker import decision_ranker

router = APIRouter(prefix="/decisions", tags=["Decisions"])


@router.post("/rank", response_model=DecisionRankResponse)
def rank_decisions(
    request: DecisionRankRequest,
    settings: Settings = Depends(get_settings),
) -> DecisionRankResponse:
    return DecisionRankResponse(
        top_decisions=decision_ranker.rank(
            case_text=request.case_text,
            decisions=request.decisions,
            limit=settings.max_ranked_decisions,
        )
    )
