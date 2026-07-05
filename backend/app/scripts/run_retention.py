"""P1.6.1 — Retention and purge CLI with dry-run/apply/resume.

Usage:
    python -m app.scripts.run_retention --dry-run
    python -m app.scripts.run_retention --apply
    python -m app.scripts.run_retention --resume <run_id>
    python -m app.scripts.run_retention --status <run_id>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime


def main() -> None:
    parser = argparse.ArgumentParser(description="Retention and purge lifecycle CLI")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", default=False,
                       help="Preview purge without modifying data (default)")
    group.add_argument("--apply", action="store_true", default=False,
                       help="Execute actual purge")
    parser.add_argument("--resume", type=str, default="",
                        help="Resume a previous purge run by run_id")
    parser.add_argument("--status", type=str, default="",
                        help="Show status of a purge run by run_id")
    parser.add_argument("--batch", type=int, default=10,
                        help="Maximum items per batch (default: 10, max: 100)")
    parser.add_argument("--tenant-id", type=str, default="",
                        help="Filter by tenant (default: all)")
    args = parser.parse_args()

    if args.resume and not args.apply and not args.dry_run:
        args.apply = False
        args.dry_run = False

    if not args.dry_run and not args.apply and not args.resume and not args.status:
        args.dry_run = True

    batch = min(args.batch, 100)

    from app.services.lifecycle_service import lifecycle_service

    if args.status:
        result = lifecycle_service.purge_item_status(args.status)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.resume:
        run_id = args.resume
        is_dry = not args.apply
        print(f"Resuming purge run: {run_id} (dry_run={is_dry})")
        result = lifecycle_service.purge_resume(
            run_id, tenant_id=args.tenant_id, dry_run=is_dry, batch=batch,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    dry_run = args.dry_run or (not args.apply)
    if dry_run:
        print(f"DRY RUN MODE — No data will be modified")
    else:
        print(f"APPLY MODE — Data WILL be permanently purged!")
        print(f"Proceeding in 3 seconds... Ctrl+C to abort")
        import time
        time.sleep(3)

    result = lifecycle_service.run_purge(
        tenant_id=args.tenant_id, dry_run=dry_run, batch=batch,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not dry_run and result.get("status") == "completed":
        print(f"\nRun completed. Run ID: {result.get('run_id')}")


if __name__ == "__main__":
    main()
