"""P2.8S — Live-contract alignment tests for the Yargıtay official provider.

Offline fixture proofs for:
- POST+JSON discovery through the SSRF seam (request descriptor, JSON body,
  record parsing, external ids, listing metadata, recordsTotal pagination)
- fail-closed handling (malformed JSON / shape change / active CAPTCHA)
- AdaletResponseDto XML and JSON detail envelope unwrapping
- suffix/prefix docket parsing, closed-chamber normalization
- listing decision-date fallback and honest-None dates
- POST security boundary on the source seam (SSRF, allowlists, pinning,
  size cap, timeout mapping, content-type allowlist, redirect revalidation)

No live network access. All transports are deterministic fixtures.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from app.services.source_fetcher import (
    ALLOWED_FETCH_METHODS,
    HttpxSourceTransport,
    MAX_POST_BODY_BYTES,
    SourceFetchError,
    SourceFetchRequest,
    fetch_source,
    fetch_source_request,
    validate_destination,
)
from app.services.source_providers.base import (
    ERR_ACCESS_DENIED,
    ERR_CHALLENGE,
    ERR_EMPTY_LEGAL_BODY,
    ERR_MISSING_IDENTIFIER,
    ERR_SSRF_BLOCKED,
    ERR_STRUCTURE_CHANGED,
    ProviderDiscoveryCandidate,
    ProviderError,
)
from app.services.source_providers.shared import (
    extract_docket,
    normalize_chamber,
    parse_iso_date,
)
from app.services.source_providers.yargitay import (
    YargitayProvider,
    compute_inner_content_hash,
    unwrap_decision_html,
)
from app.services.source_fetcher import FetchResult

SEARCH_URL = "https://karararama.yargitay.gov.tr/aramalist"
DETAIL_URL = "https://karararama.yargitay.gov.tr/getDokuman?id=638970600"
SAFE_IP = "93.184.216.34"


def _resolver(ip: str = SAFE_IP):
    return lambda _host: [ip]


class StubResp:
    def __init__(self, status_code=200, content=b"", content_type="application/json",
                 location=None, headers=None):
        self.status_code = status_code
        self.headers = {"content-type": content_type}
        if headers:
            self.headers.update(headers)
        self.content = content
        self.location = location


class RecordingTransport:
    """Request-descriptor-aware stub transport recording every seam call."""

    def __init__(self, responder):
        self.responder = responder
        self.requests: list[SourceFetchRequest] = []

    def __call__(self, url: str, request: SourceFetchRequest | None = None):
        assert request is not None, "seam must always pass the request descriptor"
        self.requests.append(request)
        return self.responder(url, request)


def _search_payload(records, total=None):
    return json.dumps({
        "data": {
            "data": records,
            "recordsTotal": len(records) if total is None else total,
            "recordsFiltered": len(records) if total is None else total,
        },
        "metadata": {"FMTY": "SUCCESS"},
    }, ensure_ascii=False).encode("utf-8")


_RECORD = {
    "id": "638970600",
    "daire": "6. Hukuk Dairesi",
    "esasNo": "2009/11739",
    "kararNo": "2010/4923",
    "kararTarihi": "26.04.2010",
    "siraNo": 1,
    "index": 1,
    "arananKelime": "kira tahliye",
}

_DECISION_HTML = (
    '<html><head></head><body>'
    "<b>(Kapatılan) 6. Hukuk Dairesi&nbsp;&nbsp;2009/11739 E.&nbsp;,&nbsp;2010/4923 K.</b>"
    '<p>"İçtihat Metni"</p>'
    "<p>MAHKEMESİ: Asliye Hukuk Mahkemesi</p>"
    "<p>Mahalli mahkemesinden verilmiş bulunan tahliye davasına dair karar "
    "incelenmiş ve gereği görüşülüp düşünülmüştür. Sonuç: kararın ONANMASINA, "
    "26.4.2010 tarihinde oybirliğiyle karar verildi.</p>"
    "</body></html>"
)


def _xml_envelope(inner_html: str = _DECISION_HTML, tid: str = "tid-1", sid: str = "sid-1") -> bytes:
    escaped = inner_html.replace("&", "&amp;").replace("<", "&lt;")
    return (
        f"<AdaletResponseDto><data>{escaped}</data>"
        f"<metadata><FMTY>SUCCESS</FMTY><FMC>ADALET_SUCCESS</FMC>"
        f"<TID>{tid}</TID><SID>{sid}</SID></metadata></AdaletResponseDto>"
    ).encode("utf-8")


def _json_envelope(inner_html: str = _DECISION_HTML) -> bytes:
    return json.dumps({"data": inner_html, "metadata": {"FMTY": "SUCCESS"}},
                      ensure_ascii=False).encode("utf-8")


async def _discover(provider, transport, **kw):
    return await provider.discover(
        query=kw.pop("query", "kira tahliye"),
        cursor=kw.pop("cursor", None),
        limit=kw.pop("limit", 10),
        transport=transport,
        resolver=_resolver(),
        **kw,
    )


# ═══════════════════ POST discovery contract ═══════════════════
@pytest.mark.asyncio
async def test_discovery_emits_post_request_descriptor():
    transport = RecordingTransport(
        lambda url, req: StubResp(content=_search_payload([_RECORD])))
    await _discover(YargitayProvider(), transport)
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.method == "POST"
    assert request.url.startswith(SEARCH_URL)
    assert "application/json" in (request.content_type or "")


@pytest.mark.asyncio
async def test_discovery_json_body_has_exact_fields():
    transport = RecordingTransport(
        lambda url, req: StubResp(content=_search_payload([_RECORD])))
    await _discover(YargitayProvider(), transport, query="kira tahliye", limit=10, cursor="2")
    body = json.loads(transport.requests[0].body.decode("utf-8"))
    assert body == {"data": {"arananKelime": "kira tahliye", "pageSize": 10, "pageNumber": 2}}


@pytest.mark.asyncio
async def test_discovery_parses_data_data_records_and_external_id():
    transport = RecordingTransport(
        lambda url, req: StubResp(content=_search_payload([_RECORD])))
    page = await _discover(YargitayProvider(), transport)
    assert len(page.candidates) == 1
    candidate = page.candidates[0]
    assert candidate.external_id == "638970600"
    assert candidate.detail_url == "https://karararama.yargitay.gov.tr/getDokuman?id=638970600"


@pytest.mark.asyncio
async def test_discovered_metadata_preserves_listing_fields_only():
    transport = RecordingTransport(
        lambda url, req: StubResp(content=_search_payload([_RECORD])))
    page = await _discover(YargitayProvider(), transport)
    metadata = page.candidates[0].discovered_metadata
    assert metadata == {
        "daire": "6. Hukuk Dairesi",
        "esasNo": "2009/11739",
        "kararNo": "2010/4923",
        "kararTarihi": "26.04.2010",
    }
    # The full search response / query echo is never preserved.
    assert "arananKelime" not in metadata
    assert "siraNo" not in metadata


@pytest.mark.asyncio
async def test_pagination_uses_records_total():
    provider = YargitayProvider()
    # Full page but recordsTotal says exhausted → no next page.
    transport = RecordingTransport(
        lambda url, req: StubResp(content=_search_payload([_RECORD], total=1)))
    page = await _discover(provider, transport, limit=1)
    assert page.next_cursor is None
    assert page.exhausted is True
    # recordsTotal larger than seen → next page advances.
    transport = RecordingTransport(
        lambda url, req: StubResp(content=_search_payload([_RECORD], total=50)))
    page = await _discover(provider, transport, limit=1)
    assert page.next_cursor == "2"
    assert page.exhausted is False


@pytest.mark.asyncio
async def test_malformed_json_fails_closed():
    transport = RecordingTransport(
        lambda url, req: StubResp(content=b"<html>not json</html>"))
    with pytest.raises(ProviderError) as exc:
        await _discover(YargitayProvider(), transport)
    assert exc.value.code == ERR_STRUCTURE_CHANGED


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    b"[]",
    b'{"data": null, "metadata": {}}',
    b'{"data": {"data": "not-a-list"}}',
    b'{"data": {"data": ["not-a-dict"]}}',
])
async def test_malformed_response_shape_fails_closed(payload):
    transport = RecordingTransport(lambda url, req: StubResp(content=payload))
    with pytest.raises(ProviderError) as exc:
        await _discover(YargitayProvider(), transport)
    assert exc.value.code == ERR_STRUCTURE_CHANGED


@pytest.mark.asyncio
async def test_active_captcha_marker_fails_closed():
    challenge = json.dumps({
        "status": "EXCEPTION",
        "detailMessage": "DisplayCaptcha",
        "data": None,
    }).encode("utf-8")
    transport = RecordingTransport(lambda url, req: StubResp(content=challenge))
    with pytest.raises(ProviderError) as exc:
        await _discover(YargitayProvider(), transport)
    assert exc.value.code == ERR_CHALLENGE


@pytest.mark.asyncio
async def test_access_denied_marker_fails_closed():
    denied = json.dumps({
        "status": "EXCEPTION",
        "detailMessage": "Access Denied",
        "data": None,
    }).encode("utf-8")
    transport = RecordingTransport(lambda url, req: StubResp(content=denied))
    with pytest.raises(ProviderError) as exc:
        await _discover(YargitayProvider(), transport)
    assert exc.value.code == ERR_ACCESS_DENIED


# ═══════════════════ detail envelope unwrapping ═══════════════════
def test_xml_adalet_envelope_unwraps_inner_data():
    inner = unwrap_decision_html(_xml_envelope(), "application/xhtml+xml")
    assert inner.startswith("<html>")
    assert "İçtihat Metni" in inner
    assert "AdaletResponseDto" not in inner


def test_json_data_envelope_unwraps_inner_data():
    inner = unwrap_decision_html(_json_envelope(), "application/json")
    assert inner.startswith("<html>")
    assert "İçtihat Metni" in inner


@pytest.mark.parametrize("content", [
    b'{"metadata": {}}',                              # missing data
    b'{"data": 42}',                                  # non-string data
    b'{"data": "   "}',                               # empty decision html
    b"<AdaletResponseDto><metadata/></AdaletResponseDto>",  # envelope missing data node
    b"",                                              # empty body
])
def test_envelope_unwrap_rejects_invalid_shapes(content):
    ctype = "application/json" if content.startswith(b"{") else "application/xhtml+xml"
    with pytest.raises(ProviderError) as exc:
        unwrap_decision_html(content, ctype)
    assert exc.value.code == ERR_STRUCTURE_CHANGED


@pytest.mark.asyncio
async def test_outer_envelope_metadata_absent_from_raw_legal_text():
    provider = YargitayProvider()
    candidate = provider.build_exact_candidate("638970600")
    fetch_result = FetchResult(
        final_url=DETAIL_URL, status_code=200,
        content=_xml_envelope(tid="TIDSENTINEL9001", sid="SIDSENTINEL9002"),
        content_type="application/xhtml+xml",
    )
    parsed = await provider.parse(candidate, fetch_result)
    assert "TIDSENTINEL9001" not in parsed.raw_text
    assert "SIDSENTINEL9002" not in parsed.raw_text
    assert "ADALET_SUCCESS" not in parsed.raw_text
    assert "AdaletResponseDto" not in parsed.raw_text


@pytest.mark.asyncio
async def test_provider_fetch_returns_unwrapped_inner_html_with_stable_hash():
    """provider.fetch unwraps the envelope so canonical bytes exclude TID/SID."""
    provider = YargitayProvider()
    candidate = provider.build_exact_candidate("638970600")

    def respond_factory(tid, sid):
        def _respond(url, request=None):
            return StubResp(
                content=_xml_envelope(tid=tid, sid=sid),
                content_type="application/xhtml+xml",
            )
        return _respond

    first = await provider.fetch(
        candidate, transport=respond_factory("tid-A", "sid-A"),
        resolver=_resolver(),
    )
    second = await provider.fetch(
        candidate, transport=respond_factory("tid-B", "sid-B"),
        resolver=_resolver(),
    )
    assert b"tid-A" not in first.content and b"sid-A" not in first.content
    # Volatile envelope metadata never varies the canonical fetch content.
    assert hashlib.sha256(first.content).hexdigest() == hashlib.sha256(second.content).hexdigest()
    assert first.content_type == "text/html"


# ═══════════════════ docket / chamber / date parsing ═══════════════════
def test_suffix_e_docket_parses():
    assert extract_docket("Önce metin 2009/11739 E. sonra devam", "E") == "2009/11739"


def test_suffix_k_docket_parses():
    assert extract_docket("2009/11739 E. , 2010/4923 K. karar başlığı", "K") == "2010/4923"


def test_prefix_docket_forms_remain_supported():
    assert extract_docket("E. 2020/123 sayılı", "E") == "2020/123"
    assert extract_docket("K. 2021/456 sayılı", "K") == "2021/456"
    assert extract_docket("Esas No: 2020/123", "E") == "2020/123"
    assert extract_docket("Karar No: 2021/456", "K") == "2021/456"


def test_decision_date_never_matches_as_docket():
    assert extract_docket("Karar Tarihi: 26.04.2010", "E") is None
    assert extract_docket("Karar Tarihi: 26.04.2010", "K") is None


def test_wrong_kind_suffix_does_not_match():
    assert extract_docket("sadece 2010/4923 K. var", "E") is None
    assert extract_docket("sadece 2009/11739 E. var", "K") is None


def test_bare_number_without_marker_does_not_match():
    assert extract_docket("dosya 2020/123 hakkında", "E") is None
    assert extract_docket("dosya 2020/123 hakkında", "K") is None


def test_closed_chamber_prefix_normalizes_correctly():
    assert normalize_chamber("(Kapatılan) 6. Hukuk Dairesi") == "6. Hukuk Dairesi"
    assert normalize_chamber("6. Hukuk Dairesi") == "6. Hukuk Dairesi"
    # Board identity is preserved and never collapsed.
    assert normalize_chamber("Hukuk Genel Kurulu") == "Hukuk Genel Kurulu"
    assert normalize_chamber("Ceza Genel Kurulu") == "Ceza Genel Kurulu"


@pytest.mark.asyncio
async def test_parse_extracts_metadata_from_live_shape_body():
    provider = YargitayProvider()
    candidate = provider.build_exact_candidate("638970600")
    candidate.discovered_metadata = dict(_RECORD)
    parsed = await provider.parse(candidate, FetchResult(
        final_url=DETAIL_URL, status_code=200,
        content=_xml_envelope(), content_type="application/xhtml+xml",
    ))
    assert parsed.court == "Yargıtay"
    assert parsed.chamber == "6. Hukuk Dairesi"
    assert parsed.case_number == "2009/11739"
    assert parsed.decision_number == "2010/4923"
    assert parsed.provider_metadata["external_id"] == "638970600"
    assert parsed.provider_metadata["inner_content_hash"] == compute_inner_content_hash(
        unwrap_decision_html(_xml_envelope(), "application/xhtml+xml"))


@pytest.mark.asyncio
async def test_listing_decision_date_fallback_parses():
    provider = YargitayProvider()
    candidate = provider.build_exact_candidate("638970600")
    candidate.discovered_metadata = {"kararTarihi": "26.04.2010"}
    parsed = await provider.parse(candidate, FetchResult(
        final_url=DETAIL_URL, status_code=200,
        content=_xml_envelope(), content_type="application/xhtml+xml",
    ))
    # Body has no labelled decision date → deterministic listing fallback.
    assert parsed.decision_date == "2010-04-26"
    assert parse_iso_date("26.04.2010") == "2010-04-26"


@pytest.mark.asyncio
async def test_missing_deterministic_date_remains_none():
    provider = YargitayProvider()
    candidate = provider.build_exact_candidate("638970600")
    candidate.discovered_metadata = {"kararTarihi": "bilinmiyor"}
    parsed = await provider.parse(candidate, FetchResult(
        final_url=DETAIL_URL, status_code=200,
        content=_xml_envelope(), content_type="application/xhtml+xml",
    ))
    assert parsed.decision_date is None


@pytest.mark.asyncio
async def test_labelled_body_date_takes_precedence_over_listing():
    body = _DECISION_HTML.replace(
        '"İçtihat Metni"', '"İçtihat Metni" Karar Tarihi: 12.06.2021')
    provider = YargitayProvider()
    candidate = provider.build_exact_candidate("638970600")
    candidate.discovered_metadata = {"kararTarihi": "26.04.2010"}
    parsed = await provider.parse(candidate, FetchResult(
        final_url=DETAIL_URL, status_code=200,
        content=_xml_envelope(inner_html=body), content_type="application/xhtml+xml",
    ))
    assert parsed.decision_date == "2021-06-12"


@pytest.mark.asyncio
async def test_meaningful_body_gate_applies_to_inner_body():
    thin = "<html><body><p>Arama</p></body></html>"
    provider = YargitayProvider()
    candidate = provider.build_exact_candidate("638970600")
    with pytest.raises(ProviderError) as exc:
        await provider.parse(candidate, FetchResult(
            final_url=DETAIL_URL, status_code=200,
            content=_xml_envelope(inner_html=thin), content_type="application/xhtml+xml",
        ))
    assert exc.value.code == ERR_EMPTY_LEGAL_BODY


@pytest.mark.asyncio
async def test_missing_e_k_fails_closed_with_missing_identifier():
    body = (
        "<html><body><p>6. Hukuk Dairesi kararı hakkında uzun ve anlamlı bir "
        "hukuki metin bulunmaktadır ancak esas ve karar numarası yoktur burada "
        "kesinlikle.</p></body></html>"
    )
    provider = YargitayProvider()
    candidate = provider.build_exact_candidate("638970600")
    with pytest.raises(ProviderError) as exc:
        await provider.parse(candidate, FetchResult(
            final_url=DETAIL_URL, status_code=200,
            content=_xml_envelope(inner_html=body), content_type="application/xhtml+xml",
        ))
    assert exc.value.code == ERR_MISSING_IDENTIFIER


def test_build_exact_candidate_rejects_unsafe_external_id():
    provider = YargitayProvider()
    for bad in ("", "  ", "a/b", "x?y=1", "a" * 200, "id&evil=1"):
        with pytest.raises(ProviderError):
            provider.build_exact_candidate(bad)


def test_inner_content_hash_is_deterministic_documented_representation():
    inner = unwrap_decision_html(_xml_envelope(), "application/xhtml+xml")
    assert compute_inner_content_hash(inner) == hashlib.sha256(
        inner.encode("utf-8")).hexdigest()
    # Identical inner decision HTML under different envelope TIDs → same hash.
    other = unwrap_decision_html(
        _xml_envelope(tid="other-tid", sid="other-sid"), "application/xhtml+xml")
    assert compute_inner_content_hash(other) == compute_inner_content_hash(inner)


# ═══════════════════ POST security boundary on the seam ═══════════════════
def _post_request(url=SEARCH_URL):
    return SourceFetchRequest.post_json(url, {"data": {"arananKelime": "x"}})


def test_post_method_vocabulary_is_closed():
    assert ALLOWED_FETCH_METHODS == frozenset({"GET", "POST"})
    for method in ("PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"):
        with pytest.raises(SourceFetchError) as exc:
            SourceFetchRequest(url=SEARCH_URL, method=method, body=b"{}",
                               content_type="application/json")
        assert exc.value.code == "method_not_allowed"


def test_post_body_must_be_bounded_controlled_bytes():
    with pytest.raises(SourceFetchError):
        SourceFetchRequest(url=SEARCH_URL, method="POST", body=None,
                           content_type="application/json")
    with pytest.raises(SourceFetchError):
        SourceFetchRequest(url=SEARCH_URL, method="POST", body="not-bytes",
                           content_type="application/json")
    with pytest.raises(SourceFetchError):
        SourceFetchRequest(url=SEARCH_URL, method="POST",
                           body=b"x" * (MAX_POST_BODY_BYTES + 1),
                           content_type="application/json")


def test_request_descriptor_rejects_header_injection():
    for evil in ("application/json\r\nHost: evil", "a\nb", "x" * 500):
        with pytest.raises(SourceFetchError):
            SourceFetchRequest(url=SEARCH_URL, method="POST", body=b"{}",
                               content_type=evil)
        with pytest.raises(SourceFetchError):
            SourceFetchRequest.get(SEARCH_URL, accept=evil)


def test_get_descriptor_rejects_body():
    with pytest.raises(SourceFetchError):
        SourceFetchRequest(url=SEARCH_URL, method="GET", body=b"{}")


def test_post_destination_validation_enforced():
    with pytest.raises(SourceFetchError) as exc:
        fetch_source_request(
            _post_request("https://evil.example.com/aramalist"),
            resolver=_resolver(), transport=lambda url, request=None: StubResp(),
        )
    assert exc.value.code == "domain_not_allowed"


def test_post_global_allowlist_enforced():
    # A domain outside the global official allowlist is rejected even when the
    # provider scope would nominally include it.
    with pytest.raises(SourceFetchError) as exc:
        fetch_source_request(
            _post_request("https://example.org/aramalist"),
            resolver=_resolver(),
            transport=lambda url, request=None: StubResp(),
            allowed_domains=("example.org",),
        )
    assert exc.value.code == "domain_not_allowed"


def test_post_provider_domain_scope_enforced():
    # Globally official domain, but outside the executing provider's scope.
    with pytest.raises(SourceFetchError) as exc:
        fetch_source_request(
            _post_request("https://mevzuat.gov.tr/aramalist"),
            resolver=_resolver(),
            transport=lambda url, request=None: StubResp(),
            allowed_domains=YargitayProvider.official_domains,
        )
    assert exc.value.code == "domain_not_allowed"


@pytest.mark.parametrize("ip", ["10.0.0.5", "127.0.0.1", "169.254.169.254", "192.168.1.7"])
def test_post_private_reserved_resolved_ip_rejected(ip):
    with pytest.raises(SourceFetchError) as exc:
        fetch_source_request(
            _post_request(),
            resolver=_resolver(ip),
            transport=lambda url, request=None: StubResp(),
        )
    assert exc.value.code == "dns_unsafe_ip"


def test_post_validated_ip_pinning_exercised():
    """POST through the real transport builds a pool pinned to validated IPs."""
    captured = {}

    class CapturingPool:
        def __init__(self):
            self.closed = False

        def stream(self, method, url, headers=None, content=None, extensions=None):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers
            captured["content"] = content
            raise SourceFetchError("connect_error", "stop before network")

        def close(self):
            self.closed = True

    import app.services.source_fetcher as sf
    transport = HttpxSourceTransport(timeout_seconds=5)
    dest = validate_destination(SEARCH_URL, resolver=_resolver())

    original = sf._make_pinned_pool
    pool = CapturingPool()

    def fake_make_pinned_pool(d, timeout_seconds, *, network_backend=None):
        captured["pinned_ips"] = d.validated_ips
        captured["hostname"] = d.hostname
        return pool

    sf._make_pinned_pool = fake_make_pinned_pool
    try:
        with pytest.raises(SourceFetchError):
            transport.fetch_pinned(dest, request=_post_request())
    finally:
        sf._make_pinned_pool = original

    assert captured["pinned_ips"] == (SAFE_IP,)
    assert captured["hostname"] == "karararama.yargitay.gov.tr"
    assert captured["method"] == "POST"
    assert captured["content"] == _post_request().body
    header_names = [k for k, _v in captured["headers"]]
    assert b"host" in header_names and b"content-type" in header_names
    assert pool.closed is True


def test_post_response_size_cap_enforced():
    big = b"x" * 128
    with pytest.raises(SourceFetchError) as exc:
        fetch_source_request(
            _post_request(),
            resolver=_resolver(),
            transport=lambda url, request=None: StubResp(content=big),
            max_bytes=64,
        )
    assert exc.value.code == "response_too_large"


def test_post_timeout_maps_to_safe_error():
    from app.services.source_providers import registry

    provider = registry.get_definition("yargitay")
    err = provider._provider_error_from_fetch_error(
        SourceFetchError("fetch_timeout", "safe"))
    assert err.code == "fetch_failed"
    assert err.retryable is True


def test_post_content_type_allowlist_enforced():
    with pytest.raises(SourceFetchError) as exc:
        fetch_source_request(
            _post_request(),
            resolver=_resolver(),
            transport=lambda url, request=None: StubResp(
                content=b"x", content_type="application/octet-stream"),
        )
    assert exc.value.code == "unsupported_content_type"


def test_post_redirect_revalidation_preserved():
    """A POST redirect to a foreign destination is blocked on re-validation."""
    def respond(url, request=None):
        if "aramalist" in url:
            return StubResp(status_code=307, location="https://evil.example.com/x")
        return StubResp(content=b"should never arrive")

    with pytest.raises(SourceFetchError) as exc:
        fetch_source_request(_post_request(), resolver=_resolver(), transport=respond)
    assert exc.value.code == "domain_not_allowed"


def test_post_301_302_redirects_fail_closed():
    for status in (301, 302):
        def respond(url, request=None, _status=status):
            return StubResp(status_code=_status,
                            location="https://karararama.yargitay.gov.tr/elsewhere")
        with pytest.raises(SourceFetchError) as exc:
            fetch_source_request(_post_request(), resolver=_resolver(), transport=respond)
        assert exc.value.code == "post_redirect_not_allowed"


def test_post_303_follows_as_get():
    seen = []

    def respond(url, request=None):
        seen.append(request.method)
        if "aramalist" in url:
            return StubResp(status_code=303,
                            location="https://karararama.yargitay.gov.tr/result")
        return StubResp(content=b'{"ok": true}')

    result = fetch_source_request(_post_request(), resolver=_resolver(), transport=respond)
    assert seen == ["POST", "GET"]
    assert result.status_code == 200


def test_post_307_preserves_method_and_body_after_revalidation():
    seen = []

    def respond(url, request=None):
        seen.append((request.method, request.body))
        if url.endswith("/aramalist"):
            return StubResp(status_code=307,
                            location="https://karararama.yargitay.gov.tr/sonucliste")
        return StubResp(content=b'{"ok": true}')

    request = _post_request()
    result = fetch_source_request(request, resolver=_resolver(), transport=respond)
    assert seen[0] == ("POST", request.body)
    assert seen[1] == ("POST", request.body)
    assert result.status_code == 200


def test_post_routed_to_legacy_get_only_stub_fails_closed():
    def legacy_stub(url):
        return StubResp(content=b"{}")

    with pytest.raises(SourceFetchError) as exc:
        fetch_source_request(_post_request(), resolver=_resolver(), transport=legacy_stub)
    assert exc.value.code == "transport_unavailable"


def test_get_regressions_remain_green_via_wrapper():
    """The GET-only fetch_source entrypoint is unchanged for legacy stubs."""
    def legacy_stub(url):
        return StubResp(content=b"<html><body>icerik</body></html>",
                        content_type="text/html")

    result = fetch_source(DETAIL_URL, resolver=_resolver(), transport=legacy_stub)
    assert result.status_code == 200
    assert result.final_url == DETAIL_URL


@pytest.mark.asyncio
async def test_provider_discovery_post_flows_through_ssrf_seam_only():
    """The provider never bypasses the seam: a private resolver blocks discovery
    before any transport call."""
    calls = []

    def transport(url, request=None):
        calls.append(url)
        return StubResp(content=_search_payload([_RECORD]))

    provider = YargitayProvider()
    with pytest.raises(ProviderError) as exc:
        await provider.discover(
            query="kira", cursor=None, limit=1,
            transport=transport, resolver=_resolver("10.0.0.5"),
        )
    assert exc.value.code == ERR_SSRF_BLOCKED
    assert calls == []


@pytest.mark.asyncio
async def test_requires_browser_is_false_after_live_proof():
    provider = YargitayProvider()
    assert provider.capabilities.requires_browser is False
    assert provider.capabilities.discovery is True
    assert provider.capabilities.fetch is True
    assert provider.request_policy.max_concurrency == 1
    assert provider.request_policy.min_interval_seconds >= 3.0
