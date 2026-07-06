"""Application configuration.

Environment variables intentionally keep the service deployment-friendly while
avoiding a dependency on an external configuration provider at this stage.
"""

from functools import lru_cache
from os import getenv
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = "Emsalist API"
    app_version: str = "0.1.0"
    debug: bool = False
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
    _load_env_file()
    gemini_api_key = getenv("GEMINI_API_KEY", "").strip()
    gemini_enabled_value = getenv("GEMINI_ENABLED")
    gemini_enabled = (
        bool(gemini_api_key)
        if gemini_enabled_value is None
        else gemini_enabled_value.lower() in {"1", "true", "yes", "on"}
    )
    return Settings(
        debug=getenv("EMSALIST_DEBUG", "false").lower() in {"1", "true", "yes"},
        max_ranked_decisions=int(getenv("EMSALIST_MAX_RANKED_DECISIONS", "10")),
        gemini_enabled=gemini_enabled,
        gemini_api_key=gemini_api_key,
        gemini_model=getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        gemini_timeout_seconds=int(getenv("GEMINI_TIMEOUT_SECONDS", "30")),
    )
