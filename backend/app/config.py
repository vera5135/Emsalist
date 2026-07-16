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
    ai_reasoning_provider: str = ""
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-pro"
    deepseek_reasoning_effort: str = "high"
    deepseek_timeout_seconds: int = 60
    deepseek_max_retries: int = 2
    # ── P2.7 Hybrid Search ───────────────────────────────────────
    search_semantic_enabled: bool = False
    search_embedding_model: str = "gemini-embedding-001"
    search_embedding_version: str = "p2.7-embedding-1"
    search_max_candidate_pool: int = 5000
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
    apple_sign_in_enabled: bool = False
    apple_client_id: str = ""
    apple_team_id: str = ""
    apple_key_id: str = ""
    apple_private_key_path: str = ""
    apple_subject_pepper: str = ""
    apple_token_endpoint: str = "https://appleid.apple.com/auth/token"
    apple_jwks_url: str = "https://appleid.apple.com/auth/keys"
    apple_issuer: str = "https://appleid.apple.com"
    apple_http_timeout_seconds: int = 5
    apple_jwks_cache_seconds: int = 3600
    apple_link_ticket_seconds: int = 300
    # P2.6C — official legal source provider enablement (default disabled).
    official_provider_yargitay_enabled: bool = False
    official_provider_danistay_enabled: bool = False
    official_provider_aym_enabled: bool = False
    official_provider_uyusmazlik_enabled: bool = False
    official_provider_mevzuat_enabled: bool = False
    official_provider_resmi_gazete_enabled: bool = False
    official_provider_live_smoke: bool = False
    official_provider_browser_discovery_enabled: bool = False


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

    if settings.apple_sign_in_enabled:
        missing = []
        if not settings.apple_client_id:
            missing.append("APPLE_CLIENT_ID")
        if not settings.apple_team_id:
            missing.append("APPLE_TEAM_ID")
        if not settings.apple_key_id:
            missing.append("APPLE_KEY_ID")
        if not settings.apple_private_key_path:
            missing.append("APPLE_PRIVATE_KEY_PATH")
        if not settings.apple_subject_pepper:
            missing.append("APPLE_SUBJECT_PEPPER")
        elif len(settings.apple_subject_pepper) < 32:
            issues.append("APPLE_SUBJECT_PEPPER productionda en az 32 karakter olmalidir")
        if missing:
            blocking.append(f"Apple Sign-In enabled fakat eksik: {', '.join(missing)}")
        if settings.apple_private_key_path:
            pk_path = Path(settings.apple_private_key_path)
            if not pk_path.exists():
                blocking.append(f"APPLE_PRIVATE_KEY_PATH bulunamadi: {settings.apple_private_key_path}")

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
        ai_reasoning_provider=getenv("AI_REASONING_PROVIDER", "").strip().lower(),
        deepseek_api_key=getenv("DEEPSEEK_API_KEY", "").strip(),
        deepseek_base_url=getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        deepseek_model=getenv("DEEPSEEK_MODEL", "deepseek-v4-pro").strip(),
        deepseek_reasoning_effort=getenv("DEEPSEEK_REASONING_EFFORT", "high").strip().lower(),
        deepseek_timeout_seconds=int(getenv("DEEPSEEK_TIMEOUT_SECONDS", "60")),
        deepseek_max_retries=int(getenv("DEEPSEEK_MAX_RETRIES", "2")),
        search_semantic_enabled=getenv("EMSALIST_SEARCH_SEMANTIC_ENABLED", "false").lower() in {"1", "true", "yes"},
        search_embedding_model=getenv("EMSALIST_SEARCH_EMBEDDING_MODEL", "gemini-embedding-001"),
        search_embedding_version=getenv("EMSALIST_SEARCH_EMBEDDING_VERSION", "p2.7-embedding-1"),
        search_max_candidate_pool=int(getenv("EMSALIST_SEARCH_MAX_CANDIDATE_POOL", "5000")),
        database_url=_env("DATABASE_URL", ""),
        storage_backend=_env("STORAGE_BACKEND", "json"),
        jwt_secret_key=getenv("JWT_SECRET_KEY", ""),
        auth_mode=getenv("AUTH_MODE", "local"),
        backup_encryption_enabled=getenv("BACKUP_ENCRYPTION_ENABLED", "").lower() in {"1", "true", "yes"},
        backup_encryption_key=getenv("BACKUP_ENCRYPTION_KEY", ""),
        backup_root=_env("BACKUP_ROOT", ""),
        allowed_hosts=_env("ALLOWED_HOSTS", ""),
        cors_allow_origins=_env("CORS_ALLOW_ORIGINS", ""),
        max_upload_size_bytes=int(getenv("EMSALIST_MAX_UPLOAD_SIZE", str(MAX_UPLOAD_SIZE_BYTES))),
        apple_sign_in_enabled=getenv("APPLE_SIGN_IN_ENABLED", "false").lower() in {"1", "true", "yes"},
        apple_client_id=getenv("APPLE_CLIENT_ID", ""),
        apple_team_id=getenv("APPLE_TEAM_ID", ""),
        apple_key_id=getenv("APPLE_KEY_ID", ""),
        apple_private_key_path=getenv("APPLE_PRIVATE_KEY_PATH", ""),
        apple_subject_pepper=getenv("APPLE_SUBJECT_PEPPER", ""),
        apple_token_endpoint=getenv("APPLE_TOKEN_ENDPOINT", "https://appleid.apple.com/auth/token"),
        apple_jwks_url=getenv("APPLE_JWKS_URL", "https://appleid.apple.com/auth/keys"),
        apple_issuer=getenv("APPLE_ISSUER", "https://appleid.apple.com"),
        apple_http_timeout_seconds=int(getenv("APPLE_HTTP_TIMEOUT_SECONDS", "5")),
        apple_jwks_cache_seconds=int(getenv("APPLE_JWKS_CACHE_SECONDS", "3600")),
        apple_link_ticket_seconds=int(getenv("APPLE_LINK_TICKET_SECONDS", "300")),
        official_provider_yargitay_enabled=getenv("OFFICIAL_PROVIDER_YARGITAY_ENABLED", "false").lower() in {"1", "true", "yes"},
        official_provider_danistay_enabled=getenv("OFFICIAL_PROVIDER_DANISTAY_ENABLED", "false").lower() in {"1", "true", "yes"},
        official_provider_aym_enabled=getenv("OFFICIAL_PROVIDER_AYM_ENABLED", "false").lower() in {"1", "true", "yes"},
        official_provider_uyusmazlik_enabled=getenv("OFFICIAL_PROVIDER_UYUSMAZLIK_ENABLED", "false").lower() in {"1", "true", "yes"},
        official_provider_mevzuat_enabled=getenv("OFFICIAL_PROVIDER_MEVZUAT_ENABLED", "false").lower() in {"1", "true", "yes"},
        official_provider_resmi_gazete_enabled=getenv("OFFICIAL_PROVIDER_RESMI_GAZETE_ENABLED", "false").lower() in {"1", "true", "yes"},
        official_provider_live_smoke=getenv("OFFICIAL_PROVIDER_LIVE_SMOKE", "false").lower() in {"1", "true", "yes"},
        official_provider_browser_discovery_enabled=getenv("OFFICIAL_PROVIDER_BROWSER_DISCOVERY_ENABLED", "false").lower() in {"1", "true", "yes"},
    )

    if _os.environ.get("EMSALIST_SKIP_PRODUCTION_VALIDATION", "").lower() not in ("1", "true", "yes"):
        validate_production_config(settings)

    return settings
