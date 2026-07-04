"""P0.6 — Claim-level grounding models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SourceRef(BaseModel):
    source_ref_id: str = ""
    source_type: str = ""  # case_text | user_answer | uploaded_document | legal_issue_graph | legal_ground | precedent | official_source | system_profile
    source_id: str = ""
    case_id: str = ""
    locator: str = ""  # page, paragraph, line, node_id
    excerpt_hash: str = ""
    source_hash: str = ""
    verified: bool = False
    authority_level: str = "none"


class GroundingClaim(BaseModel):
    claim_id: str = ""
    case_id: str = ""
    claim_type: str = ""  # factual | legal | procedural | evidentiary | relief | precedent | risk | qualification
    text: str = ""
    normalized_text: str = ""
    section: str = ""
    paragraph_index: int = 0
    sentence_index: int = 0
    assertion_mode: str = "allegation"  # definite | qualified | allegation | disputed | missing | unsupported
    status: str = "unsupported"  # grounded | partially_grounded | unsupported | contradicted | stale | prohibited
    confidence: int = Field(default=0, ge=0, le=100)
    source_refs: list[SourceRef] = Field(default_factory=list)
    fact_node_ids: list[str] = Field(default_factory=list)
    legal_ground_ids: list[str] = Field(default_factory=list)
    precedent_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    related_issue_node_ids: list[str] = Field(default_factory=list)
    related_relief_node_ids: list[str] = Field(default_factory=list)
    contradiction_ids: list[str] = Field(default_factory=list)
    missing_requirement_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class ClaimGroundingResult(BaseModel):
    version: str = "p0.6"
    generated_at: str = ""
    source_fingerprint: str = ""
    petition_hash: str = ""
    claims: list[GroundingClaim] = Field(default_factory=list)
    source_refs: list[SourceRef] = Field(default_factory=list)
    grounded_claim_ids: list[str] = Field(default_factory=list)
    partially_grounded_claim_ids: list[str] = Field(default_factory=list)
    unsupported_claim_ids: list[str] = Field(default_factory=list)
    contradicted_claim_ids: list[str] = Field(default_factory=list)
    prohibited_claim_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    grounding_ready: bool = False
    summary: dict = Field(default_factory=dict)


class GroundingAnalyzeRequest(BaseModel):
    case_id: str = Field(min_length=1)
    petition_text: str = Field(min_length=10)


class GroundingAnalyzeResponse(BaseModel):
    case_id: str = ""
    grounding: ClaimGroundingResult = Field(default_factory=ClaimGroundingResult)
    grounded_petition_text: str = ""
    raw_petition_text: str = ""
    warnings: list[str] = Field(default_factory=list)
    grounding_ready: bool = False
    summary: dict = Field(default_factory=dict)
