"""P2.8S-Y1 — Bounded live Yargıtay corpus smoke (max 10 canonical decisions).

Operator-run acceptance harness. It drives ONLY the canonical chain:

    provider discover -> SSRF-safe official transport -> provider fetch
    -> provider parse -> quality gate -> ingest_official_fetch
    -> exact verification evidence -> paragraphs

through the existing provider ingestion orchestration — it never writes
SourceRecord/SourceVersion/SourceParagraph/SourceVerification directly.

Fail-closed guards (ALL required):
- ``--confirm-live-smoke`` CLI flag
- ``OFFICIAL_PROVIDER_LIVE_SMOKE`` truthy
- ``OFFICIAL_PROVIDER_YARGITAY_ENABLED`` truthy
- ``DATABASE_URL`` points at the DEDICATED PostgreSQL corpus-smoke database
  ``emsalist_p28sy1_yargitay_corpus_smoke`` (never SQLite, never the P2.7
  acceptance database, never a demo/user database)

Safety:
- provider_code is hard-enforced to ``yargitay``
- hard cap: 10 successfully canonicalized decisions TOTAL
- hard cap: 40 live network requests TOTAL, concurrency 1
- provider politeness (min 3s interval) is enforced by the orchestration policy
- full decision bodies, cookies, raw outer envelopes and secrets are NEVER
  printed — only safe structural metadata

Exit code is non-zero on any acceptance failure.

Usage:
    python -m scripts.p28sy1_yargitay_corpus_smoke --confirm-live-smoke
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from urllib.parse import urlparse

PROVIDER_CODE = "yargitay"
REQUIRED_DATABASE_NAME = "emsalist_p28sy1_yargitay_corpus_smoke"
FORBIDDEN_DATABASE_NAMES = frozenset({"emsalist_p27_acceptance", "emsalist"})
MAX_TOTAL_INGESTED = 10
MAX_LIVE_REQUESTS = 40
QUERY_PLAN = (
    ("kira tahliye", 4),
    ("ayıplı mal", 3),
    ("kıdem tazminatı", 3),
)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes"}


def _fail(message: str) -> int:
    print(f"P2.8S-Y1 SMOKE FAIL-CLOSED: {message}", file=sys.stderr)
    return 2


def _validate_environment() -> str | None:
    """Return an error message when the smoke may not run, else None."""
    if not _truthy(os.environ.get("OFFICIAL_PROVIDER_LIVE_SMOKE")):
        return "OFFICIAL_PROVIDER_LIVE_SMOKE is not enabled"
    if not _truthy(os.environ.get("OFFICIAL_PROVIDER_YARGITAY_ENABLED")):
        return "OFFICIAL_PROVIDER_YARGITAY_ENABLED is not enabled"

    from app.config import get_settings

    settings = get_settings()
    url = settings.database_url or ""
    if not url:
        return "postgresql_unavailable_for_yargitay_corpus_persistence (DATABASE_URL empty)"
    try:
        from sqlalchemy.engine import make_url

        parsed = make_url(url)
    except Exception:
        return "DATABASE_URL could not be parsed"
    if parsed.get_backend_name() != "postgresql":
        return "postgresql_unavailable_for_yargitay_corpus_persistence (non-PostgreSQL DATABASE_URL)"
    database = (parsed.database or "").strip()
    if database in FORBIDDEN_DATABASE_NAMES:
        return f"forbidden database for corpus smoke: {database}"
    if database != REQUIRED_DATABASE_NAME:
        return f"corpus smoke requires dedicated database {REQUIRED_DATABASE_NAME}"
    return None


def _budgeted_transport():
    from app.services.source_fetcher import (
        HttpxSourceTransport,
        SourceFetchError,
    )

    class BudgetedTransport(HttpxSourceTransport):
        """Real SSRF-safe transport with a hard live-request budget."""

        def __init__(self, *, max_requests: int, **kw):
            super().__init__(**kw)
            self.request_count = 0
            self._max_requests = max_requests

        def fetch_pinned(self, dest, *, timeout_seconds=None, request=None):
            if self.request_count >= self._max_requests:
                raise SourceFetchError(
                    "transport_unavailable", "live request budget exhausted",
                )
            self.request_count += 1
            return super().fetch_pinned(
                dest, timeout_seconds=timeout_seconds, request=request,
            )

    return BudgetedTransport(max_requests=MAX_LIVE_REQUESTS, timeout_seconds=20)


async def _verify_ingested_records(db) -> list[dict]:
    """Section-17 database proof for every ingested Yargıtay decision."""
    from sqlalchemy import select

    from app.db.models import (
        SourceParagraph,
        SourceRecord,
        SourceVerification,
        SourceVersion,
    )
    from app.services.source_ingestion_service import get_version_official_evidence

    rows = (await db.execute(
        select(SourceRecord).where(SourceRecord.source_type == "supreme_court_decision")
    )).scalars().all()
    proofs: list[dict] = []
    for record in rows:
        assert record.current_version_id, f"record {record.id} has no current version"
        version = (await db.execute(
            select(SourceVersion).where(SourceVersion.id == record.current_version_id)
        )).scalars().one()
        assert version.retrieval_method == "official_fetch"
        assert len(version.content_hash or "") == 64
        paragraphs = (await db.execute(
            select(SourceParagraph).where(SourceParagraph.source_version_id == version.id)
        )).scalars().all()
        assert paragraphs, f"record {record.id} has no paragraphs"
        assert all((p.text or "").strip() and p.text_hash for p in paragraphs)
        assert record.court == "Yargıtay"
        assert record.chamber and record.case_number and record.decision_number
        evidence = await get_version_official_evidence(db, record.id, version.id)
        assert evidence.valid, f"record {record.id} lacks exact official evidence"
        verifications = (await db.execute(
            select(SourceVerification).where(
                SourceVerification.source_record_id == record.id,
                SourceVerification.source_version_id == version.id,
            )
        )).scalars().all()
        official = [
            v for v in verifications
            if v.verification_method == "official_fetch_match"
            and v.verifier_type == "official_match"
            and v.result == "verified_official"
            and v.evidence_hash == version.content_hash
        ]
        assert official, f"record {record.id} lacks official_fetch_match verification"
        host = (urlparse(official[0].evidence_url or "").hostname or "").lower()
        assert host.endswith("yargitay.gov.tr"), "evidence host is not official"
        proofs.append({
            "source_record_id": record.id,
            "source_version_id": version.id,
            "paragraph_count": len(paragraphs),
            "title": record.title,
            "chamber": record.chamber,
            "case_number": record.case_number,
            "decision_number": record.decision_number,
            "decision_date": record.decision_date,
            "verification_status": record.verification_status,
            "canonical_key": record.canonical_key,
            "official_host": host,
        })
    return proofs


async def _run(args) -> int:
    error = _validate_environment()
    if error:
        return _fail(error)
    if not args.confirm_live_smoke:
        return _fail("--confirm-live-smoke is required")

    from app.db.session import get_sessionmaker
    from app.services.provider_ingestion_service import run_ingestion
    from app.services.source_providers import registry

    if not registry.is_enabled(PROVIDER_CODE):
        return _fail("yargitay provider is not enabled in settings")

    transport = _budgeted_transport()
    maker = get_sessionmaker()
    total_ingested = 0
    summaries = []

    async with maker() as db:
        for query, budget in QUERY_PLAN:
            remaining = MAX_TOTAL_INGESTED - total_ingested
            if remaining <= 0:
                break
            summary = await run_ingestion(
                db,
                provider_code=PROVIDER_CODE,
                run_type="fetch_and_ingest",
                query=query,
                max_items=min(budget, remaining),
                transport=transport,
                created_by="p28sy1_corpus_smoke",
            )
            summaries.append(summary)
            total_ingested += summary.ingested
            print(
                f"query done: discovered={summary.discovered} fetched={summary.fetched} "
                f"ingested={summary.ingested} duplicate={summary.duplicate} "
                f"failed={summary.failed} status={summary.status} "
                f"last_error={summary.last_safe_error_code or '-'}"
            )
            if summary.last_safe_error_code in {
                "challenge_detected", "rate_limited", "access_denied",
            }:
                print("stop condition reached — live collection halted", file=sys.stderr)
                break

    if total_ingested == 0:
        return _fail("no decisions were canonically ingested")
    if total_ingested > MAX_TOTAL_INGESTED:
        return _fail("ingestion cap exceeded — investigate immediately")

    async with maker() as db:
        proofs = await _verify_ingested_records(db)
    for proof in proofs:
        print("DECISION PROOF:", proof)
    print(f"total_ingested={total_ingested} live_requests={transport.request_count}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="P2.8S-Y1 bounded live Yargitay corpus smoke (max 10 decisions)",
    )
    parser.add_argument("--confirm-live-smoke", action="store_true",
                        help="explicit operator confirmation for bounded live access")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
