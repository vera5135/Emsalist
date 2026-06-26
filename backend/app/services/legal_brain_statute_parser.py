"""Statute-specific parser / enricher for Legal Brain card data."""

from __future__ import annotations

import re
from typing import Any


class LegalBrainStatuteParser:
    """Parse and enrich statute-type cards with code/article metadata."""

    CODE_ARTICLE_RE = re.compile(
        r"\b(TMK|HMK|TBK|İİK|IİK|TCK|CMK|TKK|VuK|İšK|ISK)\s*(?:m\.?|madde)?\s*(\d+(?:/\d+)?)",
        flags=re.IGNORECASE,
    )

    def parse(self, card):
        text = " ".join([card.get("summary", ""), card.get("source_file", ""), " ".join(card.get("legal_rules", []))])
        articles = self._extract_articles(text)
        codes = self._extract_codes(articles)
        card["parsed_articles"] = articles[:15]
        card["parsed_codes"] = codes[:10]
        card["parser_type"] = "statute"
        return card

    def parse_text(self, text, metadata):
        articles = self._extract_articles(text)
        codes = self._extract_codes(articles)
        return {"parsed_articles": articles[:15], "parsed_codes": codes[:10], "parser_type": "statute"}

    def _extract_articles(self, text):
        found = []
        for match in self.CODE_ARTICLE_RE.finditer(text):
            code = match.group(1).upper()
            code = "İ�K" if code in ("IİK", "İ�K") else code
            found.append(f"{code} m.{match.group(2)}")
        return list(dict.fromkeys(found))

    @staticmethod
    def _extract_codes(articles):
        codes = []
        for entry in articles:
            code = entry.split()[0] if entry else ""
            if code and code not in codes:
                codes.append(code)
        return codes


legal_brain_statute_parser = LegalBrainStatuteParser()
