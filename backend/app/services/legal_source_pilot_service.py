
"""Pilot Legal Source Ingestion Service.

Handles manifest-based batch ingestion of local legal sources (TXT, PDF)
with SHA256 integrity, deterministic chunking, dedup/conflict detection,
and JSON reporting.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

VALID_SOURCE_TYPES = frozenset({
    "legislation", "regulation", "communique", "court_decision",
    "constitutional_court_decision", "council_of_state_decision",
    "petition_template", "legal_checklist", "internal_guidance", "other",
})

VALID_STATUSES = frozenset({"active", "repealed", "partially_repealed", "unknown"})

REQUIRED_MANIFEST_FIELDS = frozenset({"source_id", "title", "source_type", "authority", "file"})

ARTICLE_HEADING_RE = re.compile(
    r"^\s*(?:MADDE|Madde|madde)\s*(\d{1,4})(?:\s*[/.-]?\s*(.*))?$",
    re.MULTILINE,
)

SECTION_MARKERS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^\s*(BAŞLIK|BASLIK)\s*[:]?\s*(.*)", re.IGNORECASE), "title"),
    (re.compile(r"^\s*OLAY\s*[:]?\s*(.*)", re.IGNORECASE), "facts"),
    (re.compile(r"^\s*(GEREKÇE|GEREKCE)\s*[:]?\s*(.*)", re.IGNORECASE), "reasoning"),
    (re.compile(r"^\s*(HÜKÜM|HUKUM|SONUÇ|SONUC)\s*[:]?\s*(.*)", re.IGNORECASE), "ruling"),
]

CHUNK_MIN_WORDS = 50
CHUNK_MAX_WORDS = 1200


def _safe_path(source_dir: Path, file_rel: str) -> Path:
    raw = os.path.normpath(file_rel)
    if os.path.isabs(raw):
        raise ValueError(f"absolute_path_forbidden: {file_rel}")
    resolved = (source_dir / raw).resolve()
    if not str(resolved).startswith(str(source_dir.resolve())):
        raise ValueError(f"path_traversal_blocked: {file_rel}")
    if resolved.is_symlink():
        raise ValueError(f"symlink_forbidden: {file_rel}")
    return resolved


def _compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _extract_text(path: Path) -> tuple[str, list[str]]:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return path.read_text(encoding="utf-8"), []
    if suffix == ".pdf":
        return _extract_pdf(path)
    raise ValueError(f"unsupported_file_type: {suffix}")


def _extract_pdf(path: Path) -> tuple[str, list[str]]:
    warnings: list[str] = []
    for name, fn in (
        ("pymupdf", _extract_pymupdf),
        ("pdfplumber", _extract_pdfplumber),
        ("pypdf", _extract_pypdf),
    ):
        try:
            text = fn(path)
            if text and len(text.split()) > 10:
                return text, warnings
            if text and len(text.split()) <= 10:
                warnings.append("ocr_required")
                return "", warnings
        except Exception as exc:
            warnings.append(f"{name}_failed: {str(exc)[:80]}")
    return "", warnings or ["pdf_extraction_failed"]


def _extract_pymupdf(path: Path) -> str:
    import fitz
    parts: list[str] = []
    with fitz.open(path) as doc:
        for i, page in enumerate(doc):
            text = page.get_text("text") or ""
            if text.strip():
                parts.append(f"[sayfa {i + 1}]\n{text}")
    return "\n\n".join(parts)


def _extract_pdfplumber(path: Path) -> str:
    import pdfplumber
    parts: list[str] = []
    with pdfplumber.open(path) as doc:
        for i, page in enumerate(doc.pages):
            text = page.extract_text() or ""
            if text.strip():
                parts.append(f"[sayfa {i + 1}]\n{text}")
    return "\n\n".join(parts)


def _extract_pypdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            parts.append(f"[sayfa {i + 1}]\n{text}")
    return "\n\n".join(parts)


def _is_statute(source_type: str, text: str) -> bool:
    if source_type in ("legislation", "regulation", "communique"):
        return True
    return False


def _is_court_decision(source_type: str) -> bool:
    return source_type in (
        "court_decision", "constitutional_court_decision", "council_of_state_decision",
    )


def _chunk_text(source_id: str, text: str, metadata: dict, ingest_version: str) -> list[dict]:
    source_type = metadata.get("source_type", "other")
    if _is_statute(source_type, text):
        return _chunk_by_articles(source_id, text, metadata, ingest_version)
    if _is_court_decision(source_type):
        return _chunk_by_sections(source_id, text, metadata, ingest_version)
    return _chunk_by_window(source_id, text, metadata, ingest_version)


def _chunk_by_articles(source_id: str, text: str, metadata: dict, ingest_version: str) -> list[dict]:
    chunks: list[dict] = []
    lines = text.split("\n")
    current_article: str = ""
    current_lines: list[str] = []
    chunk_index = 0

    for line in lines:
        m = ARTICLE_HEADING_RE.match(line)
        if m:
            if current_lines:
                body = "\n".join(current_lines).strip()
                if body and len(body.split()) >= CHUNK_MIN_WORDS:
                    chunk_index += 1
                    chunk_id = _chunk_id(source_id, str(chunk_index), ingest_version)
                    chunks.append({
                        "chunk_id": chunk_id,
                        "source_id": source_id,
                        "text": body if current_article else body,
                        "article_number": current_article or None,
                        "section": "article" if current_article else "body",
                        "ingest_version": ingest_version,
                    })
                current_lines = []
            current_article = m.group(1)
            if m.lastindex and m.lastindex >= 2 and m.group(2):
                current_lines.append(m.group(2).strip())
        else:
            current_lines.append(line)

    if current_lines:
        body = "\n".join(current_lines).strip()
        if body and len(body.split()) >= CHUNK_MIN_WORDS:
            chunk_index += 1
            chunk_id = _chunk_id(source_id, str(chunk_index), ingest_version)
            chunks.append({
                "chunk_id": chunk_id,
                "source_id": source_id,
                "text": body,
                "article_number": current_article or None,
                "section": "article" if current_article else "body",
                "ingest_version": ingest_version,
            })

    return chunks


def _chunk_by_sections(source_id: str, text: str, metadata: dict, ingest_version: str) -> list[dict]:
    chunks: list[dict] = []
    lines = text.split("\n")
    current_section = "body"
    section_lines: list[str] = []
    chunk_index = 0

    for line in lines:
        matched = None
        leftover = ""
        for pattern, section_name in SECTION_MARKERS:
            m = pattern.match(line.strip())
            if m:
                matched = section_name
                if m.lastindex and m.lastindex >= 1:
                    leftover = (m.group(m.lastindex) or "").strip()
                break
        if matched:
            if section_lines:
                body = "\n".join(section_lines).strip()
                if body and len(body.split()) >= CHUNK_MIN_WORDS:
                    chunk_index += 1
                    chunk_id = _chunk_id(source_id, f"s{chunk_index}", ingest_version)
                    chunks.append({
                        "chunk_id": chunk_id,
                        "source_id": source_id,
                        "text": body,
                        "section": current_section,
                        "ingest_version": ingest_version,
                    })
                section_lines = []
            current_section = matched
            if leftover:
                section_lines.append(leftover)
        else:
            section_lines.append(line)

    if section_lines:
        body = "\n".join(section_lines).strip()
        if body and len(body.split()) >= CHUNK_MIN_WORDS:
            chunk_index += 1
            chunk_id = _chunk_id(source_id, f"s{chunk_index}", ingest_version)
            chunks.append({
                "chunk_id": chunk_id,
                "source_id": source_id,
                "text": body,
                "section": current_section,
                "ingest_version": ingest_version,
            })

    return chunks


def _chunk_by_window(source_id: str, text: str, metadata: dict, ingest_version: str) -> list[dict]:
    words = text.split()
    chunks: list[dict] = []
    chunk_index = 0
    start = 0
    while start < len(words):
        end = min(start + CHUNK_MAX_WORDS, len(words))
        chunk_text = " ".join(words[start:end])
        if len(words[start:end]) >= CHUNK_MIN_WORDS:
            chunk_index += 1
            chunk_id = _chunk_id(source_id, f"w{chunk_index}", ingest_version)
            chunks.append({
                "chunk_id": chunk_id,
                "source_id": source_id,
                "text": chunk_text,
                "section": "body",
                "ingest_version": ingest_version,
            })
        start = end
    return chunks


def _chunk_id(source_id: str, suffix: str, ingest_version: str) -> str:
    raw = f"{source_id}|{suffix}|{ingest_version}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


class LegalSourcePilotService:

    def __init__(self, data_dir: Path | None = None):
        if data_dir is None:
            data_dir = Path(__file__).resolve().parents[3] / "legal_sources" / "pilot"
        self.data_dir = data_dir
        self.ingested_dir = data_dir / "ingested"
        self.reports_dir = data_dir.parent / "reports"

    def load_manifest(self, manifest_path: Path) -> dict:
        if not manifest_path.exists():
            raise FileNotFoundError(f"manifest_not_found: {manifest_path}")
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "sources" not in raw:
            raise ValueError("manifest_missing_sources_array")
        sources = raw.get("sources", [])
        if not isinstance(sources, list):
            raise ValueError("manifest_sources_must_be_array")
        validated = []
        for i, src in enumerate(sources):
            if not isinstance(src, dict):
                raise ValueError(f"manifest_entry_{i}_not_object")
            vl = self._validate_source(src)
            validated.append(vl)
        return {"pilot_version": raw.get("pilot_version", "unknown"), "sources": validated}

    def _validate_source(self, src: dict) -> dict:
        missing = REQUIRED_MANIFEST_FIELDS - set(src.keys())
        if missing:
            raise ValueError(f"missing_required_fields: {sorted(missing)} for source_id={src.get('source_id', 'unknown')}")
        st = src.get("source_type", "")
        if st not in VALID_SOURCE_TYPES:
            raise ValueError(f"invalid_source_type: {st}")
        status = src.get("status", "unknown")
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid_status: {status}")
        return {
            "source_id": src["source_id"],
            "title": src["title"],
            "source_type": src["source_type"],
            "authority": src["authority"],
            "file": src["file"],
            "jurisdiction": src.get("jurisdiction", ""),
            "publication_date": src.get("publication_date", ""),
            "effective_date": src.get("effective_date", ""),
            "decision_date": src.get("decision_date", ""),
            "decision_number": src.get("decision_number", ""),
            "chamber": src.get("chamber", ""),
            "legislation_number": src.get("legislation_number", ""),
            "article_numbers": src.get("article_numbers", ""),
            "status": src.get("status", "unknown"),
            "language": src.get("language", "tr"),
        }

    def run_ingest(
        self,
        source_dir: Path,
        manifest_path: Path,
        dry_run: bool = False,
        force: bool = False,
        source_id_filter: str | None = None,
        report_path: Path | None = None,
        ingest_version: str = "pilot-v1",
    ) -> dict:
        started_at = datetime.now(UTC).isoformat()
        warnings: list[str] = []
        errors: list[str] = []

        manifest = self.load_manifest(manifest_path)
        sources = manifest["sources"]
        if source_id_filter:
            sources = [s for s in sources if s["source_id"] == source_id_filter]
            if not sources:
                raise ValueError(f"source_id_not_found_in_manifest: {source_id_filter}")

        index = self._load_index()
        registered_count = 0
        results: list[dict] = []
        stats = {
            "total_files": len(sources),
            "registered_sources": 0,
            "successful_sources": 0,
            "skipped_sources": 0,
            "duplicate_sources": 0,
            "conflicted_sources": 0,
            "failed_sources": 0,
            "total_chunks": 0,
        }

        known_files = self._scan_source_dir(source_dir)
        unregistered = known_files - {s["file"] for s in sources}
        if unregistered:
            warnings.append(f"unregistered_files_in_source_dir: {sorted(unregistered)}")

        for src_def in sources:
            try:
                file_rel = src_def["file"]
                source_path = _safe_path(source_dir, file_rel)

                if not source_path.exists():
                    errors.append(f"file_not_found: {file_rel}")
                    stats["failed_sources"] += 1
                    results.append(self._result_entry(src_def, "failed", error_code="file_not_found"))
                    continue

                sha256 = _compute_sha256(source_path)
                src_def["file_sha256"] = sha256

                dup_check = self._check_duplicate(index, src_def["source_id"], sha256, force)
                if dup_check["action"] == "skip":
                    stats["skipped_sources"] += 1
                    if dup_check["reason"] == "duplicate":
                        stats["duplicate_sources"] += 1
                    elif dup_check["reason"] == "conflict":
                        stats["conflicted_sources"] += 1
                    results.append(self._result_entry(src_def, "skipped",
                        error_code=dup_check["reason"], warning_codes=[dup_check["reason"]]))
                    continue

                stats["registered_sources"] += 1

                if dry_run:
                    stats["successful_sources"] += 1
                    results.append(self._result_entry(src_def, "dry_run_ok"))
                    continue

                try:
                    text, extraction_warnings = _extract_text(source_path)
                except ValueError as e:
                    errors.append(f"unsupported_type: {file_rel}")
                    stats["failed_sources"] += 1
                    results.append(self._result_entry(src_def, "failed", error_code="unsupported_file_type"))
                    continue

                warn_codes = []
                if extraction_warnings:
                    warn_codes.extend(extraction_warnings)

                if not text or len(text.split()) < 5:
                    if "ocr_required" in extraction_warnings:
                        warn_codes.append("ocr_required")
                    else:
                        errors.append(f"empty_or_unreadable: {file_rel}")
                        stats["failed_sources"] += 1
                        results.append(self._result_entry(src_def, "failed", error_code="empty_or_unreadable"))
                        continue

                chunks = _chunk_text(src_def["source_id"], text, src_def, ingest_version)
                src_def["ingest_version"] = ingest_version
                src_def["ingested_at"] = datetime.now(UTC).isoformat()
                src_def["chunk_count"] = len(chunks)

                if not dry_run:
                    self._persist_source(src_def, chunks)
                    index[src_def["source_id"]] = {
                        "sha256": sha256,
                        "ingest_version": ingest_version,
                        "ingested_at": src_def["ingested_at"],
                        "chunk_count": len(chunks),
                        "title": src_def["title"],
                    }
                    self._persist_index(index)

                stats["successful_sources"] += 1
                stats["total_chunks"] += len(chunks)
                results.append(self._result_entry(src_def, "success",
                    chunk_count=len(chunks), warning_codes=warn_codes if warn_codes else None))

            except ValueError as e:
                errors.append(str(e))
                stats["failed_sources"] += 1
                results.append(self._result_entry(src_def, "failed", error_code=str(e)[:100]))

        completed_at = datetime.now(UTC).isoformat()
        report = {
            "started_at": started_at,
            "completed_at": completed_at,
            "mode": "dry_run" if dry_run else "execute",
            "ingest_version": ingest_version,
            **stats,
            "warnings": warnings,
            "errors": errors,
            "sources": results,
        }
        if report_path:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return report

    def _scan_source_dir(self, source_dir: Path) -> set[str]:
        known: set[str] = set()
        src_root = source_dir.resolve()
        for f in source_dir.rglob("*"):
            if f.is_file() and str(f.resolve()).startswith(str(src_root)):
                known.add(str(f.relative_to(source_dir)).replace("\\", "/"))
        return known

    def _check_duplicate(self, index: dict, source_id: str, sha256: str, force: bool) -> dict:
        existing = index.get(source_id)
        if not existing:
            return {"action": "ingest"}
        if existing["sha256"] == sha256:
            if force:
                return {"action": "ingest"}
            return {"action": "skip", "reason": "duplicate"}
        if not force:
            return {"action": "skip", "reason": "conflict"}
        return {"action": "ingest"}

    def _result_entry(self, src_def: dict, status: str, **kwargs) -> dict:
        entry: dict[str, Any] = {
            "source_id": src_def.get("source_id", ""),
            "file": src_def.get("file", ""),
            "sha256": src_def.get("file_sha256", ""),
            "status": status,
        }
        for key in ("chunk_count", "warning_codes", "error_code"):
            if key in kwargs and kwargs[key] is not None:
                entry[key] = kwargs[key]
        return entry

    def _load_index(self) -> dict:
        idx_path = self.ingested_dir / "pilot_index.json"
        if idx_path.exists():
            return json.loads(idx_path.read_text(encoding="utf-8"))
        return {}

    def _persist_index(self, index: dict) -> None:
        self.ingested_dir.mkdir(parents=True, exist_ok=True)
        idx_path = self.ingested_dir / "pilot_index.json"
        idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    def _persist_source(self, src_def: dict, chunks: list[dict]) -> None:
        dest_dir = self.ingested_dir / src_def["source_id"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        meta = {
            k: v for k, v in src_def.items()
            if k not in ("file_sha256",)
        }
        meta["file_sha256"] = src_def.get("file_sha256", "")
        (dest_dir / "metadata.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        with open(dest_dir / "chunks.jsonl", "w", encoding="utf-8") as f:
            for chunk in chunks:
                f.write(json.dumps(chunk, ensure_ascii=False, default=str) + "\n")


pilot_service = LegalSourcePilotService()
