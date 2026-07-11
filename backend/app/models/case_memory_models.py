"""P2.4 — Structured case memory API contract models."""
from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------
class FactCreateRequest(BaseModel):
    fact_type: str = Field(min_length=1, max_length=80)
    value: str = Field(default="", max_length=20000)
    importance: str = Field(default="medium", max_length=20)
    source_type: str = Field(default="user_message", max_length=40)
    source_id: str = Field(default="", max_length=64)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class FactUpdateRequest(BaseModel):
    version: int = Field(ge=1)
    value: str | None = Field(default=None, max_length=20000)
    importance: str | None = Field(default=None, max_length=20)


class FactResponse(BaseModel):
    id: str
    case_id: str
    fact_type: str
    value: str
    importance: str
    source_type: str
    source_id: str
    confidence: float
    verification_status: str
    version: int
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------
class TimelineCreateRequest(BaseModel):
    event_type: str = Field(default="", max_length=80)
    description: str = Field(min_length=1, max_length=20000)
    event_date: str = Field(default="", max_length=20)
    event_time: str = Field(default="", max_length=12)
    is_approximate: bool = Field(default=False)
    party_reference: str = Field(default="", max_length=200)
    legal_significance: str = Field(default="", max_length=20000)
    source_type: str = Field(default="user_message", max_length=40)
    source_id: str = Field(default="", max_length=64)


class TimelineEventResponse(BaseModel):
    id: str
    case_id: str
    event_type: str
    description: str
    event_date: str
    event_time: str
    is_approximate: bool
    party_reference: str
    legal_significance: str
    verification_status: str
    version: int
    created_at: str


# ---------------------------------------------------------------------------
# Missing information
# ---------------------------------------------------------------------------
class MissingInfoCreateRequest(BaseModel):
    field_key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=200)
    reason_required: str = Field(default="", max_length=20000)
    importance: str = Field(default="medium", max_length=20)
    related_legal_issue: str = Field(default="", max_length=200)
    expected_source: str = Field(default="", max_length=40)
    completion_condition: dict = Field(default_factory=dict)


class MissingInfoResponse(BaseModel):
    id: str
    case_id: str
    field_key: str
    label: str
    reason_required: str
    importance: str
    related_legal_issue: str
    expected_source: str
    status: str
    resolved_by_fact_id: str | None = None
    resolved_at: str | None = None
    version: int
    created_at: str


# ---------------------------------------------------------------------------
# Contradictions
# ---------------------------------------------------------------------------
class ContradictionResolveRequest(BaseModel):
    resolution_fact_id: str = Field(min_length=1, max_length=32)
    note: str = Field(default="", max_length=2000)


class ContradictionResponse(BaseModel):
    id: str
    case_id: str
    contradiction_type: str
    subject_key: str
    description: str
    fact_ids: list[str] = Field(default_factory=list)
    severity: str
    status: str
    resolution_fact_id: str | None = None
    resolution_note: str = ""
    version: int
    created_at: str
    resolved_at: str | None = None


# ---------------------------------------------------------------------------
# Risks
# ---------------------------------------------------------------------------
class RiskCreateRequest(BaseModel):
    risk_type: str = Field(default="procedure", max_length=40)
    severity: str = Field(default="low", max_length=20)
    title: str = Field(min_length=1, max_length=300)
    rationale: str = Field(default="", max_length=20000)
    affected_claim: str = Field(default="", max_length=200)
    supporting_reference: str = Field(default="", max_length=200)
    mitigation: str = Field(default="", max_length=20000)
    related_missing_information: str | None = Field(default=None, max_length=32)


class RiskResponse(BaseModel):
    id: str
    case_id: str
    risk_type: str
    severity: str
    title: str
    rationale: str
    affected_claim: str
    supporting_reference: str
    mitigation: str
    related_missing_information: str | None = None
    status: str
    version: int
    created_at: str


# ---------------------------------------------------------------------------
# Aggregate memory view
# ---------------------------------------------------------------------------
class CaseMemoryResponse(BaseModel):
    case_id: str
    overall_risk_level: str
    facts: list[FactResponse] = Field(default_factory=list)
    timeline: list[TimelineEventResponse] = Field(default_factory=list)
    missing_information: list[MissingInfoResponse] = Field(default_factory=list)
    contradictions: list[ContradictionResponse] = Field(default_factory=list)
    risks: list[RiskResponse] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


class MessageResponse(BaseModel):
    message: str
