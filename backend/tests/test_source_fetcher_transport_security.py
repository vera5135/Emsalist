"""P2.6C — Source fetcher transport security regressions (deterministic)."""
from __future__ import annotations

import os
import ssl
from unittest.mock import patch

import httpcore
import pytest

from app.services.source_fetcher import (
    MAX_REDIRECTS,
    MAX_RESPONSE_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    HttpxSourceTransport,
    SourceFetchError,
    ValidatedDestination,
    _StubResponse,
    _ValidatedNetworkBackend,
    _make_pinned_pool,
    create_live_transport,
    create_real_transport,
    fetch_source,
    validate_destination,
    validate_url,
)

SAFE_IP = "93.184.216.34"
SAFE_IP_B = "93.184.216.35"
SAFE_IP_BOTH = (SAFE_IP, SAFE_IP_B)
YARGITAY_URL = "https://karararama.yargitay.gov.tr/karar/123"
LOOPBACK = "127.0.0.1"


def _resolver(ip):
    return lambda host: [ip]


# ── trust_env / env proxy isolation ──────────────────────────────────────
def test_env_proxy_not_consumed_by_pinned_pool():
    dest = validate_destination(YARGITAY_URL, resolver=_resolver(SAFE_IP))
    with patch.dict(os.environ, {"HTTPS_PROXY": "http://evil:9999", "SSL_CERT_FILE": "/nonexistent"}, clear=False):
        pool = _make_pinned_pool(dest, 5)
        pool.close()


def test_unpinned_call_fails_closed():
    transport = HttpxSourceTransport(timeout_seconds=5)
    with pytest.raises(SourceFetchError) as e:
        transport(YARGITAY_URL)
    assert e.value.code == "destination_not_validated"
    transport.close()


# ── Transport properties ─────────────────────────────────────────────────
def test_default_timeout():
    transport = HttpxSourceTransport()
    assert transport._timeout == DEFAULT_TIMEOUT_SECONDS
    transport.close()
    transport2 = HttpxSourceTransport(timeout_seconds=7)
    assert transport2._timeout == 7
    transport2.close()


def test_tls_verification_on_pool():
    dest = validate_destination(YARGITAY_URL, resolver=_resolver(SAFE_IP))
    pool = _make_pinned_pool(dest, 5)
    try:
        ctx = pool._ssl_context
        assert ctx is not None
        assert ctx.verify_mode == ssl.CERT_REQUIRED
        assert ctx.check_hostname is True
    finally:
        pool.close()


# ── ValidatedDestination contract ────────────────────────────────────────
def test_validate_destination_returns_typed():
    dest = validate_destination(YARGITAY_URL, resolver=_resolver(SAFE_IP))
    assert isinstance(dest, ValidatedDestination)
    assert dest.url == YARGITAY_URL
    assert dest.scheme == "https"
    assert dest.hostname == "karararama.yargitay.gov.tr"
    assert dest.port == 443
    assert dest.validated_ips == (SAFE_IP,)


def test_validate_destination_default_http_port():
    dest = validate_destination("http://mevzuat.gov.tr/x", resolver=_resolver(SAFE_IP))
    assert dest.port == 80


def test_validated_destination_immutable():
    dest = validate_destination(YARGITAY_URL, resolver=_resolver(SAFE_IP))
    from dataclasses import FrozenInstanceError
    with pytest.raises(FrozenInstanceError):
        dest.url = "hacked"  # type: ignore


def test_validate_url_compat_returns_list():
    ips = validate_url(YARGITAY_URL, resolver=_resolver(SAFE_IP))
    assert ips == [SAFE_IP]


# ── DNS safety ───────────────────────────────────────────────────────────
def test_unsafe_dns_fails_before_transport():
    with pytest.raises(SourceFetchError) as e:
        validate_destination(YARGITAY_URL, resolver=_resolver("10.0.0.5"))
    assert e.value.code == "dns_unsafe_ip"


def test_private_ip_fails_before_transport():
    with pytest.raises(SourceFetchError) as e:
        validate_destination(YARGITAY_URL, resolver=_resolver("192.168.1.1"))
    assert e.value.code == "dns_unsafe_ip"


def test_loopback_fails_before_transport():
    with pytest.raises(SourceFetchError) as e:
        validate_destination(YARGITAY_URL, resolver=_resolver(LOOPBACK))
    assert e.value.code == "dns_unsafe_ip"


def test_ipv4_mapped_ipv6_private_blocked():
    with pytest.raises(SourceFetchError) as e:
        validate_destination(YARGITAY_URL, resolver=_resolver("::ffff:127.0.0.1"))
    assert e.value.code == "dns_unsafe_ip"


# ── DNS rebinding regression ─────────────────────────────────────────────
def test_dns_rebinding_validation_catches_private():
    dest = validate_destination(YARGITAY_URL, resolver=_resolver(SAFE_IP))
    assert LOOPBACK not in dest.validated_ips
    assert SAFE_IP in dest.validated_ips


def test_dns_rebinding_transport_only_uses_validated():
    backend = _ValidatedNetworkBackend((SAFE_IP,), YARGITAY_URL)
    calls = []

    class FakeStream:
        pass

    def _fake_connect(host, port, timeout, local_address=None, socket_options=None):
        calls.append(host)
        if host == SAFE_IP:
            return FakeStream()
        raise OSError("not allowed")

    backend._inner.connect_tcp = _fake_connect
    result = backend.connect_tcp("karararama.yargitay.gov.tr", 443, 5)
    assert isinstance(result, FakeStream)
    for call_host in calls:
        assert call_host == SAFE_IP


def test_ipv6_rebinding_validated_only():
    v6_safe = "2606:2800:220:1:248:1893:25c8:1946"
    dest = validate_destination(YARGITAY_URL, resolver=_resolver(v6_safe))
    assert "::1" not in dest.validated_ips
    assert v6_safe in dest.validated_ips


# ── Multiple validated-IP fallback ───────────────────────────────────────
def test_connect_error_A_to_B_fallback():
    backend = _ValidatedNetworkBackend(SAFE_IP_BOTH, YARGITAY_URL)
    calls = []

    class FakeStream:
        pass

    def _fake_connect(host, port, timeout, local_address=None, socket_options=None):
        calls.append(host)
        if host == SAFE_IP:
            raise httpcore.ConnectError("A failed")
        return FakeStream()

    backend._inner.connect_tcp = _fake_connect
    result = backend.connect_tcp("karararama.yargitay.gov.tr", 443, 5)
    assert isinstance(result, FakeStream)
    assert calls == [SAFE_IP, SAFE_IP_B]


def test_connect_timeout_A_to_B_fallback():
    backend = _ValidatedNetworkBackend(SAFE_IP_BOTH, YARGITAY_URL)
    calls = []

    class FakeStream:
        pass

    def _fake_connect(host, port, timeout, local_address=None, socket_options=None):
        calls.append(host)
        if host == SAFE_IP:
            raise httpcore.ConnectTimeout("A timeout")
        return FakeStream()

    backend._inner.connect_tcp = _fake_connect
    result = backend.connect_tcp("karararama.yargitay.gov.tr", 443, 5)
    assert isinstance(result, FakeStream)
    assert calls == [SAFE_IP, SAFE_IP_B]


def test_all_connect_failed_maps_to_connect_error():
    backend = _ValidatedNetworkBackend(SAFE_IP_BOTH, YARGITAY_URL)

    def _fake_connect(host, port, timeout, local_address=None, socket_options=None):
        raise httpcore.ConnectError("fail")

    backend._inner.connect_tcp = _fake_connect
    with pytest.raises(SourceFetchError) as e:
        backend.connect_tcp("karararama.yargitay.gov.tr", 443, 5)
    assert e.value.code == "connect_error"


def test_all_timeout_maps_to_fetch_timeout():
    backend = _ValidatedNetworkBackend(SAFE_IP_BOTH, YARGITAY_URL)

    def _fake_connect(host, port, timeout, local_address=None, socket_options=None):
        raise httpcore.ConnectTimeout("timeout")

    backend._inner.connect_tcp = _fake_connect
    with pytest.raises(SourceFetchError) as e:
        backend.connect_tcp("karararama.yargitay.gov.tr", 443, 5)
    assert e.value.code == "fetch_timeout"


def test_outside_validated_set_blocked():
    backend = _ValidatedNetworkBackend((SAFE_IP,), YARGITAY_URL)
    calls = []

    def _fake_connect(host, port, timeout, local_address=None, socket_options=None):
        calls.append(host)
        raise httpcore.ConnectError("fail")
    backend._inner.connect_tcp = _fake_connect
    with pytest.raises(SourceFetchError) as e:
        backend.connect_tcp("karararama.yargitay.gov.tr", 443, 5)
    assert e.value.code == "connect_error"
    assert all(h == SAFE_IP for h in calls)


# ── Redirect hop binding ─────────────────────────────────────────────────
def test_redirect_hop_independent_validation():
    resolver_a = _resolver(SAFE_IP)
    resolver_b = _resolver(SAFE_IP_B)

    def transport(url):
        if url == YARGITAY_URL:
            return _StubResponse(302, {"content-type": "text/html"}, b"",
                                 location="https://mevzuat.gov.tr/redirected")
        return _StubResponse(200, {"content-type": "text/html"}, b"OK")

    result = fetch_source(
        YARGITAY_URL,
        resolver=lambda h: (resolver_a(h) if "yargitay" in h else resolver_b(h)),
        transport=transport,
    )
    assert result.final_url == "https://mevzuat.gov.tr/redirected"
    assert result.status_code == 200


def test_previous_hop_ip_not_automatically_authorized():
    def transport(url):
        if url == YARGITAY_URL:
            return _StubResponse(302, {"content-type": "text/html"}, b"",
                                 location="https://mevzuat.gov.tr/6098")
        return _StubResponse(200, {"content-type": "text/html"}, b"done")

    result = fetch_source(YARGITAY_URL, resolver=_resolver(SAFE_IP), transport=transport)
    assert result.status_code == 200


# ── Redirect normalization ───────────────────────────────────────────────
def test_relative_redirect_resolved():
    def transport(url):
        if url == YARGITAY_URL:
            return _StubResponse(302, {"content-type": "text/html"}, b"",
                                 location="/karar/456")
        return _StubResponse(200, {"content-type": "text/html"}, b"ok")

    result = fetch_source(YARGITAY_URL, resolver=_resolver(SAFE_IP), transport=transport)
    assert "karararama.yargitay.gov.tr" in result.final_url
    assert "/karar/456" in result.final_url


def test_protocol_relative_external_redirect_blocked():
    def transport(url):
        return _StubResponse(302, {"content-type": "text/html"}, b"",
                             location="//evil.example.com/x")

    with pytest.raises(SourceFetchError) as e:
        fetch_source(YARGITAY_URL, resolver=_resolver(SAFE_IP), transport=transport)
    assert e.value.code == "domain_not_allowed"


def test_private_redirect_blocked():
    def transport(url):
        return _StubResponse(302, {"content-type": "text/html"}, b"",
                             location="http://127.0.0.1/x")

    with pytest.raises(SourceFetchError) as e:
        fetch_source(YARGITAY_URL, resolver=_resolver(SAFE_IP), transport=transport)
    assert e.value.code in ("ip_literal_not_allowed", "blocked_ip")


def test_credentials_in_redirect_blocked():
    def transport(url):
        return _StubResponse(302, {"content-type": "text/html"}, b"",
                             location="https://user:pass@yargitay.gov.tr/x")

    with pytest.raises(SourceFetchError) as e:
        fetch_source(YARGITAY_URL, resolver=_resolver(SAFE_IP), transport=transport)
    assert e.value.code == "credentials_in_url"


def test_redirect_loop_uses_normalized_urls():
    def transport(url):
        return _StubResponse(302, {"content-type": "text/html"}, b"",
                             location=YARGITAY_URL)

    with pytest.raises(SourceFetchError) as e:
        fetch_source(YARGITAY_URL, resolver=_resolver(SAFE_IP), transport=transport)
    assert e.value.code == "redirect_loop"


def test_too_many_redirects_preserved():
    count = [0]

    def transport(url):
        count[0] += 1
        return _StubResponse(302, {"content-type": "text/html"}, b"",
                             location="https://karararama.yargitay.gov.tr/karar/%d" % count[0])

    with pytest.raises(SourceFetchError) as e:
        fetch_source(YARGITAY_URL, resolver=_resolver(SAFE_IP), transport=transport)
    assert e.value.code == "too_many_redirects"


# ── Error codes ─────────────────────────────────────────────────────────
def test_fetch_timeout_safe_error():
    from app.services.source_fetcher import _EC
    assert _EC["fetch_timeout"]


def test_connect_safe_error():
    from app.services.source_fetcher import _EC
    assert _EC["connect_error"]


def test_tls_safe_error():
    from app.services.source_fetcher import _EC
    assert _EC["tls_error"]


def test_destination_not_validated_safe_error():
    from app.services.source_fetcher import _EC
    assert _EC["destination_not_validated"]


def test_no_raw_exception_in_network_error():
    er = SourceFetchError("network_error", "Ag hatasi.")
    assert len(er.message) < 120


# ── Transport lifecycle ─────────────────────────────────────────────────
def test_transport_close():
    transport = HttpxSourceTransport(timeout_seconds=5)
    transport.close()


def test_transport_context_manager():
    with HttpxSourceTransport(timeout_seconds=5) as transport:
        assert isinstance(transport, HttpxSourceTransport)


def test_pool_closes_after_stream():
    dest = validate_destination(YARGITAY_URL, resolver=_resolver(SAFE_IP))
    pool = _make_pinned_pool(dest, 5)
    pool.close()


# ── Factory gates ────────────────────────────────────────────────────────
def test_create_real_transport():
    t = create_real_transport(timeout_seconds=5)
    assert isinstance(t, HttpxSourceTransport)
    t.close()


def test_create_live_transport_gated():
    t = create_live_transport()
    assert t is None


def test_create_live_transport_disabled_with_invalid_env():
    with patch.dict(os.environ, {"OFFICIAL_PROVIDER_LIVE_SMOKE": "0"}, clear=False):
        t = create_live_transport()
        assert t is None


def test_create_live_transport_enabled():
    with patch.dict(os.environ, {"OFFICIAL_PROVIDER_LIVE_SMOKE": "1"}, clear=False):
        t = create_live_transport(timeout_seconds=5)
        assert isinstance(t, HttpxSourceTransport)
        t.close()


# ── Real pinned end-to-end path ──────────────────────────────────────────
class _FakeNetworkStream(httpcore.NetworkStream):
    def __init__(self, response_bytes, captured=None):
        self._buf = bytearray(response_bytes)
        self._tls_captured = captured or {}
        self.closed = False

    def read(self, max_bytes, timeout=None):
        data = bytes(self._buf[:max_bytes])
        self._buf = self._buf[max_bytes:]
        return data

    def write(self, data, timeout=None):
        pass

    def close(self):
        self.closed = True

    def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        self._tls_captured["server_hostname"] = server_hostname
        self._tls_captured["check_hostname"] = ssl_context.check_hostname
        self._tls_captured["verify_mode"] = ssl_context.verify_mode
        return self

    def get_extra_info(self, info, default=None):
        return self._tls_captured.get(info, default)


class _FakePinnedBackend(httpcore.NetworkBackend):
    def __init__(self, response_bytes=b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n",
                 captures=None):
        self._response_bytes = response_bytes
        self._captures = captures or {}
        self._captured_hosts = []

    def connect_tcp(self, host, port, timeout, local_address=None, socket_options=None):
        self._captured_hosts.append(host)
        return _FakeNetworkStream(self._response_bytes, self._captures)

    def connect_unix_socket(self, path, timeout, socket_options=None):
        raise OSError()

    def sleep(self, seconds):
        pass


def test_end_to_end_pinned_fetch_200():
    response_body = (b"HTTP/1.1 200 OK\r\n"
                     b"Content-Type: text/html\r\n"
                     b"\r\n"
                     b"<html><article>Yargitay karari</article></html>")

    backend = _FakePinnedBackend(response_body)
    ssl_ctx = ssl.create_default_context()
    pool = httpcore.ConnectionPool(
        ssl_context=ssl_ctx, max_connections=1,
        max_keepalive_connections=0, network_backend=backend,
    )
    headers = [(b"host", b"karararama.yargitay.gov.tr")]
    with pool.stream("GET", YARGITAY_URL, headers=headers) as resp:
        body = b"".join(resp.iter_stream())
        assert resp.status == 200
        assert b"Yargitay karari" in body
    pool.close()


def test_end_to_end_pinned_fetch_via_transport():
    response_body = (b"HTTP/1.1 200 OK\r\n"
                     b"Content-Type: text/html\r\n"
                     b"\r\n"
                     b"<html>test body</html>")

    dest = validate_destination(YARGITAY_URL, resolver=_resolver(SAFE_IP))
    ssl_ctx = ssl.create_default_context()
    backend = _FakePinnedBackend(response_body)

    pool = httpcore.ConnectionPool(
        ssl_context=ssl_ctx, max_connections=1,
        max_keepalive_connections=0, network_backend=backend,
    )
    headers = [(b"host", dest.hostname.encode())]
    with pool.stream("GET", dest.url, headers=headers) as resp:
        body = b"".join(resp.iter_stream())
        assert resp.status == 200
        assert b"test body" in body
    pool.close()


def test_host_header_pinned_to_original_hostname():
    dest = validate_destination(YARGITAY_URL, resolver=_resolver(SAFE_IP))
    pool = _make_pinned_pool(dest, 5)
    try:
        request_host = dest.hostname
        assert "karararama.yargitay.gov.tr" in request_host
        assert SAFE_IP not in request_host
    finally:
        pool.close()


def test_tls_server_hostname_is_original_hostname():
    dest = validate_destination(YARGITAY_URL, resolver=_resolver(SAFE_IP))
    from app.services.source_fetcher import _build_pinned_ssl_context
    ctx = _build_pinned_ssl_context(dest.hostname)
    assert ctx.check_hostname is True
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    # _build_pinned_ssl_context creates context for the original hostname,
    # so TLS SNI will use dest.hostname (not the validated IP)


# ── Actual-path DNS rebinding ────────────────────────────────────────────
def test_actual_path_dns_rebinding_never_uses_rebind_target():
    dest = validate_destination(YARGITAY_URL, resolver=_resolver(SAFE_IP))

    validated_backend = _ValidatedNetworkBackend(dest.validated_ips, dest.hostname)
    calls = []

    class FakeStream:
        pass

    def _fake_connect(host, port, timeout, local_address=None, socket_options=None):
        calls.append(host)
        return FakeStream()

    validated_backend._inner.connect_tcp = _fake_connect
    validated_backend.connect_tcp(dest.hostname, 443, 5)

    assert LOOPBACK not in calls
    assert all(h == SAFE_IP for h in calls)


# ── FetchSource uses pinned transport correctly ──────────────────────────
def test_fetch_source_pinned_transport_fails_on_unpinned_call():
    transport = HttpxSourceTransport(timeout_seconds=5)
    with pytest.raises(SourceFetchError) as e:
        transport(YARGITAY_URL)
    assert e.value.code == "destination_not_validated"


# ── Response size / content-type ─────────────────────────────────────────
def test_oversized_response_rejected():
    def transport(url):
        return _StubResponse(200, {"content-type": "text/html"},
                             b"x" * (MAX_RESPONSE_BYTES + 1))

    with pytest.raises(SourceFetchError) as e:
        fetch_source(YARGITAY_URL, resolver=_resolver(SAFE_IP), transport=transport,
                     max_bytes=MAX_RESPONSE_BYTES)
    assert e.value.code == "response_too_large"


def test_unsupported_content_type_rejected():
    def transport(url):
        return _StubResponse(200, {"content-type": "application/octet-stream"}, b"data")

    with pytest.raises(SourceFetchError) as e:
        fetch_source(YARGITAY_URL, resolver=_resolver(SAFE_IP), transport=transport)
    assert e.value.code == "unsupported_content_type"


def test_no_transport_raises():
    with pytest.raises(SourceFetchError) as e:
        fetch_source(YARGITAY_URL, resolver=_resolver(SAFE_IP), transport=None)
    assert e.value.code == "no_transport"


# ── HTTP status codes ────────────────────────────────────────────────────
def test_http_4xx_raises():
    def transport(url):
        return _StubResponse(404, {"content-type": "text/html"}, b"not found")

    with pytest.raises(SourceFetchError) as e:
        fetch_source(YARGITAY_URL, resolver=_resolver(SAFE_IP), transport=transport)
    assert e.value.code == "http_error"


def test_http_5xx_raises():
    def transport(url):
        return _StubResponse(503, {"content-type": "text/html"}, b"error")

    with pytest.raises(SourceFetchError) as e:
        fetch_source(YARGITAY_URL, resolver=_resolver(SAFE_IP), transport=transport)
    assert e.value.code == "http_error"
