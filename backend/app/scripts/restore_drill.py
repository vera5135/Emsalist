"""P1.9.1 — Automated restore drill."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("restore_drill")


def main():
    parser = argparse.ArgumentParser(description="Synthetic restore drill")
    parser.add_argument("--skip-backup", action="store_true")
    args = parser.parse_args()
    asyncio.run(_run(args))


async def _run(args):
    from app.db.session import get_sessionmaker
    from app.services.backup_orchestration import backup_service
    from app.services.restore_service import restore_service

    summary = {"steps": [], "status": "unknown"}

    try:
        maker = get_sessionmaker()
        async with maker() as db:
            logger.info("=== Restore Drill: Creating backup ===")
            backup = await backup_service.create(db, backup_type="drill", scope="full",
                                                  created_by="restore_drill", verify=True)
            if backup["status"] != "succeeded":
                summary["status"] = "failed_backup"
                summary["steps"].append("backup_failed")
                print(_safe_json(summary))
                sys.exit(1)
            summary["steps"].append("backup_created")
            logger.info("Backup: %s status=%s items=%d", backup["id"], backup["status"], backup["item_count"])

            logger.info("=== Restore Drill: Verifying backup ===")
            verify = await backup_service.verify(db, backup["id"])
            if not verify.get("valid"):
                summary["status"] = "failed_verify"
                summary["steps"].append("verify_failed")
                print(_safe_json(summary))
                sys.exit(1)
            summary["steps"].append("backup_verified")

            logger.info("=== Restore Drill: Validating restore ===")
            val = await restore_service.validate(db, backup["id"])
            if not val.get("valid"):
                summary["status"] = "failed_validation"
                summary["steps"].append("validation_failed")
            else:
                summary["steps"].append("restore_validated")

            logger.info("=== Restore Drill: Dry-run restore ===")
            dry = await restore_service.execute(db, backup["id"], target="test", dry_run=True)
            summary["steps"].append("dry_run_completed" if dry.get("status") == "succeeded" else "dry_run_failed")

            logger.info("=== Restore Drill: Pruning old backups ===")
            prune = await backup_service.prune(db, dry_run=True)
            summary["steps"].append(f"prune_dry_run_{prune.get('pruned', 0)}_candidates")

            summary["status"] = "completed"
            summary["backup_id"] = backup["id"][:16]
            summary["item_count"] = backup.get("item_count", 0)
            summary["encrypted"] = backup.get("encrypted", False)

    except Exception as e:
        summary["status"] = "error"
        summary["steps"].append(f"error_{str(e)[:80]}")
        logger.exception("drill_failed")

    print(_safe_json(summary))


def _safe_json(data: dict) -> str:
    safe = {k: v for k, v in data.items()
            if k not in ("password", "key", "secret", "token", "url", "connection")}
    return json.dumps(safe, default=str, indent=2)


if __name__ == "__main__":
    main()
