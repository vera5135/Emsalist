"""P1.8 — Job admin CLI: python -m app.scripts.job_admin [recover|list-failed|retry|cancel]"""
import sys

async def _cleanup_artifacts(dry_run: bool, batch_size: int):
    import os
    from pathlib import Path
    from datetime import UTC, datetime
    from app.db.session import get_sessionmaker
    from app.db.models import BackgroundJobArtifact
    from sqlalchemy import select, update

    maker = get_sessionmaker()
    async with maker() as db:
        result = await db.execute(
            select(BackgroundJobArtifact).where(
                BackgroundJobArtifact.deleted_at.is_(None),
                BackgroundJobArtifact.expires_at.isnot(None),
                BackgroundJobArtifact.expires_at < datetime.now(UTC),
            ).limit(batch_size)
        )
        expired = result.scalars().all()
        cleaned = 0
        for art in expired:
            if not dry_run:
                storage_root = Path(os.path.join(os.path.dirname(__file__), "..", "..", "export_store"))
                file_path = storage_root / art.storage_key
                resolved = file_path.resolve()
                if not str(resolved).startswith(str(storage_root.resolve())):
                    print(f"  SKIP (path traversal): {art.storage_key}")
                    continue
                if resolved.is_symlink():
                    print(f"  SKIP (symlink): {art.storage_key}")
                    continue
                if resolved.exists():
                    try:
                        resolved.unlink()
                    except OSError as e:
                        print(f"  FAILED to delete {art.storage_key}: {e}")
                        continue
                art.deleted_at = datetime.now(UTC)
                cleaned += 1
        if not dry_run and cleaned:
            await db.commit()
        mode = "[DRY RUN]" if dry_run else "[APPLY]"
        print(f"{mode} Cleaned {cleaned}/{len(expired)} expired artifacts")


def main():
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Emsalist job admin")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("recover", help="Recover expired leases")
    sub.add_parser("list-failed", help="List failed/dead-letter jobs (summary only)")
    retry_p = sub.add_parser("retry", help="Retry a job")
    retry_p.add_argument("job_id", type=str)
    cancel_p = sub.add_parser("cancel", help="Cancel a job")
    cancel_p.add_argument("job_id", type=str)
    cleanup_p = sub.add_parser("cleanup-artifacts", help="Clean expired artifacts")
    cleanup_p.add_argument("--dry-run", action="store_true", default=True, help="Dry run only")
    cleanup_p.add_argument("--apply", dest="dry_run", action="store_false", help="Actually delete")
    cleanup_p.add_argument("--batch-size", type=int, default=100)

    args = parser.parse_args()

    from app.db.session import get_sessionmaker
    from app.services.job_service import job_service
    from app.services.job_worker import recover_jobs
    from app.config import get_settings
    get_settings()

    async def _run():
        maker = get_sessionmaker()
        if args.cmd == "recover":
            n = await recover_jobs()
            print(f"Recovered {n} job(s)")
        elif args.cmd == "list-failed":
            async with maker() as db:
                from sqlalchemy import select
                from app.db.models import BackgroundJob
                r = await db.execute(
                    select(BackgroundJob).where(BackgroundJob.status.in_(["failed", "dead_lettered"])).limit(20)
                )
                jobs = r.scalars().all()
                for j in jobs:
                    print(f"  {j.id[:12]} {j.job_type:25s} {j.status:15s} {j.safe_error_code or ''}")
                print(f"Total: {len(jobs)}")
        elif args.cmd == "retry":
            async with maker() as db:
                result = await job_service.retry(db, "local", args.job_id)
                print(f"Retried: {result['status']}")
                await db.commit()
        elif args.cmd == "cancel":
            async with maker() as db:
                result = await job_service.cancel(db, "local", args.job_id)
                print(f"Cancelled: {result['status']}")
                await db.commit()
        elif args.cmd == "cleanup-artifacts":
            await _cleanup_artifacts(args.dry_run, args.batch_size)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
