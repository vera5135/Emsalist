"""P2.5 — Document pipeline API contract models."""
from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    id: str
    case_id: str
    original_filename: str
    mime_type: str
    extension: str
    size_bytes: int
    document_type: str
    document_type_source: str
    status: str
    analysis_status: str
    support_level: str
    page_count: int
    extracted_text_available: bool
    failure_code: str | None = None
    version: int
    created_at: str
    updated_at: str


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0
    has_more: bool = False


class DocumentPageResponse(BaseModel):
    page_number: int
    text: str
    extraction_status: str


class ExtractionResponse(BaseModel):
    id: str
    document_id: str
    case_id: str
    extraction_type: str
    field_key: str
    value: str
    page_number: int | None = None
    text_span: str
    source_quote: str = ""
    confidence: float
    verification_status: str
    provider_name: str = ""
    provider_model: str = ""
    analysis_run_id: str = ""
    memory_fact_id: str | None = None
    version: int
    created_at: str


class DocumentAnalysisResponse(BaseModel):
    document_id: str
    status: str
    analysis_status: str
    support_level: str
    page_count: int
    extracted_text_available: bool
    document_type: str
    document_type_source: str
    failure_code: str | None = None
    extractions: list[ExtractionResponse] = Field(default_factory=list)


class DocumentTypeUpdateRequest(BaseModel):
    document_type: str = Field(min_length=1, max_length=100)


class MessageResponse(BaseModel):
    message: str
