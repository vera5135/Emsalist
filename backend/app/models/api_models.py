"""P1.12 — API contract and shared response models."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: Any | None = Field(default=None, description="Optional structured details")
    request_id: str = Field(default="", description="Correlation ID for request tracing")


class ErrorResponse(BaseModel):
    error: ErrorDetail


class PaginationMeta(BaseModel):
    limit: int = Field(default=20, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)
    has_more: bool = Field(default=False)


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T] = Field(default_factory=list)
    pagination: PaginationMeta = Field(default_factory=PaginationMeta)


class CapabilitiesResponse(BaseModel):
    api_version: str = Field(default="v1")
    features: dict[str, bool] = Field(default_factory=dict)
    limits: dict[str, Any] = Field(default_factory=dict)


class HealthStatus(BaseModel):
    status: str
    service: str
    components: dict[str, Any] = Field(default_factory=dict)


class ReadyStatus(BaseModel):
    status: str
    checks: dict[str, dict[str, str]] = Field(default_factory=dict)


class TimestampedModel(BaseModel):
    created_at: str | None = Field(default=None)
    updated_at: str | None = Field(default=None)


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


KNOWN_ERROR_CODES = frozenset({
    "VALIDATION_ERROR",
    "AUTHENTICATION_REQUIRED",
    "INVALID_CREDENTIALS",
    "TOKEN_INVALID",
    "TOKEN_EXPIRED",
    "ACCESS_DENIED",
    "RESOURCE_NOT_FOUND",
    "CASE_NOT_FOUND",
    "DOCUMENT_NOT_FOUND",
    "INVALID_FILE",
    "FILE_TOO_LARGE",
    "UNSUPPORTED_FILE_TYPE",
    "DUPLICATE_DOCUMENT",
    "CONFLICT",
    "RATE_LIMITED",
    "SERVICE_UNAVAILABLE",
    "INTERNAL_ERROR",
    "JOB_NOT_FOUND",
    "JOB_CANNOT_CANCEL",
    "EXPORT_FAILED",
    "BACKUP_FAILED",
    "RESTORE_FAILED",
})
