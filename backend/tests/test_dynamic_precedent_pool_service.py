from types import SimpleNamespace

import pytest

from app.models.case_models import CaseSearchProfileResponse
from app.models.search_models import (
    DynamicPrecedentPoolRequest,
    LegalSearchResponse,
)
from app.services.dynamic_precedent_pool_service import (
    allocate_candidate_budget,
    build_dynamic_precedent_pool,
)
from app.services.provider_ingestion_service import RunSummary
from app.services.source_providers.base import ProviderError


class _ProfileProvider:
    def build(self, request):
        return CaseSearchProfileResponse(
            case_id=request.case_id,
            legal_area="Tüketici Hukuku",
            dispute_type="Ayıplı ikinci el araç",
            party_roles=["Alıcı", "Satıcı"],
            material_facts=["Motor arızası satıştan kısa süre sonra ortaya çıktı."],
            chronology=[],
            claims=["Bedel iadesi"],
            possible_defenses=["Ayıbın kullanıcı hatasından doğduğu savunması"],
            legal_issues=["gizli ayıp", "satıcının ayıptan sorumluluğu"],
            evidence_issues=["bilirkişi incelemesi", "ekspertiz raporu"],
            legislation_hypotheses=["6502 sayılı Kanun", "TBK ayıptan sorumluluk"],
            missing_information=["Satış tarihi"],
            yargitay_queries=[
                "ikinci el araç gizli ayıp motor arızası",
                "ekspertiz raporu ayıplı araç",
                "satıcının ayıptan sorumluluğu",
            ],
            extraction_mode="deterministic_v1",
            confidence=0.85,
        )


def _summary(*, ingested=0, duplicate=0, failed=0, error=""):
    return RunSummary(
        run_id="run-1",
        provider_code="yargitay",
        run_type="fetch_and_ingest",
        status="completed" if not failed else "completed_with_errors",
        discovered=ingested + duplicate + failed,
        fetched=ingested + duplicate,
        ingested=ingested,
        duplicate=duplicate,
        new_version=0,
        conflict=0,
        failed=failed,
        last_safe_error_code=error,
    )


def test_candidate_budget_never_exceeds_hard_cap():
    budgets = allocate_candidate_budget(50, 6)
    assert budgets == [9, 9, 8, 8, 8, 8]
    assert sum(budgets) == 50
    assert all(value >= 1 for value in budgets)


def test_candidate_budget_handles_more_queries_than_candidates():
    budgets = allocate_candidate_budget(3, 6)
    assert budgets == [1, 1, 1]
    assert sum(budgets) == 3


@pytest.mark.asyncio
async def test_dynamic_pool_profiles_ingests_and_shortlists_with_one_total_cap():
    calls = []
    captured_search = []

    async def fake_ingestion(db, **kwargs):
        calls.append(kwargs)
        return _summary(ingested=2)

    async def fake_search(db, request, security_context):
        captured_search.append(request)
        return LegalSearchResponse(total=2, index_version="idx-1")

    request = DynamicPrecedentPoolRequest(
        case_id="case-1",
        case_text="Müvekkil ikinci el araç satın aldı ve kısa süre sonra motor arızası çıktı.",
        max_queries=3,
        max_candidates=50,
        shortlist_size=12,
    )
    result = await build_dynamic_precedent_pool(
        object(),
        request,
        SimpleNamespace(actor_id="user-1", tenant_id="tenant-1"),
        profile_provider=_ProfileProvider(),
        ingestion_runner=fake_ingestion,
        search_executor=fake_search,
        sleeper=lambda _: None,
    )

    assert len(calls) == 3
    assert sum(call["max_items"] for call in calls) == 50
    assert all(call["provider_code"] == "yargitay" for call in calls)
    assert all(call["run_type"] == "fetch_and_ingest" for call in calls)
    assert result.total_ingested == 6
    assert result.provider_status == "completed"
    assert result.candidate_cap == 50
    assert result.shortlist.total == 2

    search_request = captured_search[0]
    assert search_request.case_id == "case-1"
    assert search_request.official_only is True
    assert search_request.source_types == ["supreme_court_decision"]
    assert search_request.court == "Yargıtay"
    assert search_request.limit == 12


@pytest.mark.asyncio
async def test_provider_failure_degrades_to_existing_verified_corpus():
    search_called = False

    async def unavailable_ingestion(db, **kwargs):
        raise ProviderError("transport_unavailable", "provider unavailable")

    async def existing_corpus_search(db, request, security_context):
        nonlocal search_called
        search_called = True
        return LegalSearchResponse(total=4, index_version="existing")

    result = await build_dynamic_precedent_pool(
        object(),
        DynamicPrecedentPoolRequest(
            case_text="İkinci el araç alındıktan sonra gizli motor arızası ortaya çıktı.",
            max_queries=3,
            max_candidates=30,
            shortlist_size=10,
        ),
        SimpleNamespace(actor_id="user-1", tenant_id="tenant-1"),
        profile_provider=_ProfileProvider(),
        ingestion_runner=unavailable_ingestion,
        search_executor=existing_corpus_search,
    )

    assert search_called is True
    assert result.provider_status == "degraded_existing_corpus"
    assert result.total_ingested == 0
    assert result.total_failed == 1
    assert result.ingestion_runs[0].safe_error_code == "transport_unavailable"
    assert result.shortlist.total == 4


@pytest.mark.asyncio
async def test_provider_wide_stop_code_halts_remaining_queries():
    calls = 0

    async def challenged_ingestion(db, **kwargs):
        nonlocal calls
        calls += 1
        return _summary(failed=1, error="challenge_detected")

    async def empty_search(db, request, security_context):
        return LegalSearchResponse(total=0, index_version="idx")

    result = await build_dynamic_precedent_pool(
        object(),
        DynamicPrecedentPoolRequest(
            case_text="İkinci el araç satışında ekspertize rağmen motor arızası çıktı.",
            max_queries=6,
            max_candidates=50,
        ),
        SimpleNamespace(actor_id="user-1", tenant_id="tenant-1"),
        profile_provider=_ProfileProvider(),
        ingestion_runner=challenged_ingestion,
        search_executor=empty_search,
    )

    assert calls == 1
    assert len(result.ingestion_runs) == 1
    assert result.provider_status == "degraded_existing_corpus"
