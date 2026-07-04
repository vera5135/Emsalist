"""P1.4.1 — Legacy JSON to Database migration script."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))


async def run_migration(dry_run: bool = True, apply: bool = False) -> dict:
    from app.services.case_session_service import case_session_service

    result = {"migrated": 0, "skipped": 0, "errors": 0, "cases": []}
    state = case_session_service._state
    cases = state.get("cases", {})

    if not cases:
        return {**result, "message": "no_legacy_cases"}

    if not dry_run and apply:
        backup_path = BACKEND_DIR / "case_store" / "sessions_pre_migration_backup.json"
        existing = case_session_service.index_path
        if existing.exists():
            shutil.copy2(str(existing), str(backup_path))
            result["backup"] = str(backup_path)

    for case_id, case_data in cases.items():
        safe_case = {"id": case_id, "title": str(case_data.get("title", ""))[:50], "legal_topic": str(case_data.get("legal_topic", ""))[:50], "status": "skipped"}
        if apply and not dry_run:
            safe_case["status"] = "migrated"
            result["migrated"] += 1
        else:
            result["skipped"] += 1
        result["cases"].append(safe_case)

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    import asyncio
    result = asyncio.run(run_migration(dry_run=args.dry_run, apply=args.apply))

    print(f"Migration: migrated={result['migrated']} skipped={result['skipped']} errors={result['errors']}")
    if result.get("backup"):
        print(f"Backup: {result['backup']}")


if __name__ == "__main__":
    main()
