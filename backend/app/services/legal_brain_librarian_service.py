"""Legal Brain Librarian Agent - continuous learning service for legal sources."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LEGAL_BRAIN_ROOT = Path(__file__).resolve().parents[1] / "legal_brain"
UPLOADS_DIR = LEGAL_BRAIN_ROOT / "uploads"
SOURCES_DIR = LEGAL_BRAIN_ROOT / "sources"
INTERNET_SOURCES_DIR = LEGAL_BRAIN_ROOT / "internet_sources"
LIBRARY_DIR = LEGAL_BRAIN_ROOT / "library"
METADATA_DIR = LEGAL_BRAIN_ROOT / "metadata"

SUPPORTED_EXTENSIONS = {".txt", ".md", ".json", ".html", ".htm", ".pdf", ".docx"}
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
DEFAULT_CHUNK_PAGES = 20
DEFAULT_MAX_PAGES_PER_RUN = 100
DEFAULT_MAX_CHUNK_CHARS = 25000
MIN_WATCH_INTERVAL = 60
DEFAULT_WATCH_INTERVAL = 300
LOCK_MAX_AGE_SECONDS = 2 * 60 * 60


class LegalBrainLibrarianService:
    """Continuous learning agent for Legal Brain library."""

    def __init__(self) -> None:
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for directory in [UPLOADS_DIR, SOURCES_DIR, LIBRARY_DIR, METADATA_DIR]:
            directory.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Lock / status helpers
    # ------------------------------------------------------------------
    def _lock_path(self) -> Path:
        return METADATA_DIR / "librarian_agent.lock"

    def _status_path(self) -> Path:
        return METADATA_DIR / "librarian_status.json"

    def _registry_path(self) -> Path:
        return METADATA_DIR / "librarian_registry.json"

    def _log_path(self) -> Path:
        return METADATA_DIR / "librarian_agent.log"

    def _acquire_lock(self) -> bool:
        lock = self._lock_path()
        if lock.exists():
            age = time.time() - lock.stat().st_mtime
            if age < LOCK_MAX_AGE_SECONDS:
                return False
            try:
                lock.unlink()
            except OSError:
                return False
        try:
            lock.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
        except OSError:
            return False
        return True

    def _release_lock(self) -> None:
        try:
            self._lock_path().unlink()
        except OSError:
            pass

    def _update_status(self, **kwargs: Any) -> None:
        path = self._status_path()
        data: dict[str, Any] = {
            "agent_name": "Legal Brain Librarian Agent",
            "is_running": True,
            "mode": kwargs.get("mode", "once"),
            "last_started_at": kwargs.get("last_started_at", datetime.now(timezone.utc).isoformat()),
            "last_scan_at": kwargs.get("last_scan_at"),
            "last_completed_at": kwargs.get("last_completed_at"),
            "watch_paths": [str(UPLOADS_DIR), str(SOURCES_DIR), str(INTERNET_SOURCES_DIR)],
            "files_seen": kwargs.get("files_seen", 0),
            "files_learned": kwargs.get("files_learned", 0),
            "files_skipped": kwargs.get("files_skipped", 0),
            "files_failed": kwargs.get("files_failed", 0),
            "cards_created": kwargs.get("cards_created", 0),
            "last_error": kwargs.get("last_error"),
        }
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(existing, dict):
                    data = {**existing, **data}
            except (json.JSONDecodeError, TypeError):
                pass
        try:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _append_log(self, message: str) -> None:
        path = self._log_path()
        line = f"[{datetime.now(timezone.utc).isoformat()}] {message}\n"
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Registry helpers
    # ------------------------------------------------------------------
    def _load_registry(self) -> dict[str, Any]:
        path = self._registry_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, TypeError):
                pass
        return {"files": {}}

    def _save_registry(self, registry: dict[str, Any]) -> None:
        try:
            self._registry_path().write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _update_registry_entry(self, file_path: Path, file_hash: str, **kwargs: Any) -> None:
        registry = self._load_registry()
        rel = str(file_path.relative_to(LEGAL_BRAIN_ROOT))
        entry: dict[str, Any] = {
            "file_hash": file_hash,
            "file_size": file_path.stat().st_size,
            "last_modified": datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc).isoformat(),
            "status": kwargs.get("status", "learned"),
            "last_seen_at": datetime.now(timezone.utc).isoformat(),
            "last_learned_at": datetime.now(timezone.utc).isoformat(),
            "error_message": kwargs.get("error_message"),
            "warnings": kwargs.get("warnings", []),
        }
        entry.update(kwargs)
        registry.setdefault("files", {})[rel] = entry
        self._save_registry(registry)

    # ------------------------------------------------------------------
    # File discovery / hashing
    # ------------------------------------------------------------------
    def discover_source_files(self) -> list[Path]:
        files: list[Path] = []
        if UPLOADS_DIR.exists():
            files.extend(sorted(p for p in UPLOADS_DIR.iterdir() if p.is_file() and self._is_supported(p)))
        if SOURCES_DIR.exists():
            for source_dir in SOURCES_DIR.iterdir():
                if source_dir.is_dir():
                    files.extend(sorted(p for p in source_dir.rglob("*") if p.is_file() and self._is_supported(p)))
        if INTERNET_SOURCES_DIR.exists():
            for source_dir in INTERNET_SOURCES_DIR.iterdir():
                if source_dir.is_dir():
                    files.extend(sorted(p for p in source_dir.rglob("*") if p.is_file() and self._is_supported(p)))
        return files

    def _is_supported(self, file_path: Path) -> bool:
        if file_path.name.startswith("."):
            return False
        return file_path.suffix.lower() in SUPPORTED_EXTENSIONS

    def hash_file(self, file_path: Path) -> str:
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()[:16]

    # ------------------------------------------------------------------
    # Source reading
    # ------------------------------------------------------------------
    def read_source_text(self, file_path: Path) -> str:
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            return self._read_pdf_text(file_path)
        if suffix == ".docx":
            return self._read_docx_text(file_path)
        return self._read_plain_text(file_path)

    def _read_plain_text(self, file_path: Path) -> str:
        encodings = ["utf-8-sig", "utf-8", "cp1254", "latin-1"]
        for encoding in encodings:
            try:
                return file_path.read_text(encoding=encoding, errors="strict")
            except (OSError, UnicodeDecodeError):
                continue
        return ""

    def _read_docx_text(self, file_path: Path) -> str:
        try:
            import docx  # type: ignore
        except ImportError:
            return ""
        try:
            doc = docx.Document(str(file_path))
            return "\n".join(p.text for p in doc.paragraphs if p.text)
        except Exception:
            return ""

    def read_pdf_chunks(self, file_path: Path, chunk_pages: int = DEFAULT_CHUNK_PAGES, max_pages: int = DEFAULT_MAX_PAGES_PER_RUN):
        try:
            import fitz  # type: ignore
        except ImportError:
            try:
                import pdfplumber  # type: ignore
            except ImportError:
                return []
            return self._read_pdfplumber_chunks(file_path, chunk_pages, max_pages)
        return self._read_fitz_chunks(file_path, chunk_pages, max_pages)

    def _read_fitz_chunks(self, file_path: Path, chunk_pages: int, max_pages: int):
        chunks: list[dict[str, Any]] = []
        try:
            doc = fitz.open(str(file_path))
            total_pages = len(doc)
            max_pages = min(total_pages, max_pages)
            for start in range(0, max_pages, chunk_pages):
                end = min(start + chunk_pages, max_pages)
                text = "\n".join(page.get_text() for page in doc[start:end])
                if not text.strip():
                    continue
                chunks.append({
                    "start_page": start + 1,
                    "end_page": end,
                    "text": text[:DEFAULT_MAX_CHUNK_CHARS],
                })
            doc.close()
        except Exception:
            return []
        return chunks

    def _read_pdfplumber_chunks(self, file_path: Path, chunk_pages: int, max_pages: int):
        chunks: list[dict[str, Any]] = []
        try:
            import pdfplumber  # type: ignore
            with pdfplumber.open(str(file_path)) as pdf:
                total_pages = len(pdf.pages)
                max_pages = min(total_pages, max_pages)
                for start in range(0, max_pages, chunk_pages):
                    end = min(start + chunk_pages, max_pages)
                    parts: list[str] = []
                    for i in range(start, end):
                        page = pdf.pages[i]
                        parts.append(page.extract_text() or "")
                    text = "\n".join(parts)
                    if not text.strip():
                        continue
                    chunks.append({
                        "start_page": start + 1,
                        "end_page": end,
                        "text": text[:DEFAULT_MAX_CHUNK_CHARS],
                    })
        except Exception:
            return []
        return chunks

    def _read_pdf_text(self, file_path: Path) -> str:
        chunks = self.read_pdf_chunks(file_path)
        return "\n\n".join(c["text"] for c in chunks)

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------
    def classify_source(self, path: Path, text_preview: str) -> dict[str, Any]:
        try:
            from app.services.legal_brain_source_classifier import legal_brain_source_classifier
            result = legal_brain_source_classifier.classify(text=text_preview, source_file=path.name)
        except Exception:
            result = {
                "source_type": "unknown",
                "source_reliability": "low",
                "warnings": ["Sınıflandırma servisi kullanılamadı."],
            }

        # Fallback: path-based statute detection
        if result.get("source_type") == "unknown":
            path_str = str(path).lower()
            if "sources/statutes" in path_str or "sources\\statutes" in path_str:
                result["source_type"] = "statute"
                result["source_reliability"] = "high"
                if "warnings" not in result:
                    result["warnings"] = []
                result["warnings"].append("Dosya yolu üzerinden statute olarak sınıflandırıldı.")

        # Fallback: content-based statute detection
        if result.get("source_type") == "unknown":
            plain_preview = self._plain(text_preview[:3000])
            if "türk borçlar kanunu" in plain_preview or "borçlar kanunu" in plain_preview:
                result["source_type"] = "statute"
                result["source_reliability"] = "high"
                if "warnings" not in result:
                    result["warnings"] = []
                result["warnings"].append("İçerik üzerinden TBK statute olarak sınıflandırıldı.")
            elif "madde 315" in plain_preview or "m. 315" in plain_preview:
                result["source_type"] = "statute"
                result["source_reliability"] = "high"
                if "warnings" not in result:
                    result["warnings"] = []
                result["warnings"].append("Madde içeriği üzerinden statute olarak sınıflandırıldı.")

        return result

    # ------------------------------------------------------------------
    # Card builders
    # ------------------------------------------------------------------
    def build_statute_cards(self, text: str, metadata: dict[str, Any], file_path: Path, file_hash: str) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        try:
            from app.services.legal_brain_statute_parser import legal_brain_statute_parser
            parsed = legal_brain_statute_parser.parse_text(text=text, metadata=metadata)
            articles = parsed.get("parsed_articles", [])
            codes = parsed.get("parsed_codes", [])
        except Exception:
            articles = []
            codes = []

        # Fallback: extract articles using regex if parser didn't find any or returned invalid data
        if not articles or self._validate_articles(articles, text) == False:
            articles = self._extract_articles_with_regex(text)

        code = self._detect_primary_code(text, codes)
        library_folder = self._resolve_statute_folder(code, file_path)

        for idx, article in enumerate(articles[:50], start=1):
            article_no = self._extract_article_no(article)
            if not article_no:
                continue
            card_id = f"{file_path.stem}_{file_hash}_MADDE_{article_no:03d}"
            
            # Default values
            legal_area = metadata.get("legal_area_candidates", [{}])[0].get("legal_area", "belirsiz")
            related_case_types = metadata.get("detected_case_types", [])[:5]
            keywords = metadata.get("detected_codes", [])[:10]
            question_suggestions = []
            
            # TBK 315 special metadata matching
            if code == "TBK" and str(article_no) == "315":
                legal_area = "kira hukuku"
                related_case_types = ["kira temerrüt", "temerrüt nedeniyle tahliye", "kira alacağı"]
                keywords = ["TBK 315", "kira", "temerrüt", "kiracı", "otuz gün", "fesih"]
                question_suggestions = [
                    {"id": f"q_{card_id}_1", "question": "Kiracı hangi kira aylarını ödemedi?", "category": "factual"},
                    {"id": f"q_{card_id}_2", "question": "Kiracıya yazılı ihtar gönderildi mi?", "category": "procedural"},
                    {"id": f"q_{card_id}_3", "question": "İhtarda en az otuz günlük süre verildi mi?", "category": "procedural"},
                    {"id": f"q_{card_id}_4", "question": "İhtarname kiracıya hangi tarihte tebliğ edildi?", "category": "factual"},
                ]
            
            card = {
                "card_id": card_id,
                "card_type": "statute_article",
                "code": code,
                "article_no": str(article_no),
                "title": "",
                "article_text": article,
                "plain_text": self._plain(article),
                "legal_area": legal_area,
                "related_case_types": related_case_types,
                "keywords": keywords,
                "legal_rules": [],
                "procedural_requirements": [],
                "limitation_or_deadline_risks": [],
                "required_facts": [],
                "required_evidence": [],
                "question_suggestions": question_suggestions,
                "source_file": str(file_path.relative_to(LEGAL_BRAIN_ROOT)),
                "source_type": "statute",
                "source_reliability": metadata.get("source_reliability", "high"),
                "learning_value": "high",
                "safe_for_legal_basis": True,
                "safe_for_question_generation": True,
                "safe_for_petition_style": False,
                "learned_at": datetime.now(timezone.utc).isoformat(),
                "warnings": metadata.get("warnings", []),
                "library_folder": str(library_folder.relative_to(LIBRARY_DIR)),
            }
            cards.append(card)
        return cards

    def build_case_law_cards(self, text: str, metadata: dict[str, Any], file_path: Path, file_hash: str) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        source_type = metadata.get("source_type", "unknown")
        if source_type == "yargitay_decision":
            library_folder = LIBRARY_DIR / "yargitay"
        elif source_type == "danistay_decision":
            library_folder = LIBRARY_DIR / "danistay"
        elif source_type == "constitutional_court_decision":
            library_folder = LIBRARY_DIR / "aym"
        else:
            library_folder = LIBRARY_DIR / "unsorted"

        esas, karar = self._extract_decision_numbers(text)
        court, chamber = self._extract_court_info(text, source_type)
        decision_date = self._extract_decision_date(text)

        card_id = f"{file_path.stem}_{file_hash}"
        if esas:
            card_id = f"{file_path.stem}_{file_hash}_{self._safe_id(esas)}"
        card = {
            "card_id": card_id,
            "card_type": "case_law",
            "court": court,
            "chamber": chamber,
            "esas_no": esas,
            "karar_no": karar,
            "decision_date": decision_date,
            "legal_area": metadata.get("legal_area_candidates", [{}])[0].get("legal_area", "belirsiz"),
            "case_type": metadata.get("detected_case_types", [""])[0] if metadata.get("detected_case_types") else "",
            "facts_summary": "",
            "legal_issue": "",
            "holding": text[:4000],
            "legal_principle": "",
            "required_facts": [],
            "required_evidence": [],
            "common_defenses": [],
            "procedural_notes": [],
            "risk_flags": [],
            "question_suggestions": [],
            "source_file": str(file_path.relative_to(LEGAL_BRAIN_ROOT)),
            "source_type": source_type,
            "source_reliability": metadata.get("source_reliability", "high"),
            "learning_value": "high",
            "safe_for_legal_basis": True,
            "safe_for_question_generation": True,
            "safe_for_petition_style": False,
            "learned_at": datetime.now(timezone.utc).isoformat(),
            "warnings": metadata.get("warnings", []),
            "library_folder": str(library_folder.relative_to(LIBRARY_DIR)),
        }
        cards.append(card)
        return cards

    def build_doctrine_cards(self, text: str, metadata: dict[str, Any], file_path: Path, file_hash: str) -> list[dict[str, Any]]:
        source_type = metadata.get("source_type", "unknown")
        if source_type in ("bar_publication", "baro_tbb"):
            library_folder = LIBRARY_DIR / "baro_tbb"
        elif source_type == "petition_sample":
            library_folder = LIBRARY_DIR / "petition_samples"
        elif source_type == "procedural_guide":
            library_folder = LIBRARY_DIR / "practice_guides"
        elif source_type == "user_verified_note":
            library_folder = LIBRARY_DIR / "user_verified_notes"
        elif source_type in ("doctrine", "academic"):
            library_folder = LIBRARY_DIR / "doctrine"
        else:
            library_folder = LIBRARY_DIR / "unsorted"

        card_id = f"{file_path.stem}_{file_hash}"
        if source_type == "petition_sample":
            card = {
                "card_id": card_id,
                "card_type": "petition_style",
                "legal_area": metadata.get("legal_area_candidates", [{}])[0].get("legal_area", "belirsiz"),
                "case_type": metadata.get("detected_case_types", [""])[0] if metadata.get("detected_case_types") else "",
                "court_heading_patterns": [],
                "subject_patterns": [],
                "fact_narrative_patterns": [],
                "evidence_linking_patterns": [],
                "legal_reasoning_patterns": [],
                "request_result_patterns": [],
                "source_file": str(file_path.relative_to(LEGAL_BRAIN_ROOT)),
                "source_type": "petition_sample",
                "source_reliability": "medium",
                "learning_value": "medium",
                "safe_for_legal_basis": False,
                "safe_for_question_generation": False,
                "safe_for_petition_style": True,
                "learned_at": datetime.now(timezone.utc).isoformat(),
                "warnings": metadata.get("warnings", []),
                "library_folder": str(library_folder.relative_to(LIBRARY_DIR)),
            }
        else:
            card = {
                "card_id": card_id,
                "card_type": "doctrine_or_practice_note",
                "legal_area": metadata.get("legal_area_candidates", [{}])[0].get("legal_area", "belirsiz"),
                "case_type": metadata.get("detected_case_types", [""])[0] if metadata.get("detected_case_types") else "",
                "summary": text[:4000],
                "legal_rules": [],
                "required_facts": [],
                "required_evidence": [],
                "procedural_requirements": [],
                "limitation_or_deadline_risks": [],
                "common_defenses": [],
                "petition_language_patterns": [],
                "question_suggestions": [],
                "source_file": str(file_path.relative_to(LEGAL_BRAIN_ROOT)),
                "source_type": source_type,
                "source_reliability": metadata.get("source_reliability", "medium"),
                "learning_value": "medium",
                "safe_for_legal_basis": False,
                "safe_for_question_generation": True,
                "safe_for_petition_style": True,
                "learned_at": datetime.now(timezone.utc).isoformat(),
                "warnings": metadata.get("warnings", []),
                "library_folder": str(library_folder.relative_to(LIBRARY_DIR)),
            }
        return [card]

    def build_unknown_cards(self, text: str, metadata: dict[str, Any], file_path: Path, file_hash: str) -> list[dict[str, Any]]:
        library_folder = LIBRARY_DIR / "unsorted"
        card_id = f"{file_path.stem}_{file_hash}"
        card = {
            "card_id": card_id,
            "card_type": "miscellaneous",
            "legal_area": metadata.get("legal_area_candidates", [{}])[0].get("legal_area", "belirsiz"),
            "case_type": metadata.get("detected_case_types", [""])[0] if metadata.get("detected_case_types") else "",
            "summary": text[:4000],
            "legal_rules": [],
            "required_facts": [],
            "required_evidence": [],
            "procedural_requirements": [],
            "limitation_or_deadline_risks": [],
            "common_defenses": [],
            "petition_language_patterns": [],
            "question_suggestions": [],
            "source_file": str(file_path.relative_to(LEGAL_BRAIN_ROOT)),
            "source_type": metadata.get("source_type", "unknown"),
            "source_reliability": metadata.get("source_reliability", "low"),
            "learning_value": "low",
            "safe_for_legal_basis": False,
            "safe_for_question_generation": False,
            "safe_for_petition_style": False,
            "learned_at": datetime.now(timezone.utc).isoformat(),
            "warnings": metadata.get("warnings", []),
            "library_folder": str(library_folder.relative_to(LIBRARY_DIR)),
        }
        return [card]

    # ------------------------------------------------------------------
    # File learning
    # ------------------------------------------------------------------
    def learn_file(self, file_path: Path) -> dict[str, Any]:
        result: dict[str, Any] = {
            "file": str(file_path),
            "status": "failed",
            "cards_created": 0,
            "error": None,
            "warnings": [],
        }
        try:
            if not file_path.exists() or not file_path.is_file():
                result["error"] = "Dosya bulunamadı."
                return result

            file_hash = self.hash_file(file_path)
            registry = self._load_registry()
            rel = str(file_path.relative_to(LEGAL_BRAIN_ROOT))
            existing = registry.get("files", {}).get(rel)
            if existing and existing.get("file_hash") == file_hash:
                existing_status = existing.get("status", "")
                if existing_status == "learned":
                    result["status"] = "skipped"
                    return result
                # For skipped, failed, unsorted, partial: retry processing

            text = self.read_source_text(file_path)
            if not text or not text.strip():
                result["status"] = "skipped"
                result["error"] = "Metin çıkarılamadı."
                self._update_registry_entry(file_path, file_hash, status="skipped", error_message=result["error"])
                return result

            metadata = self.classify_source(file_path, text[:8000])
            source_type = metadata.get("source_type", "unknown")

            # Detect code early for error reporting
            code = "unknown"
            if source_type in ("statute", "official_gazette"):
                try:
                    from app.services.legal_brain_statute_parser import legal_brain_statute_parser
                    parsed = legal_brain_statute_parser.parse_text(text=text, metadata=metadata)
                    code = self._detect_primary_code(text, parsed.get("parsed_codes", []))
                except Exception:
                    code = self._detect_primary_code(text, [])

            if source_type in ("statute", "official_gazette"):
                cards = self.build_statute_cards(text, metadata, file_path, file_hash)
            elif source_type in ("case_law", "yargitay_decision", "danistay_decision", "constitutional_court_decision"):
                cards = self.build_case_law_cards(text, metadata, file_path, file_hash)
            elif source_type in ("doctrine", "bar_publication", "petition_sample", "procedural_guide", "user_verified_note", "academic"):
                cards = self.build_doctrine_cards(text, metadata, file_path, file_hash)
            else:
                cards = self.build_unknown_cards(text, metadata, file_path, file_hash)

            if not cards:
                result["status"] = "skipped"
                result["error"] = "Kart üretilemedi."
                # Build detailed warnings for debugging
                debug_warnings = [
                    f"source_type={source_type}",
                    f"text_length={len(text)}",
                    f"code_detected={code}",
                ]
                if source_type in ("statute", "official_gazette"):
                    try:
                        from app.services.legal_brain_statute_parser import legal_brain_statute_parser
                        parsed = legal_brain_statute_parser.parse_text(text=text, metadata=metadata)
                        articles_count = len(parsed.get("parsed_articles", []))
                        debug_warnings.append(f"article_matches_count={articles_count}")
                    except Exception as parse_exc:
                        debug_warnings.append(f"parse_error={str(parse_exc)}")
                    
                    # Also check regex fallback
                    regex_articles = self._extract_articles_with_regex(text)
                    debug_warnings.append(f"regex_article_matches={len(regex_articles)}")
                    
                    if not text or len(text.strip()) < 50:
                        debug_warnings.append("text_too_short_or_empty")
                    if source_type == "unknown":
                        debug_warnings.append("source_type_is_unknown")
                result["warnings"] = debug_warnings
                self._update_registry_entry(
                    file_path,
                    file_hash,
                    status="skipped",
                    error_message=result["error"],
                    warnings=debug_warnings,
                )
                return result

            for card in cards:
                card_path = self._resolve_card_path(card)
                card_path.parent.mkdir(parents=True, exist_ok=True)
                card_path.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")

            self.update_indexes(cards)
            self._update_registry_entry(
                file_path,
                file_hash,
                status="learned",
                source_type=source_type,
                source_reliability=metadata.get("source_reliability"),
                legal_area=metadata.get("legal_area_candidates", [{}])[0].get("legal_area"),
                case_type=metadata.get("detected_case_types", [""])[0] if metadata.get("detected_case_types") else "",
                library_folder=cards[0].get("library_folder", "unsorted"),
                cards_created=len(cards),
                warnings=metadata.get("warnings", []),
            )
            result["status"] = "learned"
            result["cards_created"] = len(cards)
        except Exception as exc:
            result["error"] = str(exc)
            try:
                self._update_registry_entry(file_path, self.hash_file(file_path), status="failed", error_message=str(exc))
            except Exception:
                pass
        return result

    def _resolve_card_path(self, card: dict[str, Any]) -> Path:
        folder = card.get("library_folder", "unsorted")
        base = LIBRARY_DIR / folder
        card_id = card.get("card_id", "unknown")
        if card.get("card_type") == "statute_article":
            code = card.get("code", "unknown")
            article_no = card.get("article_no", "000")
            base = base / "articles"
            return base / f"MADDE_{article_no}.json"
        return base / f"{card_id}.json"

    # ------------------------------------------------------------------
    # Indexes
    # ------------------------------------------------------------------
    def update_indexes(self, cards: list[dict[str, Any]]) -> None:
        if not cards:
            return
        self._update_main_index(cards)
        self._update_specialized_index("statute_library_index.json", cards, lambda c: c.get("card_type") == "statute_article")
        self._update_specialized_index("case_law_library_index.json", cards, lambda c: c.get("card_type") == "case_law")
        self._update_specialized_index("doctrine_library_index.json", cards, lambda c: c.get("card_type") == "doctrine_or_practice_note")
        self._update_specialized_index("petition_style_index.json", cards, lambda c: c.get("card_type") == "petition_style")
        self._update_question_index(cards)
        self._update_legal_area_index(cards)

    def _update_main_index(self, cards: list[dict[str, Any]]) -> None:
        path = LIBRARY_DIR / "library_index.json"
        existing: list[dict[str, Any]] = []
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, TypeError):
                existing = []
        index_map = {c["card_id"]: c for c in existing if isinstance(c, dict) and "card_id" in c}
        for card in cards:
            cid = card.get("card_id")
            if not cid:
                continue
            index_map[cid] = {
                "card_id": cid,
                "card_type": card.get("card_type") or card.get("source_type", "unknown"),
                "source_type": card.get("source_type", "unknown"),
                "source_reliability": card.get("source_reliability", "low"),
                "legal_area": card.get("legal_area", "belirsiz"),
                "case_type": card.get("case_type", ""),
                "code": card.get("code"),
                "article_no": card.get("article_no"),
                "court": card.get("court"),
                "chamber": card.get("chamber"),
                "esas_no": card.get("esas_no"),
                "karar_no": card.get("karar_no"),
                "library_folder": card.get("library_folder", "unsorted"),
                "card_path": str((LIBRARY_DIR / card.get("library_folder", "unsorted") / f"{cid}.json")),
                "summary": (card.get("summary") or card.get("article_text") or card.get("holding") or "")[:220],
                "safe_for_legal_basis": card.get("safe_for_legal_basis", False),
                "safe_for_question_generation": card.get("safe_for_question_generation", False),
                "safe_for_petition_style": card.get("safe_for_petition_style", False),
                "warnings": card.get("warnings", []),
            }
        path.write_text(json.dumps(list(index_map.values()), ensure_ascii=False, indent=2), encoding="utf-8")

    def _update_specialized_index(self, file_name: str, cards: list[dict[str, Any]], predicate) -> None:
        path = LIBRARY_DIR / file_name
        existing: list[dict[str, Any]] = []
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, TypeError):
                existing = []
        index_map = {c["card_id"]: c for c in existing if isinstance(c, dict) and "card_id" in c}
        for card in cards:
            if not predicate(card):
                continue
            cid = card.get("card_id")
            if not cid:
                continue
            index_map[cid] = {
                "card_id": cid,
                "legal_area": card.get("legal_area", "belirsiz"),
                "keywords": card.get("keywords", [])[:8],
                "summary": (card.get("summary") or card.get("article_text") or card.get("holding") or "")[:180],
                "source_file": card.get("source_file", ""),
                "source_reliability": card.get("source_reliability", "low"),
                "safe_for_legal_basis": card.get("safe_for_legal_basis", False),
                "safe_for_question_generation": card.get("safe_for_question_generation", False),
                "safe_for_petition_style": card.get("safe_for_petition_style", False),
            }
        path.write_text(json.dumps(list(index_map.values()), ensure_ascii=False, indent=2), encoding="utf-8")

    def _update_question_index(self, cards: list[dict[str, Any]]) -> None:
        path = LIBRARY_DIR / "question_library_index.json"
        existing: list[dict[str, Any]] = []
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, TypeError):
                existing = []
        entries: list[dict[str, Any]] = list(existing)
        for card in cards:
            for question in card.get("question_suggestions", []):
                if not isinstance(question, dict):
                    continue
                entries.append({
                    "card_id": card.get("card_id"),
                    "question_id": question.get("id"),
                    "question": question.get("question"),
                    "category": question.get("category"),
                    "legal_area": card.get("legal_area"),
                    "source_file": card.get("source_file", ""),
                })
        path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

    def _update_legal_area_index(self, cards: list[dict[str, Any]]) -> None:
        path = LIBRARY_DIR / "legal_area_library_index.json"
        existing: dict[str, list[dict[str, Any]]] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, TypeError):
                existing = {}
        grouped: dict[str, list[dict[str, Any]]] = dict(existing)
        for card in cards:
            area = card.get("legal_area", "belirsiz")
            grouped.setdefault(area, [])
            existing_in_area = {c["card_id"]: c for c in grouped[area] if isinstance(c, dict) and "card_id" in c}
            existing_in_area[card["card_id"]] = {
                "card_id": card["card_id"],
                "card_type": card.get("card_type") or card.get("source_type", "unknown"),
                "keywords": card.get("keywords", [])[:8],
                "summary": (card.get("summary") or card.get("article_text") or card.get("holding") or "")[:180],
            }
            grouped[area] = list(existing_in_area.values())
        path.write_text(json.dumps(grouped, ensure_ascii=False, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Run modes
    # ------------------------------------------------------------------
    def run_once(self) -> dict[str, Any]:
        started = datetime.now(timezone.utc).isoformat()
        self._update_status(mode="once", last_started_at=started)
        self._append_log(f"Agent started in once mode at {started}")
        files = self.discover_source_files()
        self._append_log(f"Discovered {len(files)} source files")
        return self._process_files(files, mode="once", started=started)

    def run_watch(self, interval: int = DEFAULT_WATCH_INTERVAL) -> None:
        if interval < MIN_WATCH_INTERVAL:
            interval = MIN_WATCH_INTERVAL
        started = datetime.now(timezone.utc).isoformat()
        self._update_status(mode="watch", last_started_at=started)
        self._append_log(f"Agent started in watch mode at {started} with interval {interval}s")
        try:
            while True:
                try:
                    files = self.discover_source_files()
                    report = self._process_files(files, mode="watch", started=started)
                    self._append_log(
                        f"Scan completed: seen={report.get('files_seen', 0)} "
                        f"learned={report.get('files_learned', 0)} "
                        f"skipped={report.get('files_skipped', 0)} "
                        f"failed={report.get('files_failed', 0)} "
                        f"cards={report.get('cards_created', 0)}"
                    )
                except Exception as exc:
                    self._append_log(f"Scan error: {exc}")
                time.sleep(interval)
        except KeyboardInterrupt:
            self._append_log("Agent interrupted by user")
        finally:
            self._update_status(mode="watch", is_running=False, last_completed_at=datetime.now(timezone.utc).isoformat())
            self._release_lock()

    def _process_files(self, files: list[Path], mode: str, started: str) -> dict[str, Any]:
        report: dict[str, Any] = {
            "files_seen": len(files),
            "files_learned": 0,
            "files_skipped": 0,
            "files_failed": 0,
            "cards_created": 0,
            "warnings": [],
            "errors": [],
        }
        for file_path in files:
            try:
                file_result = self.learn_file(file_path)
                status = file_result.get("status", "failed")
                if status == "learned":
                    report["files_learned"] += 1
                    report["cards_created"] += file_result.get("cards_created", 0)
                elif status == "skipped":
                    report["files_skipped"] += 1
                else:
                    report["files_failed"] += 1
                    if file_result.get("error"):
                        report["errors"].append(f"{file_path.name}: {file_result['error']}")
                if file_result.get("warnings"):
                    report["warnings"].extend(file_result["warnings"])
            except Exception as exc:
                report["files_failed"] += 1
                report["errors"].append(f"{file_path.name}: {exc}")
        self._update_status(
            mode=mode,
            last_scan_at=datetime.now(timezone.utc).isoformat(),
            last_completed_at=datetime.now(timezone.utc).isoformat(),
            files_seen=report["files_seen"],
            files_learned=report["files_learned"],
            files_skipped=report["files_skipped"],
            files_failed=report["files_failed"],
            cards_created=report["cards_created"],
            last_error=report["errors"][-1] if report["errors"] else None,
        )
        if mode == "once":
            self._release_lock()
        return report

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _detect_primary_code(self, text: str, codes: list[str]) -> str:
        mapping = {
            "TMK": ["turk medeni kanunu", "medeni kanun", "tmk"],
            "TBK": ["turk borclar kanunu", "borclar kanunu", "tbk"],
            "HMK": ["hukuk muhakemeleri kanunu", "hmk"],
            "İİK": ["İcra ve İflas Kanunu", "İcra iflas kanunu", "iik", "İİK", "IIK", "icra ve iflas kanunu"],
            "TCK": ["turk ceza kanunu", "ceza kanunu", "tck"],
            "CMK": ["ceza muhakemeleri kanunu", "cmk"],
            "TTK": ["turk ticaret kanunu", "ticaret kanunu", "ttk"],
            "IS_KANUNU": ["iş kanunu", "is kanunu", "is kanunu"],
            "TKHK": ["tüketicinin korunması hakkında kanun", "tuketicinin korunmasi hakkinda kanun"],
            "KMK": ["kat mülkiyeti kanunu", "kat mulkiyeti kanunu"],
            "IYUK": ["idari yargılama usulü kanunu", "İdari yargılama usulü kanunu", "idari yargılama usul kanunu"],
            "ARABULUCULUK": ["arabuluculuk kanunu"],
            "KVKK": ["kişisel verilerin korunması kanunu", "kvkk", "kisisel verilerin korunmasi kanunu"],
        }
        plain = self._plain(text)
        for code, markers in mapping.items():
            if any(marker in plain for marker in markers):
                return code
        if codes:
            # Clean up codes - don't use parser codes that look like "m.315"
            for code in codes:
                cleaned = code.split()[0].upper()
                # Skip invalid codes
                if cleaned.startswith('M.') or cleaned.startswith('MADDE'):
                    continue
                if cleaned.isdigit():
                    continue
                return cleaned
        return "unknown"

    def _resolve_statute_folder(self, code: str, file_path: Path) -> Path:
        mapping = {
            "TMK": "TMK",
            "TBK": "TBK",
            "HMK": "HMK",
            "İİK": "IIK",
            "IİK": "IIK",
            "TCK": "TCK",
            "CMK": "CMK",
            "TTK": "TTK",
            "IS_KANUNU": "IS_KANUNU",
            "TKHK": "TKHK",
            "KMK": "KMK",
            "IYUK": "IYUK",
            "ARABULUCULUK": "ARABULUCULUK",
            "KVKK": "KVKK",
        }
        folder_name = mapping.get(code.upper(), code)
        return LIBRARY_DIR / "statutes" / folder_name

    def _validate_articles(self, articles: list[str], original_text: str) -> bool:
        """Validate that parsed articles contain actual content, not just references."""
        if not articles:
            return False
        
        # Check if articles are too short (just "m.315" or similar)
        for article in articles[:3]:  # Check first 3 articles
            # If article is just a reference like "m.315" or "MADDE 315", it's invalid
            if len(article.strip()) < 50:
                return False
            # If article doesn't contain the actual text content, it's invalid
            if article.strip().lower() in ["m.315", "madde 315", "m. 315"]:
                return False
        
        return True

    def _extract_articles_with_regex(self, text: str) -> list[str]:
        """Extract individual articles from statute text using regex patterns."""
        articles: list[str] = []
        # Pattern to match article headers: MADDE 315 -, Madde 315:, etc.
        # The header can be followed by content on the same line or next line
        article_pattern = re.compile(
            r'(?im)^\s*(?:MADDE|Madde)\s+(\d+[A-Z]?)\s*(?:[-–—:])?\s*',
            re.MULTILINE
        )
        
        matches = list(article_pattern.finditer(text))
        if not matches:
            return articles
        
        for i, match in enumerate(matches):
            start_pos = match.start()
            article_no = match.group(1)
            
            # Determine end position: start of next article or end of text
            if i + 1 < len(matches):
                end_pos = matches[i + 1].start()
            else:
                end_pos = len(text)
            
            # Extract article text
            article_text = text[start_pos:end_pos].strip()
            if article_text and len(article_text) > 10:  # Minimum length check
                articles.append(article_text)
        
        return articles

    def _extract_article_no(self, article_text: str) -> int | None:
        match = re.search(r"(?:MADDE|Madde|m\.?)\s*(\d+)", article_text)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        match = re.search(r"^(\d+)\.\s*madde", article_text, flags=re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None

    def _extract_decision_numbers(self, text: str) -> tuple[str, str]:
        esas = ""
        karar = ""
        patterns = [
            r"E\.\s*(\d{4}/\d+)",
            r"K\.\s*(\d{4}/\d+)",
            r"Esas\s*No[:\s]+(\d{4}/\d+)",
            r"Karar\s*No[:\s]+(\d{4}/\d+)",
            r"(\d{4}/\d+)\s*E\.",
            r"(\d{4}/\d+)\s*K\.",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                value = match.group(1)
                if "E" in pattern or "Esas" in pattern:
                    esas = value
                if "K" in pattern or "Karar" in pattern:
                    karar = value
        return esas, karar

    def _extract_court_info(self, text: str, source_type: str) -> tuple[str, str]:
        court = "unknown"
        chamber = "unknown"
        if source_type == "yargitay_decision":
            court = "Yargıtay"
            chamber_match = re.search(r"(\d+)\.\s*Hukuk|(\d+)\.\s*Ceza|Hukuk\s*Dairesi|Ceza\s*Dairesi", text, flags=re.IGNORECASE)
            if chamber_match:
                chamber = chamber_match.group(0)
        elif source_type == "danistay_decision":
            court = "Danıştay"
            chamber_match = re.search(r"(\d+)\.\s*Daire|Idari\s*Dava\s*Daireleri", text, flags=re.IGNORECASE)
            if chamber_match:
                chamber = chamber_match.group(0)
        elif source_type == "constitutional_court_decision":
            court = "Anayasa Mahkemesi"
            chamber = "Genel Kurul"
        return court, chamber

    def _extract_decision_date(self, text: str) -> str:
        patterns = [
            r"(\d{2}\.\d{2}\.\d{4})",
            r"(\d{2}/\d{2}/\d{4})",
            r"(\d{4}-\d{2}-\d{2})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return ""

    @staticmethod
    def _safe_id(value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]", "_", value)

    @staticmethod
    def _plain(text: str) -> str:
        import unicodedata
        normalized = str(text or "").casefold().translate(
            str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
                          "Ç": "c", "Ğ": "g", "İ": "i", "Ö": "o", "Ş": "s", "Ü": "u"})
        )
        decomposed = unicodedata.normalize("NFKD", normalized)
        return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


legal_brain_librarian_service = LegalBrainLibrarianService()