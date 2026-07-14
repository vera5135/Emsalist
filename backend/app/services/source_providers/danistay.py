"""P2.6C — Danıştay (Council of State) official source provider.

Board identities (İdari Dava Daireleri Kurulu, Vergi Dava Daireleri Kurulu,
İçtihatları Birleştirme Kurulu) are preserved exactly and never collapsed into
a numbered chamber.
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

_DATE_RE = re.compile(
    r"(?i)(?:karar\s*tarihi|tarih)\s*[:\-]?\s*(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4})"
)
_BOARD_RE = re.compile(
    r"(?i)(idari\s+dava\s+daireleri\s+kurulu|vergi\s+dava\s+daireleri\s+kurulu|"
    r"i?çtihatları\s+birleştirme\s+kurulu|ictihatlari\s+birlestirme\s+kurulu|"
    r"\d{1,2}\.?\s*daire)"
)


class DanistayProvider(OfficialSourceProvider):
    provider_code = "danistay"
    provider_name = "Danıştay Karar Arama"
    source_types = ("council_of_state_decision",)
    official_domains = ("karararama.danistay.gov.tr", "danistay.gov.tr")
    capabilities = ProviderCapabilities(
        discovery=True, fetch=True, parse=True,
        incremental=False, bounded_window=False, requires_browser=True,
    )
    request_policy = ProviderRequestPolicy(min_interval_seconds=3.0, max_concurrency=1)

    _SEARCH_BASE = "https://karararama.danistay.gov.tr/aramalist"
    _DETAIL_BASE = "https://karararama.danistay.gov.tr/getDokuman"

    async def discover(self, *, query=None, cursor=None, limit=20, from_date=None,
                       to_date=None, transport=None, resolver=None) -> ProviderDiscoveryPage:
        q = quote((query or "").strip())
        page = cursor or "1"
        url = f"{self._SEARCH_BASE}?arananKelime={q}&pageNumber={page}"
        result = self._secure_fetch(url, transport=transport, resolver=resolver)
        soup = BeautifulSoup(result.content.decode("utf-8", errors="replace"), "lxml")
        candidates: list[ProviderDiscoveryCandidate] = []
        for a in soup.select("a.karar-link, a[data-karar-id]")[:limit]:
            karar_id = str(a.get("data-karar-id") or "")
            href = str(a.get("href") or "")
            if not karar_id and not href:
                continue
            detail_url = f"{self._DETAIL_BASE}?id={quote(karar_id)}" if karar_id else href
            candidates.append(ProviderDiscoveryCandidate(
                provider_code=self.provider_code,
                source_type="council_of_state_decision",
                detail_url=detail_url,
                external_id=karar_id or None,
                discovered_metadata={"snippet": a.get_text(" ", strip=True)[:200]},
            ))
        next_cursor = str(int(page) + 1) if len(candidates) >= limit else None
        return ProviderDiscoveryPage(candidates=candidates, next_cursor=next_cursor,
                                     exhausted=next_cursor is None)

    async def parse(self, candidate, fetch_result) -> ParsedOfficialSource:
        text = html_to_text(fetch_result.content)
        assert_meaningful_body(text)

        board_m = _BOARD_RE.search(text)
        chamber = normalize_chamber(board_m.group(1)) if board_m else ""
        case_number = extract_docket(text, "E")
        decision_number = extract_docket(text, "K")
        date_m = _DATE_RE.search(text)
        decision_date = parse_iso_date(date_m.group(1)) if date_m else None

        if not (case_number and decision_number):
            raise ProviderError(ERR_MISSING_IDENTIFIER, "danistay decision requires E and K numbers")
        if not chamber:
            raise ProviderError(ERR_STRUCTURE_CHANGED, "danistay board/chamber not found")

        title = f"Danıştay {chamber} E. {case_number} K. {decision_number}"
        return ParsedOfficialSource(
            provider_code=self.provider_code,
            source_type="council_of_state_decision",
            title=title,
            official_url=fetch_result.final_url,
            raw_text=text,
            court="Danıştay",
            chamber=chamber,
            case_number=case_number,
            decision_number=decision_number,
            decision_date=decision_date,
            provider_metadata={"external_id": candidate.external_id},
        )

    def build_exact_candidate(self, external_id: str) -> ProviderDiscoveryCandidate:
        return ProviderDiscoveryCandidate(
            provider_code=self.provider_code,
            source_type="admin_court",
            detail_url=f"{self._DETAIL_BASE}?id={external_id}",
            external_id=external_id,
        )
