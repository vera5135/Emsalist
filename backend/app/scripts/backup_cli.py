"""P1.9 — Backup CLI."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys

from app.config import get_settings
from app.core.logging import setup_logging

_settings = get_settings()
os.environ.setdefault("ENVIRONMENT", _settings.environment)
os.environ.setdefault("LOG_LEVEL", _settings.log_level)
os.environ.setdefault("LOG_FORMAT", _settings.log_format)
os.environ.setdefault("LOG_SERVICE_NAME", _settings.log_service_name)
setup_logging()

logger = logging.getLogger("backup")


def main():
    parser = argparse.ArgumentParser(description="Emsalist backup CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    c = sub.add_parser("create")
    c.add_argument("--scope", default="full")
    c.add_argument("--dry-run", action="store_true")

    sub.add_parser("list")

    s = sub.add_parser("show")
    s.add_argument("backup_id")

    v = sub.add_parser("verify")
    v.add_argument("backup_id")

    p = sub.add_parser("prune")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--apply", action="store_true")

    args = parser.parse_args()
    asyncio.run(_run(args))


async def _run(args):
    from app.db.session import get_sessionmaker
    if args.command == "create":
        from app.services.backup_orchestration import backup_service
        maker = get_sessionmaker()
        async with maker() as db:
            if getattr(args, "dry_run", False):
                print(json.dumps({"dry_run": True, "status": "would_create"}))
                return
            run = await backup_service.create(db, scope=args.scope)
            print(json.dumps(_safe_summary(run), indent=2))

    elif args.command == "list":
        from app.services.backup_service import BackupRepository
        maker = get_sessionmaker()
        async with maker() as db:
            repo = BackupRepository()
            runs = await repo.list_runs(db, limit=20)
            for r in runs:
                print(json.dumps(_safe_summary(r)))

    elif args.command == "show":
        from app.services.backup_service import BackupRepository
        maker = get_sessionmaker()
        async with maker() as db:
            repo = BackupRepository()
            run = await repo.get_run(db, args.backup_id)
            if run:
                items = await repo.get_items(db, run["id"])
                print(json.dumps({**_safe_summary(run), "items": len(items)}, indent=2))
            else:
                print(json.dumps({"error": "not_found"}))

    elif args.command == "verify":
        from app.services.backup_orchestration import backup_service
        maker = get_sessionmaker()
        async with maker() as db:
            result = await backup_service.verify(db, args.backup_id)
            print(json.dumps(result, indent=2))

    elif args.command == "prune":
        from app.services.backup_orchestration import backup_service
        maker = get_sessionmaker()
        async with maker() as db:
            result = await backup_service.prune(db, dry_run=not getattr(args, "apply", False))
            print(json.dumps(result, indent=2))


def _safe_summary(run: dict) -> dict:
    return {
        "id": run.get("id"),
        "backup_type": run.get("backup_type"),
        "status": run.get("status"),
        "scope": run.get("scope"),
        "encrypted": run.get("encrypted"),
        "manifest_sha256": run.get("manifest_sha256", "")[:16],
        "total_size_bytes": run.get("total_size_bytes"),
        "item_count": run.get("item_count"),
        "warning_count": run.get("warning_count"),
        "failure_count": run.get("failure_count"),
        "created_at": run.get("created_at"),
        "completed_at": run.get("completed_at"),
        "retention_until": run.get("retention_until"),
    }


if __name__ == "__main__":
    main()
