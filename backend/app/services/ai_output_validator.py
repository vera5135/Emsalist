"""Validation helpers for AI generated legal outputs."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


VEHICLE_MARKERS = (
    "ayipli arac",
    "gizli ayip",
    "ikinci el arac",
    "arac satisi",
    "tramer",
    "ekspertiz",
    "motor",
    "tbk 219",
    "tbk 223",
    "tbk 227",
    "tbk 229",
    "tkhk",
)

VEHICLE_BLOCKED_TOPICS = (
    "tmk",
    "nafaka",
    "tmk 175",
    "tmk 176",
    "bosanma",
    "velayet",
    "aile hukuku",
)

BANNED_ARTIFACTS = (
    "talebimizin kabulu talebimizin kabulune",
    "talebimizin kabulu talebimiz ile",
    "ictihat sinyali",
    "ictihat sinyalleri",
    "alicinin, aracin, arac",
    "aracin, arac, aractaki",
    "arac, aractaki",
    "eksik bilgiler tamamlandiginda",
    "riskli degerlendirmeler",
)

ARTICLE_RE = re.compile(r"\b(TMK|TBK|HMK|TKHK)\s*(?:m\.?|madde)?\s*([0-9]{1,4}(?:/[0-9]+)?)", flags=re.IGNORECASE)
DECISION_RE = re.compile(r"\bE\.\s*([0-9./-]+).*?\bK\.\s*([0-9./-]+)", flags=re.IGNORECASE | re.DOTALL)


class AIOutputValidator:
    def audit_draft(
        self,
        *,
        draft_text: str,
        case_text: str = "",
        selected_decisions: list[dict[str, Any]] | None = None,
    ) -> dict[str, list[str]]:
        plain_draft = self.plain(draft_text)
        plain_case = self.plain(case_text)
        is_vehicle = self.is_vehicle_case(f"{plain_case} {plain_draft}")

        critical: list[str] = []
        major: list[str] = []
        minor: list[str] = []
        source_problems: list[str] = []
        precedent_problems: list[str] = []
        language_problems: list[str] = []

        for banned in BANNED_ARTIFACTS:
            if banned in plain_draft:
                language_problems.append(f"Yasaklı veya yapay ifade bulundu: {banned}")

        if is_vehicle:
            for topic in VEHICLE_BLOCKED_TOPICS:
                if topic in plain_draft:
                    critical.append(f"Araç gizli ayıp dosyasında konu dışı ifade bulundu: {topic}")

        if "konu" in plain_draft and "talebimiz ile" in plain_draft:
            major.append("KONU bölümü genel ve acemi bir kalıpla kurulmuş.")
        if "sonuc ve istem" in plain_draft and is_vehicle and "bedel indirimi" not in plain_draft:
            major.append("Araç dosyasında SONUÇ VE İSTEM terditli bedel indirimi içermiyor.")
        if "eksik bilgiler tamamlandiginda" in plain_draft:
            major.append("Olay metni varken gereksiz eksik bilgi cümlesi kullanılmış.")

        duplicate_decisions = self._duplicate_decision_identities(draft_text)
        for identity in duplicate_decisions:
            precedent_problems.append(f"Aynı emsal karar birden fazla kullanılmış: {identity}")

        if self._risk_presented_as_supportive(plain_draft):
            precedent_problems.append("Riskli/aleyhe karar talebi destekler gibi sunulmuş.")

        if selected_decisions:
            seen: set[str] = set()
            for decision in selected_decisions:
                identity = self.decision_identity(decision)
                if identity in seen:
                    precedent_problems.append(f"selected_decisions içinde tekrar eden karar var: {identity}")
                seen.add(identity)

        return {
            "critical": critical,
            "major": major,
            "minor": minor,
            "source_problems": source_problems,
            "precedent_problems": precedent_problems,
            "language_problems": language_problems,
        }

    def validate_refined_draft(
        self,
        *,
        original_draft: str,
        refined_draft: str,
        case_text: str = "",
    ) -> list[str]:
        warnings: list[str] = []
        audit = self.audit_draft(draft_text=refined_draft, case_text=case_text)
        for group in ("critical", "major", "precedent_problems", "language_problems"):
            warnings.extend(audit[group])

        original_articles = self._article_set(original_draft)
        refined_articles = self._article_set(refined_draft)
        new_articles = sorted(refined_articles - original_articles)
        if new_articles:
            warnings.append("Verilmeyen kanun maddesi eklenmiş olabilir: " + ", ".join(new_articles))

        original_decisions = self._decision_set(original_draft)
        refined_decisions = self._decision_set(refined_draft)
        new_decisions = sorted(refined_decisions - original_decisions)
        if new_decisions:
            warnings.append("Verilmeyen esas/karar numarası eklenmiş olabilir: " + ", ".join(new_decisions))

        return self.dedupe(warnings)

    def clean_ai_list(self, values: Any, *, max_items: int = 20) -> list[str]:
        if not isinstance(values, list):
            return []
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = " ".join(str(value or "").split())
            key = self.plain(cleaned)
            if cleaned and key not in seen:
                seen.add(key)
                result.append(cleaned)
            if len(result) >= max_items:
                break
        return result

    @staticmethod
    def decision_identity(decision: dict[str, Any]) -> str:
        parts = [
            decision.get("court") or decision.get("source") or "Yargıtay",
            decision.get("esas_no") or "",
            decision.get("karar_no") or "",
            decision.get("date") or "",
        ]
        return " | ".join(" ".join(str(part).split()) for part in parts)

    @staticmethod
    def is_vehicle_case(text: str) -> bool:
        plain_text = AIOutputValidator.plain(text)
        return any(marker in plain_text for marker in VEHICLE_MARKERS)

    @staticmethod
    def _risk_presented_as_supportive(plain_text: str) -> bool:
        if not any(marker in plain_text for marker in ("riskli", "aleyhe", "usul")):
            return False
        return any(marker in plain_text for marker in ("talebi destekler", "destekleyen emsal", "destekleyici emsal"))

    @staticmethod
    def _duplicate_decision_identities(text: str) -> list[str]:
        seen: set[str] = set()
        duplicates: list[str] = []
        for esas, karar in DECISION_RE.findall(text):
            identity = f"E. {esas} K. {karar}"
            key = AIOutputValidator.plain(identity)
            if key in seen and identity not in duplicates:
                duplicates.append(identity)
            seen.add(key)
        return duplicates

    @staticmethod
    def _article_set(text: str) -> set[str]:
        return {f"{code.upper()} {article}" for code, article in ARTICLE_RE.findall(text)}

    @staticmethod
    def _decision_set(text: str) -> set[str]:
        return {f"E. {esas} K. {karar}" for esas, karar in DECISION_RE.findall(text)}

    @staticmethod
    def dedupe(values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            key = AIOutputValidator.plain(value)
            if value and key not in seen:
                seen.add(key)
                result.append(value)
        return result

    @staticmethod
    def plain(value: str) -> str:
        translated = str(value or "").translate(
            str.maketrans(
                {
                    "ç": "c",
                    "Ç": "c",
                    "ğ": "g",
                    "Ğ": "g",
                    "ı": "i",
                    "I": "i",
                    "İ": "i",
                    "ö": "o",
                    "Ö": "o",
                    "ş": "s",
                    "Ş": "s",
                    "ü": "u",
                    "Ü": "u",
                }
            )
        )
        translated = translated.translate(
            str.maketrans(
                {
                    "ç": "c",
                    "Ç": "c",
                    "ğ": "g",
                    "Ğ": "g",
                    "ı": "i",
                    "İ": "i",
                    "ö": "o",
                    "Ö": "o",
                    "ş": "s",
                    "Ş": "s",
                    "ü": "u",
                    "Ü": "u",
                }
            )
        )
        decomposed = unicodedata.normalize("NFKD", translated)
        plain = "".join(character for character in decomposed if not unicodedata.combining(character))
        return re.sub(r"\s+", " ", plain).strip().casefold()


ai_output_validator = AIOutputValidator()
