"""P2.6C — Official provider ingestion tests (fixture transport, PostgreSQL).

Covers the full Section AB matrix: registry, authorization, trust boundary,
SSRF, rate-limit policy, per-provider parsing, runs, idempotency and privacy.
All transports are deterministic fixtures — no live network access.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

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
from app.services.source_providers import registry
from app.services.source_fetcher import FetchResult, SourceFetchError
from app.services.source_providers.base import (
    ERR_ACCESS_DENIED,
    ERR_CHALLENGE,
    ERR_FETCH_FAILED,
    ERR_MANUAL_REVIEW_REQUIRED,
    ERR_RATE_LIMITED,
    ERR_SSRF_BLOCKED,
    ERR_STRUCTURE_CHANGED,
    ERR_TRANSPORT_UNAVAILABLE,
    OfficialSourceProvider,
    ParsedOfficialSource,
    ProviderCapabilities,
    ProviderDiscoveryCandidate,
    ProviderDiscoveryPage,
    ProviderError,
    ProviderRequestPolicy,
)

BODY_SENTINEL = "GİZLİKARARGÖVDESİSENTINEL2026"


# ── deterministic transport + resolver ─────────────────────────────────────
class StubResp:
    def __init__(self, status_code=200, content=b"", content_type="text/html", location=None):
        self.status_code = status_code
        self.headers = {"content-type": content_type}
        self.content = content
        self.location = location


def make_transport(mapping: dict[str, StubResp]):
    """Substring-keyed transport: first key found in the URL wins."""
    def _t(url: str):
        for key, resp in mapping.items():
            if key in url:
                return resp
        return StubResp(status_code=404, content=b"not found")
    return _t


def public_resolver(_host: str) -> list[str]:
    return ["93.184.216.34"]


def private_resolver(_host: str) -> list[str]:
    return ["10.0.0.5"]


def _html(body: str) -> bytes:
    return f"<html><body><article>{body}</article></body></html>".encode("utf-8")


def _search_html(links: str) -> bytes:
    return f"<html><body>{links}</body></html>".encode("utf-8")


# ── fixtures ────────────────────────────────────────────────────────────────
@pytest_asyncio.fixture(autouse=True)
async def clean_sources():
    maker = get_sessionmaker()
    async def _clean(session):
        await session.execute(delete(SourceUsage))
        await session.execute(delete(SourceParagraph))
        await session.execute(delete(SourceVerification))
        await session.execute(delete(SourceRelationship))
        await session.execute(delete(SourceVersion))
        await session.execute(delete(SourceRecord))
        await session.execute(delete(SourceIngestionItem))
        await session.execute(delete(SourceIngestionRun))
    async with maker() as session:
        await _clean(session)
        await session.commit()
    yield
    async with maker() as session:
        await _clean(session)
        await session.commit()


@pytest.fixture
def enabled_all():
    with patch("app.services.source_providers.registry.is_enabled", return_value=True):
        yield


# ── fixture payloads ────────────────────────────────────────────────────────
YARGITAY_DETAIL = _html(
    "Yargıtay 13. Hukuk Dairesi\n"
    "Esas No: 2020/123 Karar No: 2021/456\n"
    "Karar Tarihi: 12.06.2021\n"
    f"Davacı satış bedelinin iadesini talep etmiştir. {BODY_SENTINEL} "
    "Mahkemece davanın kabulüne karar verilmiştir ve hüküm onanmıştır."
)
YARGITAY_SEARCH = _search_html(
    '<a class="karar-link" data-karar-id="Y-1">Karar 1 ozeti uzun metin</a>'
    '<a class="karar-link" data-karar-id="Y-2">Karar 2 ozeti uzun metin</a>'
)
DANISTAY_DETAIL = _html(
    "Danıştay İdari Dava Daireleri Kurulu\n"
    "Esas No: 2019/50 Karar No: 2020/75\n"
    "Karar Tarihi: 01.03.2020\n"
    "İdari işlemin iptali istemiyle açılan davada yürütmenin durdurulmasına karar verilmiştir."
)
AYM_NORM_DETAIL = _html(
    "Anayasa Mahkemesi Genel Kurul\n"
    "Esas No: 2018/10 Karar No: 2019/20\n"
    "Karar Tarihi: 15.05.2019\n"
    "1. Başvuru, ifade özgürlüğünün ihlal edildiği iddiasına ilişkindir.\n"
    "2. Mahkeme, ihlal bulunmadığına karar vermiştir."
)
AYM_INDIVIDUAL_NO_KARAR = _html(
    "Anayasa Mahkemesi Birinci Bölüm\n"
    "Başvuru Numarası: 2018/12345\n"
    "Karar Tarihi: 10.10.2019\n"
    "1. Başvurucu, adil yargılanma hakkının ihlal edildiğini ileri sürmüştür."
)
UYUSMAZLIK_DETAIL = _html(
    "Uyuşmazlık Mahkemesi Hukuk Bölümü\n"
    "Esas No: 2021/5 Karar No: 2021/8\n"
    "Karar Tarihi: 20.02.2021\n"
    "Görevli yargı yerinin belirlenmesi istemiyle yapılan başvuru incelenmiştir."
)
MEVZUAT_DETAIL = (
    "<html><body><h1>Türk Borçlar Kanunu</h1><main>"
    "Kanun Numarası: 6098\n"
    "Resmî Gazete Tarihi: 04.02.2011\n"
    "Yürürlük Tarihi: 01.07.2012\n"
    "Madde 1\nBu Kanunun amacı borç ilişkilerini düzenlemektir ve kapsamı geniştir.\n"
    "Ek Madde 1\nEk hükümler bu madde altında düzenlenmiştir.\n"
    "Geçici Madde 1\nGeçiş hükümleri burada yer alır.\n"
    "</main></body></html>"
).encode("utf-8")
MEVZUAT_NAV_ONLY = (
    "<html><body><nav>Ana Sayfa Arama Menü</nav><footer>Çerez politikası</footer>"
    "<main>Arama</main></body></html>"
).encode("utf-8")
RG_ISSUE_DETAIL = (
    "<html><body><h1>Resmî Gazete</h1><main>"
    "Sayı: 32345 Tarih: 12.07.2026\n"
    "Bu sayıda yayımlanan düzenlemeler ve kararlar listelenmiştir. İçerik uzundur."
    "</main></body></html>"
).encode("utf-8")
UI_ONLY_DETAIL = _html("Arama")


def _prov_transport(detail: bytes, search: bytes | None = None):
    mapping = {"getDokuman": StubResp(content=detail),
               "MevzuatMetin": StubResp(content=detail),
               "BB?": StubResp(content=detail),
               "/BB": StubResp(content=detail),
               "eskiler": StubResp(content=detail)}
    if search is not None:
        mapping = {"aramalist": StubResp(content=search),
                   "/Ara": StubResp(content=search),
                   "fihrist": StubResp(content=search), **mapping}
    return make_transport(mapping)


async def _run(**kw):
    from app.services.provider_ingestion_service import run_ingestion

    async def _no_sleep(_s):
        return None

    maker = get_sessionmaker()
    async with maker() as db:
        return await run_ingestion(db, sleeper=_no_sleep, resolver=public_resolver, **kw)


# ═══════════════════ REGISTRY ═══════════════════
def test_registry_six_providers_registered():
    assert set(registry.all_provider_codes()) == {
        "yargitay", "danistay", "aym", "uyusmazlik", "mevzuat", "resmi_gazete"}


def test_registry_unknown_rejected():
    with pytest.raises(ProviderError) as ei:
        registry.get("wikipedia")
    assert ei.value.code == "unknown_provider"


def test_registry_disabled_blocked_by_default():
    with pytest.raises(ProviderError) as ei:
        registry.get("yargitay")  # default disabled
    assert ei.value.code == "provider_disabled"


def test_registry_no_arbitrary_module_import():
    # Registry is a closed dict; arbitrary dotted names are never importable.
    with pytest.raises(ProviderError):
        registry.get("os.system")
    with pytest.raises(ProviderError):
        registry.get_definition("app.main")


def test_registry_by_source_type():
    assert registry.by_source_type("legislation") == ["mevzuat", "resmi_gazete"]
    assert registry.by_source_type("supreme_court_decision") == ["yargitay"]


# ═══════════════════ TRUST BOUNDARY ═══════════════════
@pytest.mark.asyncio
async def test_exact_official_fetch_produces_p26_evidence(enabled_all):
    summary = await _run(
        provider_code="yargitay", run_type="fetch_and_ingest",
        transport=_prov_transport(YARGITAY_DETAIL, YARGITAY_SEARCH), max_items=1,
    )
    assert summary.ingested == 1
    maker = get_sessionmaker()
    async with maker() as db:
        rec = (await db.execute(select(SourceRecord))).scalars().first()
        assert rec is not None
        assert rec.verification_status == "verified_official"
        ver = (await db.execute(select(SourceVersion).where(
            SourceVersion.source_record_id == rec.id))).scalars().first()
        vrf = (await db.execute(select(SourceVerification).where(
            SourceVerification.source_record_id == rec.id))).scalars().all()
    official = [v for v in vrf if v.verifier_type == "official_match"]
    assert official, "official_match verification must exist"
    assert official[0].evidence_hash == ver.content_hash
    assert official[0].verification_method == "official_fetch_match"


@pytest.mark.asyncio
async def test_discovery_metadata_cannot_produce_verified_official(enabled_all):
    summary = await _run(
        provider_code="yargitay", run_type="discover_only",
        transport=_prov_transport(YARGITAY_DETAIL, YARGITAY_SEARCH), max_items=2,
    )
    assert summary.discovered == 2
    assert summary.ingested == 0
    maker = get_sessionmaker()
    async with maker() as db:
        recs = (await db.execute(select(SourceRecord))).scalars().all()
        vrfs = (await db.execute(select(SourceVerification))).scalars().all()
    assert recs == []
    assert vrfs == []


@pytest.mark.asyncio
async def test_provider_does_not_write_verification_directly(enabled_all):
    # Only the P2.6 official-fetch engine writes verifications; a discover_only
    # run (which calls provider discover/parse but not ingest) writes none.
    await _run(provider_code="mevzuat", run_type="discover_only",
               transport=_prov_transport(MEVZUAT_DETAIL, _search_html(
                   '<a class="mevzuat-link" data-mevzuat-id="M-1">TBK</a>')), max_items=1)
    maker = get_sessionmaker()
    async with maker() as db:
        assert (await db.execute(select(SourceVerification))).scalars().all() == []


@pytest.mark.asyncio
async def test_changed_official_content_preserves_old_version(enabled_all):
    search = YARGITAY_SEARCH
    await _run(provider_code="yargitay", run_type="fetch_and_ingest",
               transport=_prov_transport(YARGITAY_DETAIL, search), max_items=1)
    changed = _html(
        "Yargıtay 13. Hukuk Dairesi\nEsas No: 2020/123 Karar No: 2021/456\n"
        "Karar Tarihi: 12.06.2021\nDEĞİŞMİŞ RESMİ İÇERİK farklı hüküm gerekçesi uzun metin buraya.")
    summary = await _run(provider_code="yargitay", run_type="fetch_and_ingest",
                         transport=_prov_transport(changed, search), max_items=1)
    assert summary.new_version == 1
    maker = get_sessionmaker()
    async with maker() as db:
        rec = (await db.execute(select(SourceRecord))).scalars().first()
        versions = (await db.execute(select(SourceVersion).where(
            SourceVersion.source_record_id == rec.id))).scalars().all()
    assert len(versions) == 2  # old preserved


# ═══════════════════ SSRF ═══════════════════
@pytest.mark.asyncio
async def test_ssrf_private_ip_blocked(enabled_all):
    from app.services.provider_ingestion_service import run_ingestion

    async def _no_sleep(_s):
        return None

    maker = get_sessionmaker()
    async with maker() as db:
        summary = await run_ingestion(
            db, provider_code="yargitay", run_type="fetch_and_ingest",
            transport=_prov_transport(YARGITAY_DETAIL, YARGITAY_SEARCH),
            resolver=private_resolver, sleeper=_no_sleep, max_items=1,
        )
    # discovery itself fetches through the seam → blocked before any ingest.
    assert summary.ingested == 0
    assert summary.status == "failed"
    assert summary.last_safe_error_code in ("ssrf_blocked",)


def test_ssrf_seam_blocks_credentials_scheme_loopback_metadata():
    prov = registry.get_definition("yargitay")
    # credentials-in-URL
    cand = ProviderDiscoveryCandidate(provider_code="yargitay", source_type="supreme_court_decision",
                                      detail_url="https://u:p@karararama.yargitay.gov.tr/x")
    with pytest.raises(ProviderError) as ei:
        prov._secure_fetch(cand.detail_url, transport=make_transport({}), resolver=public_resolver)
    assert ei.value.code == "ssrf_blocked"
    # unsupported scheme
    with pytest.raises(ProviderError):
        prov._secure_fetch("ftp://karararama.yargitay.gov.tr/x",
                           transport=make_transport({}), resolver=public_resolver)
    # loopback resolver
    with pytest.raises(ProviderError):
        prov._secure_fetch("https://karararama.yargitay.gov.tr/x",
                           transport=make_transport({"x": StubResp()}),
                           resolver=lambda h: ["127.0.0.1"])
    # metadata/link-local resolver
    with pytest.raises(ProviderError):
        prov._secure_fetch("https://karararama.yargitay.gov.tr/x",
                           transport=make_transport({"x": StubResp()}),
                           resolver=lambda h: ["169.254.169.254"])


def test_ssrf_every_redirect_hop_revalidated():
    prov = registry.get_definition("yargitay")
    # hop 1 allowlisted (public); redirect to a disallowed domain → blocked on hop 2.
    transport = make_transport({
        "karararama.yargitay.gov.tr/start": StubResp(status_code=302, location="https://evil.example.com/x"),
        "evil.example.com": StubResp(content=b"malicious"),
    })
    with pytest.raises(ProviderError) as ei:
        prov._secure_fetch("https://karararama.yargitay.gov.tr/start",
                           transport=transport, resolver=public_resolver)
    assert ei.value.code == "ssrf_blocked"


# ═══════════════════ RATE LIMIT / POLITENESS ═══════════════════
def test_rate_limit_policy_defaults_low_concurrency():
    for code in registry.all_provider_codes():
        pol = registry.get_definition(code).request_policy
        assert pol.max_concurrency == 1
        assert pol.min_interval_seconds >= 2.0
        assert pol.max_retries <= 3
        assert 429 not in pol.retryable_statuses  # 429 handled explicitly, not blind retry


@pytest.mark.asyncio
async def test_politeness_sleep_invoked_between_calls(enabled_all):
    calls: list[float] = []

    async def _record_sleep(seconds):
        calls.append(seconds)

    from app.services.provider_ingestion_service import run_ingestion
    maker = get_sessionmaker()
    async with maker() as db:
        await run_ingestion(
            db, provider_code="yargitay", run_type="fetch_and_ingest",
            transport=_prov_transport(YARGITAY_DETAIL, YARGITAY_SEARCH),
            resolver=public_resolver, sleeper=_record_sleep, max_items=2,
        )
    assert calls and all(s >= 2.0 for s in calls)


# ═══════════════════ PER-PROVIDER PARSING ═══════════════════
@pytest.mark.asyncio
async def test_yargitay_parse_metadata_and_ek(enabled_all):
    await _run(provider_code="yargitay", run_type="fetch_and_ingest",
               transport=_prov_transport(YARGITAY_DETAIL, YARGITAY_SEARCH), max_items=1)
    maker = get_sessionmaker()
    async with maker() as db:
        rec = (await db.execute(select(SourceRecord))).scalars().first()
    assert rec.court == "Yargıtay"
    assert rec.chamber == "13. Hukuk Dairesi"
    assert rec.case_number == "2020/123"
    assert rec.decision_number == "2021/456"
    assert rec.decision_date == "2021-06-12"


@pytest.mark.asyncio
async def test_yargitay_ui_only_body_rejected(enabled_all):
    summary = await _run(provider_code="yargitay", run_type="fetch_and_ingest",
                         transport=_prov_transport(UI_ONLY_DETAIL, YARGITAY_SEARCH), max_items=1)
    assert summary.ingested == 0
    assert summary.failed >= 1
    assert summary.last_safe_error_code == "empty_legal_body"


@pytest.mark.asyncio
async def test_danistay_board_not_collapsed(enabled_all):
    await _run(provider_code="danistay", run_type="fetch_and_ingest",
               transport=_prov_transport(DANISTAY_DETAIL, _search_html(
                   '<a class="karar-link" data-karar-id="D-1">Danıştay kararı ozet</a>')), max_items=1)
    maker = get_sessionmaker()
    async with maker() as db:
        rec = (await db.execute(select(SourceRecord))).scalars().first()
    assert rec.court == "Danıştay"
    assert rec.chamber == "İdari Dava Daireleri Kurulu"  # NOT a numbered chamber
    assert rec.case_number == "2019/50"


@pytest.mark.asyncio
async def test_aym_norm_control_ingests(enabled_all):
    await _run(provider_code="aym", run_type="fetch_and_ingest",
               transport=_prov_transport(AYM_NORM_DETAIL, _search_html(
                   '<a class="karar-link" data-karar-id="A-1">AYM kararı ozet metni</a>')), max_items=1)
    maker = get_sessionmaker()
    async with maker() as db:
        rec = (await db.execute(select(SourceRecord))).scalars().first()
    assert rec is not None
    assert rec.court == "Anayasa Mahkemesi"
    assert rec.case_number == "2018/10"
    assert rec.decision_number == "2019/20"


@pytest.mark.asyncio
async def test_aym_individual_without_karar_not_fabricated(enabled_all):
    summary = await _run(provider_code="aym", run_type="fetch_and_ingest",
                         transport=_prov_transport(AYM_INDIVIDUAL_NO_KARAR, _search_html(
                             '<a class="karar-link" data-karar-id="A-2">AYM bireysel basvuru</a>')), max_items=1)
    assert summary.ingested == 0
    assert summary.last_safe_error_code == "manual_review_required"
    maker = get_sessionmaker()
    async with maker() as db:
        assert (await db.execute(select(SourceRecord))).scalars().all() == []


@pytest.mark.asyncio
async def test_uyusmazlik_parse(enabled_all):
    await _run(provider_code="uyusmazlik", run_type="fetch_and_ingest",
               transport=_prov_transport(UYUSMAZLIK_DETAIL, _search_html(
                   '<a class="karar-link" data-karar-id="U-1">Uyusmazlik karari ozet</a>')), max_items=1)
    maker = get_sessionmaker()
    async with maker() as db:
        rec = (await db.execute(select(SourceRecord))).scalars().first()
    assert rec.court == "Uyuşmazlık Mahkemesi"
    assert rec.case_number == "2021/5"
    assert rec.decision_number == "2021/8"


@pytest.mark.asyncio
async def test_mevzuat_article_parsing_and_nav_excluded(enabled_all):
    search = _search_html('<a class="mevzuat-link" data-mevzuat-id="M-1">TBK</a>')
    await _run(provider_code="mevzuat", run_type="fetch_and_ingest",
               transport=_prov_transport(MEVZUAT_DETAIL, search), max_items=1)
    maker = get_sessionmaker()
    async with maker() as db:
        rec = (await db.execute(select(SourceRecord))).scalars().first()
        assert rec.source_type == "legislation"
        assert rec.official_url
        ver = (await db.execute(select(SourceVersion).where(
            SourceVersion.source_record_id == rec.id))).scalars().first()
        paras = (await db.execute(select(SourceParagraph).where(
            SourceParagraph.source_version_id == ver.id))).scalars().all()
    articles = {p.article_number for p in paras if p.article_number}
    assert "1" in articles
    # Navigation/cookie chrome never becomes a paragraph.
    assert all("Çerez" not in p.text for p in paras)


@pytest.mark.asyncio
async def test_mevzuat_nav_only_rejected(enabled_all):
    search = _search_html('<a class="mevzuat-link" data-mevzuat-id="M-2">bos</a>')
    summary = await _run(provider_code="mevzuat", run_type="fetch_and_ingest",
                         transport=_prov_transport(MEVZUAT_NAV_ONLY, search), max_items=1)
    assert summary.ingested == 0
    assert summary.last_safe_error_code in ("empty_legal_body", "missing_identifier")


@pytest.mark.asyncio
async def test_resmi_gazete_issue_ingest(enabled_all):
    search = _search_html(
        '<a class="gazete-issue" href="https://resmigazete.gov.tr/eskiler/2026/07/rg.htm" data-issue-no="32345">RG</a>')
    summary = await _run(provider_code="resmi_gazete", run_type="fetch_and_ingest",
                         transport=make_transport({
                             "fihrist": StubResp(content=search),
                             "eskiler": StubResp(content=RG_ISSUE_DETAIL),
                         }), max_items=1)
    assert summary.ingested == 1
    maker = get_sessionmaker()
    async with maker() as db:
        rec = (await db.execute(select(SourceRecord))).scalars().first()
    assert rec.source_type == "official_gazette_issue"
    assert rec.publication_date == "2026-07-12"


@pytest.mark.asyncio
async def test_resmi_gazete_uncertain_instrument_not_fabricated(enabled_all):
    # An instrument candidate whose content has no deterministic number.
    search = _search_html(
        '<a class="gazete-instrument" data-instrument-type="yönetmelik" '
        'data-instrument-id="I-9" href="https://resmigazete.gov.tr/eskiler/x.htm">Yön</a>')
    body = _html("Örnek Yönetmelik metni herhangi bir numara içermeyen uzun içerik buraya yazılmıştır.")
    summary = await _run(provider_code="resmi_gazete", run_type="fetch_and_ingest",
                         transport=make_transport({
                             "fihrist": StubResp(content=search),
                             "eskiler": StubResp(content=body),
                         }), max_items=1)
    assert summary.ingested == 0
    assert summary.last_safe_error_code == "manual_review_required"


# ═══════════════════ RUNS ═══════════════════
@pytest.mark.asyncio
async def test_run_counts_and_no_raw_text_stored(enabled_all):
    summary = await _run(provider_code="yargitay", run_type="fetch_and_ingest",
                         transport=_prov_transport(YARGITAY_DETAIL, YARGITAY_SEARCH), max_items=2)
    maker = get_sessionmaker()
    async with maker() as db:
        run = await db.get(SourceIngestionRun, summary.run_id)
        items = (await db.execute(select(SourceIngestionItem).where(
            SourceIngestionItem.run_id == summary.run_id))).scalars().all()
    assert run.status in ("completed", "completed_with_errors")
    assert run.discovered_count == 2
    # Privacy: raw body sentinel must not appear in run/item persisted columns.
    assert BODY_SENTINEL not in str(run.__dict__)
    for it in items:
        assert BODY_SENTINEL not in str(it.__dict__)


@pytest.mark.asyncio
async def test_run_cancel_queued():
    from app.db.source_ingestion_repository import SourceIngestionRunRepository
    maker = get_sessionmaker()
    async with maker() as db:
        run = await SourceIngestionRunRepository.create(
            db, provider_code="yargitay", run_type="discover_only")
        await db.commit()
        ok = await SourceIngestionRunRepository.cancel(db, run)
        await db.commit()
        assert ok
        assert run.status == "cancelled"
        # Cannot cancel again.
        assert await SourceIngestionRunRepository.cancel(db, run) is False


@pytest.mark.asyncio
async def test_run_completed_with_errors(enabled_all):
    # One good candidate + one UI-only candidate → completed_with_errors.
    search = _search_html(
        '<a class="karar-link" data-karar-id="OK">iyi karar ozet metni</a>'
        '<a class="karar-link" data-karar-id="BAD">bos</a>')
    def _t(url):
        if "aramalist" in url:
            return StubResp(content=search)
        if "id=OK" in url:
            return StubResp(content=YARGITAY_DETAIL)
        return StubResp(content=UI_ONLY_DETAIL)
    summary = await _run(provider_code="yargitay", run_type="fetch_and_ingest",
                         transport=_t, max_items=2)
    assert summary.ingested == 1
    assert summary.failed == 1
    assert summary.status == "completed_with_errors"


# ═══════════════════ IDEMPOTENCY ═══════════════════
@pytest.mark.asyncio
async def test_rediscovery_no_duplicate_item_and_no_duplicate_version(enabled_all):
    t = _prov_transport(YARGITAY_DETAIL, YARGITAY_SEARCH)
    await _run(provider_code="yargitay", run_type="fetch_and_ingest", transport=t, max_items=1)
    second = await _run(provider_code="yargitay", run_type="fetch_and_ingest", transport=t, max_items=1)
    maker = get_sessionmaker()
    async with maker() as db:
        recs = (await db.execute(select(SourceRecord))).scalars().all()
        versions = (await db.execute(select(SourceVersion))).scalars().all()
        items = (await db.execute(select(SourceIngestionItem))).scalars().all()
    assert len(recs) == 1
    assert len(versions) == 1  # exact same fetch → no duplicate version
    # Rediscovery of an already-ingested candidate creates no new item.
    assert len(items) == 1


# ═══════════════════ AUTHORIZATION (jwt mode) ═══════════════════
def _jwt_token(role: str) -> str:
    from app.services.auth_service import create_access_token
    return create_access_token(f"u-{role}", "prov-tenant", role, f"s-{role}")


async def _jwt_client():
    from app.main import app as _app
    return AsyncClient(transport=ASGITransport(app=_app), base_url="http://test")


async def _jwt_get(ac, path, role):
    with patch("app.services.auth_service.get_auth_mode", return_value="jwt"), \
         patch("app.routes.source_routes.get_auth_mode", return_value="jwt"):
        return await ac.get(path, headers={"Authorization": f"Bearer {_jwt_token(role)}"})


async def _jwt_post(ac, path, role, json=None):
    with patch("app.services.auth_service.get_auth_mode", return_value="jwt"), \
         patch("app.routes.source_routes.get_auth_mode", return_value="jwt"):
        return await ac.post(path, json=json, headers={"Authorization": f"Bearer {_jwt_token(role)}"})


@pytest.mark.asyncio
async def test_provider_list_lawyer_and_tenant_admin_forbidden():
    ac = await _jwt_client()
    try:
        for role in ("lawyer", "tenant_admin"):
            r = await _jwt_get(ac, "/api/v1/official-source-providers", role)
            assert r.status_code == 403, f"{role} must be 403, got {r.status_code}"
    finally:
        await ac.aclose()


@pytest.mark.asyncio
async def test_provider_list_editor_and_admin_allowed():
    ac = await _jwt_client()
    try:
        for role in ("editor", "admin"):
            r = await _jwt_get(ac, "/api/v1/official-source-providers", role)
            assert r.status_code == 200, f"{role} must be 200, got {r.status_code}"
            codes = {p["code"] for p in r.json()["items"]}
            assert codes == {"yargitay", "danistay", "aym", "uyusmazlik", "mevzuat", "resmi_gazete"}
    finally:
        await ac.aclose()


@pytest.mark.asyncio
async def test_create_run_authorization_and_queue(enabled_all):
    ac = await _jwt_client()
    try:
        # lawyer forbidden
        r = await _jwt_post(ac, "/api/v1/official-source-providers/yargitay/runs",
                            "lawyer", json={"run_type": "discover_only"})
        assert r.status_code == 403
        # editor allowed → 202 queued
        r = await _jwt_post(ac, "/api/v1/official-source-providers/yargitay/runs",
                            "editor", json={"run_type": "discover_only", "max_items": 5})
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["status"] == "queued"
        assert body["provider_code"] == "yargitay"
    finally:
        await ac.aclose()


@pytest.mark.asyncio
async def test_create_run_unknown_provider_404_and_disabled_409():
    ac = await _jwt_client()
    try:
        r = await _jwt_post(ac, "/api/v1/official-source-providers/nope/runs",
                            "editor", json={"run_type": "discover_only"})
        assert r.status_code == 404
        # Known but disabled (default) → 409.
        r = await _jwt_post(ac, "/api/v1/official-source-providers/yargitay/runs",
                            "editor", json={"run_type": "discover_only"})
        assert r.status_code == 409
    finally:
        await ac.aclose()


@pytest.mark.asyncio
async def test_no_arbitrary_url_ingestion_surface():
    # There is no endpoint that accepts an arbitrary fetch URL for ingestion.
    from app.main import app as _app
    schema = _app.openapi()
    for path in schema.get("paths", {}):
        assert "ingest-url" not in path
        assert "fetch-url" not in path


# ═════════════════ P2.6C retry/status closure regressions ═════════════════
class SequencedProvider(OfficialSourceProvider):
    provider_code = "yargitay"
    provider_name = "Fake Provider"
    source_types = ("legislation",)
    official_domains = ("karararama.yargitay.gov.tr",)
    capabilities = ProviderCapabilities(discovery=True, fetch=True, parse=True)

    def __init__(
        self,
        *,
        discover_steps=None,
        fetch_steps=None,
        parse_error: ProviderError | None = None,
        candidate_count: int = 1,
        policy: ProviderRequestPolicy | None = None,
    ):
        self.discover_steps = list(discover_steps or [])
        self.fetch_steps = list(fetch_steps or [])
        self.parse_error = parse_error
        self.candidate_count = candidate_count
        self.request_policy = policy or ProviderRequestPolicy(
            min_interval_seconds=0,
            max_retries=2,
            backoff_base_seconds=1,
            backoff_max_seconds=5,
        )
        self.discover_calls = 0
        self.fetch_calls = 0
        self.parse_calls = 0

    async def discover(self, **_kw) -> ProviderDiscoveryPage:
        self.discover_calls += 1
        if self.discover_steps:
            step = self.discover_steps.pop(0)
            if isinstance(step, Exception):
                raise step
        return ProviderDiscoveryPage(
            candidates=[
                ProviderDiscoveryCandidate(
                    provider_code=self.provider_code,
                    source_type="legislation",
                    detail_url=f"https://karararama.yargitay.gov.tr/doc/{idx}",
                    external_id=f"fake-{idx}",
                )
                for idx in range(self.candidate_count)
            ]
        )

    async def fetch(self, candidate, *, transport=None, resolver=None):
        self.fetch_calls += 1
        if self.fetch_steps:
            step = self.fetch_steps.pop(0)
            if isinstance(step, Exception):
                raise step
        return FetchResult(
            final_url=candidate.detail_url,
            status_code=200,
            content=_html(
                "Kanun Numarasi: 6098 Resmi metin govdesi yeterince uzun."
            ),
            content_type="text/html",
        )

    async def parse(self, candidate, fetch_result) -> ParsedOfficialSource:
        self.parse_calls += 1
        if self.parse_error is not None:
            raise self.parse_error
        return ParsedOfficialSource(
            provider_code=self.provider_code,
            source_type="legislation",
            title="Fake Law",
            official_url=fetch_result.final_url,
            raw_text="Kanun Numarasi: 6098 Resmi metin govdesi yeterince uzun.",
            number="6098",
        )


def _retry_error(code=ERR_FETCH_FAILED, *, retry_after=None, status=None):
    return ProviderError(
        code,
        "safe",
        retryable=True,
        retry_after_seconds=retry_after,
        http_status=status,
    )


def _outcome(outcome="created"):
    return SimpleNamespace(
        outcome=outcome,
        source_record_id="sr-1",
        source_version_id="sv-1",
    )


async def _run_fake_provider(provider: SequencedProvider, *, sleeper=None):
    from app.services.provider_ingestion_service import run_ingestion

    async def _no_sleep(_seconds):
        return None

    maker = get_sessionmaker()
    with patch("app.services.provider_ingestion_service.registry.get", return_value=provider), \
         patch("app.services.provider_ingestion_service.ingest_official_fetch",
               new=AsyncMock(return_value=_outcome())):
        async with maker() as db:
            return await run_ingestion(
                db,
                provider_code=provider.provider_code,
                run_type="fetch_and_ingest",
                transport=make_transport({}),
                resolver=public_resolver,
                sleeper=sleeper or _no_sleep,
                max_items=provider.candidate_count,
            )


@pytest.mark.asyncio
async def test_injected_resolver_used_for_discovery_and_fetch_no_external_dns(enabled_all):
    calls = []

    def fail_default_resolver(*_args, **_kw):
        calls.append(_args)
        raise AssertionError("external DNS must not be used")

    with patch("app.services.source_fetcher.default_resolver",
               side_effect=fail_default_resolver):
        discover_summary = await _run(
            provider_code="mevzuat",
            run_type="discover_only",
            transport=_prov_transport(
                MEVZUAT_DETAIL,
                _search_html('<a class="mevzuat-link" data-mevzuat-id="M-1">TBK</a>'),
            ),
            max_items=1,
        )
        fetch_summary = await _run(
            provider_code="mevzuat",
            run_type="fetch_and_ingest",
            transport=_prov_transport(
                MEVZUAT_DETAIL,
                _search_html('<a class="mevzuat-link" data-mevzuat-id="M-1">TBK</a>'),
            ),
            max_items=1,
        )
    assert discover_summary.status == "completed"
    assert fetch_summary.ingested == 1
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_code,search_key,link", [
    ("yargitay", "aramalist", '<a class="karar-link" data-karar-id="Y-1">Y</a>'),
    ("danistay", "aramalist", '<a class="karar-link" data-karar-id="D-1">D</a>'),
    ("aym", "/Ara", '<a class="karar-link" data-karar-id="A-1">A</a>'),
    ("uyusmazlik", "aramalist", '<a class="karar-link" data-karar-id="U-1">U</a>'),
    ("mevzuat", "/Ara", '<a class="mevzuat-link" data-mevzuat-id="M-1">M</a>'),
    ("resmi_gazete", "fihrist", '<a class="gazete-issue" href="https://resmigazete.gov.tr/eskiler/x.htm" data-issue-no="1">RG</a>'),
])
async def test_discover_only_all_providers_use_injected_resolver(
    enabled_all, provider_code, search_key, link,
):
    with patch("app.services.source_fetcher.default_resolver",
               side_effect=AssertionError("external DNS")) as dns:
        summary = await _run(
            provider_code=provider_code,
            run_type="discover_only",
            transport=make_transport({search_key: StubResp(content=_search_html(link))}),
            max_items=1,
        )
    assert summary.discovered == 1
    assert dns.call_count == 0


@pytest.mark.parametrize("fetch_error,expected,retryable", [
    (SourceFetchError("unsafe_scheme", "safe"), ERR_SSRF_BLOCKED, False),
    (SourceFetchError("no_transport", "safe"), ERR_TRANSPORT_UNAVAILABLE, False),
    (SourceFetchError("http_error", "safe", http_status=429, retry_after_seconds=2), ERR_RATE_LIMITED, True),
    (SourceFetchError("http_error", "safe", http_status=503), ERR_FETCH_FAILED, True),
    (SourceFetchError("http_error", "safe", http_status=403), ERR_ACCESS_DENIED, False),
    (SourceFetchError("http_error", "safe", http_status=404), ERR_FETCH_FAILED, False),
    (SourceFetchError("fetch_timeout", "safe"), ERR_FETCH_FAILED, True),
    (SourceFetchError("connect_error", "safe"), ERR_FETCH_FAILED, True),
    (SourceFetchError("network_error", "safe"), ERR_FETCH_FAILED, True),
    (SourceFetchError("tls_error", "safe"), ERR_FETCH_FAILED, False),
    (SourceFetchError("response_too_large", "safe"), ERR_FETCH_FAILED, False),
    (SourceFetchError("unsupported_content_type", "safe"), ERR_FETCH_FAILED, False),
])
def test_provider_fetch_error_classification_matrix(fetch_error, expected, retryable):
    provider = registry.get_definition("yargitay")
    err = provider._provider_error_from_fetch_error(fetch_error)
    assert err.code == expected
    assert err.retryable is retryable
    assert err.http_status == fetch_error.http_status
    assert err.retry_after_seconds == fetch_error.retry_after_seconds


@pytest.mark.asyncio
async def test_retry_503_then_200_succeeds(enabled_all):
    provider = SequencedProvider(fetch_steps=[_retry_error(status=503)])
    summary = await _run_fake_provider(provider)
    assert summary.status == "completed"
    assert provider.fetch_calls == 2


@pytest.mark.asyncio
async def test_retry_503_503_then_200_succeeds(enabled_all):
    provider = SequencedProvider(fetch_steps=[_retry_error(status=503), _retry_error(status=503)])
    summary = await _run_fake_provider(provider)
    assert summary.status == "completed"
    assert provider.fetch_calls == 3


@pytest.mark.asyncio
async def test_retry_exhaustion_has_no_fourth_attempt(enabled_all):
    provider = SequencedProvider(fetch_steps=[
        _retry_error(status=503), _retry_error(status=503), _retry_error(status=503),
    ])
    summary = await _run_fake_provider(provider)
    assert summary.status == "failed"
    assert summary.last_safe_error_code == ERR_FETCH_FAILED
    assert provider.fetch_calls == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("err", [
    ProviderError(ERR_FETCH_FAILED, "connect", retryable=True),
    ProviderError(ERR_FETCH_FAILED, "network", retryable=True),
])
async def test_connect_and_network_errors_retry_to_success(enabled_all, err):
    provider = SequencedProvider(fetch_steps=[err])
    summary = await _run_fake_provider(provider)
    assert summary.status == "completed"
    assert provider.fetch_calls == 2


@pytest.mark.asyncio
async def test_429_retry_after_respects_min_interval(enabled_all):
    sleeps = []

    async def record_sleep(seconds):
        sleeps.append(seconds)

    provider = SequencedProvider(
        fetch_steps=[_retry_error(ERR_RATE_LIMITED, retry_after=2, status=429)],
        policy=ProviderRequestPolicy(
            min_interval_seconds=3,
            max_retries=2,
            backoff_base_seconds=1,
            backoff_max_seconds=5,
        ),
    )
    summary = await _run_fake_provider(provider, sleeper=record_sleep)
    assert summary.status == "completed"
    assert provider.fetch_calls == 2
    assert 3 in sleeps


@pytest.mark.asyncio
async def test_429_retry_after_above_max_fails_without_retry(enabled_all):
    provider = SequencedProvider(
        fetch_steps=[_retry_error(ERR_RATE_LIMITED, retry_after=30, status=429)],
        policy=ProviderRequestPolicy(
            min_interval_seconds=0,
            max_retries=2,
            backoff_base_seconds=1,
            backoff_max_seconds=5,
        ),
    )
    summary = await _run_fake_provider(provider)
    assert summary.status == "failed"
    assert summary.last_safe_error_code == ERR_RATE_LIMITED
    assert provider.fetch_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("err", [
    ProviderError(ERR_ACCESS_DENIED, "403"),
    ProviderError(ERR_SSRF_BLOCKED, "ssrf"),
    ProviderError(ERR_FETCH_FAILED, "tls"),
    ProviderError(ERR_FETCH_FAILED, "too_large"),
])
async def test_non_retryable_fetch_errors_attempt_once(enabled_all, err):
    provider = SequencedProvider(fetch_steps=[err])
    summary = await _run_fake_provider(provider)
    assert summary.status == "failed"
    assert provider.fetch_calls == 1


@pytest.mark.asyncio
async def test_parse_failure_does_not_retry_fetch(enabled_all):
    provider = SequencedProvider(parse_error=ProviderError(ERR_STRUCTURE_CHANGED, "parse"))
    summary = await _run_fake_provider(provider)
    assert summary.status == "failed"
    assert provider.fetch_calls == 1
    assert provider.parse_calls == 1


@pytest.mark.asyncio
async def test_ingest_rejection_does_not_retry_fetch_or_ingest(enabled_all):
    from app.services.provider_ingestion_service import run_ingestion

    provider = SequencedProvider()
    ingest = AsyncMock(side_effect=ValueError("safe reject"))

    async def _no_sleep(_seconds):
        return None

    maker = get_sessionmaker()
    with patch("app.services.provider_ingestion_service.registry.get", return_value=provider), \
         patch("app.services.provider_ingestion_service.ingest_official_fetch", new=ingest):
        async with maker() as db:
            summary = await run_ingestion(
                db,
                provider_code=provider.provider_code,
                run_type="fetch_and_ingest",
                transport=make_transport({}),
                resolver=public_resolver,
                sleeper=_no_sleep,
                max_items=1,
            )
    assert summary.status == "failed"
    assert provider.fetch_calls == 1
    assert ingest.await_count == 1


@pytest.mark.asyncio
async def test_discovery_retry_uses_shared_executor(enabled_all):
    provider = SequencedProvider(discover_steps=[_retry_error()])
    summary = await _run_fake_provider(provider)
    assert summary.status == "completed"
    assert provider.discover_calls == 2


@pytest.mark.asyncio
async def test_fetch_retry_uses_shared_executor(enabled_all):
    provider = SequencedProvider(fetch_steps=[_retry_error()])
    summary = await _run_fake_provider(provider)
    assert summary.status == "completed"
    assert provider.fetch_calls == 2


@pytest.mark.asyncio
async def test_challenge_first_candidate_stops_run(enabled_all):
    provider = SequencedProvider(
        candidate_count=3,
        fetch_steps=[ProviderError(ERR_CHALLENGE, "challenge")],
    )
    summary = await _run_fake_provider(provider)
    maker = get_sessionmaker()
    async with maker() as db:
        items = (await db.execute(select(SourceIngestionItem))).scalars().all()
    assert summary.status == "failed"
    assert summary.failed == 1
    assert provider.fetch_calls == 1
    assert len(items) == 1


@pytest.mark.asyncio
async def test_structure_change_after_success_stops_with_errors(enabled_all):
    provider = SequencedProvider(
        candidate_count=3,
        fetch_steps=[None, ProviderError(ERR_STRUCTURE_CHANGED, "changed")],
    )
    summary = await _run_fake_provider(provider)
    maker = get_sessionmaker()
    async with maker() as db:
        items = (await db.execute(select(SourceIngestionItem))).scalars().all()
    assert summary.status == "completed_with_errors"
    assert summary.ingested == 1
    assert summary.failed == 1
    assert provider.fetch_calls == 2
    assert len(items) == 2


@pytest.mark.asyncio
async def test_rate_limit_exhausted_stops_provider_hammering(enabled_all):
    provider = SequencedProvider(
        candidate_count=3,
        fetch_steps=[
            _retry_error(ERR_RATE_LIMITED, status=429),
            _retry_error(ERR_RATE_LIMITED, status=429),
            _retry_error(ERR_RATE_LIMITED, status=429),
        ],
    )
    summary = await _run_fake_provider(provider)
    assert summary.status == "failed"
    assert summary.last_safe_error_code == ERR_RATE_LIMITED
    assert provider.fetch_calls == 3


def test_operational_status_precedence():
    from app.routes import provider_ingestion_routes as routes

    caps = ProviderCapabilities()
    definition = SimpleNamespace(capabilities=caps)
    terminal = SimpleNamespace(status="failed", last_safe_error_code="")
    success = SimpleNamespace(status="completed")
    with patch("app.services.source_providers.registry.is_enabled", return_value=False):
        assert routes._provider_status("x", definition, terminal, success) == "disabled"
    with patch("app.services.source_providers.registry.is_enabled", return_value=True):
        assert routes._provider_status(
            "x", SimpleNamespace(capabilities=ProviderCapabilities(requires_auth=True)),
            terminal, success,
        ) == "unsupported_requires_auth"
        assert routes._provider_status(
            "x", SimpleNamespace(capabilities=ProviderCapabilities(requires_browser=True)),
            terminal, success,
        ) == "browser_discovery_unavailable"
    with patch("app.services.source_providers.registry.is_enabled", return_value=True), \
         patch("app.routes.provider_ingestion_routes._automatic_live_transport_configured",
               return_value=False):
        assert routes._provider_status("x", definition, terminal, success) == "transport_unavailable"
    with patch("app.services.source_providers.registry.is_enabled", return_value=True), \
         patch("app.routes.provider_ingestion_routes._automatic_live_transport_configured",
               return_value=True):
        assert routes._provider_status("x", definition, None, None) == "fixture_tested_only"
        assert routes._provider_status(
            "x", definition,
            SimpleNamespace(status="failed", last_safe_error_code="provider_structure_changed"),
            success,
        ) == "provider_changed"
        assert routes._provider_status(
            "x", definition,
            SimpleNamespace(status="failed", last_safe_error_code="challenge_detected"),
            success,
        ) == "manual_review_required"
        assert routes._provider_status("x", definition, terminal, success) == "degraded"
        assert routes._provider_status(
            "x", definition,
            SimpleNamespace(status="completed_with_errors", last_safe_error_code="fetch_failed"),
            success,
        ) == "degraded"
        assert routes._provider_status(
            "x", definition,
            SimpleNamespace(status="completed", last_safe_error_code=""),
            success,
        ) == "available"


@pytest.mark.asyncio
async def test_provider_info_uses_history_queries_and_safe_fields(enabled_all):
    from app.db.source_ingestion_repository import SourceIngestionRunRepository
    from app.routes import provider_ingestion_routes as routes

    maker = get_sessionmaker()
    async with maker() as db:
        terminal = await SourceIngestionRunRepository.create(
            db, provider_code="mevzuat", run_type="fetch_and_ingest")
        terminal.discovered_count = 1
        await SourceIngestionRunRepository.mark_running(db, terminal)
        await SourceIngestionRunRepository.finalize(
            db, terminal, status="completed", last_safe_error_code="")
        queued = await SourceIngestionRunRepository.create(
            db, provider_code="mevzuat", run_type="fetch_and_ingest")
        await db.commit()
        with patch("app.services.source_providers.registry.is_enabled", return_value=True), \
             patch("app.routes.provider_ingestion_routes._automatic_live_transport_configured",
                   return_value=True):
            info = await routes._provider_info(db, "mevzuat")
    assert info.status == "available"
    assert info.last_run_status == "queued"
    assert info.last_run_at == queued.created_at.isoformat()
    assert info.last_success_at == terminal.completed_at.isoformat()
    assert info.last_safe_error_code == ""


@pytest.mark.asyncio
async def test_execute_run_uses_persisted_max_items(enabled_all):
    from app.db.source_ingestion_repository import SourceIngestionRunRepository
    from app.services.provider_ingestion_service import execute_run

    provider = SequencedProvider(candidate_count=10)
    seen_limits = []
    original_discover = provider.discover

    async def discover_with_limit(**kw):
        seen_limits.append(kw["limit"])
        return await original_discover(**kw)

    provider.discover = discover_with_limit
    maker = get_sessionmaker()
    with patch("app.services.provider_ingestion_service.registry.get", return_value=provider):
        async with maker() as db:
            run = await SourceIngestionRunRepository.create(
                db,
                provider_code=provider.provider_code,
                run_type="discover_only",
                cursor={"max_items": 7},
            )
            await db.commit()
            summary = await execute_run(db, run.id, transport=make_transport({}), resolver=public_resolver)
    assert summary.discovered == 7
    assert seen_limits == [7]


@pytest.mark.asyncio
async def test_cli_enable_live_semantics_and_transport_closure():
    from app import official_source_ingestion as cli

    class FakeMaker:
        def __call__(self):
            return self

        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_args):
            return None

    class FakeTransport:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    summary = SimpleNamespace(
        run_id="run-1", provider_code="yargitay", run_type="discover_only",
        status="completed", discovered=0, fetched=0, ingested=0,
        duplicate=0, new_version=0, conflict=0, failed=0,
        last_safe_error_code="",
    )
    args = SimpleNamespace(
        enable_live=False, run_id="", provider="yargitay", mode="discover_only",
        query=None, from_date=None, to_date=None, max_items=1,
    )
    transport = FakeTransport()
    with patch("app.official_source_ingestion.get_sessionmaker", return_value=FakeMaker()), \
         patch("app.official_source_ingestion.run_ingestion", new=AsyncMock(return_value=summary)), \
         patch("app.services.source_fetcher.create_real_transport", return_value=transport) as factory:
        assert await cli._run(args) == 0
        assert factory.call_count == 0
    args.enable_live = True
    with patch("app.official_source_ingestion.get_sessionmaker", return_value=FakeMaker()), \
         patch("app.official_source_ingestion.run_ingestion", new=AsyncMock(return_value=summary)), \
         patch("app.services.source_fetcher.create_real_transport", return_value=transport) as factory:
        assert await cli._run(args) == 0
        assert factory.call_count == 1
        assert transport.closed is True
