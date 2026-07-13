"""P2.6C — Deterministic official source provider registry.

Providers are registered EXPLICITLY (never dynamically imported from user
input). Enablement is controlled by configuration flags. Unknown providers
raise an explicit error.
"""
from __future__ import annotations

from app.config import get_settings
from app.services.source_providers.base import OfficialSourceProvider, ProviderError
from app.services.source_providers.aym import AymProvider
from app.services.source_providers.danistay import DanistayProvider
from app.services.source_providers.mevzuat import MevzuatProvider
from app.services.source_providers.resmi_gazete import ResmiGazeteProvider
from app.services.source_providers.uyusmazlik import UyusmazlikProvider
from app.services.source_providers.yargitay import YargitayProvider

# Explicit, closed registry. The keys are the ONLY valid provider codes.
_PROVIDERS: dict[str, OfficialSourceProvider] = {
    YargitayProvider.provider_code: YargitayProvider(),
    DanistayProvider.provider_code: DanistayProvider(),
    AymProvider.provider_code: AymProvider(),
    UyusmazlikProvider.provider_code: UyusmazlikProvider(),
    MevzuatProvider.provider_code: MevzuatProvider(),
    ResmiGazeteProvider.provider_code: ResmiGazeteProvider(),
}

PROVIDER_CODES = tuple(_PROVIDERS.keys())

_ENABLED_FLAG = {
    "yargitay": "official_provider_yargitay_enabled",
    "danistay": "official_provider_danistay_enabled",
    "aym": "official_provider_aym_enabled",
    "uyusmazlik": "official_provider_uyusmazlik_enabled",
    "mevzuat": "official_provider_mevzuat_enabled",
    "resmi_gazete": "official_provider_resmi_gazete_enabled",
}


def all_provider_codes() -> tuple[str, ...]:
    return PROVIDER_CODES


def is_known(provider_code: str) -> bool:
    return provider_code in _PROVIDERS


def is_enabled(provider_code: str) -> bool:
    flag = _ENABLED_FLAG.get(provider_code)
    if flag is None:
        return False
    return bool(getattr(get_settings(), flag, False))


def get(provider_code: str) -> OfficialSourceProvider:
    """Return the registered provider or raise an explicit error.

    Raises ProviderError('unknown_provider') for unknown codes and
    ProviderError('provider_disabled') when the provider is not enabled.
    """
    if provider_code not in _PROVIDERS:
        raise ProviderError("unknown_provider", f"unknown provider: {provider_code}")
    if not is_enabled(provider_code):
        raise ProviderError("provider_disabled", f"provider disabled: {provider_code}")
    return _PROVIDERS[provider_code]


def get_definition(provider_code: str) -> OfficialSourceProvider:
    """Return the provider definition regardless of enablement (metadata only)."""
    if provider_code not in _PROVIDERS:
        raise ProviderError("unknown_provider", f"unknown provider: {provider_code}")
    return _PROVIDERS[provider_code]


def enabled() -> list[str]:
    return [code for code in PROVIDER_CODES if is_enabled(code)]


def by_source_type(source_type: str) -> list[str]:
    return [
        code for code, prov in _PROVIDERS.items()
        if source_type in prov.source_types
    ]
