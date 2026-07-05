"""P1.8 — Job admin CLI: python -m app.scripts.job_admin [recover|list-failed|retry|cancel]"""
import sys

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

    asyncio.run(_run())


if __name__ == "__main__":
    main()
