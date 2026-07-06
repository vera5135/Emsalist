"""P1.9 — Safe migration: backup → verify → migrate."""
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
os.environ.setdefault("EMSALIST_ENVIRONMENT", _settings.environment)
os.environ.setdefault("EMSALIST_LOG_LEVEL", _settings.log_level)
os.environ.setdefault("EMSALIST_LOG_FORMAT", _settings.log_format)
os.environ.setdefault("EMSALIST_LOG_SERVICE_NAME", _settings.log_service_name)
setup_logging()

logger = logging.getLogger("safe_migrate")


def main():
    parser = argparse.ArgumentParser(description="Safe migration with pre-backup")
    parser.add_argument("--skip-backup", action="store_true", help="Skip pre-migration backup")
    args = parser.parse_args()
    asyncio.run(_run(args))


async def _run(args):
    from app.db.session import get_sessionmaker

    if not args.skip_backup:
        logger.info("Creating pre-migration backup...")
        from app.services.backup_orchestration import backup_service
        maker = get_sessionmaker()
        async with maker() as db:
            backup = await backup_service.create(db, backup_type="pre_migration", scope="full",
                                                  created_by="safe_migrate")
            if backup["status"] != "succeeded":
                logger.error("Pre-migration backup failed: %s", backup.get("safe_summary", {}).get("error"))
                sys.exit(1)
            logger.info("Backup created: %s status=%s", backup["id"], backup["status"])
            verify = await backup_service.verify(db, backup["id"])
            if not verify.get("valid"):
                logger.error("Backup verification failed: %s", verify.get("issues"))
                sys.exit(1)
            logger.info("Backup verified: %s", backup["id"])

    logger.info("Running alembic upgrade head...")
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True, text=True,
        cwd=str(__import__("pathlib").Path(__file__).resolve().parents[2]),
    )
    if result.returncode != 0:
        logger.error("Migration failed: %s", result.stderr[:500])
        sys.exit(1)
    logger.info("Migration completed successfully")

    logger.info("Running post-migration health check...")
    from app.db.session import check_db_health
    health = await check_db_health()
    logger.info("Health: %s", json.dumps(health, default=str))


if __name__ == "__main__":
    main()
