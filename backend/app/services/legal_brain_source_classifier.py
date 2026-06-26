"""Classify legal sources by type, reliability, and legal area."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any



LEGAL_BRAIN_ROOT = Path(__file__).resolve().parents[1] / "legal_brain"
TAXONOMY_PATH = LEGAL_BRAIN_ROOT / "metadata" / "legal_area_taxonomy.json"

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

SOURCE_TYPES = {
    "statute": ["kanun", "mevzuat", "tüzük", "tuzuk", "kanun metni", "tam metin"],
    "regulation": ["yönetmelik", "yonetmelik", "genelge", "tebliğ", "teblig", "sirküler", "sirkuler", "resmi mevzuat"],
    "official_gazette": ["resmî gazete", "resmi gazete", "resmigazete", "resmî", "rg"],
    "case_law": ["yargıtay", "danıştay", "sayıştay", "sayistay", "uyap", "emsal", "karar"],
    "yargitay_decision": ["yargıtay", "yargitay hukuk genel kurulu", "yargıtay ceza genel kurulu", "ygk", "ygk hukuk"],
    "danistay_decision": ["danıştay", "danistay idari dava daireleri", "ddk", "danıştay kararı"],
    "constitutional_court_decision": ["anayasa mahkemesi", "aym", "anayasa mahkemesi kararı", "aym kararı"],
    "doctrine": ["doktrin", "öğreti", "ogreti", "kitap", "dergi", "makale", "akademik", "yayın"],
    "bar_publication": ["baro", "barolar birliği", "tbb", "izmir barosu", "istanbul barosu", "ankara barosu", "baro bülteni"],
    "petition_sample": ["dilekçe", "dilekce", "örnek dilekçe", "ornek dilekce", "talep", "istem", "dilekçe örneği"],
    "procedural_guide": ["usul", "süre", "sure", "dava şartı", "dava sarti", "görev", "gorev", "yetki", "zamanaşımı", "zamanasimi", "rehber", "kılavuz"],
    "user_verified_note": ["başarılı dava", "deneyim", "pratik not", "uygulama notu"],
    "dictionary": ["sözlük", "sozluk", "kavram", "tanım", "terim", "tanim", "hukuk sozlugu"],
    "unknown": [],
}


class LegalBrainSourceClassifier:
    """Classify legal source type, reliability, and legal area."""

    def __init__(self) -> None:
        self._taxonomy = self._load_taxonomy()

    @staticmethod
    def _load_taxonomy() -> dict[str, Any]:
        if TAXONOMY_PATH.exists():
            return json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
        return {}

    def classify(self, text: str, source_file: str = "") -> dict[str, Any]:
        """Classify source and return structured metadata."""
        plain_text = self._plain(text)
        source_type = self._detect_source_type(plain_text)
        reliability = self._assess_reliability(plain_text, source_file, source_type)
        legal_area_candidates = self._detect_legal_area_candidates(plain_text)
        detected_codes = self._detect_codes(plain_text)
        detected_case_types = self._detect_case_types(plain_text)
        confidence = self._calculate_confidence(reliability, len(legal_area_candidates))

        warnings = self._generate_warnings(source_type, reliability, plain_text)

        return {
            "source_type": source_type,
            "source_reliability": reliability,
            "legal_area_candidates": legal_area_candidates,
            "detected_codes": detected_codes,
            "detected_case_types": detected_case_types,
            "confidence": confidence,
            "warnings": warnings,
        }

    def _detect_source_type(self, plain_text: str) -> str:
        """Detect the primary source type from text."""
        if not plain_text:
            return "unknown"
        for source_type, markers in SOURCE_TYPES.items():
            if source_type == "unknown":
                continue
            if any(marker in plain_text for marker in markers):
                # Narrower checks: prefer specific over general
                if source_type == "yargitay_decision" and "yargıtay" in plain_text:
                    return "yargitay_decision"
                if source_type == "danistay_decision" and "danıştay" in plain_text:
                    return "danistay_decision"
                if source_type == "constitutional_court_decision" and any(m in plain_text for m in ["anayasa mahkemesi", "aym"]):
                    return "constitutional_court_decision"
                if source_type in ("case_law", "yargitay_decision", "danistay_decision"):
                    return "case_law"
                if source_type == "official_gazette":
                    return "official_gazette"
                if source_type in ("statute", "regulation"):
                    return "statute"
                if source_type in ("doctrine", "bar_publication"):
                    return "doctrine"
                if source_type == "petition_sample":
                    return "petition_sample"
                if source_type == "procedural_guide":
                    return "procedural_guide"
                if source_type == "dictionary":
                    return "dictionary"
                return source_type
        return "unknown"

    def _assess_reliability(self, plain_text: str, source_file: str, source_type: str) -> str:
        """Assess source reliability based on source type and content."""
        # High reliability sources
        if source_type in ("statute", "official_gazette", "regulation"):
            return "high"
        if source_type in ("yargitay_decision", "danistay_decision", "constitutional_court_decision", "case_law"):
            if any(m in plain_text for m in ["yargıtay", "danıştay", "anayasa mahkemesi", "uyap", "esas no", "karar no"]):
                return "high"
        if any(m in plain_text for m in ["resmî gazete", "resmi gazete", "kanun", "tüzük", "yönetmelik", "kararname"]):
            return "high"
        
        # Medium reliability sources
        if source_type in ("doctrine", "bar_publication", "procedural_guide", "user_verified_note"):
            return "medium"
        if any(m in plain_text for m in ["baro", "tbb", "makale", "kitap", "dergi", "akademik", "doktrin", "üniversite", "yayın"]):
            return "medium"
        if any(m in plain_text for m in ["başarılı dava", "deneyim", "pratik not", "doğrulandı"]):
            return "medium"
        
        # Low reliability sources
        if any(m in plain_text for m in ["blog", "forum", "haber", "reklam", "tanıtım", "sosyal medya"]):
            return "low"
        
        # Default based on source type
        if source_type == "petition_sample":
            return "medium"
        if source_type == "dictionary":
            return "medium"
        
        return "low"

    def _detect_legal_area_candidates(self, plain_text: str) -> list[dict[str, Any]]:
        """Score each legal area from taxonomy based on keyword matches."""
        candidates: list[dict[str, Any]] = []
        if not self._taxonomy:
            return [{"legal_area": "belirsiz", "score": 0, "matched_terms": []}]

        for area, details in self._taxonomy.items():
            keywords = details.get("keywords", [])
            matched = [kw for kw in keywords if kw in plain_text]
            if matched:
                candidates.append({
                    "legal_area": area,
                    "score": len(matched),
                    "matched_terms": matched[:8],
                })

        # Also check source_text directly for area patterns not in taxonomy
        candidates.sort(key=lambda x: x["score"], reverse=True)
        if not candidates:
            return [{"legal_area": "belirsiz", "score": 0, "matched_terms": []}]
        return candidates[:4]

    def _detect_codes(self, plain_text: str) -> list[str]:
        """Detect Turkish legal code references."""
        code_patterns = [
            r"(?:TMK|tbk|hmk|iik|tck|cmk|ttk|KvkK|İİk|ıİk)\s*(?:m\.|madde)?\s*\d*",
            r"tbk\s*m\.\s*\d+",
            r"tmk\s*m\.\s*\d+",
            r"hmk\s*m\.\s*\d+",
            r"iik\s*m\.\s*\d+",
            r"tck\s*m\.\s*\d+",
            r"cmk\s*m\.\s*\d+",
            r"ttk\s*m\.\s*\d+",
            r"madde\s*\d+",
            r"m\.\s*\d+",
            r"\d{4}\s*sayılı", "sayili",
        ]
        found: list[str] = []
        for pattern in code_patterns:
            matches = re.findall(pattern, plain_text)
            found.extend(matches[:3])
        unique = list(dict.fromkeys(found))
        return unique[:10]

    def _detect_case_types(self, plain_text: str) -> list[str]:
        """Detect likely case types from text."""
        case_patterns = {
            "alacak davası": ["alacak", "tahsil", "ödenmedi"],
            "tazminat davası": ["tazminat", "zarar", "haksız fiil"],
            "müdahalenin men'i": ["müdahale", "mudahale", "gürültü"],
            "iptal davası": ["iptal", "yürütmenin durdurulması"],
            "kira tahliyesi": ["tahliye", "kira", "kiracı"],
            "işçi alacağı": ["işçi", "iscı", "kidem", "kidem tazminatı"],
            "nafaka davası": ["nafaka", "yoksulluk nafakası"],
        }
        found: list[str] = []
        for case_type, markers in case_patterns.items():
            if any(m in plain_text for m in markers):
                found.append(case_type)
        return found[:4]

    def _calculate_confidence(self, reliability: str, candidate_count: int) -> float:
        """Calculate classification confidence score."""
        base = {"high": 0.8, "medium": 0.5, "low": 0.2}
        score = base.get(reliability, 0.2)
        if candidate_count >= 2:
            score = min(1.0, score + 0.1)
        if candidate_count == 1:
            score = max(0.1, score - 0.1)
        return round(score, 2)

    def _generate_warnings(self, source_type: str, reliability: str, plain_text: str) -> list[str]:
        """Generate warnings about classification."""
        warnings: list[str] = []
        if reliability == "low":
            warnings.append("Bu kaynak tek başına hukuki dayanak yapılamaz; yalnızca yardımcı/pratik not olarak kullanılmalıdır.")
        if source_type == "unknown":
            warnings.append("Kaynak türü belirlenemedi.")
        if len(plain_text) < 50:
            warnings.append("Kaynak metni çok kısa, sınıflandırma güvenilir olmayabilir.")
        if source_type == "petition_sample":
            warnings.append("Örnek dilekçe; hukuki dayanak olarak kullanılmamalı, sadece stil ve yapı öğrenmek için kullanılmalıdır.")
        return warnings

    def is_large_file(self, file_path: str | Path) -> bool:
        """Check if file exceeds size limit."""
        path = Path(file_path)
        return path.exists() and path.stat().st_size > MAX_FILE_SIZE_BYTES

    @staticmethod
    def _plain(text: str) -> str:
        """Normalize Turkish text to plain ASCII lowercase."""
        import unicodedata
        normalized = str(text or "").casefold().translate(
            str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
                          "Ç": "c", "Ğ": "g", "İ": "i", "Ö": "o", "Ş": "s", "Ü": "u"})
        )
        decomposed = unicodedata.normalize("NFKD", normalized)
        return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


legal_brain_source_classifier = LegalBrainSourceClassifier()