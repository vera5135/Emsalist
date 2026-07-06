
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any


class JsonFormatter(logging.Formatter):

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": getattr(record, "service", ""),
            "environment": getattr(record, "environment", ""),
        }

        for key in (
            "correlation_id", "request_id", "method", "path",
            "status_code", "duration_ms", "tenant_id", "user_id",
            "job_id", "queue_name",
        ):
            val = getattr(record, key, None)
            if val is not None and val != "":
                log_entry[key] = val

        if record.exc_info and record.exc_info[1]:
            log_entry["exception_type"] = type(record.exc_info[1]).__name__
            log_entry["exception_message"] = str(record.exc_info[1])[:500]

        return json.dumps(log_entry, ensure_ascii=False, default=str)


class SafeTextFormatter(logging.Formatter):

    def __init__(self):
        super().__init__(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


class ContextFilter(logging.Filter):

    def __init__(self, service_name: str, environment: str):
        super().__init__()
        self._service = service_name
        self._environment = environment

    def filter(self, record: logging.LogRecord) -> bool:
        record.service = self._service
        record.environment = self._environment
        return True


_configured = False


def _is_test_environment() -> bool:
    return (
        os.environ.get("ENVIRONMENT", "").lower() == "test"
        or "PYTEST_CURRENT_TEST" in os.environ
    )


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    env = os.environ.get("ENVIRONMENT", "development").lower()
    log_level_name = os.environ.get("LOG_LEVEL", "INFO" if env == "production" else "DEBUG").upper()
    log_format = os.environ.get("LOG_FORMAT", "json" if env == "production" else "text").lower()
    service_name = os.environ.get("LOG_SERVICE_NAME", "emsalist-api")

    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stderr)
    if log_format == "json" and not _is_test_environment():
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(SafeTextFormatter())

    root_logger.setLevel(getattr(logging, log_level_name, logging.INFO))
    root_logger.addHandler(handler)
    root_logger.addFilter(ContextFilter(service_name, env))

    for lib in ("sqlalchemy.engine", "asyncio", "aiosqlite", "httpx", "httpcore", "urllib3", "PIL"):
        logging.getLogger(lib).setLevel(logging.WARNING)

    _configure_uvicorn_loggers()

    logging.getLogger(__name__).info(
        "logging_initialized format=%s level=%s env=%s service=%s",
        log_format, log_level_name, env, service_name,
    )


def _configure_uvicorn_loggers() -> None:
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
