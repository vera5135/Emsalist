"""P2.6 — Legal source backbone API contract models."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SourceRecordResponse(BaseModel):
    id: str
    source_type: str
    canonical_key: str
    title: str
    issuing_authority: str
    court: str
    chamber: str
    case_number: str
    decision_number: str
    decision_date: str
    publication_date: str
    effective_date: str
    repeal_date: str
    official_url: str
    jurisdiction: str
    verification_status: str
    temporal_status: str
    current_version_id: str | None = None
    version: int
    created_at: str
    updated_at: str


class SourceRecordListResponse(BaseModel):
    items: list[SourceRecordResponse] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0
    has_more: bool = False


class SourceVersionResponse(BaseModel):
    id: str
    source_record_id: str
    version_label: str
    content_hash: str
    retrieval_method: str
    parser_version: str
    valid_from: str
    valid_to: str
    supersedes_version_id: str | None = None
    status: str
    retrieved_at: str


class SourceParagraphResponse(BaseModel):
    id: str
    source_version_id: str
    paragraph_index: int
    heading_path: str
    text: str
    page: int | None = None
    article_number: str
    embedding_status: str


class SourceRelationshipResponse(BaseModel):
    id: str
    source_record_id: str
    related_source_record_id: str
    relationship_type: str
    verification_status: str
    created_at: str


class SourceRelationshipCreateRequest(BaseModel):
    related_source_record_id: str = Field(min_length=1, max_length=32)
    relationship_type: str = Field(min_length=1, max_length=30)
    evidence: str = Field(default="", max_length=500)


# --- Ingestion / verification (editor/admin) ------------------------------
class SourceIngestRequest(BaseModel):
    source_type: str = Field(min_length=1, max_length=50)
    title: str = Field(default="", max_length=1000)
    raw_text: str = Field(min_length=1, max_length=5_000_000)
    official_url: str = Field(default="", max_length=1000)
    issuing_authority: str = Field(default="", max_length=200)
    court: str = Field(default="", max_length=120)
    chamber: str = Field(default="", max_length=120)
    case_number: str = Field(default="", max_length=80)
    decision_number: str = Field(default="", max_length=80)
    decision_date: str = Field(default="", max_length=20)
    publication_date: str = Field(default="", max_length=20)
    number: str = Field(default="", max_length=80)
    effective_date: str = Field(default="", max_length=20)


class SourceIngestResponse(BaseModel):
    source_record_id: str
    source_version_id: str
    canonical_key: str
    verification_status: str
    outcome: str


class SourceVerifyRequest(BaseModel):
    target_status: str = Field(min_length=1, max_length=30)
    notes: str = Field(default="", max_length=500)
    evidence_url: str = Field(default="", max_length=1000)


class ResolveConflictRequest(BaseModel):
    target_status: str = Field(default="editor_verified", max_length=30)
    notes: str = Field(default="", max_length=500)


# --- Case source usage ----------------------------------------------------
class SourceUsageCreateRequest(BaseModel):
    source_record_id: str = Field(min_length=1, max_length=32)
    source_version_id: str = Field(min_length=1, max_length=32)
    source_paragraph_id: str | None = Field(default=None, max_length=32)
    usage_type: str = Field(default="reference", max_length=30)
    reason: str = Field(default="", max_length=500)


class SourceUsageResponse(BaseModel):
    id: str
    case_id: str
    source_record_id: str
    source_version_id: str
    source_paragraph_id: str | None = None
    usage_type: str
    reason: str
    relevance_score: float | None = None
    used_in_final_draft: bool
    # Denormalized display fields for the client:
    source_title: str = ""
    source_type: str = ""
    court: str = ""
    decision_date: str = ""
    case_number: str = ""
    decision_number: str = ""
    verification_status: str = ""
    temporal_status: str = ""
    official_url: str = ""
    selected_paragraph: str = ""
    created_at: str = ""


class SourceUsageListResponse(BaseModel):
    items: list[SourceUsageResponse] = Field(default_factory=list)


# --- Official source tracking ---------------------------------------------
class OfficialTrackingItem(BaseModel):
    source_id: str
    title: str
    source_type: str
    official_url: str
    last_checked_at: str | None = None
    last_successful_check_at: str | None = None
    content_fingerprint: str = ""
    temporal_status: str = ""
    verification_status: str = ""
    new_version_detected: bool = False
    latest_version_id: str | None = None
    change_summary: str | None = None
    affected_case_count: int = 0
    affected_draft_count: int = 0
    affected_draft_supported: bool = False
    requires_review: bool = False


class OfficialTrackingResponse(BaseModel):
    items: list[OfficialTrackingItem] = Field(default_factory=list)


# --- Review queue ---------------------------------------------------------
class SourceReviewItem(BaseModel):
    source_id: str
    title: str
    source_type: str
    verification_status: str
    canonical_key: str
    updated_at: str


class SourceReviewListResponse(BaseModel):
    items: list[SourceReviewItem] = Field(default_factory=list)
