"""Offline regressions for the bounded non-browser provider live-smoke harness."""
from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import json
from types import SimpleNamespace

import pytest

from app.official_source_ingestion_smoke import (
    ERR_LIVE_SMOKE_NOT_AUTHORIZED,
    ERR_NO_ENABLED_ELIGIBLE_PROVIDER,
    HARNESS_VERSION,
    LIVE_SMOKE_ENV,
    MAX_DETAIL_FETCHES,
    MAX_DISCOVERY_CANDIDATES,
    SMOKE_OUTCOMES,
    _build_parser,
    _run,
    _safe_final_host,
    eligible_provider_codes,
    live_smoke_authorized,
    render_evidence_document,
    run_controlled_live_smoke,
)
from app.services.source_fetcher import FetchResult
from app.services.source_providers.base import (
    ERR_ACCESS_DENIED,
    ERR_CHALLENGE,
    ERR_FETCH_FAILED,
    ERR_STRUCTURE_CHANGED,
    ProviderCapabilities,
    ProviderDiscoveryCandidate,
    ProviderDiscoveryPage,
    ProviderError,
    ProviderRequestPolicy,
)

SENTINEL = "PRIVATE_CASE_QUERY_SENTINEL_98231"
RAW_URL = "https://mevzuat.gov.tr/private/path?query=secret"
EXTERNAL_ID = "SECRET-EXTERNAL-ID-123"


async def _no_sleep(_seconds):
    return None


class FakeTransport:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class FakeProvider:
    def __init__(
        self,
        code,
        *,
        requires_browser=False,
        enabled=True,
        candidates=1,
        discover_error=None,
        fetch_error=None,
        retry_discover_once=False,
    ):
        self.provider_code = code
        self.capabilities = ProviderCapabilities(
            discovery=True,
            fetch=True,
            parse=True,
            requires_browser=requires_browser,
        )
        self.request_policy = ProviderRequestPolicy(
            min_interval_seconds=0,
            max_retries=1,
            backoff_base_seconds=0,
            backoff_max_seconds=0,
        )
        self.enabled = enabled
        self.candidates = candidates
        self.discover_error = discover_error
        self.fetch_error = fetch_error
        self.retry_discover_once = retry_discover_once
        self.discover_calls = 0
        self.fetch_calls = 0
        self.observed_limits = []
        self.observed_cursors = []
        self.observed_queries = []

    @staticmethod
    def default_resolver():
        return lambda _host: ["93.184.216.34"]

    async def discover(self, *, query, cursor, limit, from_date, to_date, transport, resolver):
        self.discover_calls += 1
        self.observed_limits.append(limit)
        self.observed_cursors.append(cursor)
        self.observed_queries.append(query)
        if self.retry_discover_once and self.discover_calls == 1:
            raise ProviderError(ERR_FETCH_FAILED, SENTINEL, retryable=True)
        if self.discover_error:
            raise self.discover_error
        candidates = [
            ProviderDiscoveryCandidate(
                provider_code=self.provider_code,
                source_type="legislation",
                detail_url=RAW_URL,
                external_id=f"{EXTERNAL_ID}-{index}",
            )
            for index in range(self.candidates)
        ]
        return ProviderDiscoveryPage(candidates=candidates, next_cursor="do-not-follow")

    async def fetch(self, candidate, *, transport, resolver):
        self.fetch_calls += 1
        if self.fetch_error:
            raise self.fetch_error
        return FetchResult(
            final_url=RAW_URL,
            status_code=200,
            content=b"safe body",
            content_type="text/html; charset=utf-8",
        )


def _install_registry(monkeypatch, providers):
    by_code = {provider.provider_code: provider for provider in providers}
    monkeypatch.setattr(
        "app.official_source_ingestion_smoke.registry.all_provider_codes",
        lambda: tuple(by_code),
    )
    monkeypatch.setattr(
        "app.official_source_ingestion_smoke.registry.get_definition",
        lambda code: by_code[code],
    )
    monkeypatch.setattr(
        "app.official_source_ingestion_smoke.registry.is_enabled",
        lambda code: by_code[code].enabled,
    )


async def _execute(monkeypatch, providers):
    _install_registry(monkeypatch, providers)
    return await run_controlled_live_smoke(
        transport=FakeTransport(),
        authorized=True,
        resolver=lambda _host: ["93.184.216.34"],
        sleeper=_no_sleep,
        now=datetime(2026, 7, 13, 12, 0, tzinfo=UTC),
        git_sha="a" * 40,
    )


def test_dual_opt_in_guard_requires_environment_and_cli_confirmation():
    assert not live_smoke_authorized(confirm_live_smoke=False, environ={})
    assert not live_smoke_authorized(
        confirm_live_smoke=True,
        environ={LIVE_SMOKE_ENV: "false"},
    )
    assert not live_smoke_authorized(
        confirm_live_smoke=False,
        environ={LIVE_SMOKE_ENV: "true"},
    )
    assert live_smoke_authorized(
        confirm_live_smoke=True,
        environ={LIVE_SMOKE_ENV: "true"},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("argv", "environ"), [
    ([], {LIVE_SMOKE_ENV: "true"}),
    (["--confirm-live-smoke"], {}),
])
async def test_missing_guard_makes_zero_transport_factory_calls(argv, environ):
    args = _build_parser().parse_args(argv)
    calls = []
    result = await _run(
        args,
        environ=environ,
        transport_factory=lambda: calls.append("factory"),
        evidence_writer=lambda _report: calls.append("writer"),
    )
    assert result == 2
    assert calls == []


def test_real_registry_eligibility_is_capability_derived():
    # Uyusmazlik currently also requires a browser and is therefore excluded.
    assert eligible_provider_codes() == ("mevzuat", "resmi_gazete")


@pytest.mark.asyncio
async def test_browser_required_provider_is_not_attempted(monkeypatch):
    browser_provider = FakeProvider("yargitay", requires_browser=True)
    report = await _execute(monkeypatch, [browser_provider])
    item = report.providers[0]
    assert item.eligible is False
    assert item.attempted is False
    assert item.discovery_outcome == "not_eligible"
    assert browser_provider.discover_calls == 0
    assert browser_provider.fetch_calls == 0


@pytest.mark.asyncio
async def test_direct_harness_call_requires_explicit_authorization():
    with pytest.raises(ProviderError) as caught:
        await run_controlled_live_smoke(
            transport=FakeTransport(),
            git_sha="a" * 40,
        )
    assert caught.value.code == ERR_LIVE_SMOKE_NOT_AUTHORIZED


@pytest.mark.asyncio
async def test_disabled_non_browser_provider_is_not_attempted(monkeypatch):
    provider = FakeProvider("mevzuat", enabled=False)
    report = await _execute(monkeypatch, [provider])
    assert report.providers[0].discovery_outcome == "not_enabled"
    assert provider.discover_calls == 0


@pytest.mark.asyncio
async def test_bounds_one_candidate_one_detail_and_no_pagination(monkeypatch):
    provider = FakeProvider("mevzuat", candidates=5)
    report = await _execute(monkeypatch, [provider])
    item = report.providers[0]
    assert MAX_DISCOVERY_CANDIDATES == 1
    assert MAX_DETAIL_FETCHES == 1
    assert provider.observed_limits == [1]
    assert provider.observed_cursors == [None]
    assert provider.fetch_calls == 1
    assert item.candidate_count == 1


@pytest.mark.asyncio
async def test_no_candidates_is_safe_successful_observation(monkeypatch):
    provider = FakeProvider("mevzuat", candidates=0)
    report = await _execute(monkeypatch, [provider])
    item = report.providers[0]
    assert item.discovery_outcome == "no_candidates"
    assert item.detail_fetch_attempted is False
    assert provider.fetch_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("error_code", [ERR_CHALLENGE, ERR_ACCESS_DENIED, ERR_STRUCTURE_CHANGED])
async def test_safe_discovery_errors_never_fetch_detail(monkeypatch, error_code):
    provider = FakeProvider(
        "mevzuat",
        discover_error=ProviderError(error_code, SENTINEL),
    )
    report = await _execute(monkeypatch, [provider])
    item = report.providers[0]
    assert item.discovery_outcome == error_code
    assert item.safe_error_code == error_code
    assert provider.fetch_calls == 0
    assert SENTINEL not in json.dumps(asdict(report), ensure_ascii=False)


@pytest.mark.asyncio
async def test_unknown_exception_is_reduced_to_closed_safe_code(monkeypatch):
    provider = FakeProvider("mevzuat", discover_error=RuntimeError(SENTINEL))
    report = await _execute(monkeypatch, [provider])
    item = report.providers[0]
    assert item.discovery_outcome == ERR_FETCH_FAILED
    assert item.safe_error_code == ERR_FETCH_FAILED
    assert SENTINEL not in json.dumps(asdict(report))


@pytest.mark.asyncio
async def test_existing_retry_executor_owns_retry(monkeypatch):
    provider = FakeProvider("mevzuat", retry_discover_once=True)
    report = await _execute(monkeypatch, [provider])
    assert provider.discover_calls == 2
    assert report.providers[0].detail_fetch_outcome == "detail_success"


@pytest.mark.asyncio
async def test_report_excludes_query_external_id_raw_url_and_body(monkeypatch):
    provider = FakeProvider("mevzuat")
    monkeypatch.setattr(
        "app.official_source_ingestion_smoke._smoke_inputs",
        lambda _code, _day: {"query": SENTINEL, "from_date": None, "to_date": None},
    )
    report = await _execute(monkeypatch, [provider])
    rendered = json.dumps(asdict(report), ensure_ascii=False)
    assert SENTINEL not in rendered
    assert EXTERNAL_ID not in rendered
    assert RAW_URL not in rendered
    assert "safe body" not in rendered
    assert report.providers[0].final_host == "mevzuat.gov.tr"


def test_final_host_is_hostname_only_and_fail_closed():
    assert _safe_final_host("https://user:pass@mevzuat.gov.tr/path?q=secret#x") == "mevzuat.gov.tr"
    assert _safe_final_host("not a url") == ""
    assert "/" not in _safe_final_host(RAW_URL)
    assert "?" not in _safe_final_host(RAW_URL)


@pytest.mark.asyncio
async def test_all_report_outcomes_use_closed_vocabulary(monkeypatch):
    providers = [
        FakeProvider("browser", requires_browser=True),
        FakeProvider("disabled", enabled=False),
        FakeProvider("empty", candidates=0),
        FakeProvider("success"),
    ]
    report = await _execute(monkeypatch, providers)
    for item in report.providers:
        assert item.discovery_outcome in SMOKE_OUTCOMES
        assert item.detail_fetch_outcome in SMOKE_OUTCOMES
        assert item.canonical_ingestion_outcome in SMOKE_OUTCOMES


@pytest.mark.asyncio
async def test_confirmed_cli_creates_one_transport_writes_evidence_and_closes(monkeypatch):
    provider = FakeProvider("mevzuat", candidates=0)
    _install_registry(monkeypatch, [provider])
    transport = FakeTransport()
    factory_calls = []
    written = []
    args = _build_parser().parse_args(["--confirm-live-smoke"])
    result = await _run(
        args,
        environ={LIVE_SMOKE_ENV: "true"},
        transport_factory=lambda: factory_calls.append(1) or transport,
        evidence_writer=written.append,
        git_sha_resolver=lambda: "b" * 40,
        resolver=lambda _host: ["93.184.216.34"],
        sleeper=_no_sleep,
    )
    assert result == 0
    assert factory_calls == [1]
    assert len(written) == 1
    assert transport.closed is True


@pytest.mark.asyncio
async def test_confirmed_cli_without_enabled_eligible_provider_writes_no_evidence(
    monkeypatch, capsys,
):
    provider = FakeProvider("mevzuat", enabled=False)
    _install_registry(monkeypatch, [provider])
    transport = FakeTransport()
    written = []
    args = _build_parser().parse_args(["--confirm-live-smoke"])
    result = await _run(
        args,
        environ={LIVE_SMOKE_ENV: "true"},
        transport_factory=lambda: transport,
        evidence_writer=written.append,
        git_sha_resolver=lambda: "b" * 40,
    )
    assert result == 1
    assert written == []
    assert transport.closed is True
    assert ERR_NO_ENABLED_ELIGIBLE_PROVIDER in capsys.readouterr().err


@pytest.mark.asyncio
@pytest.mark.parametrize("error_code", [ERR_CHALLENGE, ERR_ACCESS_DENIED, ERR_FETCH_FAILED])
async def test_cli_closes_transport_for_safe_provider_failures(monkeypatch, error_code):
    provider = FakeProvider(
        "mevzuat",
        discover_error=ProviderError(error_code, SENTINEL),
    )
    _install_registry(monkeypatch, [provider])
    transport = FakeTransport()
    written = []
    args = _build_parser().parse_args(["--confirm-live-smoke"])
    result = await _run(
        args,
        environ={LIVE_SMOKE_ENV: "true"},
        transport_factory=lambda: transport,
        evidence_writer=written.append,
        git_sha_resolver=lambda: "b" * 40,
        resolver=lambda _host: ["93.184.216.34"],
        sleeper=_no_sleep,
    )
    assert result == 0
    assert len(written) == 1
    assert transport.closed is True


@pytest.mark.asyncio
async def test_confirmed_cli_closes_transport_when_execution_fails(monkeypatch, capsys):
    _install_registry(monkeypatch, [FakeProvider("mevzuat")])
    transport = FakeTransport()

    async def fail_smoke(**_kwargs):
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(
        "app.official_source_ingestion_smoke.run_controlled_live_smoke",
        fail_smoke,
    )
    args = _build_parser().parse_args(["--confirm-live-smoke"])
    result = await _run(
        args,
        environ={LIVE_SMOKE_ENV: "true"},
        transport_factory=lambda: transport,
        evidence_writer=lambda _report: None,
        git_sha_resolver=lambda: "b" * 40,
    )
    assert result == 1
    assert transport.closed is True
    captured = capsys.readouterr()
    assert SENTINEL not in captured.err
    assert ERR_FETCH_FAILED in captured.err


@pytest.mark.asyncio
async def test_fixture_execution_does_not_write_real_evidence(monkeypatch):
    provider = FakeProvider("mevzuat", candidates=0)
    _install_registry(monkeypatch, [provider])
    written = []
    args = _build_parser().parse_args(["--confirm-live-smoke"])
    await _run(
        args,
        environ={LIVE_SMOKE_ENV: "true"},
        transport_factory=FakeTransport,
        evidence_writer=written.append,
        git_sha_resolver=lambda: "b" * 40,
        resolver=lambda _host: ["93.184.216.34"],
        sleeper=_no_sleep,
    )
    assert len(written) == 1
    assert HARNESS_VERSION == written[0].harness_version


@pytest.mark.asyncio
async def test_evidence_document_contains_only_safe_structural_fields(monkeypatch):
    report = await _execute(monkeypatch, [FakeProvider("mevzuat")])
    document = render_evidence_document(report)
    assert report.git_sha in document
    assert "mevzuat.gov.tr" in document
    assert SENTINEL not in document
    assert EXTERNAL_ID not in document
    assert RAW_URL not in document
    assert "safe body" not in document
