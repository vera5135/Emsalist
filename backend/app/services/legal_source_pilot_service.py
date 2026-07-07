
"""Pilot Legal Source Ingestion Service.

Handles manifest-based batch ingestion of local legal sources (TXT, PDF)
with SHA256 integrity, deterministic chunking, dedup/conflict detection,
atomic writes, symlink protection, and JSON reporting.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
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

SCAN_EXCLUDE_DIRS = frozenset({"ingested", "reports"})
SCAN_EXCLUDE_FILES = frozenset({"manifest.json"})


def _safe_path(source_dir: Path, file_rel: str) -> Path:
    raw = os.path.normpath(file_rel)
    if os.path.isabs(raw):
        raise ValueError(f"absolute_path_forbidden: {file_rel}")

    source_root = source_dir.resolve(strict=False)
    candidate = source_dir / raw

    if os.path.lexists(str(candidate)):
        if candidate.is_symlink():
            raise ValueError(f"symlink_forbidden: {file_rel}")

        if candidate.exists():
            resolved_candidate = candidate.resolve()
            try:
                resolved_candidate.relative_to(source_root)
            except ValueError:
                raise ValueError(f"path_traversal_blocked: {file_rel}")
            return resolved_candidate

    for parent in candidate.parents:
        if parent == source_dir or not str(parent).startswith(str(source_dir)):
            break
        if os.path.lexists(str(parent)):
            if parent.is_symlink():
                raise ValueError(f"symlink_forbidden: {file_rel}")
            if str(parent.resolve()) != str(parent):
                raise ValueError(f"symlink_forbidden: {file_rel}")

    return candidate


def _compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _read_text_utf8(path: Path) -> str:
    raw_bytes = path.read_bytes()
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return raw_bytes.decode("utf-8-sig")
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError(f"encoding_error: file is not valid UTF-8: {path.name}")


def _extract_text(path: Path) -> tuple[str, list[str]]:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return _read_text_utf8(path), []
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
    return "", list(set(warnings)) or ["unreadable_pdf"]


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
                        "text": body,
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


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _atomic_write_jsonl(path: Path, chunks: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False, default=str) + "\n")
    tmp.replace(path)


class LegalSourcePilotService:

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir
        self.ingested_dir = None
        self.reports_dir = None

    def _resolve_output_dirs(self, source_dir: Path) -> None:
        if self.ingested_dir is None:
            self.ingested_dir = source_dir / "ingested"
        if self.reports_dir is None:
            self.reports_dir = source_dir / "reports"

    def ingest_single_source(
        self,
        source_dir: Path,
        source_id: str,
        source_path_rel: str,
        source_def: dict,
        ingest_version: str,
        dry_run: bool = False,
        force: bool = False,
    ) -> dict:
        self._resolve_output_dirs(source_dir)
        index = self._load_index()
        file_rel = source_path_rel
        source_path = _safe_path(source_dir, file_rel)

        if not source_path.exists():
            return {"status": "failed", "error_code": "file_not_found"}

        sha256 = _compute_sha256(source_path)
        source_def = dict(source_def)
        source_def["file_sha256"] = sha256
        source_def["source_id"] = source_id

        dup_check = self._check_duplicate(index, source_id, sha256, force)
        if dup_check["action"] == "skip":
            warn = [dup_check["reason"]]
            result = self._result_entry(source_def, "skipped", error_code=dup_check["reason"], warning_codes=warn)
            return result

        cross_dup = self._check_cross_hash_duplicate(index, source_id, sha256)
        extra_warnings = []
        if cross_dup:
            extra_warnings.append(f"duplicate_content_with_source_ids: {sorted(cross_dup)}")

        if dry_run:
            result = self._result_entry(source_def, "dry_run_ok", warning_codes=extra_warnings or None)
            return result

        try:
            text, extraction_warnings = _extract_text(source_path)
        except ValueError:
            return {"status": "failed", "error_code": "unsupported_file_type", **self._base_entry(source_def)}

        warn_codes = list(extraction_warnings) + extra_warnings

        if not text or len(text.split()) < 5:
            code = "ocr_required" if "ocr_required" in extraction_warnings else "unreadable_pdf"
            return self._result_entry(source_def, "failed", error_code=code, warning_codes=warn_codes or None)

        chunks = _chunk_text(source_id, text, source_def, ingest_version)
        if not chunks:
            return self._result_entry(source_def, "failed", error_code="no_chunks_produced", warning_codes=warn_codes or None)

        source_def["ingest_version"] = ingest_version
        source_def["ingested_at"] = datetime.now(UTC).isoformat()
        source_def["chunk_count"] = len(chunks)

        self._persist_source(source_def, chunks)
        index[source_id] = {
            "sha256": sha256,
            "ingest_version": ingest_version,
            "ingested_at": source_def["ingested_at"],
            "chunk_count": len(chunks),
            "title": source_def["title"],
        }
        self._persist_index(index)

        return self._result_entry(source_def, "success",
            chunk_count=len(chunks), warning_codes=warn_codes or None)

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
        self._resolve_output_dirs(source_dir)
        started_at = datetime.now(UTC).isoformat()
        warnings: list[str] = []
        errors: list[str] = []

        manifest = self.load_manifest(manifest_path)
        sources = manifest["sources"]
        if source_id_filter:
            sources = [s for s in sources if s["source_id"] == source_id_filter]
            if not sources:
                raise ValueError(f"source_id_not_found_in_manifest: {source_id_filter}")

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
        manifest_sources_set = {s["file"] for s in sources}
        unregistered = known_files - manifest_sources_set
        if unregistered:
            warnings.append(f"unregistered_files_in_source_dir: {sorted(unregistered)}")

        for src_def in sources:
            try:
                result = self.ingest_single_source(
                    source_dir=source_dir,
                    source_id=src_def["source_id"],
                    source_path_rel=src_def["file"],
                    source_def=src_def,
                    ingest_version=ingest_version,
                    dry_run=dry_run,
                    force=force,
                )
                status = result.get("status", "failed")
                if status == "success":
                    stats["successful_sources"] += 1
                    stats["registered_sources"] += 1
                    stats["total_chunks"] += result.get("chunk_count", 0)
                elif status == "dry_run_ok":
                    stats["successful_sources"] += 1
                    stats["registered_sources"] += 1
                elif status == "skipped":
                    stats["skipped_sources"] += 1
                    error_code = result.get("error_code", "")
                    if error_code == "duplicate":
                        stats["duplicate_sources"] += 1
                    elif error_code == "conflict":
                        stats["conflicted_sources"] += 1
                elif status == "failed":
                    stats["failed_sources"] += 1
                    if result.get("error_code"):
                        errors.append(f"{result.get('source_id')}: {result['error_code']}")
                results.append(result)
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
        else:
            self.reports_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            (self.reports_dir / f"ingest-report-{ts}.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return report

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

    def _scan_source_dir(self, source_dir: Path) -> set[str]:
        known: set[str] = set()
        src_root = source_dir.resolve()
        for f in source_dir.rglob("*"):
            if not str(f.resolve()).startswith(str(src_root)):
                continue
            if f.is_file():
                rel = str(f.relative_to(source_dir)).replace("\\", "/")
                parts = rel.split("/")
                if any(p in SCAN_EXCLUDE_DIRS for p in parts):
                    continue
                if f.name in SCAN_EXCLUDE_FILES:
                    continue
                if f.name.startswith("."):
                    continue
                if f.name.endswith(".tmp"):
                    continue
                if f.suffix in (".json", ".jsonl") and any(
                    d in parts for d in ("ingested", "reports")
                ):
                    continue
                known.add(rel)
        return known

    def _base_entry(self, src_def: dict) -> dict:
        return {
            "source_id": src_def.get("source_id", ""),
            "file": src_def.get("file", ""),
            "sha256": src_def.get("file_sha256", ""),
        }

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

    def _check_cross_hash_duplicate(self, index: dict, source_id: str, sha256: str) -> list[str]:
        conflicts = []
        for sid, entry in index.items():
            if sid == source_id:
                continue
            if entry.get("sha256") == sha256:
                conflicts.append(sid)
        return conflicts

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
        _atomic_write_json(self.ingested_dir / "pilot_index.json", index)

    def _persist_source(self, src_def: dict, chunks: list[dict]) -> None:
        dest_dir = self.ingested_dir / src_def["source_id"]
        meta = {k: v for k, v in src_def.items() if k not in ("file_sha256",)}
        meta["file_sha256"] = src_def.get("file_sha256", "")
        _atomic_write_json(dest_dir / "metadata.json", meta)
        _atomic_write_jsonl(dest_dir / "chunks.jsonl", chunks)


pilot_service = LegalSourcePilotService()
