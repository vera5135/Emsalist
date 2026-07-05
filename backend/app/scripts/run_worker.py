"""P1.8 — Worker CLI: python -m app.scripts.run_worker [--once] [--job-type ...] [--concurrency ...]"""
import sys

def main():
    import argparse
    import asyncio
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Emsalist background job worker")
    parser.add_argument("--once", action="store_true", help="Process one job and exit")
    parser.add_argument("--job-type", type=str, default="", help="Filter to specific job type")
    parser.add_argument("--concurrency", type=int, default=1, help="Max concurrent jobs (1-4)")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Poll interval in seconds")
    parser.add_argument("--graceful-timeout", type=int, default=30, help="Graceful shutdown timeout seconds")
    parser.add_argument("--recover", action="store_true", help="Recover expired leases first")
    args = parser.parse_args()

    from app.services.job_worker import JobWorker, recover_jobs
    from app.config import get_settings
    get_settings()

    if args.recover:
        n = asyncio.run(recover_jobs())
        print(f"Recovered {n} expired lease(s)")

    job_types = [args.job_type] if args.job_type else None
    worker = JobWorker(
        concurrency=args.concurrency,
        poll_interval=args.poll_interval,
        graceful_timeout=args.graceful_timeout,
        job_types=job_types,
    )

    if args.once:
        n = asyncio.run(worker.run_once())
        print(f"Processed {n} job(s)")
    else:
        asyncio.run(worker.run())


if __name__ == "__main__":
    main()
