"""P2.6C — Official legal source provider contracts.

These are the strict, provider-agnostic contracts that every official source
provider adapter implements. They deliberately contain NO trust logic and NO
canonical writes:

- Provider discovery/parse results are NOT official evidence.
- Trust is produced ONLY by the P2.6 ``ingest_official_fetch`` path via the
  shared orchestration service, using server-fetched bytes.
- All network fetching goes through the P2.6 ``source_fetcher`` SSRF seam.

Provider code MUST NOT write SourceRecord / SourceVersion / SourceVerification
directly, and MUST NOT set verification_status.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

# ── Run modes ────────────────────────────────────────────────────────────
RUN_DISCOVER_ONLY = "discover_only"
RUN_FETCH_AND_INGEST = "fetch_and_ingest"
RUN_EXACT_SOURCE = "exact_source"
RUN_INCREMENTAL = "incremental"
RUN_BOUNDED_WINDOW = "bounded_window"

RUN_MODES = frozenset({
    RUN_DISCOVER_ONLY, RUN_FETCH_AND_INGEST, RUN_EXACT_SOURCE,
    RUN_INCREMENTAL, RUN_BOUNDED_WINDOW,
})

# ── Safe error codes (no raw HTML / no PII) ────────────────────────────────
ERR_STRUCTURE_CHANGED = "provider_structure_changed"
ERR_EMPTY_LEGAL_BODY = "empty_legal_body"
ERR_MISSING_IDENTIFIER = "missing_identifier"
ERR_FETCH_FAILED = "fetch_failed"
ERR_SSRF_BLOCKED = "ssrf_blocked"
ERR_RATE_LIMITED = "rate_limited"
ERR_ACCESS_DENIED = "access_denied"
ERR_CHALLENGE = "challenge_detected"
ERR_UNSUPPORTED_REQUIRES_AUTH = "unsupported_requires_auth"
ERR_MANUAL_REVIEW_REQUIRED = "manual_review_required"
ERR_PARSE_FAILED = "parse_failed"
ERR_UNSUPPORTED_MODE = "unsupported_mode"
ERR_TRANSPORT_UNAVAILABLE = "transport_unavailable"
ERR_BROWSER_DISCOVERY_UNAVAILABLE = "browser_discovery_unavailable"

# ── Provider status vocabulary ─────────────────────────────────────────────
STATUS_AVAILABLE = "available"
STATUS_DISABLED = "disabled"
STATUS_DEGRADED = "degraded"
STATUS_FIXTURE_TESTED_ONLY = "fixture_tested_only"
STATUS_TRANSPORT_UNAVAILABLE = "transport_unavailable"
STATUS_BROWSER_DISCOVERY_UNAVAILABLE = "browser_discovery_unavailable"
STATUS_UNSUPPORTED_REQUIRES_AUTH = "unsupported_requires_auth"
STATUS_PROVIDER_CHANGED = "provider_changed"
STATUS_MANUAL_REVIEW_REQUIRED = "manual_review_required"


class ProviderError(Exception):
    """Provider-level failure carrying a SAFE error code (never raw HTML)."""

    def __init__(
        self,
        code: str,
        message: str = "",
        *,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
        http_status: int | None = None,
    ):
        self.code = code
        self.message = message or code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.http_status = http_status
        super().__init__(self.message)


@dataclass(frozen=True)
class ProviderCapabilities:
    discovery: bool = False
    fetch: bool = False
    parse: bool = False
    incremental: bool = False
    bounded_window: bool = False
    requires_browser: bool = False
    requires_auth: bool = False


@dataclass(frozen=True)
class ProviderRequestPolicy:
    """Per-provider politeness / rate-limit policy."""

    min_interval_seconds: float = 2.0
    max_concurrency: int = 1
    request_timeout_seconds: int = 15
    max_retries: int = 2
    retryable_statuses: frozenset[int] = field(default_factory=lambda: frozenset({500, 502, 503, 504}))
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 30.0


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class ProviderDiscoveryCandidate:
    """A discovered candidate. Discovered metadata is UNTRUSTED until the exact
    content is fetched and parsed via the official-fetch path."""

    provider_code: str
    source_type: str
    detail_url: str
    external_id: str | None = None
    download_url: str | None = None
    discovered_metadata: dict = field(default_factory=dict)
    discovered_at: str = field(default_factory=_now_iso)

    def dedupe_key(self) -> str:
        """Provider-discovery dedupe key ONLY (not canonical legal dedupe).

        Uses a stable external_id when the provider exposes one; otherwise the
        SHA-256 of the normalized official detail URL.
        """
        if self.external_id:
            return f"{self.provider_code}:{self.external_id.strip()}"
        norm = (self.detail_url or "").strip().rstrip("/").lower()
        return f"{self.provider_code}:url:{hashlib.sha256(norm.encode('utf-8')).hexdigest()[:32]}"

    def candidate_url_hash(self) -> str:
        target = (self.download_url or self.detail_url or "").strip().lower()
        return hashlib.sha256(target.encode("utf-8")).hexdigest()[:32]

    def fetch_url(self) -> str:
        return self.download_url or self.detail_url


@dataclass
class ProviderDiscoveryPage:
    candidates: list[ProviderDiscoveryCandidate] = field(default_factory=list)
    next_cursor: str | None = None
    exhausted: bool = True


@dataclass
class ParsedOfficialSource:
    """Parsed canonical fields extracted from EXACT fetched official content.

    Provider-specific technical metadata belongs in ``provider_metadata`` and
    never leaks into canonical SourceRecord fields.
    """

    provider_code: str
    source_type: str
    title: str
    official_url: str
    raw_text: str
    court: str | None = None
    chamber: str | None = None
    case_number: str | None = None
    decision_number: str | None = None
    decision_date: str | None = None
    issuing_authority: str | None = None
    number: str | None = None
    publication_date: str | None = None
    effective_date: str | None = None
    repeal_date: str | None = None
    paragraph_hints: list | None = None
    provider_metadata: dict = field(default_factory=dict)

    def to_ingest_metadata(self) -> dict:
        """Map ONLY canonical cross-provider legal identifiers to the P2.6
        ingestion metadata dict. Provider-specific identifiers are intentionally
        excluded (they live in provider_metadata for traceability)."""
        return {
            "source_type": self.source_type,
            "title": self.title or "",
            "court": self.court or "",
            "chamber": self.chamber or "",
            "case_number": self.case_number or "",
            "decision_number": self.decision_number or "",
            "decision_date": self.decision_date or "",
            "issuing_authority": self.issuing_authority or "",
            "number": self.number or "",
            "publication_date": self.publication_date or "",
            "effective_date": self.effective_date or "",
            "repeal_date": self.repeal_date or "",
        }


class OfficialSourceProvider:
    """Base class for official source providers.

    Concrete providers implement ``discover`` and ``parse``. Fetching is
    centralized in ``fetch`` (this base) so every provider network access flows
    through the P2.6 SSRF-validated ``source_fetcher`` seam. Providers must not
    fetch URLs directly.
    """

    provider_code: str = ""
    provider_name: str = ""
    source_types: tuple[str, ...] = ()
    official_domains: tuple[str, ...] = ()
    capabilities: ProviderCapabilities = ProviderCapabilities()
    request_policy: ProviderRequestPolicy = ProviderRequestPolicy()

    def validate_contract(self) -> None:
        """Fail closed when a fetch-capable provider lacks a safe domain scope."""
        if not self.capabilities.fetch:
            return
        from app.services.source_fetcher import domains_within_global_allowlist

        if not domains_within_global_allowlist(self.official_domains):
            raise ProviderError(ERR_SSRF_BLOCKED, "provider_domain_scope_invalid")

    def is_official_url(self, url: str) -> bool:
        """Return whether *url* is globally official and owned by this provider."""
        from app.services.source_fetcher import (
            ALLOWED_DOMAINS,
            url_matches_allowed_domains,
        )

        self.validate_contract()
        return (
            url_matches_allowed_domains(url, ALLOWED_DOMAINS)
            and url_matches_allowed_domains(url, self.official_domains)
        )

    def validate_official_url(self, url: str) -> None:
        """Reject a URL outside the executing provider's closed origin scope."""
        if not self.is_official_url(url):
            raise ProviderError(ERR_SSRF_BLOCKED, "provider_origin_not_allowed")

    async def discover(
        self,
        *,
        query: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
        from_date: str | None = None,
        to_date: str | None = None,
        transport=None,
        resolver=None,
    ) -> ProviderDiscoveryPage:
        raise NotImplementedError

    async def fetch(self, candidate: ProviderDiscoveryCandidate, *, transport=None, resolver=None):
        """Securely fetch the candidate's official content via the P2.6 seam.

        Returns a ``FetchResult``. Raises ``ProviderError`` with a safe code on
        SSRF/allowlist/HTTP failures. Providers must NOT override this to bypass
        the SSRF seam.
        """
        url = candidate.fetch_url()
        if not url:
            raise ProviderError(ERR_FETCH_FAILED, "candidate has no fetch url")
        return self._secure_fetch(url, transport=transport, resolver=resolver)

    def _secure_fetch(self, url: str, *, transport=None, resolver=None):
        """Fetch an allowlisted official URL through the P2.6 SSRF seam.

        Every provider network access (discovery + detail fetch) MUST go through
        here. Raises ProviderError with a safe code on any failure.
        """
        from app.services.source_fetcher import (
            SourceFetchError,
            default_resolver,
            fetch_source,
        )

        self.validate_contract()
        try:
            return fetch_source(
                url,
                resolver=resolver or default_resolver,
                transport=transport,
                timeout=self.request_policy.request_timeout_seconds,
                allowed_domains=self.official_domains,
            )
        except SourceFetchError as e:
            raise self._provider_error_from_fetch_error(e) from e

    def _provider_error_from_fetch_error(self, e) -> ProviderError:
        """Map fetcher failures to safe provider errors and retry metadata."""
        ssrf_codes = frozenset({
            "empty_url",
            "unsafe_scheme",
            "credentials_in_url",
            "no_hostname",
            "blocked_host",
            "blocked_ip",
            "ip_literal_not_allowed",
            "domain_not_allowed",
            "dns_unsafe_ip",
            "destination_not_validated",
            "redirect_loop",
            "too_many_redirects",
        })
        if e.code in ssrf_codes:
            return ProviderError(ERR_SSRF_BLOCKED, e.code)
        if e.code in {"no_transport", "transport_unavailable"}:
            return ProviderError(ERR_TRANSPORT_UNAVAILABLE, e.code)
        if e.code == "http_error":
            status = e.http_status
            if status == 429:
                return ProviderError(
                    ERR_RATE_LIMITED,
                    e.code,
                    retryable=True,
                    retry_after_seconds=e.retry_after_seconds,
                    http_status=status,
                )
            if status in {401, 403}:
                return ProviderError(ERR_ACCESS_DENIED, e.code, http_status=status)
            retryable = (
                status in self.request_policy.retryable_statuses
                if status is not None else False
            )
            return ProviderError(
                ERR_FETCH_FAILED, e.code, retryable=retryable,
                http_status=status,
            )
        if e.code in {"fetch_timeout", "connect_error", "network_error", "dns_failed"}:
            return ProviderError(ERR_FETCH_FAILED, e.code, retryable=True)
        if e.code in {
            "tls_error",
            "response_too_large",
            "unsupported_content_type",
        }:
            return ProviderError(ERR_FETCH_FAILED, e.code)
        return ProviderError(ERR_FETCH_FAILED, e.code)

    async def parse(
        self, candidate: ProviderDiscoveryCandidate, fetch_result
    ) -> ParsedOfficialSource:
        raise NotImplementedError

    def build_exact_candidate(self, external_id: str) -> ProviderDiscoveryCandidate:
        """Resolve a provider-specific external_id into a safe official candidate.

        The provider constructs the detail_url from its own fixed official base
        (never from caller input). The returned candidate contains only provider-
        generated fields — no caller-supplied URLs.
        """
        raise ProviderError("unsupported_mode", f"{self.provider_code}: external_id resolution not supported")

    @staticmethod
    def default_resolver():
        from app.services.source_fetcher import default_resolver
        return default_resolver
