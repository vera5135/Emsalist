"""Contracts for safely ingesting and grounding case documents."""

from typing import Literal

from pydantic import BaseModel, Field


ExtractionStatus = Literal[
    "extracted",
    "partial",
    "ocr_required",
    "conversion_required",
    "unsupported",
    "failed",
]

VerificationStatus = Literal[
    "fact_confirmed",
    "fact_inferred",
    "fact_missing",
    "conflict_detected",
    "ocr_required",
    "manual_review_required",
]


class ExtractedFact(BaseModel):
    fact_key: str
    fact_value: str
    source_document_id: str
    source_file_name: str
    page_number: int | None = None
    excerpt: str
    confidence_score: float = Field(ge=0, le=1)
    verification_status: VerificationStatus


class DocumentConflict(BaseModel):
    fact_key: str
    user_value: str
    document_value: str
    source_document_id: str
    source_file_name: str
    warning: str


class DocumentRecord(BaseModel):
    model_config = {"extra": "allow"}

    document_id: str
    case_id: str = ""
    file_name: str
    safe_file_name: str
    file_extension: str
    mime_type: str
    file_size: int = Field(ge=0)
    content_sha256: str = ""
    upload_time: str
    document_type: str
    detected_document_type: str
    extraction_status: ExtractionStatus
    extraction_warning: str | None = None
    text_length: int = Field(ge=0)
    extracted_text_preview: str
    confidence_score: float = Field(ge=0, le=1)
    extracted_facts: list[ExtractedFact] = Field(default_factory=list)
    conflicts: list[DocumentConflict] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    deleted_at: str | None = None
    restore_deadline: str | None = None


class DocumentAnalyzeRequest(BaseModel):
    case_id: str | None = None
    document_ids: list[str] = Field(default_factory=list, max_length=100)
    user_claims: dict[str, str] = Field(default_factory=dict)
    document_types: dict[str, str] = Field(default_factory=dict)


class DocumentAnalyzeResponse(BaseModel):
    documents: list[DocumentRecord]
    confirmed_facts: list[ExtractedFact]
    conflicts: list[DocumentConflict]
    missing_fields: list[str]
    grounding_ready: bool
    warnings: list[str]
