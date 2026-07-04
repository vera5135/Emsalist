"""P0.5 — Canonical precedent models."""
from __future__ import annotations

from pydantic import BaseModel, Field


class CanonicalPrecedent(BaseModel):
    precedent_id: str = ""
    case_id: str = ""
    canonical_key: str = ""

    source_type: str = ""        # official_yargitay | legal_brain | user_uploaded | deterministic_fallback | ai_suggested
    source_ref: str = ""
    official_source_url: str = ""

    court: str = ""
    chamber: str = ""
    decision_type: str = ""
    docket_number: str = ""
    decision_number: str = ""
    decision_date: str = ""
    normalized_docket_number: str = ""
    normalized_decision_number: str = ""
    normalized_decision_date: str = ""

    title: str = ""
    summary: str = ""
    holding: str = ""
    full_text: str = ""
    full_text_hash: str = ""
    source_text_hash: str = ""

    verification_status: str = "unverified"      # verified | partially_verified | unverified | invalid
    authority_status: str = "persuasive"          # authoritative | persuasive | fallback_only | prohibited
    relevance_status: str = "partially_relevant"  # directly_relevant | partially_relevant | irrelevant | insufficient_facts
    selection_status: str = "candidate"            # candidate | accepted | rejected | used_in_petition | not_used
    duplicate_status: str = "unique"               # unique | duplicate | possible_duplicate
    duplicate_of: str = ""

    related_issue_node_ids: list[str] = Field(default_factory=list)
    related_relief_node_ids: list[str] = Field(default_factory=list)
    supporting_claims: list[str] = Field(default_factory=list)
    contradicting_claims: list[str] = Field(default_factory=list)
    usable_arguments: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    created_at: str = ""
    updated_at: str = ""


class PrecedentAuthority(BaseModel):
    version: str = "p0.5"
    generated_at: str = ""
    source_fingerprint: str = ""
    records: list[CanonicalPrecedent] = Field(default_factory=list)
    accepted_ids: list[str] = Field(default_factory=list)
    rejected_ids: list[str] = Field(default_factory=list)
    used_in_petition_ids: list[str] = Field(default_factory=list)
    duplicate_groups: list[list[str]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary: dict = Field(default_factory=dict)


class PrecedentSelectRequest(BaseModel):
    case_id: str = Field(min_length=1)
    precedent_id: str = Field(min_length=1)
    selected: bool = True
    reason: str = ""


class PrecedentAuditRequest(BaseModel):
    case_id: str = Field(min_length=1)
    precedent_ids: list[str] = Field(default_factory=list)


class PrecedentAuthorityResponse(BaseModel):
    case_id: str = ""
    authority: PrecedentAuthority = Field(default_factory=PrecedentAuthority)
    accepted_precedents: list[CanonicalPrecedent] = Field(default_factory=list)
    rejected_precedents: list[CanonicalPrecedent] = Field(default_factory=list)
    precedent_warnings: list[str] = Field(default_factory=list)
