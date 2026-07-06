"""P1.13 — Migration state checker and runner."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def get_migration_state() -> dict:
    """Return current and head migration revision."""
    import subprocess
    backend_dir = Path(__file__).resolve().parent.parent
    try:
        current = subprocess.check_output(
            [sys.executable, "-m", "alembic", "current"],
            cwd=str(backend_dir), text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        current = "error"
    try:
        head = subprocess.check_output(
            [sys.executable, "-m", "alembic", "heads"],
            cwd=str(backend_dir), text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        head = "error"
    return {
        "current": current.split()[-1] if current and current != "error" else current,
        "head": head.split()[-1] if head and head != "error" else head,
        "ready": current == head and current != "error",
    }


def run_migrations() -> bool:
    """Run alembic upgrade head. Returns True on success."""
    import subprocess
    backend_dir = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(backend_dir), capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"Migration failed: {result.stderr}", file=sys.stderr)
        return False
    print(f"Migration complete: {result.stdout.strip()}")
    return True


def check_pending_migrations() -> list[str]:
    """Return list of pending migration revisions."""
    import subprocess
    backend_dir = Path(__file__).resolve().parent.parent
    try:
        current = subprocess.check_output(
            [sys.executable, "-m", "alembic", "current"],
            cwd=str(backend_dir), text=True, stderr=subprocess.DEVNULL,
        ).strip()
        head = subprocess.check_output(
            [sys.executable, "-m", "alembic", "heads"],
            cwd=str(backend_dir), text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ["error_detecting_migrations"]
    current_rev = current.split()[-1] if current else ""
    head_rev = head.split()[-1] if head else ""
    if current_rev == head_rev:
        return []
    try:
        history = subprocess.check_output(
            [sys.executable, "-m", "alembic", "history", "-r", f"{current_rev}:{head_rev}"],
            cwd=str(backend_dir), text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ["error_reading_history"]
    return [line.strip() for line in history.split("\n") if line.strip() and "->" in line]


if __name__ == "__main__":
    import json
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        success = run_migrations()
        sys.exit(0 if success else 1)
    else:
        state = get_migration_state()
        print(json.dumps(state, indent=2))
        if not state["ready"]:
            pending = check_pending_migrations()
            if pending:
                print(f"Pending migrations: {len(pending)}")
