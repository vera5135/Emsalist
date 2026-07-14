"""P2.7 — Hybrid legal search request/response contract models."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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


# ── Similar search ────────────────────────────────────────────────────────────

class SimilarSearchRequest(BaseModel):
    source_id: str = Field(..., description="Reference source ID")
    source_paragraph_id: str | None = Field(None, description="Optional reference paragraph ID")
    limit: int = Field(10, ge=1, le=50)
    filters: dict[str, Any] = Field(default_factory=dict)


class SimilarSearchResponse(BaseModel):
    results: list[LegalSearchResult] = Field(default_factory=list)
    similarity_basis: str = Field("")


# ── Opposing search ───────────────────────────────────────────────────────────

class OpposingSearchRequest(BaseModel):
    source_id: str = Field(...)
    filters: dict[str, Any] = Field(default_factory=dict)


class OpposingSearchResponse(BaseModel):
    results: list[LegalSearchResult] = Field(default_factory=list)
    opposition_basis: str = Field("")


# ── Suggestions ────────────────────────────────────────────────────────────────

class SearchSuggestionResponse(BaseModel):
    suggestions: list[str] = Field(default_factory=list)


# ── Feedback ───────────────────────────────────────────────────────────────────

FeedbackType = Literal[
    "relevant", "irrelevant", "valuable_opposing",
    "wrong_metadata", "duplicate", "used_in_draft",
]


class SearchFeedbackRequest(BaseModel):
    feedback_type: FeedbackType = Field(..., description="Controlled feedback type")
    query_id: str | None = Field(None)


class SearchFeedbackResponse(BaseModel):
    acknowledged: bool = Field(True)
    feedback_id: str | None = Field(None)
