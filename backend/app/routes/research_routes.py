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
    source_type: str = "unknown"
    official_verification_status: str = "not_verified"
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


class ResearchSourceSummary(BaseModel):
    live_yargitay_count: int = 0
    legal_brain_fallback_count: int = 0
    local_seed_count: int = 0
    official_yargitay_reached: bool = False
    official_yargitay_returned_results: bool = False
    used_fallback: bool = False


class ResearchDebugSourceSummary(BaseModel):
    failure_reason: str = ""
    fallback_source: str = "none"
    raw_live_result_count: int = 0
    parsed_live_result_count: int = 0
    final_live_result_count: int = 0


class ResearchYargitayResponse(BaseModel):
    case_analysis: CaseAnalyzeResponse
    queries: list[str]
    generated_queries: list[str] = Field(default_factory=list)
    attempted_queries: list[str] = Field(default_factory=list)
    fallback_queries: list[str] = Field(default_factory=list)
    attempted_query_count: int = 0
    yargitay_search_started: bool = False
    yargitay_result_count: int = 0
    raw_live_result_count: int = 0
    parsed_live_result_count: int = 0
    final_live_result_count: int = 0
    fallback_query_used: bool = False
    skipped_due_to_rate_limit: bool = False
    failure_reason: str = ""
    user_message: str = ""
    final_precedent_count: int = 0
    live_yargitay_results: list[ResearchDecisionOutput] = Field(default_factory=list)
    fallback_precedents: list[ResearchDecisionOutput] = Field(default_factory=list)
    final_precedents: list[ResearchDecisionOutput] = Field(default_factory=list)
    source_summary: ResearchSourceSummary = Field(default_factory=ResearchSourceSummary)
    debug_source_summary: ResearchDebugSourceSummary = Field(default_factory=ResearchDebugSourceSummary)
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
        case_enrichment=request.case_enrichment,
    )
