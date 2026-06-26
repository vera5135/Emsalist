"""Quality control service for Legal Brain cards."""

from __future__ import annotations

import re
from typing import Any


class LegalBrainQualityService:
    """Evaluate and score legal brain cards for quality."""

    SUMMARY_MIN_CHARS = 50
    KEYWORD_OVERLAP_MIN = 2

    def evaluate_card(self, card: dict[str, Any]) -> dict[str, Any]:
        score = 100
        issues: list[str] = []

        # 1. source_file exists and not empty
        if not card.get("source_file"):
            score -= 15
            issues.append("source_file eksik veya boş.")

        # 2. source_reliability exists
        if "source_reliability" not in card:
            score -= 10
            issues.append("source_reliability alanı eksik.")

        # 3. statute_article must have article_no
        if card.get("card_type") == "statute_article" and not card.get("article_no"):
            score -= 20
            issues.append("Kanun maddesi kartında article_no eksik.")

        # 4. case_law must have court AND (esas_no OR karar_no)
        if card.get("card_type") == "case_law":
            if not card.get("court"):
                score -= 20
                issues.append("İçtihat kartında mahkeme bilgisi eksik.")
            if not card.get("esas_no") and not card.get("karar_no"):
                score -= 20
                issues.append("İçtihat kartında esas/karar numarası eksik.")

        # 5. question_suggestions must have options
        questions = card.get("question_suggestions", [])
        if questions:
            for question in questions:
                if not isinstance(question, dict):
                    continue
                options = question.get("options", [])
                if not options or not isinstance(options, list):
                    score -= 5
                    issues.append(f"Soru '{question.get('id', '?')}' için options listesi eksik veya boş.")
                    break

        # 6. Low reliability must have warning
        reliability = card.get("source_reliability", "low")
        if reliability == "low":
            warnings = card.get("warnings", [])
            warning_text = " ".join(warnings).lower()
            if "hukuki dayanak" not in warning_text and "tek başına" not in warning_text:
                score -= 10
                issues.append("Low reliability kaynak uyarısı eksik.")

        # 7. Fabricated case numbers (e.g. 0000/0000)
        for field in ["esas_no", "karar_no"]:
            value = card.get(field, "")
            if isinstance(value, str) and re.fullmatch(r"0{2,4}/0{2,4}", value):
                score -= 15
                issues.append(f"{field} alanında muhtemel uydurma numara tespit edildi.")
                break

        # 8. Summary length check
        summary = (
            card.get("summary")
            or card.get("doctrine_summary")
            or card.get("article_text", "")
        )
        if len(summary) < self.SUMMARY_MIN_CHARS:
            score -= 5
            issues.append("Kart özeti çok kısa.")

        # 10. Keyword overlap with summary
        keywords = card.get("keywords", [])
        if keywords and summary:
            plain_summary = self._plain(summary)
            overlap = sum(1 for kw in keywords[:10] if self._plain(kw) in plain_summary)
            if overlap < self.KEYWORD_OVERLAP_MIN:
                score -= 5
                issues.append("Anahtar kelimeler özet ile uyuşmuyor.")

        score = max(0, min(100, score))
        return {
            "quality_score": score,
            "issues": issues,
            "safe_for_retrieval": score >= 50,
            "safe_for_draft_support": score >= 70,
        }

    def evaluate_cards(self, cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen_ids: set[str] = set()
        results: list[dict[str, Any]] = []
        for card in cards:
            # 9. Duplicate card_id check in batch
            card_id = card.get("card_id")
            if card_id and card_id in seen_ids:
                evaluation = {
                    "quality_score": 0,
                    "issues": ["Duplicate kart_id tespit edildi."],
                    "safe_for_retrieval": False,
                    "safe_for_draft_support": False,
                }
            else:
                if card_id:
                    seen_ids.add(card_id)
                evaluation = self.evaluate_card(card)
            results.append(evaluation)
        return results

    def batch_report(self, cards: list[dict[str, Any]]) -> dict[str, Any]:
        evaluations = self.evaluate_cards(cards)
        scores = [e["quality_score"] for e in evaluations]
        avg_score = round(sum(scores) / len(scores), 2) if scores else 0

        return {
            "total_cards": len(cards),
            "average_quality_score": avg_score,
            "safe_for_retrieval_count": sum(1 for e in evaluations if e["safe_for_retrieval"]),
            "safe_for_draft_support_count": sum(1 for e in evaluations if e["safe_for_draft_support"]),
            "failed_count": sum(1 for e in evaluations if not e["safe_for_retrieval"]),
        }

    @staticmethod
    def _plain(text: str) -> str:
        import unicodedata
        normalized = str(text or "").casefold().translate(
            str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
                          "Ç": "c", "Ğ": "g", "İ": "i", "Ö": "o", "Ş": "s", "Ü": "u"})
        )
        decomposed = unicodedata.normalize("NFKD", normalized)
        return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


legal_brain_quality_service = LegalBrainQualityService()