"""P2 Core — bounded case-profile, official ingestion and shortlist orchestration."""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case_models import CaseSearchProfileRequest, CaseSearchProfileResponse
from app.models.search_models import (
    DynamicPrecedentIngestionRun,
    DynamicPrecedentPoolRequest,
    DynamicPrecedentPoolResponse,
    LegalSearchRequest,
    LegalSearchResponse,
)
from app.services.case_search_profile import case_search_profile_provider
from app.services.hybrid_search_service import execute_legal_search
from app.services.provider_ingestion_service import RunSummary, run_ingestion
from app.services.source_providers.base import ProviderError

_PROVIDER_CODE = "yargitay"
_STOP_ERROR_CODES = frozenset({
    "challenge_detected",
    "rate_limited",
    "access_denied",
    "structure_changed",
    "transport_unavailable",
})


IngestionRunner = Callable[..., Awaitable[RunSummary]]
SearchExecutor = Callable[..., Awaitable[LegalSearchResponse]]


def allocate_candidate_budget(total: int, query_count: int) -> list[int]:
    """Distribute one hard total cap across provider queries without overrun."""
    bounded_total = max(1, min(int(total), 50))
    bounded_queries = max(1, min(int(query_count), 6, bounded_total))
    base, remainder = divmod(bounded_total, bounded_queries)
    return [base + (1 if index < remainder else 0) for index in range(bounded_queries)]


def _build_search_query(profile: CaseSearchProfileResponse) -> str:
    """Create a broad OR query for P2.7 from safe structured profile output."""
    clauses: list[str] = []
    seen: set[str] = set()
    for value in (
        *profile.legal_issues[:6],
        *profile.evidence_issues[:4],
        *profile.claims[:3],
    ):
        for token in str(value).replace("/", " ").split():
            cleaned = token.strip(".,;:()[]{}\"'")
            key = cleaned.casefold()
            if len(cleaned) >= 3 and key not in seen:
                seen.add(key)
                clauses.append(cleaned)
    if not clauses:
        clauses.extend(profile.yargitay_queries[0].split())
    return " ".join(clauses)[:2000]


def _run_contract(query: str, budget: int, summary: RunSummary) -> DynamicPrecedentIngestionRun:
    return DynamicPrecedentIngestionRun(
        query=query,
        budget=budget,
        status=summary.status,
        discovered=summary.discovered,
        fetched=summary.fetched,
        ingested=summary.ingested,
        duplicate=summary.duplicate,
        new_version=summary.new_version,
        conflict=summary.conflict,
        failed=summary.failed,
        safe_error_code=summary.last_safe_error_code,
    )


async def build_dynamic_precedent_pool(
    db: AsyncSession,
    request: DynamicPrecedentPoolRequest,
    security_context,
    *,
    profile_provider=case_search_profile_provider,
    ingestion_runner: IngestionRunner = run_ingestion,
    search_executor: SearchExecutor = execute_legal_search,
    transport=None,
    sleeper=None,
) -> DynamicPrecedentPoolResponse:
    """Build a bounded dynamic pool and return the closest official precedents.

    The raw narrative is transient. Only the existing ingestion/search services
    may persist canonical source metadata, exact source text and safe query
    summaries. Provider failure degrades to searching the already verified corpus.
    """
    profile = profile_provider.build(
        CaseSearchProfileRequest(
            case_id=request.case_id,
            case_text=request.case_text,
            preferred_relief=request.preferred_relief,
            max_queries=request.max_queries,
        )
    )

    queries = profile.yargitay_queries[: request.max_queries]
    budgets = allocate_candidate_budget(request.max_candidates, len(queries))
    runs: list[DynamicPrecedentIngestionRun] = []
    provider_error = False

    for query, budget in zip(queries, budgets):
        try:
            summary = await ingestion_runner(
                db,
                provider_code=_PROVIDER_CODE,
                run_type="fetch_and_ingest",
                query=query,
                max_items=budget,
                transport=transport,
                created_by=getattr(security_context, "actor_id", None),
                sleeper=sleeper,
            )
        except ProviderError as exc:
            provider_error = True
            runs.append(
                DynamicPrecedentIngestionRun(
                    query=query,
                    budget=budget,
                    status="failed",
                    failed=1,
                    safe_error_code=exc.code,
                )
            )
            break

        run = _run_contract(query, budget, summary)
        runs.append(run)
        if run.safe_error_code in _STOP_ERROR_CODES:
            provider_error = True
            break

    shortlist = await search_executor(
        db,
        LegalSearchRequest(
            query=_build_search_query(profile),
            case_id=request.case_id,
            official_only=True,
            source_types=["supreme_court_decision"],
            court="Yargıtay",
            limit=request.shortlist_size,
        ),
        security_context,
    )

    total_discovered = sum(item.discovered for item in runs)
    total_ingested = sum(item.ingested for item in runs)
    total_duplicate = sum(item.duplicate for item in runs)
    total_failed = sum(item.failed for item in runs)

    if provider_error and total_ingested == 0:
        provider_status = "degraded_existing_corpus"
    elif provider_error or total_failed:
        provider_status = "completed_with_errors"
    else:
        provider_status = "completed"

    return DynamicPrecedentPoolResponse(
        profile=profile,
        provider_status=provider_status,
        candidate_cap=request.max_candidates,
        ingestion_runs=runs,
        total_discovered=total_discovered,
        total_ingested=total_ingested,
        total_duplicate=total_duplicate,
        total_failed=total_failed,
        shortlist=shortlist,
    )
