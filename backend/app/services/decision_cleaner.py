"""Utilities for converting Yargıtay decision HTML to normalized plain text."""

import re
from dataclasses import dataclass, field
from html import unescape

from bs4 import BeautifulSoup

MIN_DECISION_TEXT_LENGTH = 200


@dataclass(frozen=True)
class CleanedDecision:
    clean_text: str
    warnings: list[str] = field(default_factory=list)


class DecisionCleaner:
    """Remove HTML residue and normalize whitespace without flattening paragraphs."""

    def clean(self, raw_text: str) -> CleanedDecision:
        raw_text = self.repair_mojibake(raw_text or "")
        soup = BeautifulSoup(raw_text or "", "lxml")
        for element in soup(["script", "style", "noscript"]):
            element.decompose()

        text = unescape(soup.get_text(separator="\n"))
        text = text.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
        text = self._normalize_noise(text)

        lines: list[str] = []
        previous_was_blank = False
        for raw_line in text.split("\n"):
            line = self._normalize_line(raw_line)
            if not line:
                if lines and not previous_was_blank:
                    lines.append("")
                previous_was_blank = True
                continue
            lines.append(line)
            previous_was_blank = False

        clean_text = "\n".join(lines).strip()
        clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)
        clean_text = self._normalize_spaced_titles(clean_text)

        warnings: list[str] = []
        if len(clean_text) < MIN_DECISION_TEXT_LENGTH:
            warnings.append("insufficient_text")

        return CleanedDecision(clean_text=clean_text, warnings=warnings)

    @staticmethod
    def repair_mojibake(text: str) -> str:
        """Repair UTF-8 text that was decoded as Latin-1/Windows-1252."""
        markers = (
            "\u00c3",
            "\u00c4",
            "\u00c5",
            "\u00c2",
            "\u00e2\u20ac",
            "\u00e2\u0080",
        )
        if not text or not any(marker in text for marker in markers):
            return text
        try:
            return text.encode("latin1").decode("utf-8")
        except UnicodeError:
            return text

    @staticmethod
    def _normalize_noise(text: str) -> str:
        text = re.sub(r"#{3,}", " ", text)
        text = re.sub(r"\.{4,}", "...", text)
        return text

    def _normalize_line(self, raw_line: str) -> str:
        line = self._normalize_spaced_titles(raw_line)
        line = re.sub(r"[ \t\f\v]+", " ", line).strip()
        line = re.sub(r"\s+([,.;:!?])", r"\1", line)
        line = re.sub(r"([.!?])(?=[A-ZÇĞİÖŞÜ])", r"\1 ", line)
        return line

    @staticmethod
    def _normalize_spaced_titles(text: str) -> str:
        replacements = {
            r"\bY\s*A\s*R\s*G\s*I\s*T\s*A\s*Y\s*K\s*A\s*R\s*A\s*R\s*I\b": "YARGITAY KARARI",
            r"\bİ\s*Ç\s*T\s*İ\s*H\s*A\s*T\s*M\s*E\s*T\s*N\s*İ\b": "İçtihat Metni",
            r"\bI\s*C\s*T\s*I\s*H\s*A\s*T\s*M\s*E\s*T\s*N\s*I\b": "İçtihat Metni",
        }
        normalized = text
        for pattern, replacement in replacements.items():
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
        return normalized


decision_cleaner = DecisionCleaner()
