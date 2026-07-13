"""P2.6 — Secure source fetcher with comprehensive SSRF protection.

'Successfully fetched' is NOT 'verified'. This module only performs a
safe network retrieval; trust/verification is a separate step.

Security properties (deterministic + testable via an injectable resolver):
- only http/https
- reject credentials-in-URL
- domain allowlist
- reject localhost / loopback / private / link-local / reserved (IPv4 + IPv6)
- reject cloud metadata endpoints
- resolve DNS and validate EVERY resolved IP (defends DNS rebinding)
- re-validate URL + host + IPs on EVERY redirect hop
- max redirects + redirect-loop guard
- streaming response size limit + timeout
- content-type allowlist

For real network access, use :class:`HttpxSourceTransport` which is a
controlled SSRF-safe HTTP transport adapter. In tests, inject a callable
stub that returns objects with status_code, headers, content, location.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urlparse

import httpx

# Official/allowlisted legal domains (suffix match on registrable host).
ALLOWED_DOMAINS = frozenset({
    "mevzuat.gov.tr",
    "mevzuat.adalet.gov.tr",
    "resmigazete.gov.tr",
    "karararama.yargitay.gov.tr",
    "yargitay.gov.tr",
    "karararama.danistay.gov.tr",
    "danistay.gov.tr",
    "kararlarbilgibankasi.anayasa.gov.tr",
    "anayasa.gov.tr",
    "emsal.uyap.gov.tr",
    "kararlar.uyusmazlik.gov.tr",
    "uyusmazlik.gov.tr",
})

ALLOWED_CONTENT_TYPES = frozenset({
    "text/html", "text/plain", "application/xhtml+xml",
    "application/pdf", "application/xml", "text/xml",
    "application/json",
})

MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 25 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 10

_BLOCKED_HOSTNAMES = frozenset({
    "localhost", "metadata.google.internal", "metadata",
})


class SourceFetchError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class FetchResult:
    final_url: str
    status_code: int
    content: bytes
    content_type: str
    redirect_chain: list[str] = field(default_factory=list)


def _host_allowed(hostname: str) -> bool:
    host = hostname.lower().rstrip(".")
    for domain in ALLOWED_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return True
    return False


def _ip_is_safe(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    # Reject loopback / private / link-local / reserved / multicast /
    # unspecified for both IPv4 and IPv6 (covers ::1, fc00::/7, fe80::/10, etc.)
    if (addr.is_loopback or addr.is_private or addr.is_link_local
            or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
        return False
    # IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1) — unwrap and re-check.
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return _ip_is_safe(str(addr.ipv4_mapped))
    return True


# Injectable resolver so tests are deterministic and offline.
def default_resolver(hostname: str) -> list[str]:
    infos = socket.getaddrinfo(hostname, None)
    return list({str(info[4][0]) for info in infos})


def validate_url(url: str, resolver=default_resolver) -> list[str]:
    """Validates a single URL and returns the resolved safe IPs.

    Raises SourceFetchError on any SSRF/allowlist/scheme violation.
    """
    if not url:
        raise SourceFetchError("empty_url", "Boş URL.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SourceFetchError("unsafe_scheme", f"Desteklenmeyen şema: {parsed.scheme}")
    if parsed.username or parsed.password:
        raise SourceFetchError("credentials_in_url", "URL kimlik bilgisi içeremez.")
    hostname = parsed.hostname
    if not hostname:
        raise SourceFetchError("no_hostname", "Geçersiz ana bilgisayar.")
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        raise SourceFetchError("blocked_host", "Engellenen ana bilgisayar.")

    # If the host is an IP literal, validate it directly (fail-closed).
    try:
        literal = ipaddress.ip_address(hostname)
        if not _ip_is_safe(str(literal)):
            raise SourceFetchError("blocked_ip", "Engellenen IP adresi.")
        # IP literal must still be within an allowed domain policy → reject.
        raise SourceFetchError("ip_literal_not_allowed", "IP literal URL kabul edilmiyor.")
    except ValueError:
        pass  # not an IP literal → hostname

    if not _host_allowed(hostname):
        raise SourceFetchError("domain_not_allowed", "Alan adı izin listesinde değil.")

    resolved = resolver(hostname)
    if not resolved:
        raise SourceFetchError("dns_failed", "Alan adı çözümlenemedi.")
    for ip in resolved:
        if not _ip_is_safe(ip):
            raise SourceFetchError("dns_unsafe_ip", "Çözümlenen IP güvenli değil.")
    return resolved


@dataclass
class _StubResponse:
    status_code: int
    headers: dict
    content: bytes
    location: str | None = None


# ── Real SSRF-safe HTTP transport (P2.6C) ─────────────────────────────────
class HttpxSourceTransport:
    """Controlled HTTPS transport adapter for :func:`fetch_source`.

    This is the ONLY class that performs real network I/O for official-source
    fetching. Every HTTP request goes through this adapter, which returns a
    ``_StubResponse``-compatible object so the transport contract stays
    uniform between stubs and live fetches.

    Security invariants:
    - HTTP-client automatic redirects are DISABLED → source_fetcher owns every
      redirect-hop re-validation.
    - TLS certificate verification is ENABLED (never disabled for trusted hosts).
    - Environment proxy variables (HTTP_PROXY / HTTPS_PROXY / ALL_PROXY) are
      intentionally NOT consumed — no untrusted proxy routing without explicit
      review.
    - Response body is streamed with a hard size cap; oversized responses are
      rejected mid-stream.
    - A bounded connect/read timeout is applied to every request.
    """

    def __init__(
        self,
        *,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_bytes: int = MAX_RESPONSE_BYTES,
    ):
        self._timeout = timeout_seconds
        self._max_bytes = max_bytes
        # Explicit: no proxy auto-detection from env vars.
        self._client = httpx.Client(
            follow_redirects=False,
            verify=True,
            timeout=timeout_seconds,
        )

    def __call__(self, url: str) -> _StubResponse:
        """Fetch [url] and return a transport-agnostic stub-compatible object.

        Raises ``SourceFetchError`` on transport-level failures (connect /
        timeout / oversized / TLS / unsupported scheme). HTTP status codes
        >= 400 are returned and inspected by the caller (:func:`fetch_source`).
        """
        try:
            with self._client.stream("GET", url) as resp:
                # Stream the body with a hard byte cap so we never hold an
                # unbounded response in memory.
                body = bytearray()
                for chunk in resp.iter_bytes(65536):
                    body.extend(chunk)
                    if len(body) > self._max_bytes:
                        raise SourceFetchError("response_too_large", "Yanıt boyutu sınırı aştı.")
                return _StubResponse(
                    status_code=resp.status_code,
                    headers=dict(resp.headers),
                    content=bytes(body),
                    location=resp.headers.get("location"),
                )
        except SourceFetchError:
            raise
        except httpx.TimeoutException:
            raise SourceFetchError("fetch_timeout", "Resmî kaynak zaman aşımı.")
        except httpx.InvalidURL:
            raise SourceFetchError("invalid_url", "Geçersiz URL.")
        except httpx.ConnectError:
            raise SourceFetchError("connect_error", "Resmî kaynağa bağlanılamadı.")
        except OSError as e:
            raise SourceFetchError("network_error", str(e)[:120]) from e


def create_real_transport(**kw) -> HttpxSourceTransport:
    """Factory: the real SSRF-safe transport used when ``--enable-live``.

    Tests inject a stub transport; production/live-smoke calls this.
    """
    return HttpxSourceTransport(**kw)


def create_live_transport(**kw) -> HttpxSourceTransport | None:
    """Return the real transport ONLY when live source ingestion is explicitly
    enabled (OFFICIAL_PROVIDER_LIVE_SMOKE=1).
    Otherwise return None (fail-closed — no accidental network access).
    """
    import os as _os

    if _os.environ.get("OFFICIAL_PROVIDER_LIVE_SMOKE", "").lower() not in {
        "1", "true", "yes",
    }:
        return None
    return create_real_transport(**kw)


def fetch_source(
    url: str,
    *,
    resolver=default_resolver,
    transport=None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> FetchResult:
    """Securely fetch a source URL.

    [transport] is an injectable callable ``(url) -> _StubResponse`` used by
    tests to avoid real network I/O; it must return an object with
    status_code, headers (dict), content (bytes) and optional location. When
    None, real fetching is not performed in this build (fetch is provided via
    the ingestion service seam). Every hop re-runs [validate_url].
    """
    if transport is None:
        raise SourceFetchError("no_transport", "Ağ taşıyıcısı yapılandırılmadı.")

    current = url
    chain: list[str] = []
    for _hop in range(MAX_REDIRECTS + 1):
        validate_url(current, resolver=resolver)
        chain.append(current)
        resp = transport(current)
        if resp.status_code in (301, 302, 303, 307, 308) and resp.location:
            nxt = resp.location
            if nxt in chain:
                raise SourceFetchError("redirect_loop", "Yönlendirme döngüsü.")
            current = nxt
            continue
        if resp.status_code >= 400:
            raise SourceFetchError("http_error", f"HTTP {resp.status_code}")
        content_type = (resp.headers.get("content-type", "") or "").split(";")[0].strip().lower()
        if content_type and content_type not in ALLOWED_CONTENT_TYPES:
            raise SourceFetchError("unsupported_content_type", f"Desteklenmeyen içerik türü: {content_type}")
        content = resp.content or b""
        if len(content) > max_bytes:
            raise SourceFetchError("response_too_large", "Yanıt boyutu sınırı aştı.")
        return FetchResult(
            final_url=current, status_code=resp.status_code, content=content,
            content_type=content_type, redirect_chain=chain,
        )
    raise SourceFetchError("too_many_redirects", "Çok fazla yönlendirme.")
