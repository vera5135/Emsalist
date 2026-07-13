"""P2.6C — Official provider ingestion API contract models.

Deliberately exposes NO raw provider HTML, no fetch URL ingestion surface, no
stack traces, no secrets — only safe provider metadata, run counters and safe
status/error codes.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ProviderCapabilitiesModel(BaseModel):
    discovery: bool = False
    fetch: bool = False
    parse: bool = False
    incremental: bool = False
    bounded_window: bool = False
    requires_browser: bool = False
    requires_auth: bool = False


class ProviderInfoResponse(BaseModel):
    code: str
    name: str
    enabled: bool
    source_types: list[str] = Field(default_factory=list)
    official_domains: list[str] = Field(default_factory=list)
    capabilities: ProviderCapabilitiesModel
    status: str
    last_run_at: str | None = None
    last_success_at: str | None = None


class ProviderListResponse(BaseModel):
    items: list[ProviderInfoResponse] = Field(default_factory=list)


class CreateRunCandidate(BaseModel):
    detail_url: str = Field(min_length=1, max_length=1000)
    source_type: str = Field(default="", max_length=60)
    download_url: str | None = Field(default=None, max_length=1000)
    external_id: str | None = Field(default=None, max_length=128)


class CreateRunRequest(BaseModel):
    run_type: str = Field(min_length=1, max_length=30)
    query: str | None = Field(default=None, max_length=500)
    from_date: str | None = Field(default=None, max_length=20)
    to_date: str | None = Field(default=None, max_length=20)
    max_items: int = Field(default=50, ge=1, le=500)
    candidate: CreateRunCandidate | None = None


class IngestionRunResponse(BaseModel):
    id: str
    provider_code: str
    run_type: str
    status: str
    discovered_count: int = 0
    fetched_count: int = 0
    ingested_count: int = 0
    duplicate_count: int = 0
    new_version_count: int = 0
    conflict_count: int = 0
    failed_count: int = 0
    last_safe_error_code: str = ""
    created_by: str | None = None
    created_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None


class IngestionRunListResponse(BaseModel):
    items: list[IngestionRunResponse] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0
    has_more: bool = False
