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
    precedent_id: str
    citation: str
    verification_status: str
    similarity_reasons: list[str] = Field(default_factory=list)
    shared_facts: list[str] = Field(default_factory=list)
    shared_legal_issues: list[str] = Field(default_factory=list)
    supported_arguments: list[str] = Field(default_factory=list)
    evidence_connection: list[str] = Field(default_factory=list)
    distinguishing_risks: list[str] = Field(default_factory=list)
    recommended_use: str
    confidence_score: int = Field(ge=0, le=100)


class ResearchYargitayResponse(BaseModel):
    case_analysis: CaseAnalyzeResponse
    queries: list[str]
    generated_queries: list[str] = Field(default_factory=list)
    yargitay_search_started: bool = False
    yargitay_result_count: int = 0
    fallback_query_used: bool = False
    final_precedent_count: int = 0
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
