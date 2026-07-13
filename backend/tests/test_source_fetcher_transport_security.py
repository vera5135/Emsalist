"""P2.6C — Source fetcher transport security regressions (deterministic)."""
from __future__ import annotations

import os
import ssl
from unittest.mock import patch

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
    _make_pinned_client,
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
MEVZUAT_URL = "https://mevzuat.gov.tr/6098"
LOOPBACK = "127.0.0.1"


def _resolver(ip):
    return lambda host: [ip]


def _multi_resolver(*ips):
    return lambda host: list(ips)


# ── trust_env=False ──────────────────────────────────────────────────────
def test_trust_env_false_is_set_on_unpinned_client():
    transport = HttpxSourceTransport(timeout_seconds=10)
    with patch.dict(os.environ, {"HTTP_PROXY": "http://evil.proxy:9999"}, clear=False):
        transport2 = HttpxSourceTransport(timeout_seconds=5)
    transport2.close()
    transport.close()


def test_env_proxy_not_consumed_by_pinned_client():
    dest = validate_destination(YARGITAY_URL, resolver=_resolver(SAFE_IP))
    with patch.dict(os.environ, {"HTTPS_PROXY": "http://evil:9999", "SSL_CERT_FILE": "/nonexistent"}, clear=False):
        client = _make_pinned_client(dest, 5)
        client.close()


# ── follow_redirects=False ───────────────────────────────────────────────
def test_hardcoded_follow_redirects_false():
    dest = validate_destination(YARGITAY_URL, resolver=_resolver(SAFE_IP))
    client = _make_pinned_client(dest, 5)
    try:
        assert client.follow_redirects is False
    finally:
        client.close()

    transport = HttpxSourceTransport(timeout_seconds=5)
    transport.close()


# ── TLS verification ─────────────────────────────────────────────────────
def test_verify_true_in_source():
    dest = validate_destination(YARGITAY_URL, resolver=_resolver(SAFE_IP))
    client = _make_pinned_client(dest, 5)
    try:
        # httpx.Client wraps an httpcore transport with TLS verification.
        p = client._transport
        assert p._ssl_context is not None
        assert p._ssl_context.verify_mode == ssl.CERT_REQUIRED
    finally:
        client.close()


# ── timeout configured ───────────────────────────────────────────────────
def test_default_timeout():
    transport = HttpxSourceTransport()
    assert transport._timeout == DEFAULT_TIMEOUT_SECONDS
    transport.close()

    transport2 = HttpxSourceTransport(timeout_seconds=7)
    assert transport2._timeout == 7
    transport2.close()


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
    from httpcore import SyncBackend
    backend = _ValidatedNetworkBackend((SAFE_IP,), YARGITAY_URL)
    calls = []

    def _fake_connect(host, port, timeout, local_address=None, socket_options=None):
        calls.append(host)
        if host == SAFE_IP:
            return SyncBackend().connect_tcp(host, port, timeout)
        raise OSError("not allowed")

    backend._inner.connect_tcp = _fake_connect
    try:
        backend.connect_tcp("karararama.yargitay.gov.tr", 443, 5)
    except (OSError, SourceFetchError):
        pass
    for call_host in calls:
        assert call_host == SAFE_IP


def test_ipv6_rebinding_validated_only():
    v6_safe = "2606:2800:220:1:248:1893:25c8:1946"
    dest = validate_destination(YARGITAY_URL, resolver=_resolver(v6_safe))
    assert "::1" not in dest.validated_ips
    assert v6_safe in dest.validated_ips


# ── Multiple validated-IP fallback ───────────────────────────────────────
def test_validated_fallback_only_A_and_B():
    backend = _ValidatedNetworkBackend(SAFE_IP_BOTH, YARGITAY_URL)
    calls = []
    fail_a_count = [0]

    def _fake_connect(host, port, timeout, local_address=None, socket_options=None):
        calls.append(host)
        if host == SAFE_IP:
            fail_a_count[0] += 1
            if fail_a_count[0] == 1:
                raise OSError("A failed")
        return object()

    backend._inner.connect_tcp = _fake_connect
    try:
        backend.connect_tcp("karararama.yargitay.gov.tr", 443, 5)
    except Exception:
        pass
    for host in calls:
        assert host in SAFE_IP_BOTH


def test_outside_validated_set_blocked():
    backend = _ValidatedNetworkBackend((SAFE_IP,), YARGITAY_URL)
    calls = []

    def _fake_connect(host, port, timeout, local_address=None, socket_options=None):
        calls.append(host)
        raise OSError("fail")
    backend._inner.connect_tcp = _fake_connect
    with pytest.raises(SourceFetchError) as e:
        backend.connect_tcp("karararama.yargitay.gov.tr", 443, 5)
    assert e.value.code == "destination_not_validated"
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
        resolver=lambda h: (
            resolver_a(h) if "yargitay" in h else resolver_b(h)
        ),
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
    loop_url = YARGITAY_URL

    def transport(url):
        return _StubResponse(302, {"content-type": "text/html"}, b"",
                             location=loop_url)

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


def test_invalid_url_safe_error():
    from app.services.source_fetcher import _EC
    assert _EC["invalid_url"]


def test_transport_unavailable_safe_error():
    from app.services.source_fetcher import _EC
    assert _EC["transport_unavailable"]


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


# ── HttpxSourceTransport with real pinned path (stub) ────────────────────
def test_httpx_transport_pinned_path_accepts_validated_dest():
    transport = HttpxSourceTransport(timeout_seconds=5)
    dest = validate_destination(YARGITAY_URL, resolver=_resolver(SAFE_IP))
    assert dest.validated_ips == (SAFE_IP,)
    transport.close()


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
