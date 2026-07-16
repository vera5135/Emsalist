"""Public, explainable P2.8 API contracts (no hidden reasoning fields)."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class LegalIssueUpdateRequest(BaseModel):
    version: int = Field(ge=1)
    status: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=20000)


class EvidenceLinkRequest(BaseModel):
    claim_id: str = Field(min_length=1, max_length=32)
    evidence_id: str = Field(min_length=1, max_length=32)
    relation_type: str = Field(pattern="^(evidence_supports_claim|evidence_contradicts_claim)$")


class SourceLinkRequest(BaseModel):
    source_record_id: str = Field(min_length=1, max_length=32)
    source_version_id: str = Field(min_length=1, max_length=32)
    source_paragraph_id: str = Field(min_length=1, max_length=32)
    relation_type: str = Field(default="source_governs_issue", pattern="^source_governs_issue$")


class RebuildRequest(BaseModel):
    prompt_version: str = Field(default="p2.8b-legal-reasoning-1", max_length=40)


class LegalIssueResponse(BaseModel):
    id: str
    case_id: str
    parent_issue_id: str | None = None
    issue_code: str
    title: str
    description: str
    status: str
    confidence: float | None = None
    support_state: str
    stale: bool = False
    version: int


class ReasoningRunResponse(BaseModel):
    id: str
    case_id: str
    memory_revision_id: str
    source_fingerprint: str
    provider: str
    model_version: str
    prompt_version: str
    output_hash: str
    status: str
    stale: bool
    safe_summary: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class GraphResponse(BaseModel):
    case_id: str
    stale: bool
    issues: list[dict[str, Any]] = Field(default_factory=list)
    fact_links: list[dict[str, Any]] = Field(default_factory=list)
    evidence_links: list[dict[str, Any]] = Field(default_factory=list)
    source_links: list[dict[str, Any]] = Field(default_factory=list)
    risk_links: list[dict[str, Any]] = Field(default_factory=list)
    dependencies: list[dict[str, Any]] = Field(default_factory=list)
    burdens: list[dict[str, Any]] = Field(default_factory=list)
    counterarguments: list[dict[str, Any]] = Field(default_factory=list)
    missing_information: list[dict[str, Any]] = Field(default_factory=list)
    unsupported_claims: list[dict[str, Any]] = Field(default_factory=list)
