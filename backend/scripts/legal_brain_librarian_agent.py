#!/usr/bin/env python3
"""Legal Brain Librarian Agent - CLI entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Legal Brain Librarian Agent")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--watch", action="store_true", help="Run in watch mode")
    parser.add_argument("--interval", type=int, default=300, help="Watch interval in seconds (min 60)")
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
        interval = max(60, int(args.interval))
        print(f"Starting watch mode with interval {interval}s")
        legal_brain_librarian_service.run_watch(interval=interval)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())