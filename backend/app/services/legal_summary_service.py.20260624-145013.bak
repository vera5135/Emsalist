"""Rule-based legal summarisation helpers for real Yargıtay decisions."""

from __future__ import annotations

import re
import unicodedata
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime

from app.models.yargitay_models import YargitayDecision
from app.services.petition_profile_service import get_petition_profile, profile_relevance_terms


PROCEDURAL_PATTERNS = (
    "temyiz sınırı",
    "kesinlik sınırı",
    "parasal sınır",
    "kesin niteliktedir",
    "temyiz edilemez",
    "temyizi kabil değildir",
    "usulden",
    "süre yönünden",
    "hukuki yarar yokluğu",
    "görevsizlik",
    "yetkisizlik",
    "karar düzeltme",
)

ADVERSE_PATTERNS = (
    "davanın reddi",
    "talebin reddi",
    "reddine",
    "yerinde değildir",
    "ispatlanamamıştır",
)

SUPPORTIVE_PATTERNS = (
    "kabulüne",
    "bozulmasına",
    "karar verilmesi gerekir",
    "isabetli görülmemiştir",
    "hakkaniyet",
    "somut olay",
)


@dataclass(frozen=True)
class LegalDecisionSummary:
    relevance_bonus: int
    rank_penalty: int
    short_summary: str
    legal_principle: str
    why_relevant: str
    lehe_aleyhe: str
    is_procedural: bool
    petition_paragraph: str
    clean_text_preview: str


class RuleBasedLegalSummaryService:
    """Create short summaries and petition-ready text from decision content."""

    def summarize(
        self,
        *,
        case_text: str,
        decision: YargitayDecision,
        base_similarity_score: int,
    ) -> LegalDecisionSummary:
        profile = get_petition_profile(case_text)
        text = self._readable_text(decision.clean_text or decision.raw_text)
        match_text = self._matchable_text(text)
        profile_terms = profile_relevance_terms(profile)
        signal_labels, signal_score = self._relevance_signal_score(match_text, profile_terms)
        is_procedural = self._is_procedural_only(match_text, signal_score)
        outcome = self._decision_outcome(match_text)
        lehe_aleyhe = self._classify_alignment(match_text, outcome, is_procedural)

        recency_bonus = self._recency_bonus(decision.date)
        alignment_bonus = 3 if lehe_aleyhe == "Lehe" else 0
        relevance_bonus = min(signal_score + recency_bonus + alignment_bonus, 35)
        rank_penalty = self._rank_penalty(is_procedural=is_procedural, lehe_aleyhe=lehe_aleyhe, signal_labels=signal_labels)
        final_score = max(0, min(100, base_similarity_score + relevance_bonus - rank_penalty))
        identity = self._identity(decision)

        usefulness = self.usefulness_label(
            score=final_score,
            lehe_aleyhe=lehe_aleyhe,
            is_procedural=is_procedural,
        )

        return LegalDecisionSummary(
            relevance_bonus=relevance_bonus,
            rank_penalty=rank_penalty,
            short_summary=self._short_summary(text, signal_labels),
            legal_principle=self._legal_principle(profile.legal_assessment, signal_labels, is_procedural),
            why_relevant=self._why_relevant(
                usefulness=usefulness,
                signal_labels=signal_labels,
                is_procedural=is_procedural,
            ),
            lehe_aleyhe=lehe_aleyhe,
            is_procedural=is_procedural,
            petition_paragraph=self._petition_paragraph(
                identity=identity,
                profile_type=profile.petition_type,
                lehe_aleyhe=lehe_aleyhe,
                is_procedural=is_procedural,
                signal_labels=signal_labels,
            ),
            clean_text_preview=self._preview(text),
        )

    def usefulness_label(self, *, score: int, lehe_aleyhe: str, is_procedural: bool) -> str:
        if is_procedural:
            return "Düşük"
        if lehe_aleyhe == "Aleyhe":
            return "Riskli / Aleyhe"
        if lehe_aleyhe == "Lehe" and score >= 70:
            return "Yüksek"
        if score >= 45:
            return "Orta"
        return "Düşük"

    def _short_summary(self, text: str, signal_labels: list[str]) -> str:
        sentences = self._sentences(text)
        needles = tuple(signal_labels[:6]) + ("dava", "talep", "mahkeme", "uyuşmazlık", "karar")
        chosen: list[str] = []
        for sentence in sentences:
            matchable = self._matchable_text(sentence)
            if any(self._has(matchable, needle) for needle in needles):
                chosen.append(sentence)
            if len(chosen) >= 3:
                break
        if not chosen:
            chosen = sentences[:2]
        return self._clip(" ".join(chosen), 750)

    @staticmethod
    def _legal_principle(profile_assessment: str, signal_labels: list[str], is_procedural: bool) -> str:
        if is_procedural:
            return (
                "Karar ağırlıklı olarak usul, süre, görev, yetki veya kanun yolu koşullarıyla ilgilidir; "
                "maddi uyuşmazlık bakımından sınırlı kullanılmalıdır."
            )
        signal_text = ", ".join(signal_labels[:5])
        suffix = f" Kararda öne çıkan bağlantılar: {signal_text}." if signal_text else ""
        return profile_assessment + suffix

    @staticmethod
    def _why_relevant(*, usefulness: str, signal_labels: list[str], is_procedural: bool) -> str:
        signal_text = ", ".join(signal_labels[:6]) if signal_labels else "sınırlı kavram örtüşmesi"
        note = " Usuli ağırlık nedeniyle alt sıralamaya itildi." if is_procedural else ""
        return f"Dilekçede kullanılabilirlik: {usefulness}. Öne çıkan bağlantılar: {signal_text}.{note}"

    @staticmethod
    def _petition_paragraph(
        *,
        identity: str,
        profile_type: str,
        lehe_aleyhe: str,
        is_procedural: bool,
        signal_labels: list[str],
    ) -> str:
        if is_procedural:
            return (
                f"{identity} sayılı karar daha çok usul, süre, görev, yetki veya kanun yolu koşullarıyla ilgilidir. "
                f"Bu nedenle {profile_type} bakımından maddi uyuşmazlığın ana dayanağı yapılmamalı; yalnızca usuli riskleri "
                "göstermek amacıyla sınırlı kullanılmalıdır."
            )

        signal_text = ", ".join(signal_labels[:4]) if signal_labels else "somut olay ve hukuki değerlendirme"
        if lehe_aleyhe == "Aleyhe":
            return (
                f"{identity} sayılı karar, {profile_type} yönünden karşı tarafça ileri sürülebilecek değerlendirmeler "
                f"içermektedir. Dilekçede somut olayın bu karardan ayrılan yönleri özellikle {signal_text} ekseninde açıklanmalıdır."
            )

        return (
            f"{identity} sayılı karar, {profile_type} bakımından {signal_text} yönünden somut olaya temas eden içtihat "
            "değerlendirmesi içermektedir. Bu nedenle dilekçede talebin maddi vakıa, delil ve hukuki dayanak bağlantısını "
            "destekleyen kaynak olarak kullanılabilir."
        )

    def _classify_alignment(self, match_text: str, outcome: str, is_procedural: bool) -> str:
        supportive_score = sum(self._has(match_text, pattern) for pattern in SUPPORTIVE_PATTERNS)
        adverse_score = sum(self._has(match_text, pattern) for pattern in ADVERSE_PATTERNS)
        if is_procedural:
            return "Aleyhe" if outcome == "Ret" else "Nötr"
        if adverse_score > supportive_score:
            return "Aleyhe"
        if supportive_score > adverse_score or outcome == "Bozma":
            return "Lehe"
        return "Nötr"

    def _relevance_signal_score(self, match_text: str, profile_terms: list[str]) -> tuple[list[str], int]:
        labels: list[str] = []
        for term in profile_terms:
            if len(term) >= 4 and self._has(match_text, term):
                labels.append(term)
            if len(labels) >= 10:
                break
        return labels, min(len(labels) * 3, 25)

    def _decision_outcome(self, match_text: str) -> str:
        if self._has(match_text, "BOZULMASINA"):
            return "Bozma"
        if self._has(match_text, "REDDİNE"):
            return "Ret"
        return "Belirsiz"

    def _is_procedural_only(self, match_text: str, signal_score: int) -> bool:
        procedural_hits = sum(self._has(match_text, pattern) for pattern in PROCEDURAL_PATTERNS)
        return procedural_hits > 0 and signal_score <= 6

    @staticmethod
    def _rank_penalty(*, is_procedural: bool, lehe_aleyhe: str, signal_labels: list[str]) -> int:
        if is_procedural:
            return 35
        if lehe_aleyhe == "Aleyhe":
            return 10
        if not signal_labels:
            return 8
        return 0

    def _recency_bonus(self, date_text: str) -> int:
        year = self._extract_year(date_text)
        if year >= 2020:
            return 4
        if year >= 2015:
            return 3
        if year >= 2010:
            return 2
        if year >= 2005:
            return 1
        return 0

    @staticmethod
    def _extract_year(date_text: str) -> int:
        for date_format in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
            with suppress(ValueError):
                return datetime.strptime(date_text.strip(), date_format).year
        match = re.search(r"(19|20)\d{2}", date_text)
        return int(match.group(0)) if match else 0

    def _sentences(self, text: str) -> list[str]:
        normalized = " ".join(text.split())
        sentences = [
            sentence.strip(" -\t")
            for sentence in re.split(r"(?<=[.!?])\s+", normalized)
            if sentence.strip()
        ]
        return sentences[:35]

    def _preview(self, text: str) -> str:
        preview = self._clip(" ".join(text.split()), 1000)
        last_stop = max(preview.rfind("."), preview.rfind("!"), preview.rfind("?"))
        if 650 <= last_stop < len(preview) - 1:
            return preview[: last_stop + 1]
        return preview

    @staticmethod
    def _identity(decision: YargitayDecision) -> str:
        return f"{decision.court}, E. {decision.esas_no}, K. {decision.karar_no}, T. {decision.date}"

    def _readable_text(self, text: str) -> str:
        fixed = self._fix_mojibake(text)
        return self._normalize_common_noise(fixed)

    def _matchable_text(self, text: str) -> str:
        readable = self._readable_text(text)
        variants = [text, readable]
        expanded: list[str] = []
        for value in variants:
            expanded.append(value.casefold())
            expanded.append(self._plain(value))
        return "\n".join(dict.fromkeys(expanded))

    @staticmethod
    def _fix_mojibake(text: str) -> str:
        with suppress(UnicodeEncodeError, UnicodeDecodeError):
            fixed = text.encode("latin1").decode("utf-8")
            if fixed != text and any(character in fixed for character in "çğıöşüÇĞİÖŞÜ"):
                return fixed
        return text

    @staticmethod
    def _normalize_common_noise(text: str) -> str:
        text = re.sub(r"#{3,}", " ", text)
        text = re.sub(r"\.{4,}", "...", text)
        text = re.sub(r"\bY\s*A\s*R\s*G\s*I\s*T\s*A\s*Y\s*K\s*A\s*R\s*A\s*R\s*I\b", "YARGITAY KARARI", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        text = re.sub(r"[ \t\f\v]+", " ", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    def _has(self, match_text: str, pattern: str) -> bool:
        return pattern.casefold() in match_text or self._plain(pattern) in match_text

    @staticmethod
    def _plain(text: str) -> str:
        translated = text.translate(
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
        decomposed = unicodedata.normalize("NFKD", translated)
        return "".join(character for character in decomposed if not unicodedata.combining(character)).casefold()

    @staticmethod
    def _clip(text: str, max_length: int) -> str:
        cleaned = " ".join(text.split())
        if len(cleaned) <= max_length:
            return cleaned
        return f"{cleaned[: max_length - 3].rstrip()}..."


legal_summary_service = RuleBasedLegalSummaryService()
