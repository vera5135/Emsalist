"""P2.6C — Yargıtay (Court of Cassation) official source provider.

Discovery/parsing operate on EXACT official content fetched through the P2.6
SSRF seam. The public Karar Arama application is a JavaScript/AJAX surface
(``requires_browser``); a browser discovery seam exists (the dormant
``yargitay_scraper``) but browser discovery is NEVER treated as verification
evidence — only the exact detail/document fetch produces P2.6 official trust.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from app.services.source_providers.base import (
    ERR_MISSING_IDENTIFIER,
    ERR_STRUCTURE_CHANGED,
    OfficialSourceProvider,
    ParsedOfficialSource,
    ProviderCapabilities,
    ProviderDiscoveryCandidate,
    ProviderDiscoveryPage,
    ProviderError,
    ProviderRequestPolicy,
)
from app.services.source_providers.shared import (
    assert_meaningful_body,
    extract_docket,
    html_to_text,
    normalize_chamber,
    parse_iso_date,
)

_DECISION_DATE_RE = re.compile(
    r"(?i)(?:karar\s*tarihi|tarih)\s*[:\-]?\s*(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4})"
)
_CHAMBER_RE = re.compile(
    r"(?i)(hukuk\s*genel\s*kurulu|ceza\s*genel\s*kurulu|\d{1,2}\.?\s*(?:hukuk|ceza)\s*dairesi|\d{1,2}\.?\s*(?:hd|cd))"
)


class YargitayProvider(OfficialSourceProvider):
    provider_code = "yargitay"
    provider_name = "Yargıtay Karar Arama"
    source_types = ("supreme_court_decision",)
    official_domains = ("karararama.yargitay.gov.tr", "yargitay.gov.tr")
    capabilities = ProviderCapabilities(
        discovery=True, fetch=True, parse=True,
        incremental=False, bounded_window=False, requires_browser=True,
    )
    request_policy = ProviderRequestPolicy(min_interval_seconds=3.0, max_concurrency=1)

    _SEARCH_BASE = "https://karararama.yargitay.gov.tr/aramalist"
    _DETAIL_BASE = "https://karararama.yargitay.gov.tr/getDokuman"

    async def discover(self, *, query=None, cursor=None, limit=20, from_date=None,
                       to_date=None, transport=None, resolver=None) -> ProviderDiscoveryPage:
        q = quote((query or "").strip())
        page = cursor or "1"
        url = f"{self._SEARCH_BASE}?arananKelime={q}&pageNumber={page}"
        result = self._secure_fetch(url, transport=transport, resolver=resolver)
        return self._parse_search(result.content, limit=limit, page=page)

    def _parse_search(self, content: bytes, *, limit: int, page: str) -> ProviderDiscoveryPage:
        soup = BeautifulSoup(content.decode("utf-8", errors="replace"), "lxml")
        rows = soup.select("a.karar-link, a[data-karar-id]")
        candidates: list[ProviderDiscoveryCandidate] = []
        for a in rows[:limit]:
            karar_id = str(a.get("data-karar-id") or "")
            href = str(a.get("href") or "")
            if not karar_id and not href:
                continue
            detail_url = (
                f"{self._DETAIL_BASE}?id={quote(karar_id)}"
                if karar_id else href
            )
            candidates.append(ProviderDiscoveryCandidate(
                provider_code=self.provider_code,
                source_type="supreme_court_decision",
                detail_url=detail_url,
                external_id=karar_id or None,
                discovered_metadata={"snippet": a.get_text(" ", strip=True)[:200]},
            ))
        next_cursor = str(int(page) + 1) if len(candidates) >= limit else None
        return ProviderDiscoveryPage(
            candidates=candidates, next_cursor=next_cursor, exhausted=next_cursor is None,
        )

    async def parse(self, candidate, fetch_result) -> ParsedOfficialSource:
        text = html_to_text(fetch_result.content)
        assert_meaningful_body(text)

        chamber_m = _CHAMBER_RE.search(text)
        chamber = normalize_chamber(chamber_m.group(1)) if chamber_m else ""
        case_number = extract_docket(text, "E")
        decision_number = extract_docket(text, "K")
        date_m = _DECISION_DATE_RE.search(text)
        decision_date = parse_iso_date(date_m.group(1)) if date_m else None

        if not (case_number and decision_number):
            raise ProviderError(ERR_MISSING_IDENTIFIER, "yargitay decision requires E and K numbers")
        if not chamber:
            raise ProviderError(ERR_STRUCTURE_CHANGED, "yargitay chamber not found")

        title = f"Yargıtay {chamber} E. {case_number} K. {decision_number}"
        return ParsedOfficialSource(
            provider_code=self.provider_code,
            source_type="supreme_court_decision",
            title=title,
            official_url=fetch_result.final_url,
            raw_text=text,
            court="Yargıtay",
            chamber=chamber,
            case_number=case_number,
            decision_number=decision_number,
            decision_date=decision_date,
            provider_metadata={"external_id": candidate.external_id},
        )

    def build_exact_candidate(self, external_id: str) -> ProviderDiscoveryCandidate:
        return ProviderDiscoveryCandidate(
            provider_code=self.provider_code,
            source_type="supreme_court_decision",
            detail_url=f"{self._DETAIL_BASE}?id={external_id}",
            external_id=external_id,
        )
