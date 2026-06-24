"""Research endpoints that combine analysis, real search, ranking and summaries."""

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator
from typing import Any

from app.models.case_models import CaseAnalyzeResponse
from app.services.research_service import research_service


class ResearchYargitayRequest(BaseModel):
    case_text: str = Field(min_length=10)
    max_results: int = Field(default=5, ge=1, le=100)
    yargitay_query_templates: list[str] = Field(default_factory=list, max_length=20)
    case_enrichment: dict[str, Any] = Field(default_factory=dict)

    @field_validator("case_text")
    @classmethod
    def normalize_case_text(cls, value: str) -> str:
        return " ".join(value.split())


class ResearchDecisionOutput(BaseModel):
    similarity_score: int = Field(ge=0, le=100)
    usefulness_score: str
    source: str
    court: str
    esas_no: str
    karar_no: str
    date: str
    title: str
    detail_url: str
    short_summary: str
    legal_principle: str
    why_relevant: str
    lehe_aleyhe: str
    petition_paragraph: str
    clean_text_preview: str


class ResearchYargitayResponse(BaseModel):
    case_analysis: CaseAnalyzeResponse
    queries: list[str]
    top_decisions: list[ResearchDecisionOutput]
    errors: list[str]


router = APIRouter(prefix="/research", tags=["Araştırma"])


@router.post("/yargitay", response_model=ResearchYargitayResponse)
async def research_yargitay(request: ResearchYargitayRequest) -> dict:
    return await research_service.research_yargitay(
        case_text=request.case_text,
        max_results=request.max_results,
        yargitay_query_templates=request.yargitay_query_templates
        or request.case_enrichment.get("yargitay_query_templates")
        or [],
    )
