"""P2.6C — Official provider ingestion API contract models (v2 — safe locators).

Deliberately exposes NO raw fetch/detail/download URL, no stack traces, no
secrets. exact_source runs reference candidates by a provider-generated
external_id (or server-issued candidate_id) resolved by the provider — never
by an arbitrary caller-supplied URL.

SECURITY: extra="forbid" so payloads containing unlisted fields (e.g.
``detail_url``) are rejected fail-closed.
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
    last_run_status: str | None = None
    last_safe_error_code: str = ""


class ProviderListResponse(BaseModel):
    items: list[ProviderInfoResponse] = Field(default_factory=list)


class CreateRunRequest(BaseModel):
    """exact_source runs reference a provider-issued external_id (never a caller-
    supplied URL). The provider resolves the external_id into a safe candidate."""

    model_config = {"extra": "forbid"}

    run_type: str = Field(min_length=1, max_length=30)
    query: str | None = Field(default=None, max_length=500)
    from_date: str | None = Field(default=None, max_length=20)
    to_date: str | None = Field(default=None, max_length=20)
    max_items: int = Field(default=50, ge=1, le=500)
    external_id: str | None = Field(default=None, max_length=128)


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
