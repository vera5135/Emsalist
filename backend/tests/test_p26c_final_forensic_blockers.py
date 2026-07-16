"""Focused offline regressions for the four final P2.6C forensic blockers."""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
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
from app.db.source_ingestion_repository import SourceIngestionRunRepository
from app.models.provider_models import CreateRunRequest
from app.official_source_ingestion_smoke import (
    HARNESS_VERSION,
    SmokeExecutionReport,
    render_evidence_document,
)
from app.services.provider_ingestion_service import (
    ERR_PERSISTED_QUERY_NOT_SUPPORTED,
    _fetch_parse_ingest,
    execute_run,
    run_ingestion,
)
from app.services.source_extraction import EXTRACTION_METHOD_PROVIDER_HTML
from app.services.source_fetcher import FetchResult
from app.services.source_ingestion_service import (
    NEEDS_REVIEW,
    OUTCOME_DUPLICATE,
    OUTCOME_DUPLICATE_VERIFIED,
    VERIFIED_OFFICIAL,
    get_version_official_evidence,
    ingest_editor_candidate,
    ingest_official_fetch,
    resolve_version_verification_status,
)
from app.services.source_providers import registry
from app.services.source_providers.base import (
    ProviderCapabilities,
    ProviderDiscoveryCandidate,
    ProviderDiscoveryPage,
    ProviderError,
    ProviderRequestPolicy,
)

SENTINEL = "PRIVATE_CASE_QUERY_SENTINEL_98231"
EXTRACTION_VERSION = "p2.6c-extract-1"
OFFICIAL_URL = "https://www.mevzuat.gov.tr/forensic/9911"
LEGACY_TEXT = "Madde 1\nBu kontrollü hukuki metin aynı içerik özeti için yeterince uzundur."
LEGACY_META = {
    "source_type": "legislation",
    "title": "9911 Sayılı Test Kanunu",
    "issuing_authority": "TBMM",
    "number": "9911",
    "publication_date": "2026-07-14",
}
ISSUE_BYTES = (
    "<html><body><h1>Resmî Gazete</h1><main>"
    "Sayı: 32345 Tarih: 12.07.2026\n"
    "Bu sayıda yayımlanan düzenlemeler ve kararlar listelenmiştir. "
    "6098 sayılı Türk Borçlar Kanunu hakkında bir atıf da vardır."
    "</main></body></html>"
).encode()
REGULATION_BYTES = (
    "<html><body><h1>Örnek Yönetmelik</h1><main>"
    "Mevzuat No: 456 Tarih: 12.07.2026\n"
    "Madde 1\nBu yönetmeliğin amacı ve kapsamı belirlenmiştir."
    "</main></body></html>"
).encode()


class StubResponse:
    def __init__(self, content: bytes):
        self.status_code = 200
        self.headers = {"content-type": "text/html"}
        self.content = content
        self.location = None


async def _no_sleep(_seconds: float) -> None:
    return None


def _public_resolver(_host: str) -> list[str]:
    return ["93.184.216.34"]


@pytest_asyncio.fixture(autouse=True)
async def clean_source_tables():
    maker = get_sessionmaker()

    async def clean(db):
        await db.execute(delete(SourceUsage))
        await db.execute(delete(SourceParagraph))
        await db.execute(delete(SourceVerification))
        await db.execute(delete(SourceRelationship))
        await db.execute(delete(SourceVersion))
        await db.execute(delete(SourceRecord))
        await db.execute(delete(SourceIngestionItem))
        await db.execute(delete(SourceIngestionRun))

    async with maker() as db:
        await clean(db)
        await db.commit()
    yield
    async with maker() as db:
        await clean(db)
        await db.commit()


def _gazette_candidate(*, source_type: str, kind: str, external_id: str):
    return ProviderDiscoveryCandidate(
        provider_code="resmi_gazete",
        source_type=source_type,
        detail_url="https://resmigazete.gov.tr/eskiler/forensic.htm",
        external_id=external_id,
        discovered_metadata={"kind": kind, "instrument_type": "yonetmelik"},
    )


async def _parse_gazette(content: bytes, candidate):
    provider = registry.get_definition("resmi_gazete")
    return await provider.parse(
        candidate,
        FetchResult(
            final_url=candidate.detail_url,
            status_code=200,
            content=content,
            content_type="text/html",
        ),
    )


async def _ingest_gazette_twice(content: bytes, first, second):
    provider = registry.get_definition("resmi_gazete")
    maker = get_sessionmaker()
    transport = lambda _url: StubResponse(content)
    async with maker() as db:
        first_result = await _fetch_parse_ingest(
            db, provider, first, transport=transport,
            resolver=_public_resolver, sleeper=_no_sleep,
        )
        await db.commit()
        second_result = await _fetch_parse_ingest(
            db, provider, second, transport=transport,
            resolver=_public_resolver, sleeper=_no_sleep,
        )
        await db.commit()
        records = (await db.execute(select(SourceRecord))).scalars().all()
        versions = (await db.execute(select(SourceVersion))).scalars().all()
    return first_result, second_result, records, versions


@pytest.mark.asyncio
async def test_gazette_issue_identity_ignores_hostile_candidate_instrument_metadata():
    parsed = await _parse_gazette(
        ISSUE_BYTES,
        _gazette_candidate(
            source_type="regulation", kind="published_instrument", external_id="FAKE-999"
        ),
    )
    assert (parsed.source_type, parsed.number) == ("official_gazette_issue", "32345")


@pytest.mark.asyncio
async def test_gazette_instrument_identity_ignores_hostile_candidate_issue_metadata():
    parsed = await _parse_gazette(
        REGULATION_BYTES,
        _gazette_candidate(
            source_type="official_gazette_issue", kind="gazette_issue", external_id="ATTACK"
        ),
    )
    assert (parsed.source_type, parsed.number) == ("regulation", "456")


@pytest.mark.asyncio
async def test_same_exact_issue_bytes_cannot_create_two_canonical_source_types():
    honest = _gazette_candidate(
        source_type="official_gazette_issue", kind="gazette_issue", external_id="32345"
    )
    hostile = _gazette_candidate(
        source_type="regulation", kind="published_instrument", external_id="ATTACKER_HINT"
    )
    first, second, records, versions = await _ingest_gazette_twice(ISSUE_BYTES, honest, hostile)
    assert first.canonical_key == second.canonical_key
    assert second.outcome in (OUTCOME_DUPLICATE, OUTCOME_DUPLICATE_VERIFIED)
    assert [(row.source_type, row.id) for row in records] == [("official_gazette_issue", records[0].id)]
    assert len(versions) == 1


@pytest.mark.asyncio
async def test_same_exact_instrument_bytes_cannot_create_two_canonical_source_types():
    honest = _gazette_candidate(
        source_type="regulation", kind="published_instrument", external_id="456"
    )
    hostile = _gazette_candidate(
        source_type="official_gazette_issue", kind="gazette_issue", external_id="ATTACKER_HINT"
    )
    first, second, records, versions = await _ingest_gazette_twice(
        REGULATION_BYTES, honest, hostile
    )
    assert first.canonical_key == second.canonical_key
    assert records[0].source_type == "regulation"
    assert len(records) == len(versions) == 1


@pytest.mark.asyncio
async def test_candidate_external_id_cannot_become_canonical_issue_number_fallback():
    without_number = ISSUE_BYTES.replace("Sayı: 32345 ".encode(), b"")
    with pytest.raises(ProviderError) as caught:
        await _parse_gazette(
            without_number,
            _gazette_candidate(
                source_type="official_gazette_issue", kind="gazette_issue", external_id="FAKE-999"
            ),
        )
    assert caught.value.code == "manual_review_required"


@pytest.mark.asyncio
async def test_ambiguous_gazette_bytes_fail_closed():
    ambiguous = (
        b"<html><body><h1>Duyuru</h1><main>Uzun ve belirsiz resmi metin "
        b"govdesi siniflandirma icin yeterli uzunluktadir.</main></body></html>"
    )
    with pytest.raises(ProviderError) as caught:
        await _parse_gazette(
            ambiguous,
            _gazette_candidate(source_type="regulation", kind="published_instrument", external_id="456"),
        )
    assert caught.value.code == "manual_review_required"


@pytest.mark.asyncio
async def test_body_citation_does_not_select_gazette_instrument_type():
    citation = (
        "<html><body><h1>Kurul Duyurusu</h1><main>"
        "Bu metin 6098 sayılı Türk Borçlar Kanunu ile başka mevzuata atıf yapar."
        "</main></body></html>"
    ).encode()
    with pytest.raises(ProviderError) as caught:
        await _parse_gazette(
            citation,
            _gazette_candidate(source_type="legislation", kind="published_instrument", external_id="6098"),
        )
    assert caught.value.code == "manual_review_required"


def _extracted_fetch() -> tuple[FetchResult, str]:
    raw_hash = hashlib.sha256(b"forensic raw provider document").hexdigest()
    return (
        FetchResult(
            final_url=OFFICIAL_URL,
            status_code=200,
            content=LEGACY_TEXT.encode(),
            content_type="text/plain",
        ),
        raw_hash,
    )


async def _legacy_extraction_attack():
    maker = get_sessionmaker()
    async with maker() as db:
        created = await ingest_editor_candidate(db, metadata=LEGACY_META, raw_text=LEGACY_TEXT)
        await db.commit()
        version_before = await db.get(SourceVersion, created.source_version_id)
        provenance_before = (
            version_before.raw_document_hash,
            version_before.parser_version,
            dict(version_before.metadata_json),
        )
        paragraph_ids_before = tuple((await db.execute(
            select(SourceParagraph.id).where(
                SourceParagraph.source_version_id == created.source_version_id
            ).order_by(SourceParagraph.paragraph_index)
        )).scalars())
        fetch, raw_hash = _extracted_fetch()
        result = await ingest_official_fetch(
            db,
            metadata=LEGACY_META,
            fetch_result=fetch,
            raw_document_hash=raw_hash,
            extraction_method=EXTRACTION_METHOD_PROVIDER_HTML,
            extraction_version=EXTRACTION_VERSION,
        )
        await db.commit()
        version_after = await db.get(SourceVersion, created.source_version_id)
        evidence = await get_version_official_evidence(
            db, created.source_record_id, created.source_version_id
        )
        effective = await resolve_version_verification_status(
            db,
            created.source_record_id,
            created.source_version_id,
            (await db.get(SourceRecord, created.source_record_id)).verification_status,
        )
        paragraph_ids_after = tuple((await db.execute(
            select(SourceParagraph.id).where(
                SourceParagraph.source_version_id == created.source_version_id
            ).order_by(SourceParagraph.paragraph_index)
        )).scalars())
        version_count = await db.scalar(select(func.count()).select_from(SourceVersion))
        verification_count = await db.scalar(select(func.count()).select_from(SourceVerification))
        provenance_after = (
            version_after.raw_document_hash,
            version_after.parser_version,
            dict(version_after.metadata_json),
        )
    return SimpleNamespace(
        result=result,
        evidence=evidence,
        effective=effective,
        version_count=version_count,
        verification_count=verification_count,
        provenance_before=provenance_before,
        provenance_after=provenance_after,
        paragraph_ids_before=paragraph_ids_before,
        paragraph_ids_after=paragraph_ids_after,
    )


@pytest.mark.asyncio
async def test_legacy_same_hash_incoming_extraction_cannot_create_official_evidence():
    attack = await _legacy_extraction_attack()
    assert attack.evidence.valid is False
    assert attack.verification_count == 0


@pytest.mark.asyncio
async def test_legacy_same_hash_extraction_bypass_is_closed_through_ingest_official_fetch():
    attack = await _legacy_extraction_attack()
    assert attack.result.outcome == OUTCOME_DUPLICATE
    assert attack.version_count == 1
    assert attack.effective == NEEDS_REVIEW


@pytest.mark.asyncio
async def test_valid_extraction_provenanced_same_hash_version_can_be_reverified():
    maker = get_sessionmaker()
    fetch, raw_hash = _extracted_fetch()
    async with maker() as db:
        created = await ingest_official_fetch(
            db, metadata=LEGACY_META, fetch_result=fetch,
            raw_document_hash=raw_hash,
            extraction_method=EXTRACTION_METHOD_PROVIDER_HTML,
            extraction_version=EXTRACTION_VERSION,
        )
        await db.commit()
        paragraph_ids = tuple((await db.execute(
            select(SourceParagraph.id).where(SourceParagraph.source_version_id == created.source_version_id)
        )).scalars())
        await db.execute(delete(SourceVerification).where(
            SourceVerification.source_record_id == created.source_record_id
        ))
        record = await db.get(SourceRecord, created.source_record_id)
        record.verification_status = NEEDS_REVIEW
        await db.commit()
        repeated = await ingest_official_fetch(
            db, metadata=LEGACY_META, fetch_result=fetch,
            raw_document_hash=raw_hash,
            extraction_method=EXTRACTION_METHOD_PROVIDER_HTML,
            extraction_version=EXTRACTION_VERSION,
        )
        await db.commit()
        evidence = await get_version_official_evidence(db, created.source_record_id, created.source_version_id)
        effective = await resolve_version_verification_status(
            db, created.source_record_id, created.source_version_id, record.verification_status
        )
        paragraph_ids_after = tuple((await db.execute(
            select(SourceParagraph.id).where(SourceParagraph.source_version_id == created.source_version_id)
        )).scalars())
    assert repeated.outcome == OUTCOME_DUPLICATE_VERIFIED
    assert repeated.source_version_id == created.source_version_id
    assert evidence.valid and effective == VERIFIED_OFFICIAL
    assert paragraph_ids_after == paragraph_ids


@pytest.mark.asyncio
async def test_direct_non_extracted_exact_byte_same_hash_behavior_remains_verified():
    maker = get_sessionmaker()
    async with maker() as db:
        created = await ingest_editor_candidate(db, metadata=LEGACY_META, raw_text=LEGACY_TEXT)
        await db.commit()
        result = await ingest_official_fetch(
            db,
            metadata=LEGACY_META,
            fetch_result=FetchResult(
                final_url=OFFICIAL_URL, status_code=200,
                content=LEGACY_TEXT.encode(), content_type="text/plain",
            ),
        )
        await db.commit()
        evidence = await get_version_official_evidence(db, created.source_record_id, created.source_version_id)
    assert result.outcome == OUTCOME_DUPLICATE_VERIFIED
    assert result.source_version_id == created.source_version_id
    assert evidence.valid


@pytest.mark.asyncio
async def test_same_hash_fail_closed_branch_does_not_mutate_version_provenance():
    attack = await _legacy_extraction_attack()
    assert attack.provenance_after == attack.provenance_before


@pytest.mark.asyncio
async def test_same_hash_fail_closed_branch_does_not_rewrite_paragraphs():
    attack = await _legacy_extraction_attack()
    assert attack.paragraph_ids_after == attack.paragraph_ids_before


def _rendered_smoke_evidence() -> str:
    return render_evidence_document(SmokeExecutionReport(
        executed_at_utc="2026-07-13T20:16:52.381881+00:00",
        git_sha="40611aa26ee086407912675cde58d3e89b0c626c",
        harness_version=HARNESS_VERSION,
        environment_guard_enabled=True,
        providers=(),
    ))


def test_smoke_renderer_assigns_uyusmazlik_to_p26d():
    rendered = _rendered_smoke_evidence()
    assert "Uyuşmazlık browser/current-surface discovery validation remains deferred to P2.6D" in rendered


def test_smoke_renderer_no_longer_emits_old_ownerless_wording():
    rendered = _rendered_smoke_evidence()
    assert "Yargıtay, Danıştay and AYM browser discovery remains deferred" not in rendered
    assert "Uyuşmazlık was also excluded" not in rendered


def test_api_create_run_request_rejects_query():
    with pytest.raises(ValidationError):
        CreateRunRequest.model_validate({"run_type": "discover_only", "query": SENTINEL})


def _jwt_token(role: str) -> str:
    from app.services.auth_service import create_access_token
    return create_access_token(f"u-{role}", "prov-tenant", role, f"s-{role}")


@pytest_asyncio.fixture(autouse=True)
async def _seed_jwt_auth_for_p26c():
    from app.db.models import AuthSession, Tenant, User
    from datetime import UTC, datetime, timedelta
    from hashlib import sha256
    from app.db.session import get_sessionmaker
    maker = get_sessionmaker()
    async with maker() as session:
        t = await session.get(Tenant, "prov-tenant")
        if not t:
            session.add(Tenant(id="prov-tenant", name="Provider Tenant", slug="prov-tenant", status="active"))
        for role in ("lawyer", "tenant_admin", "editor", "admin"):
            uid = f"u-{role}"
            sid = f"s-{role}"
            u = await session.get(User, uid)
            if not u:
                session.add(User(id=uid, tenant_id="prov-tenant", email_normalized=f"{uid}@test",
                                 display_name=role, status="active", role=role, token_version=0))
            s = await session.get(AuthSession, sid)
            if not s:
                now = datetime.now(UTC)
                session.add(AuthSession(id=sid, tenant_id="prov-tenant", user_id=uid,
                    refresh_token_hash=sha256(f"rt-{sid}".encode()).hexdigest(),
                    token_family_id=f"tf-{sid}", created_at=now, last_used_at=now,
                    expires_at=now + timedelta(days=7)))
        await session.commit()
    yield


@pytest.mark.asyncio
async def test_rejected_api_query_creates_no_run_row():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch("app.services.auth_service.get_auth_mode", return_value="jwt"), patch(
            "app.routes.source_routes.get_auth_mode", return_value="jwt"
        ):
            response = await client.post(
                "/api/v1/official-source-providers/yargitay/runs",
                headers={"Authorization": f"Bearer {_jwt_token('editor')}"},
                json={"run_type": "discover_only", "query": SENTINEL},
            )
    maker = get_sessionmaker()
    async with maker() as db:
        count = await db.scalar(select(func.count()).select_from(SourceIngestionRun))
    assert response.status_code == 422
    assert count == 0
    assert SENTINEL not in response.text


def _direct_query_provider():
    discover = AsyncMock(return_value=ProviderDiscoveryPage(candidates=[
        ProviderDiscoveryCandidate(
            provider_code="yargitay",
            source_type="supreme_court_decision",
            detail_url="https://karararama.yargitay.gov.tr/karar/SAFE-1",
            external_id="SAFE-1",
        )
    ]))
    return SimpleNamespace(
        provider_code="yargitay",
        capabilities=ProviderCapabilities(discovery=True, fetch=True, parse=True),
        request_policy=ProviderRequestPolicy(min_interval_seconds=0),
        discover=discover,
        default_resolver=lambda: _public_resolver,
    )


async def _run_direct_query():
    provider = _direct_query_provider()
    metric_calls = []
    maker = get_sessionmaker()
    capture = lambda *args, **kwargs: metric_calls.append((args, kwargs))
    with patch("app.services.provider_ingestion_service.registry.get", return_value=provider), patch.object(
        metrics.official_source_provider_discovered, "inc", side_effect=capture
    ), patch.object(
        metrics.official_source_provider_run_total, "inc", side_effect=capture
    ), patch.object(
        metrics.official_source_provider_run_duration, "observe", side_effect=capture
    ):
        async with maker() as db:
            summary = await run_ingestion(
                db,
                provider_code="yargitay",
                run_type="discover_only",
                query=SENTINEL,
                max_items=1,
                transport=Mock(),
                resolver=_public_resolver,
                sleeper=_no_sleep,
            )
            run = await db.get(SourceIngestionRun, summary.run_id)
            items = (await db.execute(select(SourceIngestionItem))).scalars().all()
    return provider, summary, run, items, metric_calls


@pytest.mark.asyncio
async def test_direct_run_query_reaches_provider_in_memory():
    provider, _, _, _, _ = await _run_direct_query()
    assert provider.discover.await_args.kwargs["query"] == SENTINEL


@pytest.mark.asyncio
async def test_direct_run_query_is_absent_from_cursor_json():
    _, _, run, _, _ = await _run_direct_query()
    assert "query" not in run.cursor_json
    assert SENTINEL not in json.dumps(run.cursor_json)


@pytest.mark.asyncio
async def test_direct_run_query_is_absent_from_run_and_item_persistence():
    _, summary, run, items, metric_calls = await _run_direct_query()
    persisted = json.dumps({
        "run": run.cursor_json,
        "summary": summary.__dict__,
        "items": [
            {
                "external_id": item.external_id,
                "candidate_url_hash": item.candidate_url_hash,
                "dedupe_key": item.dedupe_key,
                "safe_error_code": item.safe_error_code,
            }
            for item in items
        ],
    })
    assert SENTINEL not in persisted
    assert SENTINEL not in repr(metric_calls)
    assert SENTINEL not in _rendered_smoke_evidence()


@pytest.mark.asyncio
async def test_direct_run_query_is_absent_from_captured_logs(caplog):
    await _run_direct_query()
    assert SENTINEL not in caplog.text


async def _execute_forged_query():
    provider = _direct_query_provider()
    transport = Mock()
    maker = get_sessionmaker()
    async with maker() as db:
        run = await SourceIngestionRunRepository.create(
            db,
            provider_code="yargitay",
            run_type="discover_only",
            cursor={"query": SENTINEL, "max_items": 1},
        )
        await db.commit()
        with patch("app.services.provider_ingestion_service.registry.get", return_value=provider):
            summary = await execute_run(
                db, run.id, transport=transport,
                resolver=_public_resolver, sleeper=_no_sleep,
            )
    return provider, transport, summary


@pytest.mark.asyncio
async def test_forged_persisted_queued_query_never_reaches_provider_discover():
    provider, _, _ = await _execute_forged_query()
    provider.discover.assert_not_awaited()


@pytest.mark.asyncio
async def test_forged_persisted_queued_query_never_reaches_transport():
    _, transport, _ = await _execute_forged_query()
    transport.assert_not_called()


@pytest.mark.asyncio
async def test_forged_persisted_queued_query_fails_with_controlled_safe_code(caplog):
    _, _, summary = await _execute_forged_query()
    assert summary.status == "failed"
    assert summary.last_safe_error_code == ERR_PERSISTED_QUERY_NOT_SUPPORTED
    assert SENTINEL not in caplog.text
    assert SENTINEL not in json.dumps(summary.__dict__)


def test_openapi_create_run_request_has_no_query_property():
    from app.main import app

    app.openapi_schema = None
    schema = app.openapi()
    properties = schema["components"]["schemas"]["CreateRunRequest"]["properties"]
    assert "query" not in properties
    assert {"run_type", "from_date", "to_date", "max_items", "external_id"} <= set(properties)
