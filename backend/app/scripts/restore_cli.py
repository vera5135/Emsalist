"""P1.9 — Restore CLI."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("restore")


def main():
    parser = argparse.ArgumentParser(description="Emsalist restore CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("validate")
    s.add_argument("backup_id")
    s.add_argument("--target", default="test")

    e = sub.add_parser("execute")
    e.add_argument("backup_id")
    e.add_argument("--target", default="test")
    e.add_argument("--confirm-production", action="store_true")
    e.add_argument("--dry-run", action="store_true")
    e.add_argument("--validation-only", action="store_true")

    st = sub.add_parser("status")
    st.add_argument("restore_run_id")

    args = parser.parse_args()
    asyncio.run(_run(args))


async def _run(args):
    from app.db.session import get_sessionmaker
    from app.services.restore_service import restore_service, RestoreRepository

    if args.command == "validate":
        maker = get_sessionmaker()
        async with maker() as db:
            result = await restore_service.validate(db, args.backup_id, args.target)
            print(json.dumps(result, indent=2))

    elif args.command == "execute":
        target = args.target
        if target == "production" and not getattr(args, "confirm_production", False):
            target = "test"
        maker = get_sessionmaker()
        async with maker() as db:
            result = await restore_service.execute(db, args.backup_id,
                target=target,
                dry_run=getattr(args, "dry_run", False),
                validation_only=getattr(args, "validation_only", False))
            print(json.dumps(_safe_restore(result), indent=2))

    elif args.command == "status":
        maker = get_sessionmaker()
        async with maker() as db:
            repo = RestoreRepository()
            run = await repo.get_run(db, args.restore_run_id)
            if run:
                print(json.dumps(_safe_restore(run), indent=2))
            else:
                print(json.dumps({"error": "not_found"}))


def _safe_restore(run: dict) -> dict:
    return {
        "id": run.get("id"),
        "backup_run_id": run.get("backup_run_id", "")[:16],
        "status": run.get("status"),
        "target_environment": run.get("target_environment"),
        "dry_run": run.get("dry_run"),
        "restored_item_count": run.get("restored_item_count"),
        "skipped_item_count": run.get("skipped_item_count"),
        "failed_item_count": run.get("failed_item_count"),
        "started_at": run.get("started_at"),
        "completed_at": run.get("completed_at"),
    }


if __name__ == "__main__":
    main()
