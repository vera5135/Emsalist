"""P2.7/P2 Core — Hybrid search and dynamic precedent pool contracts."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.case_models import CaseSearchProfileResponse


# ── Request models ────────────────────────────────────────────────────────────

class LegalSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="Arama sorgusu metni")
    case_id: str | None = Field(None, description="Opsiyonel case baglami")
    official_only: bool = Field(False, description="Sadece resmi kaynaklarda ara")
    source_types: list[str] = Field(default_factory=list, description="Kaynak turleri filtresi")
    date_range: tuple[str, str] | None = Field(None, description="Tarih araligi (baslangic, bitis)")
    court: str | None = Field(None, description="Mahkeme adi filtresi")
    limit: int = Field(20, ge=1, le=100, description="Sayfa basina sonuc sayisi")
    cursor: str | None = Field(None, description="Sayfalama imleci")


class DynamicPrecedentPoolRequest(BaseModel):
    """One bounded case-to-corpus-to-shortlist operation."""

    case_id: str | None = None
    case_text: str = Field(
        min_length=20,
        max_length=20_000,
        description="Avukatın doğal dille anlattığı olay ve uyuşmazlık özeti",
    )
    preferred_relief: list[str] = Field(default_factory=list, max_length=8)
    max_queries: int = Field(default=6, ge=3, le=6)
    max_candidates: int = Field(default=50, ge=10, le=50)
    shortlist_size: int = Field(default=12, ge=3, le=15)

    @field_validator("case_text")
    @classmethod
    def normalize_case_text(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("preferred_relief")
    @classmethod
    def normalize_relief(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = " ".join(value.split())
            key = cleaned.casefold()
            if cleaned and key not in seen:
                seen.add(key)
                result.append(cleaned)
        return result


# ── Response models ───────────────────────────────────────────────────────────

class LegalSearchResult(BaseModel):
    result_id: str = Field(..., description="Signed opaque result identifier")
    source_id: str = Field(..., description="SourceRecord.id")
    source_version_id: str = Field(..., description="Exact SourceVersion.id for this result")
    source_paragraph_id: str = Field(..., description="SourceParagraph.id for the matched paragraph")
    source_type: str = Field("", description="Source type")
    title: str = Field("", description="Source title")
    court: str = Field("", description="Court")
    chamber: str = Field("", description="Chamber")
    case_number: str = Field("", description="Case/esas number")
    decision_number: str = Field("", description="Decision number")
    decision_date: str = Field("", description="Decision date")
    official_url: str = Field("", description="Official URL")
    paragraph_snippet: str = Field("", description="First ~300 chars of matched paragraph")
    article_number: str = Field("", description="Article number")
    article_kind: str = Field("", description="Article kind (regular/additional/provisional/repeated)")
    article_label: str = Field("", description="Article display label")
    article_locator_key: str = Field("", description="Article locator key")
    verification_status: str = Field("", description="Resolved effective verification status")
    temporal_status: str = Field("", description="Temporal validity status")
    final_score: float = Field(0.0, description="Final weighted relevance score 0-1")
    lexical_score: float = Field(0.0, description="Lexical match score 0-1")
    semantic_score: float | None = Field(None, description="Cosine similarity score or None")
    authority_score: float = Field(0.0, description="Trust/verification authority score 0-1")
    temporal_score: float = Field(0.0, description="Temporal relevance score 0-1")
    case_context_score: float = Field(0.0, description="Case context rerank score 0-1")
    match_reasons: list[str] = Field(default_factory=list, description="Turkish deterministic match reasons")
    semantic_available: bool = Field(False, description="Was semantic search configured/available")
    degraded_mode: bool = Field(False, description="Did semantic search degrade to lexical")


class LegalSearchResponse(BaseModel):
    results: list[LegalSearchResult] = Field(default_factory=list)
    total: int = Field(0)
    has_more: bool = Field(False)
    next_cursor: str | None = Field(None)
    semantic_available: bool = Field(False)
    degraded_mode: bool = Field(False)
    query_id: str | None = Field(None)
    index_version: str = Field("")


class DynamicPrecedentIngestionRun(BaseModel):
    run_id: str = ""
    query: str
    budget: int = Field(ge=1, le=50)
    status: str
    discovered: int = 0
    fetched: int = 0
    ingested: int = 0
    duplicate: int = 0
    new_version: int = 0
    conflict: int = 0
    failed: int = 0
    safe_error_code: str = ""


DynamicPoolStatus = Literal[
    "completed",
    "completed_with_errors",
    "degraded_existing_corpus",
]


class DynamicPrecedentPoolResponse(BaseModel):
    pool_id: str | None = None
    profile: CaseSearchProfileResponse
    provider_code: str = "yargitay"
    provider_status: DynamicPoolStatus
    candidate_cap: int = Field(ge=10, le=50)
    ingestion_runs: list[DynamicPrecedentIngestionRun] = Field(default_factory=list)
    total_discovered: int = 0
    total_ingested: int = 0
    total_duplicate: int = 0
    total_failed: int = 0
    shortlist: LegalSearchResponse


class PrecedentPoolSummary(BaseModel):
    id: str
    case_id: str
    provider_code: str
    provider_status: str
    status: str
    candidate_cap: int
    total_discovered: int = 0
    total_ingested: int = 0
    total_duplicate: int = 0
    total_failed: int = 0
    safe_error_code: str = ""
    profile_summary: dict = Field(default_factory=dict)
    started_at: str
    completed_at: str | None = None


class PrecedentPoolDetail(PrecedentPoolSummary):
    query_strategies: list[dict] = Field(default_factory=list)
    source_ingestion_run_ids: list[str] = Field(default_factory=list)
    planner_version: str = ""
    model_version: str = ""


class PrecedentPoolDecisionResponse(BaseModel):
    id: str
    pool_id: str
    source_record_id: str
    source_version_id: str
    selected_source_paragraph_ids: list[str] = Field(default_factory=list)
    retrieval_rank: int
    scores: dict = Field(default_factory=dict)
    selection_state: str
    duplicate_of_decision_id: str | None = None
    match_reasons: list[str] = Field(default_factory=list)
    title: str = ""
    court: str = ""
    chamber: str = ""
    case_number: str = ""
    decision_number: str = ""
    decision_date: str = ""
    official_url: str = ""
    relevant_paragraph: str = ""


class AnalyzePrecedentPoolRequest(BaseModel):
    decision_ids: list[str] = Field(default_factory=list, max_length=15)
    force: bool = False


class PrecedentAnalysisResponse(BaseModel):
    id: str
    pool_id: str
    pool_decision_id: str
    source_record_id: str
    source_version_id: str
    provider: str
    model_version: str
    prompt_version: str
    schema_version: str
    source_fingerprint: str
    output_fingerprint: str
    status: str
    stale: bool
    analysis: dict = Field(default_factory=dict)
    provenance: list[dict] = Field(default_factory=list)
    created_at: str


class PrecedentAnalysisListResponse(BaseModel):
    items: list[PrecedentAnalysisResponse] = Field(default_factory=list)


# ── Similar search ────────────────────────────────────────────────────────────

class SimilarSearchRequest(BaseModel):
    source_id: str = Field(..., description="Reference source ID")
    source_paragraph_id: str | None = Field(None, description="Optional reference paragraph ID")
    limit: int = Field(10, ge=1, le=50)


class SimilarSearchResponse(BaseModel):
    results: list[LegalSearchResult] = Field(default_factory=list)
    similarity_basis: str = Field("")


# ── Opposing search ───────────────────────────────────────────────────────────

class OpposingSearchRequest(BaseModel):
    source_id: str = Field(...)


class OpposingSearchResponse(BaseModel):
    results: list[LegalSearchResult] = Field(default_factory=list)
    opposition_basis: str = Field("")


# ── Suggestions ───────────────────────────────────────────────────────────────

class SearchSuggestionResponse(BaseModel):
    suggestions: list[str] = Field(default_factory=list)


# ── Feedback ──────────────────────────────────────────────────────────────────

FeedbackType = Literal[
    "relevant", "irrelevant", "valuable_opposing",
    "wrong_metadata", "duplicate", "used_in_draft",
]


class SearchFeedbackRequest(BaseModel):
    feedback_type: FeedbackType = Field(..., description="Controlled feedback type")
    query_id: str = Field(..., description="Required search query ID")


class SearchFeedbackResponse(BaseModel):
    acknowledged: bool = Field(True)
    feedback_id: str | None = Field(None)
