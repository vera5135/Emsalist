"""P1.8 — Worker CLI: python -m app.scripts.run_worker [--once] [--job-type ...] [--concurrency ...]"""
import sys

def main():
    import argparse
    import asyncio
    import logging

    from app.config import get_settings
    from app.core.logging import setup_logging

    settings = get_settings()
    import os as _os
    _os.environ.setdefault("EMSALIST_ENVIRONMENT", settings.environment)
    _os.environ.setdefault("EMSALIST_LOG_LEVEL", settings.log_level)
    _os.environ.setdefault("EMSALIST_LOG_FORMAT", settings.log_format)
    _os.environ.setdefault("EMSALIST_LOG_SERVICE_NAME", settings.log_service_name)
    setup_logging()

    parser = argparse.ArgumentParser(description="Emsalist background job worker")
    parser.add_argument("--once", action="store_true", help="Process one job and exit")
    parser.add_argument("--job-type", type=str, default="", help="Filter to specific job type")
    parser.add_argument("--concurrency", type=int, default=1, help="Max concurrent jobs (1-4)")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Poll interval in seconds")
    parser.add_argument("--graceful-timeout", type=int, default=30, help="Graceful shutdown timeout seconds")
    parser.add_argument("--recover", action="store_true", help="Recover expired leases first")
    args = parser.parse_args()

    from app.services.job_worker import JobWorker, recover_jobs

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
