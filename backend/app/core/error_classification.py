"""P1.10.6 — Centralized error classification with safe client responses."""
from __future__ import annotations

import asyncio
import errno
from dataclasses import dataclass
from enum import Enum
from typing import Any

from fastapi.exceptions import HTTPException as FastAPIHTTPException

from app.core.correlation import get_correlation_id, generate_correlation_id


class ErrorCategory(Enum):
    VALIDATION_ERROR = "validation_error"
    AUTHENTICATION_ERROR = "authentication_error"
    AUTHORIZATION_ERROR = "authorization_error"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    EXTERNAL_SERVICE_UNAVAILABLE = "external_service_unavailable"
    DATABASE_UNAVAILABLE = "database_unavailable"
    QUEUE_UNAVAILABLE = "queue_unavailable"
    BACKUP_FAILED = "backup_failed"
    RESTORE_FAILED = "restore_failed"
    INSUFFICIENT_DISK_SPACE = "insufficient_disk_space"
    FILESYSTEM_ERROR = "filesystem_error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    INTERNAL_ERROR = "internal_error"


@dataclass(frozen=True)
class CategoryConfig:
    safe_code: str
    http_status: int
    user_safe_message: str
    retryable: bool = False
    log_level: str = "error"


CATEGORY_CONFIG: dict[ErrorCategory, CategoryConfig] = {
    ErrorCategory.VALIDATION_ERROR: CategoryConfig(
        safe_code="VALIDATION_ERROR",
        http_status=422,
        user_safe_message="The request contains invalid data",
    ),
    ErrorCategory.AUTHENTICATION_ERROR: CategoryConfig(
        safe_code="AUTHENTICATION_ERROR",
        http_status=401,
        user_safe_message="Authentication required",
    ),
    ErrorCategory.AUTHORIZATION_ERROR: CategoryConfig(
        safe_code="AUTHORIZATION_ERROR",
        http_status=403,
        user_safe_message="Access denied",
    ),
    ErrorCategory.NOT_FOUND: CategoryConfig(
        safe_code="NOT_FOUND",
        http_status=404,
        user_safe_message="The requested resource was not found",
    ),
    ErrorCategory.CONFLICT: CategoryConfig(
        safe_code="CONFLICT",
        http_status=409,
        user_safe_message="The request conflicts with the current state",
    ),
    ErrorCategory.RATE_LIMITED: CategoryConfig(
        safe_code="RATE_LIMITED",
        http_status=429,
        user_safe_message="Too many requests, please try again later",
        retryable=True,
        log_level="warning",
    ),
    ErrorCategory.EXTERNAL_SERVICE_UNAVAILABLE: CategoryConfig(
        safe_code="EXTERNAL_SERVICE_UNAVAILABLE",
        http_status=502,
        user_safe_message="An external service is currently unavailable",
        retryable=True,
        log_level="warning",
    ),
    ErrorCategory.DATABASE_UNAVAILABLE: CategoryConfig(
        safe_code="DATABASE_UNAVAILABLE",
        http_status=503,
        user_safe_message="The service is temporarily unavailable",
        retryable=True,
        log_level="error",
    ),
    ErrorCategory.QUEUE_UNAVAILABLE: CategoryConfig(
        safe_code="QUEUE_UNAVAILABLE",
        http_status=503,
        user_safe_message="The service is temporarily unavailable",
    ),
    ErrorCategory.BACKUP_FAILED: CategoryConfig(
        safe_code="BACKUP_FAILED",
        http_status=500,
        user_safe_message="Backup operation failed",
    ),
    ErrorCategory.RESTORE_FAILED: CategoryConfig(
        safe_code="RESTORE_FAILED",
        http_status=500,
        user_safe_message="Restore operation failed",
    ),
    ErrorCategory.INSUFFICIENT_DISK_SPACE: CategoryConfig(
        safe_code="INSUFFICIENT_DISK_SPACE",
        http_status=507,
        user_safe_message="Insufficient storage space",
    ),
    ErrorCategory.FILESYSTEM_ERROR: CategoryConfig(
        safe_code="FILESYSTEM_ERROR",
        http_status=500,
        user_safe_message="A filesystem error occurred",
    ),
    ErrorCategory.TIMEOUT: CategoryConfig(
        safe_code="TIMEOUT",
        http_status=504,
        user_safe_message="The operation timed out",
        retryable=True,
        log_level="warning",
    ),
    ErrorCategory.CANCELLED: CategoryConfig(
        safe_code="CANCELLED",
        http_status=499,
        user_safe_message="The operation was cancelled",
        log_level="warning",
    ),
    ErrorCategory.INTERNAL_ERROR: CategoryConfig(
        safe_code="INTERNAL_ERROR",
        http_status=500,
        user_safe_message="An unexpected error occurred",
    ),
}


def classify_exception(exc: BaseException) -> ErrorCategory:
    """Classify an exception into one of the known error categories."""
    exc_type = type(exc).__name__
    exc_msg = str(exc).lower()

    if isinstance(exc, FastAPIHTTPException):
        code = exc.status_code
        if code == 401:
            return ErrorCategory.AUTHENTICATION_ERROR
        if code == 403:
            return ErrorCategory.AUTHORIZATION_ERROR
        if code == 404:
            return ErrorCategory.NOT_FOUND
        if code == 409:
            return ErrorCategory.CONFLICT
        if code == 422:
            return ErrorCategory.VALIDATION_ERROR
        if code == 429:
            return ErrorCategory.RATE_LIMITED
        return ErrorCategory.INTERNAL_ERROR

    if isinstance(exc, ValueError):
        return ErrorCategory.VALIDATION_ERROR

    if isinstance(exc, KeyError):
        return ErrorCategory.VALIDATION_ERROR

    if isinstance(exc, PermissionError):
        return ErrorCategory.AUTHORIZATION_ERROR

    if isinstance(exc, TimeoutError):
        return ErrorCategory.TIMEOUT

    if isinstance(exc, ConnectionError):
        return ErrorCategory.DATABASE_UNAVAILABLE

    if isinstance(exc, asyncio.CancelledError):
        return ErrorCategory.CANCELLED

    if isinstance(exc, OSError):
        if getattr(exc, "errno", None) == errno.ENOSPC:
            return ErrorCategory.INSUFFICIENT_DISK_SPACE
        return ErrorCategory.FILESYSTEM_ERROR

    if "cancelled" in exc_type.lower() or "cancel" in exc_type.lower():
        return ErrorCategory.CANCELLED

    if "timeout" in exc_msg or "timed out" in exc_msg:
        return ErrorCategory.TIMEOUT

    if "disk" in exc_msg and ("full" in exc_msg or "space" in exc_msg or "enospc" in exc_msg):
        return ErrorCategory.INSUFFICIENT_DISK_SPACE

    if "database" in exc_msg or "db" in exc_msg or "sql" in exc_msg:
        return ErrorCategory.DATABASE_UNAVAILABLE

    if "connection" in exc_msg and ("refused" in exc_msg or "reset" in exc_msg):
        return ErrorCategory.EXTERNAL_SERVICE_UNAVAILABLE

    if "backup" in exc_msg:
        return ErrorCategory.BACKUP_FAILED

    if "restore" in exc_msg:
        return ErrorCategory.RESTORE_FAILED

    return ErrorCategory.INTERNAL_ERROR


def build_error_response(
    exc: BaseException,
    correlation_id: str | None = None,
    include_debug: bool = False,
) -> dict[str, Any]:
    """Build a safe error response dict suitable for JSON serialization."""
    category = classify_exception(exc)
    config = CATEGORY_CONFIG[category]

    cid = correlation_id or get_correlation_id() or generate_correlation_id()

    body: dict[str, Any] = {
        "error": {
            "code": config.safe_code,
            "message": config.user_safe_message,
            "correlation_id": cid,
        }
    }
    body["error"]["_http_status"] = config.http_status

    if include_debug:
        from app.core.redaction import redact_exception
        body["error"]["_debug"] = {
            "category": category.value,
            "exception_type": type(exc).__name__,
            "exception_message": redact_exception(exc),
            "retryable": config.retryable,
        }

    return body
