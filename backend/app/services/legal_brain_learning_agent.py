"""Legal Brain learning agent - orchestrates source ingestion, parsing, and indexing."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LEGAL_BRAIN_ROOT = Path(__file__).resolve().parents[1] / "legal_brain"
UPLOADS_DIR = LEGAL_BRAIN_ROOT / "uploads"
SOURCES_DIR = LEGAL_BRAIN_ROOT / "sources"
LEARNED_CARDS_DIR = LEGAL_BRAIN_ROOT / "learned_cards"
INDEX_DIR = LEGAL_BRAIN_ROOT / "indexes"
METADATA_DIR = LEGAL_BRAIN_ROOT / "metadata"

SUPPORTED_EXTENSIONS = {".txt", ".md", ".json", ".html", ".pdf", ".docx"}
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_PDF_PAGES = 100


class LegalBrainLearningAgent:
    """Orchestrate learning from legal sources."""

    def __init__(self) -> None:
        self._ensure_dirs()
        self._taxonomy = self._load_taxonomy()

    def _ensure_dirs(self) -> None:
        for directory in [UPLOADS_DIR, LEARNED_CARDS_DIR, INDEX_DIR, METADATA_DIR]:
            directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _load_taxonomy() -> dict[str, Any]:
        path = LEGAL_BRAIN_ROOT / "metadata" / "legal_area_taxonomy.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def learn_from_uploads(self) -> dict[str, Any]:
        """Scan uploads and learn from all supported files."""
        files: list[Path] = []
        if UPLOADS_DIR.exists():
            files.extend(sorted(p for p in UPLOADS_DIR.iterdir() if p.is_file() and self._is_supported(p)))
        if SOURCES_DIR.exists():
            for source_dir in SOURCES_DIR.iterdir():
                if source_dir.is_dir():
                    files.extend(sorted(p for p in source_dir.rglob("*") if p.is_file() and self._is_supported(p)))
        if not files:
            return {
                "sources_seen": 0,
                "sources_learned": 0,
                "sources_skipped": 0,
                "cards_created": 0,
                "statute_cards": 0,
                "case_law_cards": 0,
                "doctrine_cards": 0,
                "question_count": 0,
                "high_reliability_sources": 0,
                "medium_reliability_sources": 0,
                "low_reliability_sources": 0,
                "warnings": ["Yüklenecek dosya bulunamadı."],
                "next_recommended_sources": [],
            }

        return self._process_files(files)

    def learn_from_file(self, file_path: str | Path) -> dict[str, Any]:
        """Learn from a single file."""
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            return {"error": "Dosya bulunamadı."}
        return self._process_files([path])

    def learn_from_text(self, text: str, source_metadata: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Learn from raw text with optional metadata."""
        from app.services.legal_brain_source_classifier import legal_brain_source_classifier
        from app.services.legal_brain_statute_parser import legal_brain_statute_parser
        from app.services.legal_brain_case_law_parser import legal_brain_case_law_parser
        from app.services.legal_brain_doctrine_parser import legal_brain_doctrine_parser
        from app.services.legal_brain_quality_service import legal_brain_quality_service

        source_metadata = source_metadata or {}
        metadata = legal_brain_source_classifier.classify(
            text=text,
            source_file=source_metadata.get("source_file", ""),
        )
        source_type = metadata.get("source_type", "unknown")

        cards: list[dict[str, Any]] = []
        if source_type in ("statute", "official_gazette"):
            cards.extend(legal_brain_statute_parser.parse(text=text, source_reliability=metadata.get("source_reliability", "high")))
        elif source_type in ("case_law", "yargitay_decision", "danistay_decision", "constitutional_court_decision"):
            cards.extend(legal_brain_case_law_parser.parse(text=text, source_reliability=metadata.get("source_reliability", "high")))
        else:
            cards.append(legal_brain_doctrine_parser.parse(text=text, source_reliability=metadata.get("source_reliability", "medium")))

        for card in cards:
            card["source_file"] = source_metadata.get("source_file", "")
            card["source_reliability"] = metadata.get("source_reliability", card.get("source_reliability", "medium"))
            card["warnings"] = metadata.get("warnings", [])
            if metadata.get("source_reliability") == "low" and not card.get("warnings"):
                card["warnings"] = ["Low reliability kaynak; tek başına hukuki dayanak yapılamaz."]

        quality_results = legal_brain_quality_service.evaluate_cards(cards)
        for card, quality in zip(cards, quality_results):
            card["quality_score"] = quality.get("quality_score", 0)
            card["quality_issues"] = quality.get("issues", [])
            card["safe_for_retrieval"] = quality.get("safe_for_retrieval", False)
            card["safe_for_draft_support"] = quality.get("safe_for_draft_support", False)

        return cards

    def build_learning_report(self) -> dict[str, Any]:
        """Generate learning report from existing index data."""
        index_path = INDEX_DIR / "legal_brain_index.json"
        cards: list[dict[str, Any]] = []
        if index_path.exists():
            try:
                cards = json.loads(index_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                cards = []

        by_type: dict[str, int] = {}
        by_area: dict[str, int] = {}
        by_reliability: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
        by_folder: dict[str, int] = {}
        by_case_type: dict[str, int] = {}
        high = medium = low = 0
        for card in cards:
            card_type = card.get("card_type") or card.get("source_type", "unknown")
            by_type[card_type] = by_type.get(card_type, 0) + 1
            area = card.get("legal_area", "belirsiz")
            by_area[area] = by_area.get(area, 0) + 1
            rel = card.get("source_reliability", "low")
            by_reliability[rel] = by_reliability.get(rel, 0) + 1
            folder = card.get("source_folder", "uploads")
            by_folder[folder] = by_folder.get(folder, 0) + 1
            case_types = card.get("case_types", [])
            if isinstance(case_types, list):
                for case_type in case_types:
                    by_case_type[case_type] = by_case_type.get(case_type, 0) + 1
            if rel == "high":
                high += 1
            elif rel == "medium":
                medium += 1
            else:
                low += 1

        warnings: list[str] = []
        if low > 0:
            warnings.append(f"{low} düşük güvenilirlik kaynak bulundu.")
        if not cards:
            warnings.append("Henüz öğrenilmiş kart yok.")

        recommendations = self._recommend_sources(by_area, by_type, by_case_type)

        best_sources = sorted(by_folder.items(), key=lambda item: item[1], reverse=True)[:5]
        weak_areas = [area for area, count in by_area.items() if count < 2]

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sources_seen": len(cards),
            "sources_learned": len(cards),
            "sources_skipped": 0,
            "cards_created": len(cards),
            "cards_by_type": by_type,
            "cards_by_legal_area": by_area,
            "sources_by_folder": by_folder,
            "sources_by_type": by_type,
            "sources_by_reliability": by_reliability,
            "cards_by_case_type": by_case_type,
            "high_reliability_sources": high,
            "medium_reliability_sources": medium,
            "low_reliability_sources": low,
            "best_learning_sources": [{"folder": folder, "count": count} for folder, count in best_sources],
            "weak_areas": weak_areas[:10],
            "warnings": warnings,
            "next_recommended_sources": recommendations,
        }

    def search_legal_memory(self, query: str, legal_area: str | None = None, source_type: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        """Search learned cards by query."""
        cards = self._load_all_cards()
        if legal_area:
            cards = [c for c in cards if c.get("legal_area") == legal_area]
        if source_type:
            cards = [c for c in cards if c.get("card_type") == source_type or c.get("source_type") == source_type]
        if not query:
            return cards[:limit]

        query_terms = [t for t in re.findall(r"[a-zçğıöşü]{3,}", self._plain(query)) if len(t) > 2]
        if not query_terms:
            return cards[:limit]

        scored: list[tuple[int, dict[str, Any]]] = []
        for card in cards:
            haystack = " ".join([
                card.get("summary", ""),
                card.get("doctrine_summary", ""),
                card.get("legal_area", ""),
                " ".join(card.get("keywords", [])),
                " ".join(card.get("legal_rules", [])),
                card.get("source_file", ""),
                card.get("court", ""),
                " ".join(q.get("question", "") for q in (card.get("question_suggestions") or []) if isinstance(q, dict)),
            ])
            plain_haystack = self._plain(haystack)
            score = sum(1 for term in query_terms if term in plain_haystack)
            if score:
                scored.append((score, card))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [card for _, card in scored[:limit]]

    def get_learning_status(self) -> dict[str, Any]:
        """Return summary of learned cards."""
        cards = self._load_all_cards()
        report = self.build_learning_report()
        return {
            "total_cards": len(cards),
            "report": report,
        }

    def _process_files(self, files: list[Path]) -> dict[str, Any]:
        from app.services.legal_brain_source_classifier import legal_brain_source_classifier
        from app.services.legal_brain_statute_parser import legal_brain_statute_parser
        from app.services.legal_brain_case_law_parser import legal_brain_case_law_parser
        from app.services.legal_brain_doctrine_parser import legal_brain_doctrine_parser
        from app.services.legal_brain_quality_service import legal_brain_quality_service
        from app.services.legal_source_ingest_service import legal_source_ingest_service

        report: dict[str, Any] = {
            "sources_seen": len(files),
            "sources_learned": 0,
            "sources_skipped": 0,
            "cards_created": 0,
            "statute_cards": 0,
            "case_law_cards": 0,
            "doctrine_cards": 0,
            "question_count": 0,
            "high_reliability_sources": 0,
            "medium_reliability_sources": 0,
            "low_reliability_sources": 0,
            "warnings": [],
            "next_recommended_sources": [],
        }

        all_new_cards: list[dict[str, Any]] = []

        for file_path in files:
            file_hash = self._file_hash(file_path)
            registry_path = METADATA_DIR / "source_registry.json"
            registry: dict[str, Any] = {}
            if registry_path.exists():
                registry = json.loads(registry_path.read_text(encoding="utf-8"))

            existing = registry.get("files", {}).get(file_path.name)
            if existing and existing.get("file_hash") == file_hash and existing.get("status") == "indexed":
                report["sources_skipped"] += 1
                continue

            if legal_brain_source_classifier.is_large_file(file_path):
                if file_path.suffix.lower() == ".pdf":
                    cards = self._process_large_pdf(file_path, file_hash)
                    if cards:
                        all_new_cards.extend(cards)
                        report["cards_created"] += len(cards)
                        report["sources_learned"] += 1
                        report["high_reliability_sources"] += 1
                        registry.setdefault("files", {})[file_path.name] = {
                            "file_hash": file_hash,
                            "ingested_at": datetime.now(timezone.utc).isoformat(),
                            "status": "indexed_chunks",
                        }
                        registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
                        continue
                report["sources_skipped"] += 1
                report["warnings"].append(f"{file_path.name}: Dosya boyutu geçici limitin üzerinde (max {MAX_FILE_SIZE_MB} MB).")
                registry.setdefault("files", {})[file_path.name] = {
                    "file_hash": file_hash,
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                    "status": "skipped",
                    "error_message": f"Dosya boyutu geçici limitin üzerinde olduğu için atlandı. (max {MAX_FILE_SIZE_MB} MB)",
                }
                registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
                continue

            try:
                text = legal_source_ingest_service._extract_text(file_path)
                if not text or not text.strip():
                    report["sources_skipped"] += 1
                    continue

                manifest = self._load_source_manifest(file_path)
                metadata = legal_brain_source_classifier.classify(text=text, source_file=file_path.name)
                if manifest:
                    metadata["source_pack"] = manifest.get("pack_name")
                    metadata["legal_area"] = manifest.get("legal_area", metadata.get("legal_area_candidates", [{}])[0].get("legal_area", "belirsiz"))
                    metadata["case_type"] = manifest.get("case_type")
                    metadata["source_reliability"] = manifest.get("source_reliability", metadata.get("source_reliability", "low"))
                    metadata["source_type"] = manifest.get("source_type", metadata.get("source_type", "unknown"))
                source_type = metadata.get("source_type", "unknown")
                reliability = metadata.get("source_reliability", "low")
                source_folder = self._detect_source_folder(file_path)

                cards: list[dict[str, Any]] = []
                if source_type in ("statute", "official_gazette"):
                    cards = legal_brain_statute_parser.parse(text=text, source_reliability=reliability)
                    report["statute_cards"] += len(cards)
                elif source_type in ("case_law", "yargitay_decision", "danistay_decision", "constitutional_court_decision"):
                    cards = legal_brain_case_law_parser.parse(text=text, source_reliability=reliability)
                    report["case_law_cards"] += len(cards)
                else:
                    card = legal_brain_doctrine_parser.parse(text=text, source_reliability=reliability)
                    cards = [card]
                    report["doctrine_cards"] += 1

                for card in cards:
                    card["source_file"] = file_path.name
                    card["source_reliability"] = reliability
                    card["source_type"] = source_type
                    card["source_folder"] = source_folder
                    card["source_pack"] = metadata.get("source_pack")
                    card["warnings"] = metadata.get("warnings", [])
                    if reliability == "low" and not card.get("warnings"):
                        card["warnings"] = ["Low reliability kaynak; tek başına hukuki dayanak yapılamaz."]
                    card["learning_value"] = self._assess_learning_value(card, source_type)
                    card["safe_for_legal_basis"] = self._is_safe_for_legal_basis(source_type, reliability)
                    card["safe_for_question_generation"] = self._is_safe_for_question_generation(source_type, reliability)
                    card["safe_for_petition_style"] = self._is_safe_for_petition_style(source_type)

                quality_results = legal_brain_quality_service.evaluate_cards(cards)
                for card, quality in zip(cards, quality_results):
                    card["quality_score"] = quality.get("quality_score", 0)
                    card["quality_issues"] = quality.get("issues", [])
                    card["safe_for_retrieval"] = quality.get("safe_for_retrieval", False)
                    card["safe_for_draft_support"] = quality.get("safe_for_draft_support", False)

                for card in cards:
                    card_id = f"{file_path.stem}_{file_hash}"
                    card["card_id"] = card_id
                    card_path = LEARNED_CARDS_DIR / f"{card_id}.json"
                    card_path.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
                    all_new_cards.append(card)

                question_count = sum(len(c.get("question_suggestions", [])) for c in cards)
                report["question_count"] += question_count
                report["cards_created"] += len(cards)
                report["sources_learned"] += 1

                if reliability == "high":
                    report["high_reliability_sources"] += 1
                elif reliability == "medium":
                    report["medium_reliability_sources"] += 1
                else:
                    report["low_reliability_sources"] += 1

                registry.setdefault("files", {})[file_path.name] = {
                    "file_hash": file_hash,
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                    "status": "indexed",
                }
                registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")

            except Exception as exc:
                report["sources_skipped"] += 1
                report["warnings"].append(f"{file_path.name}: {exc}")

        if all_new_cards:
            self._update_indexes(all_new_cards)
            learning_report = self.build_learning_report()
            report_path = METADATA_DIR / "learning_report.json"
            report_path.write_text(json.dumps(learning_report, ensure_ascii=False, indent=2), encoding="utf-8")
            report["next_recommended_sources"] = learning_report.get("next_recommended_sources", [])

        return report

    def _process_large_pdf(self, file_path: Path, file_hash: str) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        try:
            import fitz
            doc = fitz.open(file_path)
            total_pages = len(doc)
            max_pages = min(total_pages, MAX_PDF_PAGES)
            chunk_size = 20
            for start in range(0, max_pages, chunk_size):
                end = min(start + chunk_size, max_pages)
                chunk_text = "\n".join(page.get_text() for page in doc[start:end])
                if not chunk_text.strip():
                    continue
                metadata = legal_brain_source_classifier.classify(text=chunk_text, source_file=file_path.name)
                source_type = metadata.get("source_type", "official_gazette")
                reliability = metadata.get("source_reliability", "high")
                card = legal_brain_doctrine_parser.parse(text=chunk_text, source_reliability=reliability)
                card_id = f"{file_path.stem}_{file_hash}_p{start+1}-{end}"
                card["card_id"] = card_id
                card["source_file"] = file_path.name
                card["source_type"] = source_type
                card["source_reliability"] = reliability
                card["source_folder"] = self._detect_source_folder(file_path)
                card["warnings"] = metadata.get("warnings", [])
                card["learning_value"] = "high"
                card["safe_for_legal_basis"] = True
                card["safe_for_question_generation"] = True
                card["safe_for_petition_style"] = False
                cards.append(card)
            doc.close()
        except Exception:
            return []
        return cards

    def _load_source_manifest(self, file_path: Path) -> dict[str, Any] | None:
        source_dir = file_path.parent
        manifest_path = source_dir / "source_manifest.json"
        if manifest_path.exists():
            try:
                return json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return None
        return None

    def _detect_source_folder(self, file_path: Path) -> str:
        try:
            return file_path.relative_to(SOURCES_DIR).parts[0]
        except ValueError:
            return "uploads"

    @staticmethod
    def _assess_learning_value(card: dict[str, Any], source_type: str) -> str:
        if source_type in ("statute", "official_gazette", "yargitay_decision", "danistay_decision", "constitutional_court_decision"):
            return "high"
        if source_type in ("doctrine", "bar_publication", "regulation"):
            return "medium"
        return "low"

    @staticmethod
    def _is_safe_for_legal_basis(source_type: str, reliability: str) -> bool:
        return source_type in ("statute", "official_gazette", "yargitay_decision", "danistay_decision", "constitutional_court_decision", "case_law", "regulation") and reliability in ("high", "medium")

    @staticmethod
    def _is_safe_for_question_generation(source_type: str, reliability: str) -> bool:
        if reliability == "low":
            return False
        return source_type in ("statute", "official_gazette", "yargitay_decision", "danistay_decision", "constitutional_court_decision", "case_law", "doctrine", "bar_publication", "regulation", "procedural_guide")

    @staticmethod
    def _is_safe_for_petition_style(source_type: str) -> bool:
        return source_type in ("petition_sample", "doctrine", "bar_publication", "procedural_guide")

    def _update_indexes(self, new_cards: list[dict[str, Any]]) -> None:
        existing: list[dict[str, Any]] = []
        main_index = INDEX_DIR / "legal_brain_index.json"
        if main_index.exists():
            try:
                existing = json.loads(main_index.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = []

        index_map = {c["card_id"]: c for c in existing}
        for card in new_cards:
            cid = card.get("card_id")
            if cid:
                index_map[cid] = {
                    "card_id": cid,
                    "card_type": card.get("card_type") or card.get("source_type", "unknown"),
                    "legal_area": card.get("legal_area", "belirsiz"),
                    "keywords": card.get("keywords", [])[:10],
                    "source_reliability": card.get("source_reliability", "low"),
                    "source_file": card.get("source_file", ""),
                    "source_folder": card.get("source_folder", "uploads"),
                    "source_type": card.get("source_type", "unknown"),
                    "learning_value": card.get("learning_value", "low"),
                    "safe_for_legal_basis": card.get("safe_for_legal_basis", False),
                    "safe_for_question_generation": card.get("safe_for_question_generation", False),
                    "safe_for_petition_style": card.get("safe_for_petition_style", False),
                    "summary": (card.get("summary") or card.get("doctrine_summary") or card.get("article_text", ""))[:180],
                }

        main_index.write_text(json.dumps(list(index_map.values()), ensure_ascii=False, indent=2), encoding="utf-8")

        self._update_specialized_index("statute_index.json", new_cards, lambda c: c.get("card_type") == "statute_article")
        self._update_specialized_index("case_law_index.json", new_cards, lambda c: c.get("card_type") == "case_law")
        self._update_specialized_index("doctrine_index.json", new_cards, lambda c: c.get("card_type") == "doctrine")
        self._update_question_index(new_cards)
        self._update_legal_area_index(new_cards)

    def _update_specialized_index(self, file_name: str, cards: list[dict[str, Any]], predicate) -> None:
        path = INDEX_DIR / file_name
        existing: list[dict[str, Any]] = []
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = []
        index_map = {c["card_id"]: c for c in existing if "card_id" in c}
        for card in cards:
            if predicate(card):
                index_map[card["card_id"]] = {
                    "card_id": card["card_id"],
                    "legal_area": card.get("legal_area"),
                    "keywords": card.get("keywords", [])[:8],
                    "summary": (card.get("summary") or card.get("doctrine_summary") or card.get("article_text", ""))[:160],
                    "source_file": card.get("source_file", ""),
                }
        path.write_text(json.dumps(list(index_map.values()), ensure_ascii=False, indent=2), encoding="utf-8")

    def _update_question_index(self, cards: list[dict[str, Any]]) -> None:
        path = INDEX_DIR / "question_index.json"
        existing: list[dict[str, Any]] = []
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
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
        path = INDEX_DIR / "legal_area_index.json"
        existing: dict[str, list[dict[str, Any]]] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}

        grouped: dict[str, list[dict[str, Any]]] = dict(existing)
        for card in cards:
            area = card.get("legal_area", "belirsiz")
            grouped.setdefault(area, [])
            existing_in_area = {c["card_id"]: c for c in grouped[area] if "card_id" in c}
            existing_in_area[card["card_id"]] = {
                "card_id": card["card_id"],
                "card_type": card.get("card_type") or card.get("source_type", "unknown"),
                "keywords": card.get("keywords", [])[:8],
                "summary": (card.get("summary") or card.get("doctrine_summary") or card.get("article_text", ""))[:160],
            }
            grouped[area] = list(existing_in_area.values())

        path.write_text(json.dumps(grouped, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_all_cards(self) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        if not LEARNED_CARDS_DIR.exists():
            return cards
        for path in sorted(LEARNED_CARDS_DIR.glob("*.json")):
            try:
                cards.append(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
        return cards

    def _is_supported(self, file_path: Path) -> bool:
        if file_path.name.startswith("."):
            return False
        return file_path.suffix.lower() in SUPPORTED_EXTENSIONS

    def _file_hash(self, file_path: Path) -> str:
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()[:16]

    def _recommend_sources(self, by_area: dict[str, int], by_type: dict[str, int], by_case_type: dict[str, int]) -> list[str]:
        recommendations: list[str] = []
        if by_type.get("statute_article", 0) < 3:
            recommendations.append("TBK ve TMK tam metni eklenmeli")
        if by_type.get("case_law", 0) < 5:
            recommendations.append("Yargıtay ve Danıştay karar seti eklenmeli")
        if by_area.get("kira hukuku", 0) < 2:
            recommendations.append("Kira hukuku için TBK tam metni + Yargıtay karar seti tamamlanmalı.")
        if by_area.get("idare hukuku", 0) < 2:
            recommendations.append("İdare hukuku için İYUK ve Danıştay karar seti eksik.")
        if by_area.get("kat mülkiyeti / komşuluk hukuku", 0) < 2:
            recommendations.append("Komşuluk hukuku için KMK tam metni ve gürültü emsalleri eklenmeli.")
        if by_area.get("tüketici hukuku", 0) < 2:
            recommendations.append("Tüketici hukuku için TKHK ve ayıplı araç karar seti eklenmeli.")
        if by_case_type.get("kira tahliyesi", 0) < 2:
            recommendations.append("Kira temerrütü tahliye davaları için Yargıtay karar seti eklenmeli.")
        if by_case_type.get("işçi alacağı", 0) < 2:
            recommendations.append("İşçilik alacakları için İş Kanunu ve Yargıtay kararları eklenmeli.")
        return recommendations[:5]

    @staticmethod
    def _plain(text: str) -> str:
        import unicodedata
        normalized = str(text or "").casefold().translate(
            str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
                          "Ç": "c", "Ğ": "g", "İ": "i", "Ö": "o", "Ş": "s", "Ü": "u"})
        )
        decomposed = unicodedata.normalize("NFKD", normalized)
        return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


legal_brain_learning_agent = LegalBrainLearningAgent()