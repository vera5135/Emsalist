from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.models import Base, Case, SourceParagraph, SourceRecord, SourceVersion, Tenant, User
from app.models.case_models import CaseSearchProfileResponse
from app.models.search_models import (
    AnalyzePrecedentPoolRequest,
    DynamicPrecedentIngestionRun,
    DynamicPrecedentPoolRequest,
    LegalSearchResult,
)
from app.services.precedent_pool_service import (
    analyze_pool,
    complete_pool,
    get_pool,
    list_pool_decisions,
    query_strategy_summary,
    start_pool,
)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as db:
        tenant = Tenant(id="t-pool", name="Tenant", slug="t-pool", status="active")
        other = Tenant(id="t-other", name="Other", slug="t-other", status="active")
        user = User(id="u-pool", tenant_id=tenant.id, email_normalized="u@test", status="active", role="lawyer")
        case = Case(id="c-pool", tenant_id=tenant.id, owner_user_id=user.id, title="Ayipli arac", status="active")
        record = SourceRecord(
            id="sr-pool",
            source_type="supreme_court_decision",
            canonical_key="yargitay:13hd:2022/1:2023/2",
            title="Yargitay 13. HD E. 2022/1 K. 2023/2",
            court="Yargitay",
            chamber="13. Hukuk Dairesi",
            case_number="2022/1",
            decision_number="2023/2",
            decision_date="2023-01-10",
            official_url="https://karararama.yargitay.gov.tr/getDokuman?id=1",
            verification_status="verified_official",
            temporal_status="current",
        )
        version = SourceVersion(
            id="sv-pool",
            source_record_id=record.id,
            content_hash="hash-v1",
            normalized_text="Davaci ayipli arac nedeniyle bedel iadesi talep etti. Mahkemece kabul edildi. Yargitay ayip ve ispat degerlendirmesi yapti, karar bozuldu.",
            retrieval_method="official_fetch",
            parser_version="test",
        )
        record.current_version_id = version.id
        paragraph = SourceParagraph(
            id="sp-pool",
            source_version_id=version.id,
            paragraph_index=1,
            text=version.normalized_text,
            text_hash="p-hash",
        )
        db.add_all([tenant, other, user, case, record, version, paragraph])
        await db.commit()
        yield db
    await engine.dispose()


def _profile() -> CaseSearchProfileResponse:
    return CaseSearchProfileResponse(
        case_id="c-pool",
        legal_area="Tuketici Hukuku",
        dispute_type="Ayipli ikinci el arac",
        party_roles=["Alici", "Satici"],
        material_facts=["Motor arizasi"],
        chronology=[],
        claims=["Bedel iadesi"],
        possible_defenses=["Kullanim hatasi"],
        legal_issues=["Gizli ayip", "Ispat"],
        evidence_issues=["Bilirkisi raporu"],
        legislation_hypotheses=["TBK 219"],
        missing_information=["Ihbar tarihi"],
        yargitay_queries=[
            "ikinci el arac gizli ayip",
            "arac satisi ayip ispat",
            "tuketici ayipli mal arac",
        ],
        extraction_mode="deterministic_v1",
        confidence=0.8,
    )


@pytest.mark.asyncio
async def test_pool_persistence_is_idempotent_and_binds_exact_source_version(session):
    ctx = SimpleNamespace(tenant_id="t-pool", actor_id="u-pool", role="lawyer")
    request = DynamicPrecedentPoolRequest(
        case_id="c-pool",
        case_text="Ikinci el arac satisindan sonra gizli ayip ortaya cikti.",
        max_queries=3,
        max_candidates=30,
        shortlist_size=8,
    )
    queries = _profile().yargitay_queries
    strategies = query_strategy_summary(queries, [10, 10, 10])
    assert all("query_hash" in item and "ikinci" not in str(item) for item in strategies)

    pool = await start_pool(session, ctx=ctx, request=request, profile=_profile(), queries=queries, budgets=[10, 10, 10])
    await session.commit()
    rerun = await start_pool(session, ctx=ctx, request=request, profile=_profile(), queries=queries, budgets=[10, 10, 10])
    assert rerun.id == pool.id

    await complete_pool(
        session,
        pool=rerun,
        ctx=ctx,
        provider_status="completed",
        runs=[DynamicPrecedentIngestionRun(run_id="run-1", query=queries[0], budget=10, status="completed", discovered=1, ingested=1)],
        shortlist=[
            LegalSearchResult(
                result_id="signed",
                source_id="sr-pool",
                source_version_id="sv-pool",
                source_paragraph_id="sp-pool",
                final_score=0.91,
                match_reasons=["Gizli ayip eslesti"],
            )
        ],
    )
    await session.commit()

    decisions = await list_pool_decisions(session, ctx, pool.id)
    assert len(decisions) == 1
    assert decisions[0].source_record_id == "sr-pool"
    assert decisions[0].source_version_id == "sv-pool"
    assert decisions[0].selected_source_paragraph_ids == ["sp-pool"]
    assert decisions[0].scores["final_score"] == 0.91


@pytest.mark.asyncio
async def test_pool_access_is_tenant_scoped(session):
    ctx = SimpleNamespace(tenant_id="t-pool", actor_id="u-pool", role="lawyer")
    request = DynamicPrecedentPoolRequest(case_id="c-pool", case_text="Ikinci el arac satisinda ayip iddiasi vardir.")
    pool = await start_pool(session, ctx=ctx, request=request, profile=_profile(), queries=_profile().yargitay_queries, budgets=[10, 10, 10])
    await session.commit()

    with pytest.raises(Exception):
        await get_pool(session, SimpleNamespace(tenant_id="t-other", actor_id="u-pool", role="lawyer"), pool.id)


@pytest.mark.asyncio
async def test_analysis_requires_source_provenance_and_rejects_hidden_reasoning(session):
    ctx = SimpleNamespace(tenant_id="t-pool", actor_id="u-pool", role="lawyer")
    request = DynamicPrecedentPoolRequest(case_id="c-pool", case_text="Ikinci el arac satisinda gizli ayip ve ispat sorunu vardir.")
    pool = await start_pool(session, ctx=ctx, request=request, profile=_profile(), queries=_profile().yargitay_queries, budgets=[10, 10, 10])
    await complete_pool(
        session,
        pool=pool,
        ctx=ctx,
        provider_status="completed",
        runs=[],
        shortlist=[LegalSearchResult(result_id="signed", source_id="sr-pool", source_version_id="sv-pool", source_paragraph_id="sp-pool")],
    )
    await session.commit()

    analyses = await analyze_pool(session, ctx, pool.id, AnalyzePrecedentPoolRequest())
    assert analyses[0].source_fingerprint == "hash-v1"
    assert analyses[0].provenance[0]["source_record_id"] == "sr-pool"
    assert analyses[0].provenance[0]["source_version_id"] == "sv-pool"
    assert analyses[0].provenance[0]["source_paragraph_id"] == "sp-pool"
    quote = analyses[0].analysis["relevant_paragraphs"][0]["text"]
    assert quote in "Davaci ayipli arac nedeniyle bedel iadesi talep etti. Mahkemece kabul edildi. Yargitay ayip ve ispat degerlendirmesi yapti, karar bozuldu."

    class HiddenProvider:
        provider = "test"
        model_version = "test"
        prompt_version = "test"
        schema_version = "test"

        def analyze(self, **kwargs):
            return {"chain_of_thought": "not allowed", "relevant_paragraphs": []}, []

    with pytest.raises(ValueError):
        await analyze_pool(session, ctx, pool.id, AnalyzePrecedentPoolRequest(force=True), provider=HiddenProvider())
