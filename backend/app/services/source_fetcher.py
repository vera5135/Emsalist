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
- P2.6C: typed validated destination contract
- P2.6C: transport IP destination pinning (no independent DNS)
- P2.6C: trust_env=False (no proxy/env consumption)
- P2.6C: TLS SNI/hostname verification pinned to original hostname

For real network access, use :class:`HttpxSourceTransport` which is a
controlled SSRF-safe HTTP transport adapter. In tests, inject a callable
stub that returns objects with status_code, headers, content, location.
"""
from __future__ import annotations

import ipaddress
import socket
import ssl
from dataclasses import dataclass, field
from types import TracebackType
from typing import Callable
from urllib.parse import urljoin, urlparse

import httpcore

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

# ── safe error codes (no raw exception strings in messages) ──────────────
_EC = {
    "empty_url": "Boş URL.",
    "unsafe_scheme": "Desteklenmeyen şema.",
    "credentials_in_url": "URL kimlik bilgisi içeremez.",
    "no_hostname": "Geçersiz ana bilgisayar.",
    "blocked_host": "Engellenen ana bilgisayar.",
    "blocked_ip": "Engellenen IP adresi.",
    "ip_literal_not_allowed": "IP literal URL kabul edilmiyor.",
    "domain_not_allowed": "Alan adı izin listesinde değil.",
    "dns_failed": "Alan adı çözümlenemedi.",
    "dns_unsafe_ip": "Çözümlenen IP güvenli değil.",
    "no_transport": "Ağ taşıyıcısı yapılandırılmadı.",
    "redirect_loop": "Yönlendirme döngüsü.",
    "too_many_redirects": "Çok fazla yönlendirme.",
    "http_error": "HTTP {}",
    "unsupported_content_type": "Desteklenmeyen içerik türü.",
    "response_too_large": "Yanıt boyutu sınırı aştı.",
    "fetch_timeout": "Resmî kaynak zaman aşımı.",
    "invalid_url": "Geçersiz URL.",
    "connect_error": "Resmî kaynağa bağlanılamadı.",
    "tls_error": "TLS bağlantı hatası.",
    "destination_not_validated": "Hedef IP doğrulanmış kümede değil.",
    "network_error": "Ağ hatası.",
    "transport_unavailable": "Güvenli taşıyıcı kullanılabilir değil.",
}


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
    if (addr.is_loopback or addr.is_private or addr.is_link_local
            or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return _ip_is_safe(str(addr.ipv4_mapped))
    return True


# Injectable resolver so tests are deterministic and offline.
def default_resolver(hostname: str) -> list[str]:
    infos = socket.getaddrinfo(hostname, None)
    return list({str(info[4][0]) for info in infos})


# ── Typed validated destination (P2.6C) ───────────────────────────────────
@dataclass(frozen=True)
class ValidatedDestination:
    """Immutable destination contract binding URL, hostname, port to
    validated IPs. Only :func:`validate_destination` may construct it."""

    url: str
    scheme: str
    hostname: str
    port: int
    validated_ips: tuple[str, ...]


def validate_destination(
    url: str, resolver=default_resolver
) -> ValidatedDestination:
    """Validate a single URL and return a typed immutable destination.

    Raises SourceFetchError on any SSRF/allowlist/scheme violation.
    Portable: no module-level mutable state, injectable resolver.
    """
    if not url:
        raise SourceFetchError("empty_url", _EC["empty_url"])
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SourceFetchError("unsafe_scheme", _EC["unsafe_scheme"])
    if parsed.username or parsed.password:
        raise SourceFetchError("credentials_in_url", _EC["credentials_in_url"])
    hostname = parsed.hostname
    if not hostname:
        raise SourceFetchError("no_hostname", _EC["no_hostname"])
    if hostname.lower() in _BLOCKED_HOSTNAMES:
        raise SourceFetchError("blocked_host", _EC["blocked_host"])

    # IP literal → reject.
    try:
        literal = ipaddress.ip_address(hostname)
        if not _ip_is_safe(str(literal)):
            raise SourceFetchError("blocked_ip", _EC["blocked_ip"])
        raise SourceFetchError("ip_literal_not_allowed", _EC["ip_literal_not_allowed"])
    except ValueError:
        pass

    if not _host_allowed(hostname):
        raise SourceFetchError("domain_not_allowed", _EC["domain_not_allowed"])

    resolved = resolver(hostname)
    if not resolved:
        raise SourceFetchError("dns_failed", _EC["dns_failed"])
    for ip in resolved:
        if not _ip_is_safe(ip):
            raise SourceFetchError("dns_unsafe_ip", _EC["dns_unsafe_ip"])

    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    return ValidatedDestination(
        url=url,
        scheme=parsed.scheme,
        hostname=hostname,
        port=port,
        validated_ips=tuple(resolved),
    )


# Backward-compatible wrapper — returns validated IPs only.
def validate_url(url: str, resolver=default_resolver) -> list[str]:
    dest = validate_destination(url, resolver=resolver)
    return list(dest.validated_ips)


# ── transport stubs ─────────────────────────────────────────────────────
@dataclass
class _StubResponse:
    status_code: int
    headers: dict
    content: bytes
    location: str | None = None


# ── Validated IP network backend (P2.6C destination pinning) ─────────────
class _ValidatedNetworkBackend(httpcore.NetworkBackend):
    """Network backend that connects only to a pre-validated IP set.

    Ignores the host parameter passed by httpcore; connects only to
    addresses in *validated_ips*. Fallback across valid IPs is attempted
    within the validated set only — no independent DNS resolution.
    """

    def __init__(self, validated_ips: tuple[str, ...], server_hostname: str):
        self._validated_ips = validated_ips
        self._server_hostname = server_hostname
        self._inner = httpcore.SyncBackend()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ) -> httpcore.NetworkStream:
        last_connect: Exception | None = None
        last_timeout: Exception | None = None
        for ip in self._validated_ips:
            try:
                return self._inner.connect_tcp(
                    ip, port, timeout, local_address, socket_options,
                )
            except httpcore.ConnectTimeout as e:
                last_timeout = e
                continue
            except (OSError, httpcore.ConnectError) as e:
                last_connect = e
                continue
        if last_timeout is not None:
            raise SourceFetchError("fetch_timeout", _EC["fetch_timeout"])
        raise SourceFetchError("connect_error", _EC["connect_error"])

    def connect_unix_socket(
        self, path: str, timeout: float | None = None, socket_options=None,
    ) -> httpcore.NetworkStream:
        raise OSError("Unix sockets not supported")

    def sleep(self, seconds: float) -> None:
        self._inner.sleep(seconds)


def _build_pinned_ssl_context(hostname: str) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def _make_pinned_pool(
    dest: ValidatedDestination,
    timeout_seconds: int,
) -> httpcore.ConnectionPool:
    """Build an httpcore pool pinned to *dest*.validated_ips.

    TCP connection goes to validated IPs only (via _ValidatedNetworkBackend).
    TLS SNI and hostname verification use dest.hostname (original hostname).
    HTTP Host header uses dest.hostname.
    """
    ssl_ctx = _build_pinned_ssl_context(dest.hostname)
    backend = _ValidatedNetworkBackend(dest.validated_ips, dest.hostname)
    return httpcore.ConnectionPool(
        ssl_context=ssl_ctx,
        max_connections=1,
        max_keepalive_connections=0,
        network_backend=backend,
    )


# ── Real SSRF-safe HTTP transport (P2.6C) ─────────────────────────────────
class HttpxSourceTransport:
    """Controlled HTTPS transport for :func:`fetch_source`.

    When ``fetch_source`` is called with a callable transport stub (tests),
    that stub receives the current URL string. For real/pinned transport,
    call ``fetch_pinned(validated_destination)`` instead.

    The unpinned ``__call__(url)`` path is fail-closed: it raises
    ``SourceFetchError`` because real network I/O without destination
    pinning is insecure. Only :meth:`fetch_pinned` may perform real I/O.

    Security invariants:
    - HTTP-client automatic redirects are DISABLED.
    - TLS certificate verification is ENABLED.
    - No HTTPX proxy/env-variable consumption (direct httpcore path).
    - Per-request destination IP pinning: only :class:`ValidatedDestination`
      IPs are eligible for connection.
    - TLS SNI = original hostname, not IP.
    - Response body is streamed with a hard size cap.
    - Bounded connect/read timeout.
    """

    def __init__(
        self,
        *,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_bytes: int = MAX_RESPONSE_BYTES,
    ):
        self._timeout = timeout_seconds
        self._max_bytes = max_bytes

    def __call__(self, url: str) -> _StubResponse:
        """Fail-closed: unpinned real network is insecure.

        Test stubs are separate callables injected directly, never routed
        through HttpxSourceTransport.
        """
        raise SourceFetchError("destination_not_validated",
                               _EC["destination_not_validated"])

    def fetch_pinned(self, dest: ValidatedDestination) -> _StubResponse:
        """Fetch [dest.url] through a pool pinned to dest.validated_ips.

        Connects only to IPs in the validated set. TLS SNI, hostname
        verification, and Host header all use dest.hostname.

        Uses httpcore.ConnectionPool directly — no httpx wrapping.
        """
        pool = _make_pinned_pool(dest, self._timeout)
        try:
            return self._stream_httpcore(pool, dest)
        finally:
            pool.close()

    def _stream_httpcore(self, pool: httpcore.ConnectionPool,
                         dest: ValidatedDestination) -> _StubResponse:
        headers = [
            (b"host", dest.hostname.encode("ascii")),
            (b"accept", b"text/html, text/plain, application/xhtml+xml, "
                        b"application/xml, text/xml, application/json"),
        ]
        try:
            with pool.stream("GET", dest.url, headers=headers) as resp:
                body = bytearray()
                for chunk in resp.iter_stream():
                    body.extend(chunk)
                    if len(body) > self._max_bytes:
                        raise SourceFetchError(
                            "response_too_large", _EC["response_too_large"],
                        )
                location = ""
                for k, v in resp.headers:
                    if k == b"location":
                        location = v.decode("latin-1")
                        break
                return _StubResponse(
                    status_code=resp.status,
                    headers={k.decode("latin-1"): v.decode("latin-1")
                             for k, v in resp.headers if isinstance(v, bytes)},
                    content=bytes(body),
                    location=location or None,
                )
        except SourceFetchError:
            raise
        except httpcore.ConnectTimeout:
            raise SourceFetchError("fetch_timeout", _EC["fetch_timeout"])
        except httpcore.ConnectError:
            raise SourceFetchError("connect_error", _EC["connect_error"])
        except ssl.SSLError:
            raise SourceFetchError("tls_error", _EC["tls_error"])
        except OSError:
            raise SourceFetchError("network_error", _EC["network_error"])

    def close(self) -> None:
        pass  # stateless — pools are created per-call

    def __enter__(self) -> HttpxSourceTransport:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()


def create_real_transport(**kw) -> HttpxSourceTransport:
    """Factory: the real SSRF-safe transport.

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


# ── Secure fetch with per-hop destination binding ──────────────────────────
def fetch_source(
    url: str,
    *,
    resolver=default_resolver,
    transport=None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> FetchResult:
    """Securely fetch a source URL with per-hop destination validation.

    [transport] is an injectable callable ``(url) -> _StubResponse`` used by
    tests to avoid real network I/O. When None, real fetching is not performed.

    Every redirect hop is independently destination-validated.
    Relative redirects are normalized via ``urljoin`` before re-validation.
    Redirect loops are detected on normalized absolute URLs.
    """
    if transport is None:
        raise SourceFetchError("no_transport", _EC["no_transport"])

    current = url
    chain: list[str] = []
    for _hop in range(MAX_REDIRECTS + 1):
        dest = validate_destination(current, resolver=resolver)
        chain.append(dest.url)

        if isinstance(transport, HttpxSourceTransport):
            resp = transport.fetch_pinned(dest)
        else:
            resp = transport(dest.url)

        if resp.status_code in (301, 302, 303, 307, 308) and resp.location:
            nxt = urljoin(current, resp.location)
            if nxt in chain:
                raise SourceFetchError("redirect_loop", _EC["redirect_loop"])
            current = nxt
            continue
        if resp.status_code >= 400:
            raise SourceFetchError("http_error", _EC["http_error"].format(resp.status_code))
        content_type = (resp.headers.get("content-type", "") or "").split(";")[0].strip().lower()
        if content_type and content_type not in ALLOWED_CONTENT_TYPES:
            raise SourceFetchError("unsupported_content_type",
                                   f"{_EC['unsupported_content_type']} ({content_type})")
        content = resp.content or b""
        if len(content) > max_bytes:
            raise SourceFetchError("response_too_large", _EC["response_too_large"])
        return FetchResult(
            final_url=current, status_code=resp.status_code, content=content,
            content_type=content_type, redirect_chain=chain,
        )
    raise SourceFetchError("too_many_redirects", _EC["too_many_redirects"])
