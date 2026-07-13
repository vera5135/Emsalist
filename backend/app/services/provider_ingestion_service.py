"""P2.6C — Official provider ingestion orchestration.

This is the ONLY place that turns provider output into canonical sources, and it
does so exclusively through the P2.6 ``ingest_official_fetch`` path:

    provider.discover  → ProviderDiscoveryCandidate (UNTRUSTED)
    provider.fetch     → FetchResult via SSRF-validated source_fetcher
    provider.parse     → ParsedOfficialSource (canonical fields only)
    quality gate       → reject empty / UI-only bodies
    ingest_official_fetch(fetch_result)  → P2.6 trust from exact fetched bytes

Provider code never writes SourceRecord/SourceVersion/SourceVerification and
never sets verification_status. Trust is derived solely from the fetched bytes
by the P2.6 engine.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.db.source_ingestion_repository import (
    RUN_COMPLETED,
    RUN_COMPLETED_WITH_ERRORS,
    RUN_FAILED,
    SourceIngestionItemRepository,
    SourceIngestionRunRepository,
)
from app.services.source_canonical_key import CanonicalKeyError
from app.services.source_extraction import extract_content_from_fetch, make_extracted_fetch_result
from app.services.source_ingestion_service import ingest_official_fetch
from app.services.source_providers import registry
from app.services.source_providers.base import (
    ERR_ACCESS_DENIED,
    ERR_CHALLENGE,
    ERR_RATE_LIMITED,
    ERR_STRUCTURE_CHANGED,
    ERR_TRANSPORT_UNAVAILABLE,
    RUN_DISCOVER_ONLY,
    RUN_EXACT_SOURCE,
    RUN_MODES,
    ParsedOfficialSource,
    ProviderDiscoveryCandidate,
    ProviderError,
)
from app.services.source_providers.shared import assert_meaningful_body

_PROVIDER_WIDE_STOP_CODES = frozenset({
    ERR_CHALLENGE,
    ERR_STRUCTURE_CHANGED,
    ERR_TRANSPORT_UNAVAILABLE,
    ERR_ACCESS_DENIED,
    ERR_RATE_LIMITED,
})


@dataclass
class RunSummary:
    run_id: str
    provider_code: str
    run_type: str
    status: str
    discovered: int
    fetched: int
    ingested: int
    duplicate: int
    new_version: int
    conflict: int
    failed: int
    last_safe_error_code: str


async def _default_sleeper(seconds: float) -> None:  # pragma: no cover - trivial
    await asyncio.sleep(seconds)


def _capability_supports(provider, run_type: str) -> bool:
    caps = provider.capabilities
    if run_type == RUN_DISCOVER_ONLY:
        return caps.discovery
    if run_type == RUN_EXACT_SOURCE:
        return caps.fetch and caps.parse
    if run_type == "incremental":
        return caps.incremental
    if run_type == "bounded_window":
        return caps.bounded_window
    if run_type == "fetch_and_ingest":
        return caps.discovery and caps.fetch and caps.parse
    return False


async def run_ingestion(
    db: AsyncSession,
    *,
    provider_code: str,
    run_type: str,
    query: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    max_items: int = 50,
    cursor: dict | None = None,
    external_id: str | None = None,
    transport=None,
    resolver=None,
    created_by: str | None = None,
    sleeper=None,
) -> RunSummary:
    """Execute a bounded, deterministic provider ingestion run.

    [external_id] is the ONLY way to specify an exact_source target
    (never an arbitrary caller-supplied URL). The provider resolves it.
    """
    if run_type not in RUN_MODES:
        raise ProviderError("unsupported_mode", f"unknown run_type: {run_type}")

    provider = registry.get(provider_code)  # raises on unknown/disabled
    if not _capability_supports(provider, run_type):
        raise ProviderError("unsupported_mode",
                            f"{provider_code} does not support {run_type}")

    params = {
        "query": query, "from_date": from_date, "to_date": to_date,
        "max_items": max_items, "external_id": external_id,
    }
    run = await SourceIngestionRunRepository.create(
        db, provider_code=provider_code, run_type=run_type,
        created_by=created_by, cursor=params,
    )
    await db.commit()
    return await _execute_loop(
        db, run, provider, run_type=run_type, query=query, from_date=from_date,
        to_date=to_date, max_items=max_items, cursor=None,
        external_id=external_id, transport=transport, resolver=resolver,
        sleeper=sleeper,
    )


async def execute_run(
    db: AsyncSession, run_id: str, *, transport=None, resolver=None, sleeper=None,
) -> RunSummary:
    """Execute a previously-created queued run in place (CLI/worker path).

    Reads persisted run parameters (query, from_date, to_date, max_items,
    external_id) from cursor_json. The provider resolves external_id into a
    safe candidate — no caller-supplied URL.
    """
    run = await SourceIngestionRunRepository.get(db, run_id)
    if run is None:
        raise ProviderError("unknown_run", f"run not found: {run_id}")
    if run.status not in ("queued",):
        raise ProviderError("run_not_queued", f"run status is {run.status}")
    provider = registry.get(run.provider_code)
    if not _capability_supports(provider, run.run_type):
        raise ProviderError("unsupported_mode",
                            f"{run.provider_code} does not support {run.run_type}")
    params = run.cursor_json or {}
    return await _execute_loop(
        db, run, provider, run_type=run.run_type,
        query=params.get("query"),
        from_date=params.get("from_date"),
        to_date=params.get("to_date"),
        max_items=params.get("max_items", 50),
        cursor=None,
        external_id=params.get("external_id"),
        transport=transport, resolver=resolver, sleeper=sleeper,
    )


async def _execute_loop(
    db: AsyncSession, run, provider, *, run_type, query, from_date, to_date,
    max_items, cursor, external_id, transport, resolver, sleeper,
) -> RunSummary:
    provider_code = provider.provider_code
    sleep = sleeper or _default_sleeper
    max_items = max(1, min(int(max_items), 500))
    await SourceIngestionRunRepository.mark_running(db, run)
    await db.commit()

    t0 = time.monotonic()
    next_cursor: dict = dict(cursor or {})
    last_error = ""
    provider_stop = False

    try:
        candidates = await _collect_candidates(
            provider, run_type=run_type, query=query, from_date=from_date,
            to_date=to_date, max_items=max_items, cursor=cursor,
            external_id=external_id, transport=transport, resolver=resolver,
            sleeper=sleep,
        )
    except ProviderError as e:
        run.discovered_count = 0
        await SourceIngestionRunRepository.finalize(
            db, run, status=RUN_FAILED, last_safe_error_code=e.code)
        await db.commit()
        metrics.official_source_provider_run_total.inc(
            labels={"provider_code": provider_code, "run_type": run_type, "status": RUN_FAILED})
        metrics.official_source_provider_error.inc(
            labels={"provider_code": provider_code, "safe_error_code": e.code})
        return _summary(run)

    run.discovered_count = len(candidates)
    metrics.official_source_provider_discovered.inc(len(candidates),
                                                    labels={"provider_code": provider_code})

    ingest = run_type not in (RUN_DISCOVER_ONLY,)

    for cand in candidates:
        dedupe = cand.dedupe_key()
        existing = await SourceIngestionItemRepository.find_by_dedupe(db, provider_code, dedupe)

        if not ingest:
            # discover_only: record each distinct candidate once (rediscovery of
            # a known candidate creates no duplicate item).
            if existing is None:
                item = await SourceIngestionItemRepository.create(
                    db, run_id=run.id, provider_code=provider_code,
                    external_id=cand.external_id, candidate_url_hash=cand.candidate_url_hash(),
                    dedupe_key=dedupe,
                )
                await SourceIngestionItemRepository.complete(db, item, status="discovered")
            continue

        # Always fetch so P2.6 same-hash change detection can run. Politeness
        # delay between provider network calls.
        await sleep(provider.request_policy.min_interval_seconds)
        try:
            outcome = await _fetch_parse_ingest(
                db, provider, cand, transport=transport, resolver=resolver,
                sleeper=sleep)
        except ProviderError as e:
            last_error = e.code
            run.failed_count += 1
            if existing is None:
                item = await SourceIngestionItemRepository.create(
                    db, run_id=run.id, provider_code=provider_code,
                    external_id=cand.external_id, candidate_url_hash=cand.candidate_url_hash(),
                    dedupe_key=dedupe,
                )
                await SourceIngestionItemRepository.complete(
                    db, item, status="failed", safe_error_code=e.code)
            metrics.official_source_provider_error.inc(
                labels={"provider_code": provider_code, "safe_error_code": e.code})
            if e.code in _PROVIDER_WIDE_STOP_CODES:
                provider_stop = True
                break
            continue
        except (ValueError, CanonicalKeyError) as e:
            code = "canonical_key_error" if isinstance(e, CanonicalKeyError) else "ingest_rejected"
            last_error = code
            run.failed_count += 1
            if existing is None:
                item = await SourceIngestionItemRepository.create(
                    db, run_id=run.id, provider_code=provider_code,
                    external_id=cand.external_id, candidate_url_hash=cand.candidate_url_hash(),
                    dedupe_key=dedupe,
                )
                await SourceIngestionItemRepository.complete(
                    db, item, status="failed", safe_error_code=code)
            metrics.official_source_provider_error.inc(
                labels={"provider_code": provider_code, "safe_error_code": code})
            continue

        run.fetched_count += 1
        metrics.official_source_provider_fetched.inc(labels={"provider_code": provider_code})
        _apply_outcome(run, provider_code, outcome.outcome)
        is_dup = outcome.outcome in ("duplicate", "duplicate_verified")
        if existing is not None and is_dup:
            # Rediscovery of unchanged content: no duplicate ingestion item and
            # (via P2.6) no duplicate SourceVersion.
            await db.commit()
            continue
        item = await SourceIngestionItemRepository.create(
            db, run_id=run.id, provider_code=provider_code,
            external_id=cand.external_id, candidate_url_hash=cand.candidate_url_hash(),
            dedupe_key=dedupe,
        )
        item_status = "duplicate" if is_dup else "ingested"
        await SourceIngestionItemRepository.complete(
            db, item, status=item_status,
            source_record_id=outcome.source_record_id,
            source_version_id=outcome.source_version_id,
            outcome=outcome.outcome,
        )
        await db.commit()

    successful_work = bool(
        run.ingested_count or run.duplicate_count or run.new_version_count
    )
    if provider_stop:
        status = RUN_COMPLETED_WITH_ERRORS if successful_work else RUN_FAILED
    elif run.failed_count and successful_work:
        status = RUN_COMPLETED_WITH_ERRORS
    elif run.failed_count and not run.discovered_count == 0:
        status = RUN_COMPLETED_WITH_ERRORS if run.discovered_count > run.failed_count else RUN_FAILED
    else:
        status = RUN_COMPLETED

    await SourceIngestionRunRepository.finalize(
        db, run, status=status, cursor=next_cursor, last_safe_error_code=last_error)
    await db.commit()

    metrics.official_source_provider_run_total.inc(
        labels={"provider_code": provider_code, "run_type": run_type, "status": status})
    metrics.official_source_provider_run_duration.observe(
        time.monotonic() - t0, labels={"provider_code": provider_code, "run_type": run_type})
    return _summary(run)


async def _collect_candidates(
    provider, *, run_type, query, from_date, to_date, max_items, cursor,
    external_id, transport, resolver, sleeper,
) -> list[ProviderDiscoveryCandidate]:
    if run_type == RUN_EXACT_SOURCE:
        if not external_id:
            raise ProviderError("missing_identifier", "exact_source requires an external_id")
        return [provider.build_exact_candidate(external_id)]
    page = await _execute_provider_network_operation(
        provider,
        operation="discover",
        sleeper=sleeper,
        call=lambda: provider.discover(
            query=query, cursor=(cursor or {}).get("page") if cursor else None,
            limit=max_items, from_date=from_date, to_date=to_date,
            transport=transport,
            resolver=resolver or provider.default_resolver(),
        ),
    )
    return page.candidates[:max_items]


async def _fetch_parse_ingest(db, provider, cand, *, transport, resolver, sleeper):
    fetch_result = await _execute_provider_network_operation(
        provider,
        operation="fetch",
        sleeper=sleeper,
        call=lambda: provider.fetch(cand, transport=transport, resolver=resolver),
    )
    parsed: ParsedOfficialSource = await provider.parse(cand, fetch_result)
    # Content-quality gate (defense in depth; providers also gate in parse()).
    assert_meaningful_body(parsed.raw_text)
    # Extraction provenance: the raw fetched bytes contain HTML/chrome. Extract
    # the deterministic legal text so the canonical SourceVersion.content_hash
    # equals the hash of the legal content, not site chrome. The raw-document
    # hash (provenance) is preserved in SourceVersion.raw_document_hash.
    extracted = extract_content_from_fetch(
        fetch_result,
        parser_version="p2.6c-extract-1",
    )
    extracted_fr = make_extracted_fetch_result(fetch_result, extracted)
    # Canonical ingestion via the P2.6 official-fetch trust path ONLY.
    return await ingest_official_fetch(
        db, metadata=parsed.to_ingest_metadata(), fetch_result=extracted_fr,
        raw_document_hash=extracted.raw_document_hash,
        extraction_method=extracted.extraction_method,
        extraction_version=extracted.parser_version,
    )


async def _execute_provider_network_operation(provider, *, operation: str, sleeper, call):
    """Execute one provider network operation with the shared retry policy."""
    policy = provider.request_policy
    attempt_index = 0
    while True:
        try:
            return await call()
        except ProviderError as e:
            if not e.retryable or attempt_index >= policy.max_retries:
                raise
            if (
                e.code == ERR_RATE_LIMITED
                and e.retry_after_seconds is not None
                and e.retry_after_seconds > policy.backoff_max_seconds
            ):
                raise
            if e.code == ERR_RATE_LIMITED and e.retry_after_seconds is not None:
                delay = e.retry_after_seconds
            else:
                delay = min(
                    policy.backoff_base_seconds * (2 ** attempt_index),
                    policy.backoff_max_seconds,
                )
            delay = max(delay, policy.min_interval_seconds)
            metrics.official_source_provider_retry_total.inc(
                labels={
                    "provider_code": provider.provider_code,
                    "operation": operation,
                    "safe_error_code": e.code,
                }
            )
            await sleeper(delay)
            attempt_index += 1


def _apply_outcome(run, provider_code: str, outcome: str) -> None:
    if outcome == "created":
        run.ingested_count += 1
        metrics.official_source_provider_ingested.inc(labels={"provider_code": provider_code})
    elif outcome == "new_version":
        run.ingested_count += 1
        run.new_version_count += 1
        metrics.official_source_provider_ingested.inc(labels={"provider_code": provider_code})
        metrics.official_source_provider_new_version.inc(labels={"provider_code": provider_code})
    elif outcome in ("duplicate", "duplicate_verified"):
        run.duplicate_count += 1
        metrics.official_source_provider_duplicate.inc(labels={"provider_code": provider_code})
    elif outcome == "conflict":
        run.conflict_count += 1
        metrics.official_source_provider_conflict.inc(labels={"provider_code": provider_code})


def _summary(run) -> RunSummary:
    return RunSummary(
        run_id=run.id, provider_code=run.provider_code, run_type=run.run_type,
        status=run.status, discovered=run.discovered_count, fetched=run.fetched_count,
        ingested=run.ingested_count, duplicate=run.duplicate_count,
        new_version=run.new_version_count, conflict=run.conflict_count,
        failed=run.failed_count, last_safe_error_code=run.last_safe_error_code,
    )
