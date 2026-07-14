"""P2.6C provider-specific official-origin binding regressions.

All network behavior is fixture-backed with an injected public resolver.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from app.core import metrics
from app.db.models import (
    SourceIngestionItem,
    SourceIngestionRun,
    SourceParagraph,
    SourceRecord,
    SourceRelationship,
    SourceUsage,
    SourceVerification,
    SourceVersion,
)
from app.db.session import get_sessionmaker
from app.services.provider_ingestion_service import (
    _execute_provider_network_operation,
    _fetch_parse_ingest,
    run_ingestion,
)
from app.services.browser_provider_discovery import BrowserDiscoveryResult
from app.services.source_fetcher import (
    FetchResult,
    SourceFetchError,
    domains_within_global_allowlist,
    host_matches_allowed_domains,
    validate_destination,
)
from app.services.source_ingestion_service import ingest_official_fetch
from app.services.source_providers import registry
from app.services.source_providers.base import (
    ERR_SSRF_BLOCKED,
    OfficialSourceProvider,
    ProviderCapabilities,
    ProviderDiscoveryCandidate,
    ProviderError,
)
from app.services.source_providers.yargitay import YargitayProvider


class StubResp:
    def __init__(
        self,
        *,
        status_code: int = 200,
        content: bytes = b"",
        content_type: str = "text/html",
        location: str | None = None,
    ):
        self.status_code = status_code
        self.headers = {"content-type": content_type}
        self.content = content
        self.location = location


class RecordingTransport:
    def __init__(self, responder):
        self.responder = responder
        self.calls: list[str] = []

    def __call__(self, url: str):
        self.calls.append(url)
        return self.responder(url)


def public_resolver(_hostname: str) -> list[str]:
    return ["93.184.216.34"]


async def no_sleep(_seconds: float) -> None:
    return None


FOREIGN_URL = "https://mevzuat.gov.tr/cross-provider-document"
YARGITAY_URL = "https://karararama.yargitay.gov.tr/example"
FOREIGN_BYTES = (
    b"<html><body><article>13. Hukuk Dairesi\n"
    b"Esas No: 2099/987651 Karar No: 2099/987652\n"
    b"Karar Tarihi: 12.06.2099\n"
    b"Davaci bedel iadesi talep etmistir. Mahkemece davanin kabulune "
    b"karar verilmistir ve hukum kesinlesmistir.</article></body></html>"
)


@pytest_asyncio.fixture(autouse=True)
async def clean_source_rows():
    maker = get_sessionmaker()

    async def clean(session):
        await session.execute(delete(SourceUsage))
        await session.execute(delete(SourceParagraph))
        await session.execute(delete(SourceVerification))
        await session.execute(delete(SourceRelationship))
        await session.execute(delete(SourceVersion))
        await session.execute(delete(SourceRecord))
        await session.execute(delete(SourceIngestionItem))
        await session.execute(delete(SourceIngestionRun))

    async with maker() as session:
        await clean(session)
        await session.commit()
    yield
    async with maker() as session:
        await clean(session)
        await session.commit()


def test_shared_domain_matcher_exact_subdomain_and_confusion_rejection():
    scope = ("yargitay.gov.tr",)
    assert host_matches_allowed_domains("yargitay.gov.tr", scope)
    assert host_matches_allowed_domains("KARARARAMA.YARGITAY.GOV.TR.", scope)
    assert not host_matches_allowed_domains("evil-yargitay.gov.tr", scope)
    assert not host_matches_allowed_domains("yargitay.gov.tr.evil.example", scope)
    assert not host_matches_allowed_domains("mevzuat.gov.tr", scope)


def test_global_official_domain_is_rejected_by_foreign_provider_scope():
    generic = validate_destination(FOREIGN_URL, resolver=public_resolver)
    assert generic.hostname == "mevzuat.gov.tr"

    with pytest.raises(SourceFetchError) as exc:
        validate_destination(
            FOREIGN_URL,
            resolver=public_resolver,
            allowed_domains=YargitayProvider.official_domains,
        )
    assert exc.value.code == "domain_not_allowed"


def test_all_fetch_capable_registry_providers_have_globally_valid_domain_scopes():
    for code in registry.all_provider_codes():
        provider = registry.get_definition(code)
        if provider.capabilities.fetch:
            assert provider.official_domains
            assert domains_within_global_allowlist(provider.official_domains)


@pytest.mark.parametrize("domains", [(), ("not-official.example",)])
def test_fetch_capable_provider_with_invalid_domain_contract_fails_closed(domains):
    class InvalidProvider(OfficialSourceProvider):
        provider_code = "invalid"
        capabilities = ProviderCapabilities(fetch=True)
        official_domains = domains

    transport = Mock()
    with pytest.raises(ProviderError) as exc:
        InvalidProvider()._secure_fetch(
            "https://mevzuat.gov.tr/x",
            transport=transport,
            resolver=public_resolver,
        )
    assert exc.value.code == ERR_SSRF_BLOCKED
    assert exc.value.message == "provider_domain_scope_invalid"
    transport.assert_not_called()


def test_six_provider_origin_matrix_accepts_own_and_rejects_foreign_domains():
    foreign_urls = {
        "yargitay": "https://mevzuat.gov.tr/x",
        "danistay": "https://yargitay.gov.tr/x",
        "aym": "https://danistay.gov.tr/x",
        "uyusmazlik": "https://anayasa.gov.tr/x",
        "mevzuat": "https://resmigazete.gov.tr/x",
        "resmi_gazete": "https://mevzuat.gov.tr/x",
    }
    for code in registry.all_provider_codes():
        provider = registry.get_definition(code)
        own_url = f"https://{provider.official_domains[0]}/x"
        assert provider.is_official_url(own_url)
        assert not provider.is_official_url(foreign_urls[code])


@pytest.mark.asyncio
async def test_yargitay_foreign_candidate_target_never_fetches_or_creates_trust():
    provider = YargitayProvider()
    provider.parse = AsyncMock(wraps=provider.parse)

    def foreign_candidate(_external_id):
        return ProviderDiscoveryCandidate(
            provider_code="yargitay",
            source_type="supreme_court_decision",
            detail_url="https://mevzuat.gov.tr/cross-provider-document",
            external_id="Y-foreign",
        )

    provider.build_exact_candidate = foreign_candidate

    class IdentifierOnlyBackend:
        async def discover(self, strategy, **_kwargs):
            return BrowserDiscoveryResult(strategy.surface_code, ("Y-foreign",))

    def respond(url: str):
        return StubResp(content=FOREIGN_BYTES)

    transport = RecordingTransport(respond)
    maker = get_sessionmaker()
    with patch(
        "app.services.provider_ingestion_service.registry.get",
        return_value=provider,
    ):
        async with maker() as db:
            summary = await run_ingestion(
                db,
                provider_code="yargitay",
                run_type="fetch_and_ingest",
                query="fixture",
                max_items=1,
                transport=transport,
                browser_backend=IdentifierOnlyBackend(),
                resolver=public_resolver,
                sleeper=no_sleep,
            )

    assert summary.status == "failed"
    assert summary.last_safe_error_code == ERR_SSRF_BLOCKED
    assert transport.calls == []
    assert all("mevzuat.gov.tr" not in url for url in transport.calls)
    assert provider.parse.await_count == 0

    async with maker() as db:
        assert await db.scalar(select(func.count()).select_from(SourceRecord)) == 0
        assert await db.scalar(select(func.count()).select_from(SourceVersion)) == 0
        assert await db.scalar(select(func.count()).select_from(SourceVerification)) == 0


@pytest.mark.asyncio
async def test_cross_provider_redirect_stops_before_second_transport_and_does_not_retry():
    provider = YargitayProvider()

    def respond(url: str):
        if url == YARGITAY_URL:
            return StubResp(status_code=302, location=FOREIGN_URL)
        return StubResp(content=FOREIGN_BYTES)

    transport = RecordingTransport(respond)
    candidate = ProviderDiscoveryCandidate(
        provider_code="yargitay",
        source_type="supreme_court_decision",
        detail_url=YARGITAY_URL,
    )
    with patch.object(
        metrics.official_source_provider_retry_total, "inc"
    ) as retry_metric:
        with pytest.raises(ProviderError) as exc:
            await _execute_provider_network_operation(
                provider,
                operation="fetch",
                sleeper=no_sleep,
                call=lambda: provider.fetch(
                    candidate,
                    transport=transport,
                    resolver=public_resolver,
                ),
            )
    assert exc.value.code == ERR_SSRF_BLOCKED
    assert exc.value.retryable is False
    assert exc.value.message == "domain_not_allowed"
    assert FOREIGN_URL not in exc.value.message
    assert transport.calls == [YARGITAY_URL]
    retry_metric.assert_not_called()


@pytest.mark.asyncio
async def test_same_provider_redirect_remains_allowed_and_scoped():
    provider = YargitayProvider()
    final_url = "https://yargitay.gov.tr/final"

    def respond(url: str):
        if url == YARGITAY_URL:
            return StubResp(status_code=302, location=final_url)
        return StubResp(content=b"same provider response")

    transport = RecordingTransport(respond)
    candidate = ProviderDiscoveryCandidate(
        provider_code="yargitay",
        source_type="supreme_court_decision",
        detail_url=YARGITAY_URL,
    )
    result = await provider.fetch(
        candidate,
        transport=transport,
        resolver=public_resolver,
    )
    assert transport.calls == [YARGITAY_URL, final_url]
    assert result.final_url == final_url
    assert provider.is_official_url(result.final_url)


@pytest.mark.asyncio
async def test_fabricated_foreign_fetch_result_is_blocked_before_parse_extract_ingest():
    provider = YargitayProvider()
    provider.fetch = AsyncMock(return_value=FetchResult(
        final_url=FOREIGN_URL,
        status_code=200,
        content=FOREIGN_BYTES,
        content_type="text/html",
    ))
    provider.parse = AsyncMock()
    candidate = ProviderDiscoveryCandidate(
        provider_code="yargitay",
        source_type="supreme_court_decision",
        detail_url=YARGITAY_URL,
    )
    ingest = AsyncMock()
    with patch(
        "app.services.provider_ingestion_service.extract_content_from_fetch"
    ) as extract, patch(
        "app.services.provider_ingestion_service.ingest_official_fetch",
        new=ingest,
    ):
        with pytest.raises(ProviderError) as exc:
            await _fetch_parse_ingest(
                None,
                provider,
                candidate,
                transport=Mock(),
                resolver=public_resolver,
                sleeper=no_sleep,
            )
    assert exc.value.code == ERR_SSRF_BLOCKED
    assert exc.value.message == "provider_origin_not_allowed"
    assert FOREIGN_URL not in exc.value.message
    assert provider.fetch.await_count == 1
    assert provider.parse.await_count == 0
    assert extract.call_count == 0
    assert ingest.await_count == 0


@pytest.mark.asyncio
async def test_provider_bound_ingest_rejects_foreign_url_and_generic_ingest_survives():
    fetch_result = FetchResult(
        final_url=FOREIGN_URL,
        status_code=200,
        content=b"Controlled globally official Mevzuat source body.",
        content_type="text/plain",
    )
    metadata = {
        "source_type": "legislation",
        "title": "Fixture Law",
        "number": "987654",
    }
    maker = get_sessionmaker()
    async with maker() as db:
        with pytest.raises(ValueError) as exc:
            await ingest_official_fetch(
                db,
                metadata=metadata,
                fetch_result=fetch_result,
                expected_official_domains=YargitayProvider.official_domains,
            )
        assert "allowlisted official domain" in str(exc.value)
        assert await db.scalar(select(func.count()).select_from(SourceRecord)) == 0
        assert await db.scalar(select(func.count()).select_from(SourceVersion)) == 0
        assert await db.scalar(select(func.count()).select_from(SourceVerification)) == 0

        result = await ingest_official_fetch(
            db,
            metadata=metadata,
            fetch_result=fetch_result,
        )
        assert result.verification_status == "verified_official"
        assert await db.scalar(select(func.count()).select_from(SourceRecord)) == 1
        assert await db.scalar(select(func.count()).select_from(SourceVersion)) == 1
        assert await db.scalar(select(func.count()).select_from(SourceVerification)) == 1
