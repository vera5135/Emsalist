#!/usr/bin/env python3
"""Legal Brain Librarian Agent - CLI entry point."""

from __future__ import annotations

import argparse
import atexit
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_WATCH_INTERVAL = 900
STALE_LOCK_SECONDS = 2 * 60 * 60


class LibrarianLock:
    """Small atomic file lock shared by once and watch modes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.token = uuid.uuid4().hex
        self.acquired = False

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(3):
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    age = time.time() - self.path.stat().st_mtime
                    if age <= STALE_LOCK_SECONDS:
                        return False
                    self.path.unlink()
                except FileNotFoundError:
                    continue
                except OSError:
                    return False
                continue

            payload = {
                "pid": os.getpid(),
                "token": self.token,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as lock_file:
                    json.dump(payload, lock_file, ensure_ascii=False)
            except Exception:
                try:
                    os.close(fd)
                except OSError:
                    pass
                try:
                    self.path.unlink()
                except OSError:
                    pass
                return False
            self.acquired = True
            return True
        return False

    def refresh(self) -> None:
        if self.acquired:
            try:
                self.path.touch()
            except OSError:
                pass

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if payload.get("token") == self.token:
                self.path.unlink()
        except (OSError, json.JSONDecodeError, TypeError):
            pass
        finally:
            self.acquired = False


def _sleep_with_lock(seconds: int, lock: LibrarianLock) -> None:
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(60, remaining))
        lock.refresh()


def _run_watch(service: Any, interval: int, max_runs: int | None, lock: LibrarianLock) -> None:
    started = datetime.now(timezone.utc).isoformat()
    service._update_status(mode="watch", last_started_at=started)
    service._append_log(f"Agent started in watch mode at {started} with interval {interval}s")
    runs = 0
    try:
        while max_runs is None or runs < max_runs:
            lock.refresh()
            try:
                files = service.discover_source_files()
                report = service._process_files(files, mode="watch", started=started)
                service._append_log(
                    f"Watch scan completed: run={runs + 1} "
                    f"seen={report.get('files_seen', 0)} "
                    f"learned={report.get('files_learned', 0)} "
                    f"skipped={report.get('files_skipped', 0)} "
                    f"failed={report.get('files_failed', 0)} "
                    f"cards={report.get('cards_created', 0)}"
                )
            except Exception as exc:
                service._append_log(f"Watch scan error at run={runs + 1}: {exc}")
            runs += 1
            if max_runs is not None and runs >= max_runs:
                break
            _sleep_with_lock(interval, lock)
    except KeyboardInterrupt:
        service._append_log("Agent interrupted by user")
    finally:
        service._update_status(
            mode="watch",
            is_running=False,
            last_completed_at=datetime.now(timezone.utc).isoformat(),
        )
        service._append_log(f"Agent watch mode stopped after {runs} run(s)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Legal Brain Librarian Agent")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--watch", action="store_true", help="Run in watch mode")
    parser.add_argument("--interval", type=int, default=DEFAULT_WATCH_INTERVAL, help="Watch interval in seconds")
    parser.add_argument("--max-runs", type=int, help="Stop watch mode after this many runs")
    args = parser.parse_args()

    if not args.once and not args.watch:
        parser.print_help()
        return 1

    # Ensure project root is on sys.path so 'app' package is importable
    project_root = Path(__file__).resolve().parents[1]
    root_str = str(project_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    from app.services.legal_brain_librarian_service import legal_brain_librarian_service

    if args.max_runs is not None and args.max_runs < 1:
        parser.error("--max-runs must be at least 1")

    lock_path = project_root / "app" / "legal_brain" / "metadata" / "librarian_agent.lock"
    lock = LibrarianLock(lock_path)
    if not lock.acquire():
        print(f"Librarian is already running (lock: {lock_path})", file=sys.stderr)
        return 2
    atexit.register(lock.release)

    try:
        if args.once:
            report = legal_brain_librarian_service.run_once()
            print(f"Run completed: learned={report.get('files_learned', 0)} "
                  f"skipped={report.get('files_skipped', 0)} "
                  f"failed={report.get('files_failed', 0)} "
                  f"cards={report.get('cards_created', 0)}")
            if report.get("errors"):
                for err in report["errors"]:
                    print(f"ERROR: {err}", file=sys.stderr)
            return 0

        if args.watch:
            interval = max(1, int(args.interval))
            print(f"Starting watch mode with interval {interval}s")
            _run_watch(legal_brain_librarian_service, interval, args.max_runs, lock)
            if args.max_runs is not None:
                print(f"Watch completed: runs={args.max_runs}")
            return 0
    finally:
        lock.release()

    return 1


if __name__ == "__main__":
    sys.exit(main())
