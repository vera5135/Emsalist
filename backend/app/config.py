"""Application configuration.

Environment variables intentionally keep the service deployment-friendly while
avoiding a dependency on an external configuration provider at this stage.
"""

from __future__ import annotations

from functools import lru_cache
from os import getenv
from pathlib import Path

from pydantic import BaseModel


class ProductionConfigError(RuntimeError):
    """Raised at startup when production configuration is unsafe."""


_DEFAULT_JWT_SECRETS = frozenset({
    "", "emsalist-local-dev-key-change-in-production",
})

MIN_JWT_SECRET_LENGTH = 32
MAX_UPLOAD_SIZE_BYTES = 15 * 1024 * 1024


class Settings(BaseModel):
    app_name: str = "Emsalist API"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: str = "development"  # development | production | test
    log_level: str = "INFO"  # DEBUG | INFO | WARNING | ERROR
    log_format: str = "text"  # json | text
    log_service_name: str = "emsalist-api"
    max_ranked_decisions: int = 10
    gemini_enabled: bool = False
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: int = 30
    database_url: str = ""
    storage_backend: str = "json"  # json | database | dual
    auth_mode: str = "local"  # local | jwt
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "emsalist"
    jwt_access_token_minutes: int = 30
    jwt_refresh_token_days: int = 7
    jwt_audience: str = "emsalist-api"
    backup_root: str = ""
    backup_retention_days: int = 30
    backup_encryption_enabled: bool = False
    backup_encryption_key: str = ""
    backup_compression: str = "gzip"
    backup_database_timeout_seconds: int = 300
    backup_file_timeout_seconds: int = 120
    backup_max_size_bytes: int = 1073741824
    backup_require_pre_restore_backup: bool = True
    backup_verify_after_create: bool = True
    backup_maintenance_mode: bool = False
    backup_include_json_projection: bool = True
    backup_include_rebuildable_indexes: bool = False
    metrics_enabled: bool = True
    allowed_hosts: str = ""  # comma-separated production hostnames
    cors_allow_origins: str = ""  # comma-separated CORS origins for production
    max_upload_size_bytes: int = MAX_UPLOAD_SIZE_BYTES


def validate_production_config(settings: Settings) -> list[str]:
    """Validate production configuration and return issues.
    Returns empty list if safe; raise ProductionConfigError for blocking issues.
    """
    issues: list[str] = []
    blocking: list[str] = []

    if settings.environment != "production":
        if settings.environment in ("development", "test"):
            return issues
        return issues

    if settings.debug:
        blocking.append("EMSALIST_DEBUG=true productionda kullanilamaz")

    if settings.auth_mode == "local":
        blocking.append("AUTH_MODE=local productionda kullanilamaz")

    if not settings.jwt_secret_key:
        blocking.append("JWT_SECRET_KEY bos olamaz")
    elif settings.jwt_secret_key in _DEFAULT_JWT_SECRETS:
        blocking.append("Varsayilan JWT_SECRET_KEY productionda kullanilamaz")
    elif len(settings.jwt_secret_key) < MIN_JWT_SECRET_LENGTH:
        blocking.append(f"JWT_SECRET_KEY en az {MIN_JWT_SECRET_LENGTH} karakter olmalidir")

    if settings.backup_encryption_enabled and not settings.backup_encryption_key:
        blocking.append("BACKUP_ENCRYPTION_KEY gerekli fakat bos (backup_encryption_enabled=true)")

    if settings.gemini_enabled and not settings.gemini_api_key:
        blocking.append("GEMINI_ENABLED=true fakat GEMINI_API_KEY bos")

    if not settings.allowed_hosts:
        blocking.append("ALLOWED_HOSTS productionda bos olamaz")

    if not settings.database_url:
        blocking.append("DATABASE_URL productionda bos olamaz")
    else:
        try:
            from sqlalchemy.engine import make_url
            parsed = make_url(settings.database_url)
            if parsed.get_backend_name() != "postgresql":
                blocking.append(
                    f"DATABASE_URL yalnizca PostgreSQL kabul eder; "
                    f"backend={parsed.get_backend_name()} desteklenmez"
                )
        except Exception:
            blocking.append("DATABASE_URL gecersiz; parse edilemedi")

    cors_origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
    if not cors_origins:
        blocking.append("CORS_ALLOW_ORIGINS productionda bos olamaz")
    for origin in cors_origins:
        if origin == "*" or (origin.startswith("*.") and len(origin) > 2):
            blocking.append("CORS_ALLOW_ORIGINS wildcard ('*') uretimde kullanilamaz")
            break

    if blocking:
        raise ProductionConfigError(
            "production_config_unsafe: " + "; ".join(blocking)
        )

    return issues


def _load_env_file() -> None:
    """Load simple KEY=VALUE lines from backend/.env without adding a dependency."""
    import os

    candidates = [
        Path(__file__).resolve().parents[2] / ".env",
        Path(__file__).resolve().parents[1] / ".env",
        Path.cwd() / ".env",
    ]
    for env_path in candidates:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""
    import os as _os

    def _env(key: str, default: str) -> str:
        prefixed = getenv(f"EMSALIST_{key}", "")
        if prefixed:
            return prefixed
        return getenv(key, default)

    _load_env_file()
    gemini_api_key = getenv("GEMINI_API_KEY", "").strip()
    gemini_enabled_value = getenv("GEMINI_ENABLED")
    gemini_enabled = (
        bool(gemini_api_key)
        if gemini_enabled_value is None
        else gemini_enabled_value.lower() in {"1", "true", "yes", "on"}
    )
    env = _env("ENVIRONMENT", "development").lower()
    if "PYTEST_CURRENT_TEST" in _os.environ and env != "test":
        env = "test"

    settings = Settings(
        debug=getenv("EMSALIST_DEBUG", "false").lower() in {"1", "true", "yes"},
        environment=env,
        log_level=_env("LOG_LEVEL", "INFO" if env == "production" else "DEBUG").upper(),
        log_format=_env("LOG_FORMAT", "json" if env == "production" else "text").lower(),
        log_service_name=_env("LOG_SERVICE_NAME", "emsalist-api"),
        max_ranked_decisions=int(getenv("EMSALIST_MAX_RANKED_DECISIONS", "10")),
        gemini_enabled=gemini_enabled,
        gemini_api_key=gemini_api_key,
        gemini_model=getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        gemini_timeout_seconds=int(getenv("GEMINI_TIMEOUT_SECONDS", "30")),
        database_url=_env("DATABASE_URL", ""),
        storage_backend=_env("STORAGE_BACKEND", "json"),
        jwt_secret_key=getenv("JWT_SECRET_KEY", ""),
        auth_mode=getenv("AUTH_MODE", "local"),
        backup_encryption_enabled=getenv("BACKUP_ENCRYPTION_ENABLED", "").lower() in {"1", "true", "yes"},
        backup_encryption_key=getenv("BACKUP_ENCRYPTION_KEY", ""),
        allowed_hosts=_env("ALLOWED_HOSTS", ""),
        cors_allow_origins=_env("CORS_ALLOW_ORIGINS", ""),
        max_upload_size_bytes=int(getenv("EMSALIST_MAX_UPLOAD_SIZE", str(MAX_UPLOAD_SIZE_BYTES))),
    )

    if _os.environ.get("EMSALIST_SKIP_PRODUCTION_VALIDATION", "").lower() not in ("1", "true", "yes"):
        validate_production_config(settings)

    return settings
