"""Pydantic contracts for optional AI-assisted legal intelligence endpoints."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AIModelMixin(BaseModel):
    ai_used: bool = False
    warnings: list[str] = Field(default_factory=list)


class CaseEnrichmentRequest(BaseModel):
    case_id: str = Field(min_length=1)
    case_text: str = Field(min_length=10)
    practice_area: str | None = "auto"
    use_gemini: bool = True

    @field_validator("case_text", "practice_area")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return " ".join(value.split()) if value else value


class CaseEnrichmentResponse(AIModelMixin):
    original_case_text: str
    enriched_case_text: str
    detected_practice_area: str
    detected_case_type: str
    legal_theory: list[str] = Field(default_factory=list)
    confirmed_facts: list[str] = Field(default_factory=list)
    inferred_facts: list[str] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    critical_questions: list[str] = Field(default_factory=list)
    search_keywords: list[str] = Field(default_factory=list)
    yargitay_query_templates: list[str] = Field(default_factory=list)
    legal_brain_query: str = ""
    relevant_codes: list[str] = Field(default_factory=list)
    relevant_articles: list[str] = Field(default_factory=list)
    blocked_topics: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    petition_strategy_hint: str = ""
    confidence: int = Field(default=0, ge=0, le=100)


class LegalQuestionRequest(BaseModel):
    case_id: str = Field(min_length=1)
    case_text: str = Field(min_length=10)
    case_enrichment: dict[str, Any] = Field(default_factory=dict)
    use_gemini: bool = True

    @field_validator("case_text")
    @classmethod
    def normalize_case_text(cls, value: str) -> str:
        return " ".join(value.split())


class LegalQuestionItem(BaseModel):
    id: str
    question: str
    why_needed: str
    suggested_answers: list[str] = Field(default_factory=list)


class LegalQuestionResponse(AIModelMixin):
    questions: list[LegalQuestionItem]


class SearchQualityRequest(BaseModel):
    case_id: str = Field(min_length=1)
    case_text: str = Field(min_length=10)
    case_enrichment: dict[str, Any] = Field(default_factory=dict)
    use_gemini: bool = True

    @field_validator("case_text")
    @classmethod
    def normalize_case_text(cls, value: str) -> str:
        return " ".join(value.split())


class SearchQualityResponse(AIModelMixin):
    yargitay_queries: list[str] = Field(default_factory=list)
    legal_brain_query: str = ""
    must_include_terms: list[str] = Field(default_factory=list)
    should_include_terms: list[str] = Field(default_factory=list)
    blocked_terms: list[str] = Field(default_factory=list)
    ranking_boost_terms: list[str] = Field(default_factory=list)


class SourceAuditRequest(BaseModel):
    case_id: str = Field(min_length=1)
    case_enrichment: dict[str, Any] = Field(default_factory=dict)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    use_gemini: bool = True


class AuditedSource(BaseModel):
    source_id: str
    is_directly_relevant: bool
    use_in_petition: bool
    relevance_score: int = Field(ge=0, le=100)
    reason: str
    source_rejected_reason: str = ""


class SourceAuditResponse(AIModelMixin):
    audited_sources: list[AuditedSource]


class PrecedentAuditRequest(BaseModel):
    case_id: str = Field(min_length=1)
    case_text: str = Field(default="", max_length=20000)
    case_enrichment: dict[str, Any] = Field(default_factory=dict)
    precedents: list[dict[str, Any]] = Field(default_factory=list)
    use_gemini: bool = True


class AuditedPrecedent(BaseModel):
    decision_id: str
    is_duplicate: bool = False
    alignment: Literal["lehe", "aleyhe", "riskli", "nötr"] = "nötr"
    use_in_petition: bool = True
    similarity_reason: str = ""
    risk_reason: str = ""
    petition_usage_paragraph: str = ""


class PrecedentAuditResponse(AIModelMixin):
    audited_precedents: list[AuditedPrecedent]


class DraftAuditRequest(BaseModel):
    case_id: str = Field(min_length=1)
    case_text: str = Field(default="", max_length=20000)
    draft_text: str = Field(min_length=10)
    case_enrichment: dict[str, Any] = Field(default_factory=dict)
    selected_decisions: list[dict[str, Any]] = Field(default_factory=list)
    use_gemini: bool = True


class DraftAuditResponse(AIModelMixin):
    quality_score: int = Field(ge=0, le=100)
    critical_issues: list[str] = Field(default_factory=list)
    major_issues: list[str] = Field(default_factory=list)
    minor_issues: list[str] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    source_problems: list[str] = Field(default_factory=list)
    precedent_problems: list[str] = Field(default_factory=list)
    petition_language_problems: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    ready_for_lawyer_review: bool = False
    can_refine: bool = True


class DraftRefineRequest(BaseModel):
    case_id: str = Field(min_length=1)
    case_text: str = Field(default="", max_length=20000)
    draft_text: str = Field(min_length=10)
    case_enrichment: dict[str, Any] = Field(default_factory=dict)
    selected_decisions: list[dict[str, Any]] = Field(default_factory=list)
    use_gemini: bool = True


class DraftRefineResponse(AIModelMixin):
    refined_draft: str
    accepted: bool
    validator_warnings: list[str] = Field(default_factory=list)
    quality_score: int = Field(default=0, ge=0, le=100)
