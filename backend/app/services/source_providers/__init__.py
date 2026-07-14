"""P2.6C — Official legal source provider adapters.

Providers discover and parse PUBLIC official legal-source surfaces and hand
exact server-fetched content to the P2.6 canonical ingestion path. They never
write canonical records or produce trust directly.
"""
from __future__ import annotations

from app.services.source_providers.base import (
    OfficialSourceProvider,
    ParsedOfficialSource,
    ProviderCapabilities,
    ProviderDiscoveryCandidate,
    ProviderDiscoveryPage,
    ProviderError,
    ProviderRequestPolicy,
)

__all__ = [
    "OfficialSourceProvider",
    "ParsedOfficialSource",
    "ProviderCapabilities",
    "ProviderDiscoveryCandidate",
    "ProviderDiscoveryPage",
    "ProviderError",
    "ProviderRequestPolicy",
]
