#!/usr/bin/env python3
"""Legal Brain source ingestion CLI.

Usage:
    python backend/scripts/ingest_legal_sources.py

Run from project root or from backend directory:
    python backend/scripts/ingest_legal_sources.py
    cd backend && python scripts/ingest_legal_sources.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure backend root is importable when run as a script.
# Works from both project root and backend/ directory.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.legal_source_ingest_service import legal_source_ingest_service  # noqa: E402
from app.services.legal_source_ingest_service import UPLOADS_DIR  # noqa: E402


def main() -> None:
    print("Legal Brain kaynak içeri aktarma başlatıldı.")
    print(f"Kaynak klasörü: {UPLOADS_DIR.resolve()}")

    result = legal_source_ingest_service.ingest_uploads()

    print(f"Bulunan dosya sayısı     : {result.get('files_found', 0)}")
    print(f"İşlenen dosya sayısı     : {result.get('files_processed', 0)}")
    print(f"Yeniden atlanan dosya    : {result.get('files_skipped', 0)}")
    print(f"Başarısız dosya          : {result.get('files_failed', 0)}")
    print(f"Oluşturulan kart sayısı  : {result.get('cards_created', 0)}")

    errors = result.get("errors", [])
    if errors:
        print("Hatalar:")
        for error in errors:
            print(f"  - {error}")


if __name__ == "__main__":
    main()