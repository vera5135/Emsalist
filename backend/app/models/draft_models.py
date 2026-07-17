"""P2.9A — Grounded draft persistence API contracts."""
from __future__ import annotations

from pydantic import BaseModel, Field


class DraftCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    draft_type: str = Field(min_length=1, max_length=40)
    supersedes_draft_id: str | None = Field(default=None, min_length=1, max_length=32)


class DraftUpdateRequest(BaseModel):
    version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    status: str | None = None


class DraftResponse(BaseModel):
    id: str
    case_id: str
    title: str
    draft_type: str
    status: str
    supersedes_draft_id: str | None = None
    paragraph_count: int = 0
    created_by: str = ""
    created_at: str
    updated_at: str
    finalized_at: str | None = None
    version: int


class DraftListResponse(BaseModel):
    items: list[DraftResponse] = Field(default_factory=list)
    total: int = 0


class DraftParagraphCreateRequest(BaseModel):
    paragraph_order: int = Field(ge=1)
    paragraph_type: str = Field(default="body", min_length=1, max_length=40)
    text: str = Field(min_length=1, max_length=50000)


class DraftParagraphUpdateRequest(BaseModel):
    version: int = Field(ge=1)
    text: str | None = Field(default=None, min_length=1, max_length=50000)
    paragraph_type: str | None = Field(default=None, min_length=1, max_length=40)
    paragraph_order: int | None = Field(default=None, ge=1)
    verification_status: str | None = None


class DraftParagraphIssueLinkRequest(BaseModel):
    legal_issue_id: str = Field(min_length=1, max_length=32)


class DraftParagraphIssueLinkResponse(BaseModel):
    id: str
    draft_paragraph_id: str
    legal_issue_id: str
    relation_type: str
    created_at: str
    version: int


class DraftParagraphSourceLinkRequest(BaseModel):
    source_record_id: str = Field(min_length=1, max_length=32)
    source_version_id: str = Field(min_length=1, max_length=32)
    source_paragraph_id: str = Field(min_length=1, max_length=32)
    usage_type: str = Field(default="citation", min_length=1, max_length=30)
    quote_hash: str = Field(min_length=64, max_length=64)


class DraftParagraphSourceLinkResponse(BaseModel):
    id: str
    draft_paragraph_id: str
    source_record_id: str
    source_version_id: str
    source_paragraph_id: str
    usage_type: str
    quote_hash: str
    verification_status: str
    effective_trust: str = ""
    created_at: str
    version: int


class DraftParagraphResponse(BaseModel):
    id: str
    draft_document_id: str
    paragraph_order: int
    paragraph_type: str
    text: str
    verification_status: str
    generated_by: str
    model_name: str = ""
    issue_links: list[DraftParagraphIssueLinkResponse] = Field(default_factory=list)
    source_links: list[DraftParagraphSourceLinkResponse] = Field(default_factory=list)
    created_at: str
    updated_at: str
    version: int


class DraftDetailResponse(DraftResponse):
    paragraphs: list[DraftParagraphResponse] = Field(default_factory=list)


class DraftFinalizeRequest(BaseModel):
    version: int = Field(ge=1)


class DraftFinalizeResponse(BaseModel):
    id: str
    case_id: str
    status: str
    finalized_at: str | None = None
    version: int
    paragraph_count: int
    issue_link_count: int
    source_link_count: int
    marked_source_usage_count: int


class DraftReadinessResponse(BaseModel):
    status: str
    blocked_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, int] = Field(default_factory=dict)


class SectionPlanEntry(BaseModel):
    order: int
    paragraph_type: str
    required: bool
    requires_source: bool
    target_issue_ids: list[str] = Field(default_factory=list)


class DraftPlanResponse(BaseModel):
    draft_id: str
    draft_type: str
    draft_version: int
    readiness_status: str
    sections: list[SectionPlanEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DraftGenerateRequest(BaseModel):
    version: int = Field(ge=1)
    selected_legal_issue_ids: list[str] = Field(default_factory=list)
    selected_source_usage_ids: list[str] = Field(default_factory=list)


class DraftGenerateResponse(BaseModel):
    draft_id: str
    status: str
    version: int
    generation_run_id: str
    provider: str
    model_name: str
    paragraph_count: int
    issue_link_count: int
    source_link_count: int
    metrics: dict[str, int | str | list[str]] = Field(default_factory=dict)


class DraftValidateResponse(BaseModel):
    valid: bool
    blocking_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, int] = Field(default_factory=dict)


class DraftParagraphEditRequest(BaseModel):
    draft_version: int = Field(ge=1)
    paragraph_version: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=50000)


class DraftParagraphRevisionResponse(BaseModel):
    id: str
    draft_paragraph_id: str
    revision_number: int
    change_type: str
    created_by: str = ""
    created_at: str
    text_hash: str
    current_revision: bool = False
    text: str


class DraftParagraphRevisionActionResponse(BaseModel):
    paragraph_id: str
    revision: DraftParagraphRevisionResponse
    verification_status: str
    paragraph_version: int
    draft_version: int
    source_links_marked_needs_review: int = 0


class DraftParagraphRestoreRequest(BaseModel):
    draft_version: int = Field(ge=1)
    paragraph_version: int = Field(ge=1)


class DraftParagraphAcceptRequest(BaseModel):
    draft_version: int = Field(ge=1)
    paragraph_version: int = Field(ge=1)
    revision_id: str = Field(min_length=1, max_length=32)


class DraftParagraphRequestChangesRequest(BaseModel):
    draft_version: int = Field(ge=1)
    paragraph_version: int = Field(ge=1)
    revision_id: str = Field(min_length=1, max_length=32)
    reason_code: str = Field(min_length=1, max_length=50)


class DraftReviewEventResponse(BaseModel):
    id: str
    draft_paragraph_id: str
    paragraph_revision_id: str
    decision: str
    reason_code: str | None = None
    reviewer_user_id: str = ""
    paragraph_version: int
    created_at: str


class DraftReviewActionResponse(BaseModel):
    paragraph_id: str
    verification_status: str
    paragraph_version: int
    draft_version: int
    review_event: DraftReviewEventResponse
