"""P2.6C — Controlled CLI runner for official provider ingestion.

Executes the SAME orchestration service used by the API (no duplicate ingestion
engine). Intended for operator-run bounded windows and for executing queued
runs created via the admin API.

Examples:
    python -m app.official_source_ingestion --provider yargitay \
        --mode bounded_window --from-date 2026-07-01 --to-date 2026-07-12 \
        --max-items 100
    python -m app.official_source_ingestion --run-id <id>

A real SSRF-safe HTTP transport must be wired (``--enable-live``) for live
provider access; by default no transport is configured and runs fail closed.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from app.db.session import get_sessionmaker
from app.services.provider_ingestion_service import execute_run, run_ingestion
from app.services.source_providers.base import ProviderError


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Official legal source provider ingestion runner")
    p.add_argument("--provider", default="", help="provider code")
    p.add_argument("--mode", default="bounded_window", help="run type/mode")
    p.add_argument("--query", default=None)
    p.add_argument("--from-date", dest="from_date", default=None)
    p.add_argument("--to-date", dest="to_date", default=None)
    p.add_argument("--max-items", dest="max_items", type=int, default=50)
    p.add_argument("--run-id", dest="run_id", default="", help="execute a previously queued run")
    p.add_argument("--enable-live", action="store_true",
                   help="wire the real SSRF-safe transport (live network access)")
    return p


def _live_transport():
    """Return the real SSRF-safe transport when live ingestion is enabled."""
    from app.services.source_fetcher import create_real_transport

    return create_real_transport()


async def _run(args) -> int:
    maker = get_sessionmaker()
    transport = _live_transport() if args.enable_live else None
    try:
        async with maker() as db:
            try:
                if args.run_id:
                    summary = await execute_run(
                        db, args.run_id, transport=transport,
                    )
                else:
                    if not args.provider:
                        print("--provider or --run-id is required", file=sys.stderr)
                        return 2
                    summary = await run_ingestion(
                        db, provider_code=args.provider, run_type=args.mode,
                        query=args.query, from_date=args.from_date, to_date=args.to_date,
                        max_items=args.max_items, transport=transport, created_by="cli",
                    )
            except ProviderError as e:
                print(f"provider error: {e.code}", file=sys.stderr)
                return 1
    finally:
        close = getattr(transport, "close", None)
        if callable(close):
            close()
    print(
        f"run={summary.run_id} provider={summary.provider_code} "
        f"mode={summary.run_type} status={summary.status} "
        f"discovered={summary.discovered} fetched={summary.fetched} "
        f"ingested={summary.ingested} duplicate={summary.duplicate} "
        f"new_version={summary.new_version} conflict={summary.conflict} "
        f"failed={summary.failed} last_error={summary.last_safe_error_code}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
