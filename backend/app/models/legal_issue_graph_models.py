"""Pydantic models for the Legal Issue Graph v1."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LegalIssue(BaseModel):
    """A single hukuki mesele (legal issue) node in the graph."""

    issue_id: str = ""
    title: str = ""
    issue_type: str = ""
    legal_basis: list[str] = Field(default_factory=list)
    required_facts: list[str] = Field(default_factory=list)
    confirmed_facts: list[str] = Field(default_factory=list)
    uncertain_facts: list[str] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    available_evidence: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    risk_level: str = "low"
    risk_reason: str = ""
    client_questions: list[str] = Field(default_factory=list)
    research_queries: list[str] = Field(default_factory=list)
    petition_argument: str = ""
    drafting_priority: int = 1


class DraftingPlanItem(BaseModel):
    """A single section in the drafting plan."""

    section: str = ""
    use_facts: list[str] = Field(default_factory=list)
    argument: str = ""


class LegalIssueGraph(BaseModel):
    """Top-level graph response."""

    model_version: str = "p0.3"
    canonical: bool = True
    source_fingerprint: str = ""
    case_id: str = ""
    legal_area: str = ""
    case_type: str = ""
    issues: list[LegalIssue] = Field(default_factory=list)
    global_risks: list[str] = Field(default_factory=list)
    next_best_questions: list[str] = Field(default_factory=list)
    research_plan: list[str] = Field(default_factory=list)
    drafting_plan: list[DraftingPlanItem] = Field(default_factory=list)
    legal_grounds: list[LegalGround] = Field(default_factory=list)


# ── P0.4 Legal Ground Models ──────────────────────────────────────────────


class LegalGround(BaseModel):
    ground_id: str = ""
    jurisdiction: str = "tr"
    canonical_legislation_id: str = ""
    canonical_article_id: str = ""
    legislation_code: str = ""
    legislation_name: str = ""
    article: str = ""
    paragraph: str = ""
    subparagraph: str = ""
    verified_article: str = ""
    normalized_citation: str = ""
    title: str = ""
    rule_summary: str = ""
    source_type: str = ""  # profile | enrichment | legal_brain | user | official
    source_ref: str = ""
    source_title: str = ""
    official_source_id: str = ""
    source_url: str = ""
    verification_status: str = "unverified"  # verified | partially_verified | unverified | invalid
    applicability_status: str = "potentially_applicable"  # directly_applicable | potentially_applicable | irrelevant | insufficient_facts
    temporal_status: str = "uncertain"  # current | historical | uncertain
    confidence: int = Field(default=0, ge=0, le=100)
    related_issue_node_ids: list[str] = Field(default_factory=list)
    related_relief_node_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LegalGroundValidationRequest(BaseModel):
    case_id: str = Field(min_length=1)
    legal_grounds: list[dict[str, Any]] = Field(default_factory=list)
    event_date: str = ""


class LegalGroundValidationResponse(BaseModel):
    case_id: str = ""
    registry_version: str = ""
    registry_scope: dict[str, Any] = Field(default_factory=dict)
    normalized_grounds: list[LegalGround] = Field(default_factory=list)
    verified_grounds: list[LegalGround] = Field(default_factory=list)
    unverified_grounds: list[LegalGround] = Field(default_factory=list)
    invalid_grounds: list[LegalGround] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
