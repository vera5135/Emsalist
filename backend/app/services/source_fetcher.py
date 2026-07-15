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

import inspect
import ipaddress
import json
import math
import re
import socket
import ssl
from collections.abc import Collection
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
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

# Closed method vocabulary for the source seam. Arbitrary methods (PUT/PATCH/
# DELETE/...) are deliberately NOT supported.
ALLOWED_FETCH_METHODS = frozenset({"GET", "POST"})
MAX_POST_BODY_BYTES = 64 * 1024

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
    "method_not_allowed": "Desteklenmeyen istek yöntemi.",
    "invalid_request_body": "Geçersiz istek gövdesi.",
    "post_redirect_not_allowed": "POST yönlendirmesi güvenli değil.",
}


# Strict single-line header-value shape (defense in depth against header
# injection through the bounded accept/content_type descriptor fields).
_HEADER_VALUE_RE = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~/;,= -]{1,200}$")


class SourceFetchError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int | None = None,
        retry_after_seconds: float | None = None,
    ):
        self.code = code
        self.message = message
        self.http_status = http_status
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)


@dataclass
class FetchResult:
    final_url: str
    status_code: int
    content: bytes
    content_type: str
    redirect_chain: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SourceFetchRequest:
    """Controlled, provider-owned request descriptor for the source seam.

    Only ``GET`` and ``POST`` are permitted. For ``POST`` the body is bytes
    derived from provider-owned JSON (never caller-controlled arbitrary
    headers, Host, connection destination or proxy configuration). The only
    request headers ever emitted are the fixed Host/Accept plus, for POST, a
    fixed Content-Type; nothing here is caller-tunable.
    """

    url: str
    method: str = "GET"
    body: bytes | None = None
    content_type: str | None = None
    accept: str | None = None

    def __post_init__(self) -> None:
        method = (self.method or "GET").upper()
        object.__setattr__(self, "method", method)
        if method not in ALLOWED_FETCH_METHODS:
            raise SourceFetchError("method_not_allowed", _EC["method_not_allowed"])
        for header_value in (self.content_type, self.accept):
            if header_value is not None and not _HEADER_VALUE_RE.fullmatch(header_value):
                raise SourceFetchError("invalid_request_body", _EC["invalid_request_body"])
        if method == "GET":
            if self.body is not None or self.content_type is not None:
                raise SourceFetchError("invalid_request_body", _EC["invalid_request_body"])
        else:  # POST
            if not isinstance(self.body, (bytes, bytearray)):
                raise SourceFetchError("invalid_request_body", _EC["invalid_request_body"])
            if len(self.body) > MAX_POST_BODY_BYTES:
                raise SourceFetchError("invalid_request_body", _EC["invalid_request_body"])
            object.__setattr__(self, "body", bytes(self.body))
            if not self.content_type:
                raise SourceFetchError("invalid_request_body", _EC["invalid_request_body"])

    @classmethod
    def get(cls, url: str, *, accept: str | None = None) -> "SourceFetchRequest":
        return cls(url=url, method="GET", accept=accept)

    @classmethod
    def post_json(
        cls,
        url: str,
        payload: object,
        *,
        accept: str | None = "application/json",
        content_type: str = "application/json; charset=utf-8",
    ) -> "SourceFetchRequest":
        """Build a POST request whose body is deterministic UTF-8 JSON bytes.

        The payload is serialized here from provider-owned data so no raw byte
        stream from an untrusted caller is ever transmitted.
        """
        try:
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        except (TypeError, ValueError):
            raise SourceFetchError("invalid_request_body", _EC["invalid_request_body"]) from None
        return cls(
            url=url, method="POST", body=body,
            content_type=content_type, accept=accept,
        )


def host_matches_allowed_domains(
    hostname: str,
    allowed_domains: Collection[str],
) -> bool:
    """Return whether *hostname* is exactly or below a controlled domain.

    Both host and domain names are normalized to lowercase without a trailing
    dot. Substring matching is deliberately forbidden.
    """
    host = (hostname or "").lower().rstrip(".")
    if not host:
        return False
    for raw_domain in allowed_domains:
        domain = (raw_domain or "").lower().rstrip(".")
        if domain and (host == domain or host.endswith("." + domain)):
            return True
    return False


def url_matches_allowed_domains(
    url: str,
    allowed_domains: Collection[str],
) -> bool:
    """Apply :func:`host_matches_allowed_domains` to a URL hostname."""
    try:
        hostname = urlparse(url).hostname or ""
    except (TypeError, ValueError):
        return False
    return host_matches_allowed_domains(hostname, allowed_domains)


def domains_within_global_allowlist(allowed_domains: Collection[str]) -> bool:
    """Validate a non-empty provider domain scope against the global boundary."""
    domains = tuple(allowed_domains or ())
    return bool(domains) and all(
        host_matches_allowed_domains(domain, ALLOWED_DOMAINS)
        for domain in domains
    )


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


def _validated_timeout_seconds(timeout_seconds: int) -> int:
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or not 1 <= timeout_seconds <= 300
    ):
        raise ValueError("timeout_seconds must be an integer from 1 to 300")
    return timeout_seconds


def parse_retry_after_seconds(
    raw_value: str | None,
    *,
    now: datetime | None = None,
) -> float | None:
    """Parse a safe Retry-After value without retaining the raw header."""
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    if not value:
        return None
    try:
        seconds = float(value)
        if seconds.is_integer():
            seconds = int(seconds)
        if not math.isfinite(float(seconds)) or float(seconds) < 0:
            return None
        return float(seconds)
    except ValueError:
        pass

    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    current = now or datetime.now(UTC)
    delta = (parsed.astimezone(UTC) - current.astimezone(UTC)).total_seconds()
    if not math.isfinite(delta) or delta < 0:
        return None
    return float(delta)


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
    url: str,
    resolver=default_resolver,
    allowed_domains: Collection[str] | None = None,
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

    if not host_matches_allowed_domains(hostname, ALLOWED_DOMAINS):
        raise SourceFetchError("domain_not_allowed", _EC["domain_not_allowed"])
    if allowed_domains is not None and not host_matches_allowed_domains(
        hostname, allowed_domains,
    ):
        raise SourceFetchError("domain_not_allowed", _EC["domain_not_allowed"])

    try:
        resolved = resolver(hostname)
    except Exception:
        raise SourceFetchError("dns_failed", _EC["dns_failed"]) from None
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
def validate_url(
    url: str,
    resolver=default_resolver,
    allowed_domains: Collection[str] | None = None,
) -> list[str]:
    dest = validate_destination(
        url, resolver=resolver, allowed_domains=allowed_domains,
    )
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

    def __init__(
        self,
        validated_ips: tuple[str, ...],
        server_hostname: str,
        *,
        inner: httpcore.NetworkBackend | None = None,
    ):
        self._validated_ips = validated_ips
        self._server_hostname = server_hostname
        self._inner = inner or httpcore.SyncBackend()

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
                stream = self._inner.connect_tcp(
                    ip, port, timeout, local_address, socket_options,
                )
                return _ClosingNetworkStream(stream)
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


class _ClosingNetworkStream(httpcore.NetworkStream):
    """Delegate stream that closes the raw socket when TLS setup fails."""

    def __init__(self, inner: httpcore.NetworkStream):
        self._inner = inner

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return self._inner.read(max_bytes, timeout)

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self._inner.write(buffer, timeout)

    def close(self) -> None:
        self._inner.close()

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.NetworkStream:
        try:
            self._inner = self._inner.start_tls(
                ssl_context, server_hostname, timeout,
            )
        except Exception:
            self._inner.close()
            raise
        return self

    def get_extra_info(self, info: str) -> object:
        return self._inner.get_extra_info(info)


def _build_pinned_ssl_context(hostname: str) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def _make_pinned_pool(
    dest: ValidatedDestination,
    timeout_seconds: int,
    *,
    network_backend: httpcore.NetworkBackend | None = None,
) -> httpcore.ConnectionPool:
    """Build an httpcore pool pinned to *dest*.validated_ips.

    TCP connection goes to validated IPs only (via _ValidatedNetworkBackend).
    TLS SNI and hostname verification use dest.hostname (original hostname).
    HTTP Host header uses dest.hostname.
    """
    ssl_ctx = _build_pinned_ssl_context(dest.hostname)
    backend = _ValidatedNetworkBackend(
        dest.validated_ips, dest.hostname, inner=network_backend,
    )
    return httpcore.ConnectionPool(
        ssl_context=ssl_ctx,
        max_connections=1,
        max_keepalive_connections=0,
        network_backend=backend,
    )


def _host_header_value(dest: ValidatedDestination) -> str:
    default_port = 443 if dest.scheme == "https" else 80
    if dest.port == default_port:
        return dest.hostname
    return f"{dest.hostname}:{dest.port}"


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
        _network_backend_factory: Callable[
            [ValidatedDestination], httpcore.NetworkBackend
        ] | None = None,
    ):
        self._timeout = _validated_timeout_seconds(timeout_seconds)
        self._max_bytes = max_bytes
        self._network_backend_factory = _network_backend_factory

    def __call__(self, url: str) -> _StubResponse:
        """Fail-closed: unpinned real network is insecure.

        Test stubs are separate callables injected directly, never routed
        through HttpxSourceTransport.
        """
        raise SourceFetchError("destination_not_validated",
                               _EC["destination_not_validated"])

    def fetch_pinned(
        self,
        dest: ValidatedDestination,
        *,
        timeout_seconds: int | None = None,
        request: SourceFetchRequest | None = None,
    ) -> _StubResponse:
        """Fetch [dest.url] through a pool pinned to dest.validated_ips.

        Connects only to IPs in the validated set. TLS SNI, hostname
        verification, and Host header all use dest.hostname.

        [request] optionally carries the controlled method/body descriptor
        (GET default). Only the closed GET/POST vocabulary is accepted and the
        body is seam-validated bytes — never caller-controlled headers.

        Uses httpcore.ConnectionPool directly — no httpx wrapping.
        """
        request_timeout = (
            self._timeout if timeout_seconds is None
            else _validated_timeout_seconds(timeout_seconds)
        )
        backend = None
        if self._network_backend_factory is not None:
            backend = self._network_backend_factory(dest)
        pool = _make_pinned_pool(
            dest, request_timeout, network_backend=backend,
        )
        try:
            return self._stream_httpcore(
                pool, dest, timeout_seconds=request_timeout, request=request,
            )
        finally:
            pool.close()

    def _stream_httpcore(self, pool: httpcore.ConnectionPool,
                         dest: ValidatedDestination, *,
                         timeout_seconds: int,
                         request: SourceFetchRequest | None = None) -> _StubResponse:
        method = "GET"
        request_body: bytes | None = None
        accept_value = (b"text/html, text/plain, application/xhtml+xml, "
                        b"application/xml, text/xml, application/json")
        headers = [
            (b"host", _host_header_value(dest).encode("ascii")),
        ]
        if request is not None:
            method = request.method
            if method not in ALLOWED_FETCH_METHODS:
                raise SourceFetchError("method_not_allowed", _EC["method_not_allowed"])
            if request.accept:
                accept_value = request.accept.encode("ascii")
            if method == "POST":
                request_body = request.body
                headers.append((
                    b"content-type",
                    (request.content_type or "application/json; charset=utf-8").encode("ascii"),
                ))
        headers.insert(1, (b"accept", accept_value))
        try:
            timeout_extensions = {
                "timeout": {
                    "connect": timeout_seconds,
                    "read": timeout_seconds,
                    "write": timeout_seconds,
                    "pool": timeout_seconds,
                },
            }
            with pool.stream(
                method, dest.url, headers=headers,
                content=request_body,
                extensions=timeout_extensions,
            ) as resp:
                body = bytearray()
                for chunk in resp.iter_stream():
                    body.extend(chunk)
                    if len(body) > self._max_bytes:
                        raise SourceFetchError(
                            "response_too_large", _EC["response_too_large"],
                        )
                location = ""
                for k, v in resp.headers:
                    if k.lower() == b"location":
                        location = v.decode("latin-1")
                        break
                return _StubResponse(
                    status_code=resp.status,
                    headers={k.decode("latin-1").lower(): v.decode("latin-1")
                             for k, v in resp.headers if isinstance(v, bytes)},
                    content=bytes(body),
                    location=location or None,
                )
        except SourceFetchError:
            raise
        except httpcore.TimeoutException:
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
def _call_stub_transport(transport, url: str, request: SourceFetchRequest):
    """Invoke a test-stub transport callable with backward compatibility.

    Legacy stubs accept ``(url)`` and are only valid for GET. POST-capable
    stubs must accept a ``request`` keyword argument. A POST routed to a
    GET-only stub fails closed (never silently degrades to GET).
    """
    accepts_request = False
    try:
        signature = inspect.signature(transport)
    except (TypeError, ValueError):
        signature = None
    if signature is not None:
        accepts_request = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD
            or parameter.name == "request"
            for parameter in signature.parameters.values()
        )
    if request.method == "GET" and not accepts_request:
        return transport(url)
    if not accepts_request:
        raise SourceFetchError("transport_unavailable", _EC["transport_unavailable"])
    return transport(url, request=request)


def fetch_source(
    url: str,
    *,
    resolver=default_resolver,
    transport=None,
    timeout: int | None = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
    allowed_domains: Collection[str] | None = None,
) -> FetchResult:
    """Securely GET a source URL with per-hop destination validation.

    Preserved GET-only entrypoint. See :func:`fetch_source_request` for the
    generalized controlled-request seam.
    """
    return fetch_source_request(
        SourceFetchRequest.get(url, accept=None),
        resolver=resolver,
        transport=transport,
        timeout=timeout,
        max_bytes=max_bytes,
        allowed_domains=allowed_domains,
    )


def fetch_source_request(
    request: SourceFetchRequest,
    *,
    resolver=default_resolver,
    transport=None,
    timeout: int | None = None,
    max_bytes: int = MAX_RESPONSE_BYTES,
    allowed_domains: Collection[str] | None = None,
) -> FetchResult:
    """Securely execute a controlled :class:`SourceFetchRequest`.

    [transport] is an injectable callable used by tests to avoid real network
    I/O. When None, real fetching is not performed.

    Every redirect hop is independently destination-validated. Relative
    redirects are normalized via ``urljoin`` before re-validation. Redirect
    loops are detected on normalized absolute URLs.

    Redirect semantics for POST-originated requests are bounded and explicit:

    - 303 → followed as GET without a body (See Other).
    - 301/302 → fail closed (a POST body is never blindly replayed and the
      seam never silently rewrites ambiguous redirect semantics).
    - 307/308 → method and body preserved ONLY because the next hop passes the
      exact same destination validation boundary as the first hop.

    GET redirect behavior is unchanged from the original seam.
    """
    if transport is None:
        raise SourceFetchError("no_transport", _EC["no_transport"])
    if not isinstance(request, SourceFetchRequest):
        raise SourceFetchError("invalid_request_body", _EC["invalid_request_body"])

    current = request.url
    method = request.method
    chain: list[str] = []
    for _hop in range(MAX_REDIRECTS + 1):
        dest = validate_destination(
            current,
            resolver=resolver,
            allowed_domains=allowed_domains,
        )
        chain.append(dest.url)

        if method == "GET":
            hop_request = SourceFetchRequest.get(dest.url, accept=request.accept)
        else:
            hop_request = SourceFetchRequest(
                url=dest.url, method="POST", body=request.body,
                content_type=request.content_type, accept=request.accept,
            )

        if isinstance(transport, HttpxSourceTransport):
            resp = transport.fetch_pinned(
                dest, timeout_seconds=timeout, request=hop_request,
            )
        else:
            resp = _call_stub_transport(transport, dest.url, hop_request)

        if resp.status_code in (301, 302, 303, 307, 308) and resp.location:
            nxt = urljoin(current, resp.location)
            if nxt in chain:
                raise SourceFetchError("redirect_loop", _EC["redirect_loop"])
            if method == "POST":
                if resp.status_code == 303:
                    method = "GET"
                elif resp.status_code in (301, 302):
                    raise SourceFetchError(
                        "post_redirect_not_allowed",
                        _EC["post_redirect_not_allowed"],
                    )
                # 307/308: method/body preserved; the next loop iteration
                # re-validates the new destination before any transport call.
            current = nxt
            continue
        if resp.status_code >= 400:
            raise SourceFetchError(
                "http_error",
                _EC["http_error"].format(resp.status_code),
                http_status=resp.status_code,
                retry_after_seconds=parse_retry_after_seconds(
                    resp.headers.get("retry-after"),
                ),
            )
        content_type = (resp.headers.get("content-type", "") or "").split(";")[0].strip().lower()
        if content_type and content_type not in ALLOWED_CONTENT_TYPES:
            raise SourceFetchError("unsupported_content_type",
                                   _EC["unsupported_content_type"])
        content = resp.content or b""
        if len(content) > max_bytes:
            raise SourceFetchError("response_too_large", _EC["response_too_large"])
        return FetchResult(
            final_url=current, status_code=resp.status_code, content=content,
            content_type=content_type, redirect_chain=chain,
        )
    raise SourceFetchError("too_many_redirects", _EC["too_many_redirects"])
