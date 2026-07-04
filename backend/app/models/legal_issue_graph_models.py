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
