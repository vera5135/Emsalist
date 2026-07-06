
"""Pilot Legal Source Ingestion CLI.

Usage:
    python -m app.scripts.ingest_legal_sources --source-dir ../legal_sources/pilot --manifest ../legal_sources/pilot/manifest.json --dry-run
    python -m app.scripts.ingest_legal_sources --source-dir ../legal_sources/pilot --manifest ../legal_sources/pilot/manifest.json --execute
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Emsalist Legal Source Pilot Ingest")
    parser.add_argument("--source-dir", required=True, help="Pilot kaynak dizini")
    parser.add_argument("--manifest", required=True, help="manifest.json dosya yolu")
    parser.add_argument("--output-dir", type=str, default="", help="Cikti dizini (varsayilan: <source_dir>/ingested)")
    parser.add_argument("--dry-run", action="store_true", help="Veri degistirmeden dogrula")
    parser.add_argument("--execute", action="store_true", help="Gercek ingest islemini calistir")
    parser.add_argument("--source-id", type=str, default="", help="Yalniz belirtilen source_id islensin")
    parser.add_argument("--force", action="store_true", help="Duplicate/conflict kontrolunu atla")
    parser.add_argument("--report-path", type=str, default="", help="Rapor dosyasi yolu")
    parser.add_argument("--ingest-version", type=str, default="pilot-v1", help="Ingest surum etiketi")
    args = parser.parse_args()

    from app.config import get_settings
    from app.core.logging import setup_logging

    settings = get_settings()
    os.environ.setdefault("EMSALIST_ENVIRONMENT", settings.environment)
    os.environ.setdefault("EMSALIST_LOG_LEVEL", settings.log_level)
    os.environ.setdefault("EMSALIST_LOG_FORMAT", settings.log_format)
    os.environ.setdefault("EMSALIST_LOG_SERVICE_NAME", settings.log_service_name)
    setup_logging()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if args.dry_run and args.execute:
        print("HATA: --dry-run ve --execute ayni anda kullanilamaz.", file=sys.stderr)
        sys.exit(2)

    if not args.dry_run and not args.execute:
        print("HATA: --dry-run veya --execute belirtilmelidir.", file=sys.stderr)
        sys.exit(2)

    source_dir = Path(args.source_dir).resolve()
    manifest_path = Path(args.manifest).resolve()

    if not source_dir.is_dir():
        print(f"HATA: Kaynak dizini bulunamadi: {source_dir}", file=sys.stderr)
        sys.exit(1)

    if not manifest_path.is_file():
        print(f"HATA: Manifest dosyasi bulunamadi: {manifest_path}", file=sys.stderr)
        sys.exit(1)

    report_path = None
    if args.report_path:
        report_path = Path(args.report_path)
    else:
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        reports_dir = source_dir / "reports"
        report_path = reports_dir / f"ingest-report-{ts}.json"

    from app.services.legal_source_pilot_service import LegalSourcePilotService

    output_dir = None
    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
        if not str(output_dir).startswith(str(source_dir)):
            print(f"HATA: --output-dir ({output_dir}) source_dir disina cikamaz", file=sys.stderr)
            sys.exit(1)

    pilot_service = LegalSourcePilotService(data_dir=output_dir)

    dry_run = args.dry_run
    source_id_filter = args.source_id.strip() or None

    print(f"\n=== Emsalist Legal Source Pilot Ingest ===")
    print(f"  Mode: {'DRY-RUN' if dry_run else 'EXECUTE'}")
    print(f"  Source Dir: {source_dir}")
    print(f"  Manifest: {manifest_path}")
    print(f"  Report: {report_path}")
    if source_id_filter:
        print(f"  Filter: source_id={source_id_filter}")
    print()

    report = pilot_service.run_ingest(
        source_dir=source_dir,
        manifest_path=manifest_path,
        dry_run=dry_run,
        force=args.force,
        source_id_filter=source_id_filter,
        report_path=report_path,
        ingest_version=args.ingest_version,
    )

    _print_summary(report)

    if report.get("errors") or report.get("failed_sources", 0) > 0:
        sys.exit(1)


def _print_summary(report: dict) -> None:
    print("=== Sonuc ===")
    print(f"  Mod: {report['mode']}")
    print(f"  Toplam dosya: {report['total_files']}")
    print(f"  Kayitli kaynak: {report['registered_sources']}")
    print(f"  Basarili: {report['successful_sources']}")
    print(f"  Atlanan: {report['skipped_sources']}")
    print(f"  Duplicate: {report['duplicate_sources']}")
    print(f"  Conflict: {report['conflicted_sources']}")
    print(f"  Basarisiz: {report['failed_sources']}")
    print(f"  Toplam chunk: {report['total_chunks']}")

    if report.get("warnings"):
        print(f"\n  Uyarilar ({len(report['warnings'])}):")
        for w in report["warnings"]:
            print(f"    - {w}")

    if report.get("errors"):
        print(f"\n  Hatalar ({len(report['errors'])}):")
        for e in report["errors"]:
            print(f"    - {e}")

    print(f"\n  Rapor: {report.get('report_path', 'N/A')}")


if __name__ == "__main__":
    main()
