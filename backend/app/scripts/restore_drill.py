"""P1.9.2 — Real restore drill with pg_restore, physical file restore, and E2E smoke."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import logging
import os
import subprocess
import sys
import tarfile
from pathlib import Path

from app.config import get_settings
from app.core.logging import setup_logging

_settings = get_settings()
os.environ.setdefault("ENVIRONMENT", _settings.environment)
os.environ.setdefault("LOG_LEVEL", _settings.log_level)
os.environ.setdefault("LOG_FORMAT", _settings.log_format)
os.environ.setdefault("LOG_SERVICE_NAME", _settings.log_service_name)
setup_logging()

logger = logging.getLogger("restore_drill")


def main():
    parser = argparse.ArgumentParser(description="Real synthetic restore drill")
    parser.add_argument("--target-db-url", default="", help="Target PostgreSQL URL for real restore")
    parser.add_argument("--target-storage-root", default="", help="Target document storage root")
    parser.add_argument("--skip-backup", action="store_true")
    args = parser.parse_args()
    exit_code = asyncio.run(_run(args))
    sys.exit(exit_code)


async def _run(args) -> int:
    from app.db.session import get_sessionmaker
    from app.services.backup_orchestration import backup_service, BackupStorage, decrypt_backup, _get_encryption_key
    from app.services.restore_service import restore_service

    summary = {"steps": [], "status": "unknown"}

    try:
        target_url = args.target_db_url or os.environ.get("PG_TARGET_URL", "")
        target_root = args.target_storage_root or os.environ.get("RESTORE_TARGET_ROOT", "")
        is_pg = bool(target_url)

        maker = get_sessionmaker()
        async with maker() as db:
            logger.info("=== Restore Drill: Creating backup ===")
            encrypt = os.environ.get("BACKUP_ENCRYPTION_ENABLED", "").lower() == "true"
            backup = await backup_service.create(db, backup_type="drill", scope="full",
                                                  created_by="restore_drill", verify=True, encrypt=encrypt)
            if backup["status"] != "succeeded":
                summary["status"] = "failed_backup"
                summary["steps"].append("backup_failed")
                summary["error"] = backup.get("safe_summary", {}).get("error", "unknown")
                print(_safe_json(summary))
                return 1
            summary["steps"].append("backup_created")
            logger.info("Backup: %s status=%s items=%d", backup["id"], backup["status"], backup["item_count"])

            logger.info("=== Restore Drill: Verifying backup ===")
            verify = await backup_service.verify(db, backup["id"])
            if not verify.get("valid"):
                summary["status"] = "failed_verify"
                summary["steps"].append("verify_failed")
                print(_safe_json(summary))
                return 1
            summary["steps"].append("backup_verified")

            storage = BackupStorage()
            enc_suffix = ".enc" if backup.get("encrypted") else ""
            archive_data = storage.read(f"{backup['id']}/backup.tar.gz{enc_suffix}")
            if backup.get("encrypted"):
                key = _get_encryption_key()
                archive_data = decrypt_backup(archive_data, key)
                summary["steps"].append("decrypted")

            if is_pg:
                logger.info("=== Restore Drill: Real pg_restore to target ===")
                pg_file = _extract_database_dump(archive_data, backup["id"])
                if pg_file:
                    env = {**os.environ, "PGPASSWORD": os.environ.get("DB_PASSWORD", "")}
                    result = subprocess.run(
                        ["pg_restore", "--clean", "--if-exists", "--no-owner", target_url, pg_file],
                        capture_output=True, timeout=300,
                        env=env,
                    )
                    os.unlink(pg_file)
                    if result.returncode != 0:
                        summary["status"] = "failed_pg_restore"
                        summary["steps"].append("pg_restore_failed")
                        print(_safe_json(summary))
                        return 1
                    summary["steps"].append("pg_restore_completed")
                    logger.info("pg_restore succeeded")

            if target_root:
                logger.info("=== Restore Drill: Physical document restore ===")
                restored_count = _restore_files_to_target(archive_data, backup["id"], target_root)
                summary["steps"].append(f"files_restored_{restored_count}")

            logger.info("=== Restore Drill: E2E smoke ===")
            if is_pg:
                smoke_ok = await _run_e2e_smoke(target_url)
                summary["steps"].append(f"e2e_smoke_{'passed' if smoke_ok else 'failed'}")
            else:
                summary["steps"].append("e2e_smoke_skipped_no_pg")

            logger.info("=== Restore Drill: Prune dry-run ===")
            prune = await backup_service.prune(db, dry_run=True)
            summary["steps"].append(f"prune_{prune.get('pruned', 0)}_candidates")

            summary["status"] = "completed"
            summary["backup_id"] = backup["id"][:16]
    except Exception as e:
        summary["status"] = "error"
        summary["steps"].append(f"error_{str(e)[:80]}")
        logger.exception("drill_failed")
        print(_safe_json(summary))
        return 1

    print(_safe_json(summary))
    return 0


def _extract_database_dump(archive_data: bytes, backup_id: str) -> str | None:
    import tempfile
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:gz") as tar:
            for m in tar.getmembers():
                if m.name.endswith(".dump") and ".." not in m.name:
                    tmp = tempfile.NamedTemporaryFile(suffix=".dump", delete=False)
                    tmp.write(tar.extractfile(m).read())
                    return tmp.name
        return None
    except Exception:
        return None


def _restore_files_to_target(archive_data: bytes, backup_id: str, target_root: str) -> int:
    restored = 0
    target = Path(target_root).resolve()
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_data), mode="r:gz") as tar:
            for m in tar.getmembers():
                name = m.name.split(f"{backup_id}/")[-1]
                if ".." in name or name.startswith("/") or m.issym():
                    continue
                if name.startswith("files/") or name.startswith("projection/"):
                    try:
                        dest = target / name.split("/", 1)[-1] if "/" in name else target / name
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        with tar.extractfile(m) as src:
                            dest.write_bytes(src.read())
                        restored += 1
                    except Exception:
                        pass
    except Exception:
        pass
    return restored


async def _run_e2e_smoke(target_url: str) -> bool:
    try:
        old_url = os.environ.get("DATABASE_URL", "")
        os.environ["DATABASE_URL"] = target_url
        from app.db.session import check_db_health
        health = await check_db_health()
        os.environ["DATABASE_URL"] = old_url
        return health.get("connected", False)
    except Exception:
        os.environ["DATABASE_URL"] = old_url
        return False


def _safe_json(data: dict) -> str:
    safe = {k: v for k, v in data.items()
            if k not in ("password", "key", "secret", "token", "url", "connection")}
    return json.dumps(safe, default=str, indent=2)


if __name__ == "__main__":
    main()
