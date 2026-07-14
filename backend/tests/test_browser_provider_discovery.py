"""P2.6D offline proofs for secure browser candidate discovery."""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.config import get_settings
from app.services.browser_provider_discovery import (
    BrowserDiscoveryResult,
    BrowserDiscoveryStrategy,
    PlaywrightBrowserDiscoveryBackend,
    browser_process_environment,
    browser_request_allowed,
    browser_strategy_available,
    discover_browser_candidates,
    extract_listing_candidate_ids,
    get_browser_strategies,
    strategy_provider_codes,
    validate_candidate_identifier,
    validate_browser_response_status,
    validate_strategy_contract,
)
from app.services.provider_ingestion_service import _collect_candidates
from app.services.source_providers import registry
from app.services.source_providers.base import (
    ERR_ACCESS_DENIED,
    ERR_CHALLENGE,
    ERR_FETCH_FAILED,
    ERR_SSRF_BLOCKED,
    ERR_STRUCTURE_CHANGED,
    ProviderError,
)


class FakeBrowserBackend:
    def __init__(self, results=None, errors=None):
        self.results = results or {}
        self.errors = list(errors or [])
        self.calls = []
        self.closed = False

    async def discover(self, strategy, *, query, cursor, limit):
        self.calls.append((strategy.surface_code, query, cursor, limit))
        if self.errors:
            raise self.errors.pop(0)
        ids = self.results.get(strategy.surface_code, ())
        return BrowserDiscoveryResult(
            surface_code=strategy.surface_code,
            candidate_ids=tuple(ids[:limit]),
        )

    async def close(self):
        self.closed = True


def _provider(code):
    return registry.get_definition(code)


async def _collect(provider, backend, *, query=None, run_type="discover_only", external_id=None):
    async def no_sleep(_seconds):
        return None

    return await _collect_candidates(
        provider,
        run_type=run_type,
        query=query,
        from_date=None,
        to_date=None,
        max_items=10,
        cursor=None,
        external_id=external_id,
        transport=None,
        browser_backend=backend,
        resolver=lambda _host: ["93.184.216.34"],
        sleeper=no_sleep,
    )


def test_strategy_registry_is_closed_and_aym_has_two_fixed_banks():
    assert strategy_provider_codes() == ("yargitay", "danistay", "aym", "uyusmazlik")
    assert get_browser_strategies("unknown") == ()
    assert [item.bank_kind for item in get_browser_strategies("aym")] == ["norm", "individual"]


def test_only_inventory_proven_aym_strategy_is_operationally_available():
    assert browser_strategy_available("aym") is True
    assert all(not browser_strategy_available(code) for code in ("yargitay", "danistay", "uyusmazlik"))


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_code,surface,candidate_id", [
    ("yargitay", "yargitay_search", "Y-17"),
    ("danistay", "danistay_search", "D-29"),
    ("uyusmazlik", "uyusmazlik_search", "U-31"),
])
async def test_single_surface_candidate_identifier_routes_through_provider_contract(
    provider_code, surface, candidate_id,
):
    backend = FakeBrowserBackend({surface: (candidate_id,)})
    candidates = await discover_browser_candidates(
        _provider(provider_code), backend, query="zamanaşımı", cursor=None, limit=1,
    )
    assert [item.external_id for item in candidates] == [candidate_id]
    assert candidates[0].provider_code == provider_code
    assert candidate_id in candidates[0].detail_url
    assert backend.calls == [(surface, "zamanaşımı", None, 1)]


@pytest.mark.asyncio
async def test_aym_norm_and_individual_remain_separate_fixed_surfaces():
    backend = FakeBrowserBackend({
        "aym_norm": ("f8bb125a-4332-4e6d-ae84-62fcf365b553",),
        "aym_individual": ("8e37ec7b-47d1-44d3-a308-1f0782ace063",),
    })
    candidates = await discover_browser_candidates(
        _provider("aym"), backend, query="iş sözleşmesi", cursor=None, limit=2,
    )
    assert [item.discovered_metadata["bank_kind"] for item in candidates] == [
        "norm", "individual",
    ]
    assert all(item.source_type == "constitutional_court_decision" for item in candidates)


@pytest.mark.parametrize("value", [
    "", " spaced", "trailing ", "https://official.example/x", "host.example",
    "../escape", "a/b", "line\nbreak", "x" * 129, None, 42,
])
def test_invalid_candidate_identifiers_fail_closed(value):
    with pytest.raises(ProviderError) as exc:
        validate_candidate_identifier(value)
    assert exc.value.code == ERR_STRUCTURE_CHANGED


def test_candidate_identifier_accepts_observed_uuid_shape():
    value = "f8bb125a-4332-4e6d-ae84-62fcf365b553"
    assert validate_candidate_identifier(value) == value


@pytest.mark.asyncio
async def test_backend_cannot_supply_arbitrary_href_or_browser_bytes():
    result = BrowserDiscoveryResult("yargitay_search", ("Y-1",))
    assert not hasattr(result, "href")
    assert not hasattr(result, "content")
    assert not hasattr(result, "body")
    candidates = await discover_browser_candidates(
        _provider("yargitay"), FakeBrowserBackend({"yargitay_search": ("Y-1",)}),
        query=None, cursor=None, limit=1,
    )
    assert candidates[0].detail_url == _provider("yargitay").build_exact_candidate("Y-1").detail_url


@pytest.mark.asyncio
async def test_nonzero_browser_detail_download_count_is_rejected():
    class DetailBackend(FakeBrowserBackend):
        async def discover(self, strategy, **_kwargs):
            return BrowserDiscoveryResult(
                strategy.surface_code, ("Y-1",), detail_download_count=1,
            )

    with pytest.raises(ProviderError) as exc:
        await discover_browser_candidates(
            _provider("yargitay"), DetailBackend(), query=None, cursor=None, limit=1,
        )
    assert exc.value.code == ERR_STRUCTURE_CHANGED


@pytest.mark.asyncio
async def test_surface_mismatch_is_structure_change():
    class WrongSurface(FakeBrowserBackend):
        async def discover(self, strategy, **_kwargs):
            return BrowserDiscoveryResult("other", ("Y-1",))

    with pytest.raises(ProviderError) as exc:
        await discover_browser_candidates(
            _provider("yargitay"), WrongSurface(), query=None, cursor=None, limit=1,
        )
    assert exc.value.code == ERR_STRUCTURE_CHANGED


@pytest.mark.asyncio
async def test_requires_browser_without_backend_fails_closed():
    with pytest.raises(ProviderError) as exc:
        await _collect(_provider("aym"), None)
    assert exc.value.code == "browser_discovery_unavailable"


@pytest.mark.asyncio
async def test_exact_source_bypasses_browser_discovery():
    candidates = await _collect(
        _provider("aym"), None, run_type="exact_source", external_id="A-1",
    )
    assert [item.external_id for item in candidates] == ["A-1"]


@pytest.mark.asyncio
async def test_browser_discovery_uses_shared_retry_executor_once():
    backend = FakeBrowserBackend(
        {"aym_norm": ("A-1",)},
        errors=[ProviderError(ERR_FETCH_FAILED, "safe", retryable=True)],
    )
    candidates = await _collect(_provider("aym"), backend)
    assert [item.external_id for item in candidates] == ["A-1"]
    assert [call[0] for call in backend.calls].count("aym_norm") == 2
    assert [call[0] for call in backend.calls].count("aym_individual") == 1


@pytest.mark.asyncio
async def test_challenge_is_not_retried():
    backend = FakeBrowserBackend(errors=[ProviderError(ERR_CHALLENGE, "safe")])
    with pytest.raises(ProviderError) as exc:
        await _collect(_provider("aym"), backend)
    assert exc.value.code == ERR_CHALLENGE
    assert len(backend.calls) == 1


@pytest.mark.asyncio
async def test_query_is_sent_only_to_selected_official_strategy_and_not_returned():
    sentinel = "PRIVATE_CASE_QUERY_SENTINEL_98231"
    backend = FakeBrowserBackend({"aym_norm": ("A-1",)})
    await discover_browser_candidates(
        _provider("aym"), backend, query=sentinel, cursor=None, limit=1,
    )
    assert backend.calls == [("aym_norm", sentinel, None, 1)]
    error = ProviderError(ERR_STRUCTURE_CHANGED, "browser_surface_changed")
    assert sentinel not in error.code and sentinel not in str(error)


def test_request_interception_allows_only_fixed_surface_host():
    strategy = get_browser_strategies("aym")[0]
    assert browser_request_allowed(strategy, strategy.origin)
    assert browser_request_allowed(
        strategy,
        "https://normkararlarbilgibankasi.anayasa.gov.tr/api/core/public/search",
        resource_type="fetch",
        method="POST",
    )
    assert not browser_request_allowed(strategy, "https://evil.example/api/core/public/search")
    assert not browser_request_allowed(
        strategy,
        "http://normkararlarbilgibankasi.anayasa.gov.tr/api/core/public/search",
        resource_type="fetch",
        method="POST",
    )
    assert not browser_request_allowed(
        strategy, "https://normkararlarbilgibankasi.anayasa.gov.tr:8443/arbitrary",
    )
    assert not browser_request_allowed(
        strategy, "https://normkararlarbilgibankasi.anayasa.gov.tr/kbb/karar/id",
    )
    assert not browser_request_allowed(strategy, "file:///etc/passwd")
    assert not browser_request_allowed(strategy, "ftp://normkararlarbilgibankasi.anayasa.gov.tr/x")
    assert not browser_request_allowed(strategy, "ws://normkararlarbilgibankasi.anayasa.gov.tr/x", resource_type="websocket")


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/x", "http://10.0.0.1/x", "http://169.254.169.254/x",
    "http://[::1]/x", "http://localhost/x", "http://metadata.google.internal/x",
])
def test_private_local_and_metadata_hosts_are_blocked(url):
    strategy = get_browser_strategies("aym")[0]
    assert browser_request_allowed(strategy, url) is False


def test_detail_paths_are_blocked_before_browser_download():
    strategy = get_browser_strategies("aym")[1]
    assert not browser_request_allowed(
        strategy, "https://kararlarbilgibankasi.anayasa.gov.tr/BB?id=A-1",
    )
    assert not browser_request_allowed(
        strategy, "https://kararlarbilgibankasi.anayasa.gov.tr/download/A-1",
    )


def test_proxy_environment_is_removed_without_mutating_other_values():
    source = {
        "HTTP_PROXY": "http://proxy", "https_proxy": "http://proxy2",
        "ALL_PROXY": "socks://proxy", "SAFE_SETTING": "kept",
    }
    assert browser_process_environment(source) == {"SAFE_SETTING": "kept"}


def test_provider_specific_origin_binding_rejects_cross_provider_strategy():
    strategy = get_browser_strategies("aym")[0]
    with pytest.raises(ProviderError) as exc:
        validate_strategy_contract(strategy, _provider("yargitay"))
    assert exc.value.code == ERR_SSRF_BLOCKED


@pytest.mark.asyncio
async def test_production_backend_rejects_strategy_not_in_closed_registry():
    forged = BrowserDiscoveryStrategy(
        provider_code="aym",
        surface_code="forged",
        origin="https://anayasa.gov.tr/arbitrary-caller-path",
        allowed_hosts=("anayasa.gov.tr",),
        live_supported=True,
    )
    backend = PlaywrightBrowserDiscoveryBackend(
        resolver=lambda _host: ["93.184.216.34"],
    )
    with pytest.raises(ProviderError) as exc:
        await backend.discover(forged, query=None, cursor=None, limit=1)
    assert exc.value.code == ERR_SSRF_BLOCKED


@pytest.mark.asyncio
async def test_norm_strategy_is_inventory_record_only_in_production_backend():
    backend = PlaywrightBrowserDiscoveryBackend(
        resolver=lambda _host: ["93.184.216.34"],
    )
    assert backend.strategy_available(get_browser_strategies("aym")[0]) is False
    assert backend.strategy_available(get_browser_strategies("aym")[1]) is True


@pytest.mark.parametrize("status,code,retryable", [
    (401, ERR_ACCESS_DENIED, False),
    (403, ERR_ACCESS_DENIED, False),
    (429, "rate_limited", False),
    (500, ERR_FETCH_FAILED, True),
    (404, ERR_FETCH_FAILED, False),
])
def test_listing_http_status_mapping(status, code, retryable):
    with pytest.raises(ProviderError) as exc:
        validate_browser_response_status(status)
    assert exc.value.code == code
    assert exc.value.retryable is retryable


def test_listing_pagination_fails_closed_instead_of_silent_truncation():
    strategy = get_browser_strategies("aym")[1]
    with pytest.raises(ProviderError) as exc:
        extract_listing_candidate_ids(
            {"data": [{"id": "A-1"}], "page": 1, "page_size": 10, "total": 11},
            strategy,
            limit=10,
        )
    assert exc.value.code == ERR_STRUCTURE_CHANGED


def test_browser_provider_bounded_window_capability_is_not_overclaimed():
    for code in ("yargitay", "danistay", "aym", "uyusmazlik"):
        assert _provider(code).capabilities.bounded_window is False


@pytest.mark.asyncio
@pytest.mark.parametrize("text,expected", [
    ("CAPTCHA", ERR_CHALLENGE),
    ("Access denied", ERR_ACCESS_DENIED),
])
async def test_page_marker_mapping_is_safe(text, expected):
    class Locator:
        async def inner_text(self, timeout):
            assert timeout == 5_000
            return text

    class Page:
        def locator(self, selector):
            assert selector == "body"
            return Locator()

    with pytest.raises(ProviderError) as exc:
        await PlaywrightBrowserDiscoveryBackend._raise_for_page_markers(Page())
    assert exc.value.code == expected


@pytest.mark.asyncio
async def test_backend_lifecycle_close_is_idempotent_and_fail_closed():
    backend = PlaywrightBrowserDiscoveryBackend(resolver=lambda _host: ["93.184.216.34"])
    await backend.close()
    await backend.close()
    with pytest.raises(ProviderError) as exc:
        await backend.discover(
            get_browser_strategies("aym")[0], query=None, cursor=None, limit=1,
        )
    assert exc.value.code == "browser_discovery_unavailable"


@pytest.mark.asyncio
async def test_playwright_timeout_maps_retryable_and_stops_runtime():
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    stopped = []

    class Chromium:
        async def launch(self, **_kwargs):
            raise PlaywrightTimeoutError("safe timeout")

    class Playwright:
        chromium = Chromium()

        async def stop(self):
            stopped.append(True)

    class Starter:
        async def start(self):
            return Playwright()

    backend = PlaywrightBrowserDiscoveryBackend(
        resolver=lambda _host: ["93.184.216.34"],
    )
    with patch("playwright.async_api.async_playwright", return_value=Starter()):
        with pytest.raises(ProviderError) as exc:
            await backend.discover(
                get_browser_strategies("aym")[1], query="zamanaşımı",
                cursor=None, limit=1,
            )
    assert exc.value.code == ERR_FETCH_FAILED
    assert exc.value.retryable is True
    assert stopped == [True]


def test_browser_config_defaults_disabled(monkeypatch):
    monkeypatch.delenv("OFFICIAL_PROVIDER_BROWSER_DISCOVERY_ENABLED", raising=False)
    get_settings.cache_clear()
    try:
        assert get_settings().official_provider_browser_discovery_enabled is False
    finally:
        get_settings.cache_clear()


def test_playwright_installation_alone_does_not_change_config(monkeypatch):
    monkeypatch.delenv("OFFICIAL_PROVIDER_BROWSER_DISCOVERY_ENABLED", raising=False)
    get_settings.cache_clear()
    try:
        assert get_settings().official_provider_browser_discovery_enabled is False
        assert browser_strategy_available("aym") is True
    finally:
        get_settings.cache_clear()


def test_status_requires_strategy_flag_and_live_transport():
    from app.routes import provider_ingestion_routes as routes

    definition = _provider("aym")
    terminal = SimpleNamespace(status="completed", last_safe_error_code="")
    success = SimpleNamespace(status="completed")
    settings = SimpleNamespace(
        official_provider_browser_discovery_enabled=False,
        official_provider_live_smoke=True,
    )
    with patch.object(registry, "is_enabled", return_value=True), \
         patch.object(routes, "get_settings", return_value=settings):
        assert routes._provider_status("aym", definition, terminal, success) == \
            "browser_discovery_unavailable"
        settings.official_provider_browser_discovery_enabled = True
        settings.official_provider_live_smoke = False
        assert routes._provider_status("aym", definition, terminal, success) == \
            "transport_unavailable"
        settings.official_provider_live_smoke = True
        assert routes._provider_status("aym", definition, terminal, success) == "available"


def test_status_keeps_unvalidated_provider_unavailable_even_when_flags_enabled():
    from app.routes import provider_ingestion_routes as routes

    settings = SimpleNamespace(
        official_provider_browser_discovery_enabled=True,
        official_provider_live_smoke=True,
    )
    with patch.object(registry, "is_enabled", return_value=True), \
         patch.object(routes, "get_settings", return_value=settings):
        assert routes._provider_status(
            "yargitay", _provider("yargitay"), None, None,
        ) == "browser_discovery_unavailable"
