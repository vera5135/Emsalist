"""Rule-based case analysis service.

The public interface is deliberately small so this implementation can later be
replaced by an LLM-backed analyzer without changing the HTTP layer.
"""

import re
from dataclasses import dataclass

from app.models.case_models import CaseAnalyzeResponse


@dataclass(frozen=True)
class TopicRule:
    topic: str
    triggers: tuple[str, ...]
    keywords: tuple[str, ...]


TOPIC_RULES = (
    TopicRule(
        topic="Nafakanın kaldırılması veya indirilmesi",
        triggers=(
            "nafaka",
            "iştirak nafakası",
            "yoksulluk nafakası",
            "nafakanın kaldırılması",
            "nafaka indirimi",
        ),
        keywords=(
            "nafakanın kaldırılması",
            "nafakanın indirilmesi",
            "yoksulluk nafakası",
            "iştirak nafakası",
            "tarafların ekonomik durumu",
            "hakkaniyet",
            "TMK 176",
            "TMK 331",
        ),
    ),
    TopicRule(
        topic="İşçilik alacakları",
        triggers=("kıdem tazminatı", "ihbar tazminatı", "fazla mesai", "işçi"),
        keywords=("işçilik alacağı", "kıdem tazminatı", "ihbar tazminatı", "fazla çalışma"),
    ),
    TopicRule(
        topic="Kira uyuşmazlığı",
        triggers=("kira", "kiracı", "tahliye", "kira bedeli"),
        keywords=("kira sözleşmesi", "tahliye", "kira bedeli", "kiracı"),
    ),
    TopicRule(
        topic="Ayıplı araç satışı ve gizli ayıp",
        triggers=("ayıp", "ayıplı araç", "gizli ayıp", "araç satışı", "ekspertiz", "ağır hasar", "tramer"),
        keywords=(
            "gizli ayıp",
            "ayıplı araç satışı",
            "satıcının ayıba karşı sorumluluğu",
            "seçimlik haklar",
            "sözleşmeden dönme",
            "bedel indirimi",
            "TBK 219",
            "TBK 227",
        ),
    ),
)

FACT_MARKERS = (
    "gelir",
    "maaş",
    "işsiz",
    "işe girdi",
    "çalışmaya başladı",
    "yeniden evlen",
    "evlendi",
    "emekli",
    "çocuk",
    "eğitim",
    "sağlık",
    "gider",
    "ödeme",
    "yoksulluk",
    "ekonomik",
    "maddi durum",
    "araç",
    "ayıp",
    "gizli ayıp",
    "ekspertiz",
    "ağır hasar",
    "motor",
    "servis",
    "satış",
)


class RuleBasedCaseAnalyzer:
    """Extract a legal topic, salient facts and keywords from a case summary."""

    def analyze(self, case_text: str) -> CaseAnalyzeResponse:
        normalized = " ".join(case_text.split())
        lowered = normalized.casefold()
        rule = self._find_topic(lowered)

        facts = self._extract_facts(normalized)
        if not facts:
            facts = [normalized]

        keywords = list(rule.keywords) if rule else self._generic_keywords(normalized)
        return CaseAnalyzeResponse(
            legal_topic=rule.topic if rule else "Genel hukuki uyuşmazlık",
            case_facts=facts,
            legal_keywords=keywords,
        )

    @staticmethod
    def _find_topic(lowered_text: str) -> TopicRule | None:
        scored_rules = (
            (sum(trigger in lowered_text for trigger in rule.triggers), rule)
            for rule in TOPIC_RULES
        )
        score, best_rule = max(scored_rules, key=lambda item: item[0])
        return best_rule if score else None

    @staticmethod
    def _extract_facts(text: str) -> list[str]:
        sentences = [
            sentence.strip(" -\t")
            for sentence in re.split(r"(?<=[.!?])\s+|[;\n]+", text)
            if sentence.strip()
        ]
        selected = [
            sentence
            for sentence in sentences
            if any(marker in sentence.casefold() for marker in FACT_MARKERS)
        ]
        return selected[:8]

    @staticmethod
    def _generic_keywords(text: str) -> list[str]:
        words = re.findall(r"[a-zçğıöşü]{4,}", text.casefold())
        stopwords = {"olan", "olarak", "ancak", "daha", "için", "ile", "veya", "bir", "davacı", "davalı"}
        frequencies: dict[str, int] = {}
        for word in words:
            if word not in stopwords:
                frequencies[word] = frequencies.get(word, 0) + 1
        return sorted(frequencies, key=lambda word: (-frequencies[word], word))[:8]


case_analyzer = RuleBasedCaseAnalyzer()
