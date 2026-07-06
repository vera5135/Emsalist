"""Legal Brain source ingestion and card generation service."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

SUPPORTED_EXTENSIONS = {".txt", ".md", ".json", ".html", ".pdf", ".docx"}

LEGAL_BRAIN_ROOT = Path(__file__).resolve().parents[1] / "legal_brain"
UPLOADS_DIR = LEGAL_BRAIN_ROOT / "uploads"
LEARNED_CARDS_DIR = LEGAL_BRAIN_ROOT / "learned_cards"
INDEX_PATH = LEGAL_BRAIN_ROOT / "indexes" / "legal_brain_index.json"
REGISTRY_PATH = LEGAL_BRAIN_ROOT / "metadata" / "source_registry.json"

LEGAL_AREA_PATTERNS = {
    "kira hukuku": ["kira", "kiracı", "kiraci", "kiralanan", "tahliye", "konut", "işyeri", "isyeri", "kira bedeli", "temerrüt", "temerrut"],
    "tüketici hukuku": ["tüketici", "tuketici", "ayıp", "ayip", "tkhk", "garanti", "işlem", "islemi"],
    "araç ayıbı / gizli ayıp": ["araç", "arac", "gizli ayıp", "gizli ayip", "tbk 219", "satış", "satis", "ikinci el", "motor arızası", "ekspertiz", "tramer"],
    "iş hukuku": ["işçi", "isci", "işveren", "isveren", "kıdem", "kidem", "ihbar", "fazla mesai", "iş sözleşmesi", "is sozlesmesi"],
    "aile hukuku": ["nafaka", "boşanma", "bosanma", "velayet", "aile", "tmk", "evlilik"],
    "icra hukuku": ["icra", "itirazın iptali", "itirazin iptali", "ödeme emri", "odeme emri", "takip", "icra takibi"],
    "miras hukuku": ["miras", "intikal", "vasiyet", "mirasçı", "mirasci", "boşanma", "bosanma"],
    "idare hukuku": ["idare", "belediye", "ruhsat", "imar", "kamu", "valilik", "kaymakam", "kanun", "yönetmelik"],
    "ceza hukuku": ["ceza", "suç", "suc", "şikayet", "sikayet", "savcı", "savci", "uzlaşma", "uzlasma"],
    "kat mülkiyeti / komşuluk hukuku": ["kat mülkiyeti", "kat mulkiyeti", "apartman", "yönetici", "yonetici", "gürültü", "gurultu", "komşu", "komsu", "ortak alan"],
    "tazminat hukuku": ["tazminat", "zarar", "maddi tazminat", "manevi tazminat", "haksız fiil", "haksiz fiil"],
    "sözleşmeler hukuku": ["sözleşme", "sozlesme", "akit", "anlaşma", "anlasma", "borç", "borc", "ödünç", "odunc"],
    "ticaret hukuku": ["ticaret", "şirket", "sirket", "tacir", "ortak", "limited", "anonim", "çek", "cek", "senet"],
}

CASE_TYPE_PATTERNS = {
    "alacak davası": ["alacak", "tahsil", "ödenmedi", "odenmedi", "borç", "borc"],
    "tazminat davası": ["tazminat", "zarar", "maddi/manevi", "haksız fiil", "haksiz fiil"],
    "müdahalenin men'i": ["müdahale", "mudahale", "gürültü", "gurultu", "rahatsız", "rahatsiz"],
    "iptal davası": ["iptal", "red", "yürütmenin durdurulması"],
    "tespit davası": ["tespit", "belirlenmesi"],
    "ifa davası": ["ifa", "yerine getirme"],
    "nafaka davası": ["nafaka", "nafaka"],
    "boşanma davası": ["boşanma", "bosanma", "velayet"],
    "kira tahliyesi": ["tahliye", "kira", "kiracı", "kiraci"],
    "işçi alacağı": ["işçi", "isci", "işveren", "isveren", "kıdem", "kidem", "ihbar"],
    "icra itirazı": ["icra", "itiraz", "iptal"],
}

RELIABILITY_HIGH_KEYWORDS = [
    "resmî gazete", "resmi gazete", "yargıtay", "danıştay", "anayasa mahkemesi",
    "aym", "uyap", "kanun", "tüzük", "yönetmelik", "kararname", "genelge",
]
RELIABILITY_MEDIUM_KEYWORDS = [
    "baro", "dergi", "makale", "kitap", "yayın", "yayin", "akademik", "doktrin",
]
RELIABILITY_LOW_KEYWORDS = [
    "blog", "forum", "haber", "reklam", "tanıtım", "tanitim", "sosyal medya",
]


class LegalSourceIngestService:
    """Ingest legal sources and generate structured cards."""

    def __init__(self) -> None:
        self._ensure_dirs()
        self._registry = self._load_registry()

    def _ensure_dirs(self) -> None:
        for directory in [UPLOADS_DIR, LEARNED_CARDS_DIR, INDEX_PATH.parent, REGISTRY_PATH.parent]:
            directory.mkdir(parents=True, exist_ok=True)

    def _load_registry(self) -> dict[str, Any]:
        if REGISTRY_PATH.exists():
            return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        return {"files": {}, "last_updated": datetime.now(timezone.utc).isoformat()}

    def _save_registry(self) -> None:
        self._registry["last_updated"] = datetime.now(timezone.utc).isoformat()
        REGISTRY_PATH.write_text(json.dumps(self._registry, ensure_ascii=False, indent=2), encoding="utf-8")

    def _file_hash(self, file_path: Path) -> str:
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()[:16]

    def _is_supported(self, file_path: Path) -> bool:
        if file_path.name.startswith("."):
            return False
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return False
        return True

    def ingest_uploads(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "files_found": 0,
            "files_processed": 0,
            "files_skipped": 0,
            "files_failed": 0,
            "cards_created": 0,
            "errors": [],
        }

        if not UPLOADS_DIR.exists():
            result["errors"].append("Yüklenecek dosya bulunamadı.")
            return result

        files = sorted(
            p for p in UPLOADS_DIR.iterdir()
            if p.is_file() and self._is_supported(p)
        )
        result["files_found"] = len(files)

        if not files:
            result["errors"].append("İşlenecek kaynak bulunamadı.")
            return result

        for file_path in files:
            file_hash = self._file_hash(file_path)
            existing = self._registry.get("files", {}).get(file_path.name)

            if file_path.stat().st_size > MAX_FILE_SIZE_BYTES:
                result["files_skipped"] += 1
                self._registry.setdefault("files", {})[file_path.name] = {
                    "file_hash": file_hash,
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                    "status": "skipped",
                    "error_message": f"Dosya boyutu geçici limitin üzerinde olduğu için atlandı. (max {MAX_FILE_SIZE_MB} MB)",
                }
                result["errors"].append(f"{file_path.name}: Dosya boyutu geçici limitin üzerinde (max {MAX_FILE_SIZE_MB} MB).")
                continue

            if existing and existing.get("file_hash") == file_hash and existing.get("status") == "indexed":
                result["files_skipped"] += 1
                continue

            try:
                text = self._extract_text(file_path)
                if not text or not text.strip():
                    self._registry.setdefault("files", {})[file_path.name] = {
                        "file_hash": file_hash,
                        "ingested_at": datetime.now(timezone.utc).isoformat(),
                        "status": "skipped",
                        "error_message": "Boş veya çıkarılamayan içerik.",
                    }
                    result["files_skipped"] += 1
                    continue

                card = self._build_card(file_path, text, file_hash)
                card_path = LEARNED_CARDS_DIR / f"{card['card_id']}.json"
                card_path.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")

                self._registry.setdefault("files", {})[file_path.name] = {
                    "file_hash": file_hash,
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                    "card_id": card["card_id"],
                    "status": "indexed",
                }
                result["files_processed"] += 1
                result["cards_created"] += 1
            except Exception as exc:  # pragma: no cover - safety net
                result["files_failed"] += 1
                result["errors"].append(f"{file_path.name}: {exc}")
                self._registry.setdefault("files", {})[file_path.name] = {
                    "file_hash": file_hash,
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                    "status": "failed",
                    "error_message": str(exc),
                }

        if result["cards_created"] > 0:
            self._update_index()

        self._save_registry()

        try:
            from app.core.degraded_state import update_component_state, ComponentStatus
            if result.get("files_failed", 0) > 0:
                update_component_state("legal_source_ingest", ComponentStatus.DEGRADED,
                                       error_code="ingest_partial_failure")
            else:
                update_component_state("legal_source_ingest", ComponentStatus.HEALTHY)
        except Exception:
            pass

        return result

    def _extract_text(self, file_path: Path) -> str:
        suffix = file_path.suffix.lower()
        if suffix == ".txt":
            return file_path.read_text(encoding="utf-8", errors="ignore")
        if suffix == ".md":
            return file_path.read_text(encoding="utf-8", errors="ignore")
        if suffix == ".json":
            data = json.loads(file_path.read_text(encoding="utf-8", errors="ignore"))
            if isinstance(data, dict):
                return json.dumps(data, ensure_ascii=False)
            return str(data)
        if suffix == ".html":
            from bs4 import BeautifulSoup
            html = file_path.read_text(encoding="utf-8", errors="ignore")
            soup = BeautifulSoup(html, "lxml")
            return soup.get_text(separator="\n")
        if suffix == ".pdf":
            try:
                import fitz
                doc = fitz.open(file_path)
                pages = [page.get_text() for page in doc]
                doc.close()
                return "\n".join(pages)
            except Exception:
                try:
                    import pdfplumber
                    pages = []
                    with pdfplumber.open(file_path) as pdf:
                        for page in pdf.pages:
                            pages.append(page.extract_text() or "")
                    return "\n".join(pages)
                except Exception:
                    return "Bu dosya türü henüz metne çevrilemedi."
        if suffix == ".docx":
            try:
                import docx
                doc = docx.Document(file_path)
                return "\n".join(paragraph.text for paragraph in doc.paragraphs)
            except Exception:
                return "Bu dosya türü henüz metne çevrilemedi."
        return ""

    def _build_card(self, file_path: Path, text: str, file_hash: str) -> dict[str, Any]:
        plain = self._plain(text)
        legal_area = self._detect_legal_area(plain)
        case_types = self._detect_case_types(plain)
        source_type = self._classify_source_type(text, legal_area)
        reliability = self._assess_reliability(plain, source_type)
        keywords = self._extract_keywords(plain)
        summary = self._build_summary(text)
        legal_rules = self._extract_legal_rules(text)
        required_facts = self._extract_required_facts(legal_area, case_types)
        required_evidence = self._extract_required_evidence(legal_area, case_types)
        procedural_requirements = self._extract_procedural_requirements(legal_area)
        limitation_risks = self._extract_limitation_risks(legal_area)
        common_defenses = self._extract_common_defenses(legal_area)
        language_patterns = self._extract_language_patterns(text)
        question_suggestions = self._generate_questions(legal_area, case_types, source_type)

        card_id = f"{file_path.stem}_{file_hash}"

        return {
            "card_id": card_id,
            "source_file": file_path.name,
            "source_type": source_type,
            "legal_area": legal_area,
            "case_types": case_types[:3],
            "keywords": keywords[:15],
            "summary": summary,
            "legal_rules": legal_rules[:10],
            "required_facts": required_facts[:10],
            "required_evidence": required_evidence[:10],
            "procedural_requirements": procedural_requirements[:6],
            "limitation_or_deadline_risks": limitation_risks[:4],
            "common_defenses": common_defenses[:6],
            "petition_language_patterns": language_patterns[:8],
            "question_suggestions": question_suggestions[:8],
            "source_reliability": reliability,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "warnings": ["Low reliability kaynak; tek başına hukuki dayanak yapılamaz."] if reliability == "low" else [],
        }

    def _update_index(self) -> None:
        cards = self._load_all_cards()
        index_entries: list[dict[str, Any]] = []
        for card in cards:
            index_entries.append({
                "card_id": card["card_id"],
                "legal_area": card["legal_area"],
                "case_types": card["case_types"],
                "keywords": card["keywords"],
                "source_type": card["source_type"],
                "source_reliability": card["source_reliability"],
                "source_file": card["source_file"],
                "summary": card["summary"][:180],
            })
        INDEX_PATH.write_text(json.dumps(index_entries, ensure_ascii=False, indent=2), encoding="utf-8")

    def search_learned_cards(self, query: str, legal_area: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        cards = self._load_all_cards()
        if legal_area:
            cards = [card for card in cards if card.get("legal_area") == legal_area]
        if not query:
            return cards[:limit]
        query_plain = self._plain(query)
        query_terms = [term for term in re.findall(r"[a-zçğıöşü]{3,}", query_plain) if len(term) > 2]
        if not query_terms:
            return cards[:limit]

        scored: list[tuple[int, dict[str, Any]]] = []
        for card in cards:
            haystack = " ".join([
                card.get("summary", ""),
                card.get("legal_area", ""),
                " ".join(card.get("keywords", [])),
                " ".join(card.get("legal_rules", [])),
                card.get("source_file", ""),
                " ".join(c.get("question", "") for c in (card.get("question_suggestions") or []) if isinstance(c, dict)),
            ])
            haystack_plain = self._plain(haystack)
            score = sum(1 for term in query_terms if term in haystack_plain)
            if score:
                scored.append((score, card))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [card for _, card in scored[:limit]]

    def get_card_by_id(self, card_id: str) -> dict[str, Any] | None:
        cards = self._load_all_cards()
        for card in cards:
            if card.get("card_id") == card_id:
                return card
        card_path = LEARNED_CARDS_DIR / f"{card_id}.json"
        if card_path.exists():
            return json.loads(card_path.read_text(encoding="utf-8"))
        return None

    def list_learned_cards(self, legal_area: str | None = None) -> list[dict[str, Any]]:
        cards = self._load_all_cards()
        if legal_area:
            cards = [card for card in cards if card.get("legal_area") == legal_area]
        return cards

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

    def _detect_legal_area(self, plain_text: str) -> str:
        best_area = "belirsiz"
        best_score = 0
        for area, markers in LEGAL_AREA_PATTERNS.items():
            score = sum(1 for marker in markers if marker in plain_text)
            if score > best_score:
                best_score = score
                best_area = area
        if best_score == 0:
            return "belirsiz"
        return best_area

    def _detect_case_types(self, plain_text: str) -> list[str]:
        scored: list[tuple[str, int]] = []
        for ctype, markers in CASE_TYPE_PATTERNS.items():
            score = sum(1 for marker in markers if marker in plain_text)
            if score:
                scored.append((ctype, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return [ctype for ctype, _ in scored[:3]]

    def _classify_source_type(self, text: str, legal_area: str) -> str:
        plain = self._plain(text)
        if legal_area == "belirsiz":
            return "bilinmeyen"
        if any(marker in plain for marker in ["kanun", "tüzük", "yönetmelik", "kararname", "resmî gazete", "resmi gazete"]):
            return "mevzuat"
        if any(marker in plain for marker in ["yargıtay", "danıştay", "anayasa mahkemesi", "karar", "hüküm", "hukum"]):
            return "içtihat"
        if any(marker in plain for marker in ["doktrin", "öğreti", "ogreti", "kitap", "dergi", "makale", "baro"]):
            return "doktrin"
        if any(marker in plain for marker in ["dilekçe", "dilekce", "örnek", "ornek", "talep", "istem"]):
            return "dilekçe_örneği"
        if any(marker in plain for marker in ["usul", "süre", "sure", "dava şartı", "dava sarti", "görev", "gorev", "yetki"]):
            return "usul bilgisi"
        if any(marker in plain for marker in ["delil", "ispat", "kanıt", "kanit", "bilirkişi", "bilirkisi", "tanık", "tanik"]):
            return "delil/ispat bilgisi"
        return "bilinmeyen"

    def _assess_reliability(self, plain_text: str, source_type: str) -> str:
        if source_type == "mevzuat":
            return "high"
        if source_type == "içtihat" and any(marker in plain_text for marker in ["yargıtay", "danıştay", "anayasa mahkemesi", "uyap"]):
            return "high"
        if any(marker in plain_text for marker in RELIABILITY_HIGH_KEYWORDS):
            return "high"
        if any(marker in plain_text for marker in RELIABILITY_MEDIUM_KEYWORDS):
            return "medium"
        if any(marker in plain_text for marker in RELIABILITY_LOW_KEYWORDS):
            return "low"
        return "low"

    def _extract_keywords(self, plain_text: str) -> list[str]:
        stopwords = {"ve", "ile", "bu", "da", "de", "gibi", "için", "göre", "gore", "olan", "olup", "olarak", "olan", "var", "yok", "olan", "olsa", "olsun"}
        words = re.findall(r"[a-zçğıöşü]{4,}", plain_text)
        freq: dict[str, int] = {}
        for word in words:
            if word not in stopwords:
                freq[word] = freq.get(word, 0) + 1
        return sorted(freq, key=freq.get, reverse=True)[:15]

    def _build_summary(self, text: str, max_chars: int = 500) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", " ".join(str(text or "").split()))
        summary_parts: list[str] = []
        length = 0
        for sentence in sentences:
            if length + len(sentence) <= max_chars:
                summary_parts.append(sentence)
                length += len(sentence) + 1
            else:
                break
        return " ".join(summary_parts)[:max_chars] or text[:max_chars]

    def _extract_legal_rules(self, text: str) -> list[str]:
        rules: list[str] = []
        plain = self._plain(text)
        rule_patterns = [
            r"(?:tbk|ttk|cmk|hmk|vuk|itf|ihk|eşm|esm|isk|irc|tk|cmk|kanun|mevzuat)\s*(?:md|madde|m\.)?\s*(?:\d+)?(?:\s*/\s*\d+)?",
            r"madde\s*\d+",
            r"hüküm\s*\d+",
            r"fıkra\s*\d+",
        ]
        for pattern in rule_patterns:
            matches = re.findall(pattern, plain)
            if matches:
                rules.extend(matches[:5])
        unique = list(dict.fromkeys(rules))
        return unique[:10]

    def _extract_required_facts(self, legal_area: str, case_types: list[str]) -> list[str]:
        facts: list[str] = []
        if "kira" in legal_area or "tahliye" in case_types:
            facts.extend(["Kira sözleşmesinin başlangıç tarihi", "Aylık kira bedeli", "Ödenmeyen kira ayları", "İhtar tebliğ tarihi"])
        if "tüketici" in legal_area or "gizli ayıp" in legal_area or "araç" in legal_area:
            facts.extend(["Satış bedeli", "Satış tarihi", "Ayıbın tespit edildiği tarih", "Satıcıya yapılan bildirim tarihi"])
        if "iş" in legal_area or "işçi" in case_types:
            facts.extend(["İşe giriş tarihi", "İşten çıkış tarihi", "Aylık ücret", "Fazla mesai süresi"])
        if "aile" in legal_area or "nafaka" in case_types:
            facts.extend(["Tarafların gelir durumu", "Gider listesi", "Evlatların yaşı ve durumu"])
        if "icra" in legal_area or "itiraz" in case_types:
            facts.extend(["İcra dosya numarası", "İtiraz tarihi", "Alacak tutarı", "Teminat mevcudiyeti"])
        if not facts:
            facts.extend(["Tarafların kimliği", "Uyuşmazlığın tarihi", "Talep konusu"])
        return list(dict.fromkeys(facts))[:10]

    def _extract_required_evidence(self, legal_area: str, case_types: list[str]) -> list[str]:
        evidence: list[str] = []
        if "kira" in legal_area or "tahliye" in case_types:
            evidence.extend(["Kira sözleşmesi", "Banka dekontları", "İhtarname ve tebliğ şerhi", "Arabuluculuk tutanağı"])
        if "tüketici" in legal_area or "gizli ayıp" in legal_area or "araç" in legal_area:
            evidence.extend(["Satış sözleşmesi", "Servis/ekspertiz raporu", "TRAMER kaydı", "WhatsApp/yazışma kayıtları"])
        if "iş" in legal_area or "işçi" in case_types:
            evidence.extend(["SGK hizmet dökümü", "Bordro örnekleri", "Fazla mesai kayıtları", "İşten çıkış bildirimi"])
        if "aile" in legal_area or "nafaka" in case_types:
            evidence.extend(["Nafaka kararları", "Gelir-gider belgeleri", "Tapu/araç kayıtları", "SGK kayıtları"])
        if "icra" in legal_area or "itiraz" in case_types:
            evidence.extend(["İcra takip dosyası", "Alacak kanıtları", "İtiraz dilekçesi", "Teminat mektubu"])
        if not evidence:
            evidence.extend(["Belgeler", "Tanık beyanları", "Resmi kayıtlar", "Bilirkişi incelemesi"])
        return list(dict.fromkeys(evidence))[:10]

    def _extract_procedural_requirements(self, legal_area: str) -> list[str]:
        reqs: list[str] = []
        if "kira" in legal_area:
            reqs.extend(["Arabuluculuk dava şartı", "İhtarın usulüne uygun tebliği"])
        if "tüketici" in legal_area or "araç" in legal_area:
            reqs.extend(["Tüketici hakem heyeti başvurusu (gönüllü)", "Satıcıya ayıp ihbarı"])
        if "iş" in legal_area:
            reqs.extend(["Arabuluculuk dava şartı", "İşyeri uzlaştırma komisyonu başvurusu"])
        if "aile" in legal_area:
            reqs.extend(["Aile mahkemesi görevliliği", "Sosyal-ekonomik araştırma"])
        if "idare" in legal_area:
            reqs.extend(["İdari başvuru sürecinin tamamlanması", "Zamanaşımı süresi"])
        if not reqs:
            reqs.extend(["Görevli mahkeme yetkisi", "Dava şartları", "Zamanaşımı süresi"])
        return list(dict.fromkeys(reqs))[:6]

    def _extract_limitation_risks(self, legal_area: str) -> list[str]:
        risks: list[str] = []
        if "kira" in legal_area:
            risks.extend(["Tahliye davası açma süresi", "Temerrüt tebellüğü süresi"])
        if "iş" in legal_area:
            risks.extend(["İşçi alacakları zamanaşımı süresi", "Kıdem tazminatı süresi"])
        if "idare" in legal_area:
            risks.extend(["İdari dava açma süresi (60 gün)", "İdari başvuru süresi"])
        if "aile" in legal_area:
            risks.extend(["Nafaka zamanaşımı süresi"])
        if not risks:
            risks.extend(["Genel zamanaşımı süreleri", "Dava şartları"])
        return risks[:4]

    def _extract_common_defenses(self, legal_area: str) -> list[str]:
        defenses: list[str] = []
        if "kira" in legal_area or "tahliye" in legal_area:
            defenses.extend(["Temerrüt oluşmadı", "Bildirim usulüne uygun değil", "İhtiyaç niteliği yok"])
        if "tüketici" in legal_area or "araç" in legal_area:
            defenses.extend(["Ayıp satıştan sonra oluştu", "Alıcı ayıbı biliyordu", "İhbarda gecikme var"])
        if "iş" in legal_area:
            defenses.extend(["Fesih haklı nedenli", "Ücret zaten ödendi", "Fazla mesai yok"])
        if "icra" in legal_area:
            defenses.extend(["Alacak ödenmiş", "Yetki itirazı", "İmza sahte"])
        if not defenses:
            defenses.extend(["İspat yükü davacıdadır", "Zamanaşımı itirazı", "Vakıalar yanlış"])
        return defenses[:6]

    def _extract_language_patterns(self, text: str) -> list[str]:
        patterns: list[str] = []
        plain = self._plain(text)
        if "mahkeme" in plain and "yürütmenin durdurulması" in plain:
            patterns.append("... yürütmenin durdurulması talebiyle dava açılmıştır.")
        if "bilirkişi" in plain and "inceleme" in plain:
            patterns.append("... bilirkişi marifetiyle tespit edilmesi gerekmektedir.")
        if "tazminat" in plain and "zarar" in plain:
            patterns.append("... zararının tazmini ve feri taleplerin ayrıştırılması gerekir.")
        if "delil" in plain and "ispat" in plain:
            patterns.append("... ispat yükü dava türüne göre değerlendirilmelidir.")
        if "süre" in plain and "zamanaşımı" in plain:
            patterns.append("... süre ve zamanaşımı unsurları dosya özelinde kontrol edilmelidir.")
        return patterns[:8]

    def _generate_questions(self, legal_area: str, case_types: list[str], source_type: str) -> list[dict[str, Any]]:
        questions: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        def add(qid: str, question: str, category: str, options: list[str], reason: str) -> None:
            if qid not in seen_ids:
                seen_ids.add(qid)
                questions.append(
                    {
                        "id": qid,
                        "question": question,
                        "category": category,
                        "answer_type": "single_choice",
                        "options": options,
                        "reason": reason,
                    }
                )

        if "kira" in legal_area or "tahliye" in case_types:
            add(
                "lease_basis",
                "Kira ilişkisi nasıl kurulmuştur?",
                "taraf",
                ["Yazılı kira sözleşmesi var", "Sözlü kira ilişkisi var", "Ödeme kayıtları var"],
                "Kira ilişkisinin varlığı ve niteliği dava şartlarını etkiler.",
            )
            add(
                "unpaid_months",
                "Ödenmeyen kira ayları hangi dönemleri kapsamaktadır?",
                "miktar",
                ["3 ay ve altı", "3-6 ay", "6 ay ve üzeri", "Düzensiz ödeme"],
                "Temerrüt ve talep kapsamı için önemlidir.",
            )

        if "tüketici" in legal_area or "araç" in legal_area or "gizli ayıp" in legal_area:
            add(
                "seller_profile",
                "Satıcı kurumsal mı, gerçek kişi mi?",
                "taraf",
                ["Galeri/şirket satıcı", "Gerçek kişi satıcı", "Tacir satıcı", "Bilinmiyor"],
                "Tüketici işlemi ve sorumluluk düzeyi satıcı sıfatına göre değişir.",
            )
            add(
                "defect_discovery",
                "Ayıp ne zaman ve nasıl öğrenildi?",
                "maddi_vakia",
                ["Teslimden kısa süre sonra", "İlk kullanımda", "Serviste öğrenildi", "Bilinmiyor"],
                "Ayıp ihbarı süresi ve gizli ayıp niteliği için kritiktir.",
            )
            add(
                "defect_evidence",
                "Ayıbı destekleyen deliller nelerdir?",
                "delil",
                ["Servis raporu", "Ekspertiz raporu", "TRAMER kaydı", "Fotoğraf/video", "Tanık", "Bilinmiyor"],
                "Ayıbın varlığı ve satıştan önceki durumu ispatlanmalıdır.",
            )

        if "iş" in legal_area or "işçi" in case_types:
            add(
                "employment_duration",
                "İş ilişkisi ne kadar sürmüştür?",
                "taraf",
                ["1 yılın altında", "1-5 yıl", "5 yılın üzeri", "Bilinmiyor"],
                "Kıdem ve ihbar tazminatı hesaplamasında esas alınır.",
            )
            add(
                "salary_type",
                "Ücret nasıl ödenmiştir?",
                "miktar",
                ["Banka dekontu", "Banka + elden", "Bordro kayıtları var", "Bilinmiyor"],
                "Ücret ispatı ve fazla mesai hesabı için gereklidir.",
            )

        if "aile" in legal_area or "nafaka" in case_types:
            add(
                "support_change_reason",
                "Nafaka miktarında değişiklik nedeni nedir?",
                "talep",
                ["Gelir artışı", "Gelir azalması", "Gider değişikliği", "Hakkaniyet değişimi"],
                "Esaslı değişiklik iddiasının dayanağıdır.",
            )
            add(
                "child_status",
                "Evlatların durumu nedir?",
                "taraf",
                ["Küçük çocuk", "Genç", "Yetişkin", "Eğitim gören"],
                "Nafaka ve velayet değerlendirmesinde önemlidir.",
            )

        if "idare" in legal_area:
            add(
                "admin_process",
                "İdari başvuru aşamaları tamamlandı mı?",
                "usul",
                ["Başvuru yapıldı - reddedildi", "Zımni ret oluştu", "Üst makama başvuruldu", "Henüz başvuru yok"],
                "İdari dava şartı olarak başvuru sürecinin tamamlanması gerekir.",
            )
            add(
                "damage_existence",
                "İdari işlem nedeniyle maddi zarar doğmuş mu?",
                "zarar",
                ["Evet - maddi zarar var", "Evet - manevi zarar var", "Henüz zarar doğmadı", "Sadece hukuki menfaat ihlali"],
                "Tam yargı davası için zarar şarttır.",
            )

        if not questions:
            add(
                "core_parties",
                "Tarafların sıfatı ve rolleri nelerdir?",
                "taraf",
                ["Davacı alacaklı", "Davacı mağdur", "Davalı borçlu", "Davalı kurum"],
                "Dava konusu ve sorumluluk nispeti için gereklidir.",
            )
            add(
                "core_demand",
                "Somut talep ve dava türü nedir?",
                "talep",
                ["Maddi tazminat", "Manevi tazminat", "Alacağın tahsili", "İptal", "Tespit"],
                "Dilekçe konusu ve sonuç istemi buna göre kurulacaktır.",
            )

        return questions

    @staticmethod
    def _plain(text: str) -> str:
        import unicodedata

        normalized = str(text or "").casefold().translate(
            str.maketrans(
                {
                    "ç": "c",
                    "ğ": "g",
                    "ı": "i",
                    "ö": "o",
                    "ş": "s",
                    "ü": "u",
                    "Ç": "c",
                    "Ğ": "g",
                    "İ": "i",
                    "Ö": "o",
                    "Ş": "s",
                    "Ü": "u",
                }
            )
        )
        decomposed = unicodedata.normalize("NFKD", normalized)
        return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


legal_source_ingest_service = LegalSourceIngestService()