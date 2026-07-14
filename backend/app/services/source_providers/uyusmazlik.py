"""P2.6C — Uyuşmazlık Mahkemesi (Court of Jurisdictional Disputes) provider.

Served via the already-allowlisted PUBLIC UYAP emsal decision surface
(``emsal.uyap.gov.tr``) — no authentication, no private case data. When an
official downloadable representation is exposed it is preferred as the fetch
target; because canonical dedupe is content-hash based, the view and download
representations of identical normalized legal content never create duplicate
SourceVersions (P2.6 same-hash behavior).
"""
from __future__ import annotations

import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from app.services.source_providers.base import (
    ERR_MISSING_IDENTIFIER,
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
    parse_iso_date,
)

_DATE_RE = re.compile(
    r"(?i)(?:karar\s*tarihi|tarih)\s*[:\-]?\s*(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4})"
)
_SECTION_RE = re.compile(r"(?i)(hukuk\s*bölümü|ceza\s*bölümü|hukuk\s*bolumu|ceza\s*bolumu)")


class UyusmazlikProvider(OfficialSourceProvider):
    provider_code = "uyusmazlik"
    provider_name = "Uyuşmazlık Mahkemesi (UYAP Emsal)"
    source_types = ("court_of_jurisdictional_disputes_decision",)
    official_domains = ("kararlar.uyusmazlik.gov.tr", "uyusmazlik.gov.tr")
    capabilities = ProviderCapabilities(
        discovery=True, fetch=True, parse=True,
        incremental=False, bounded_window=False, requires_browser=True,
    )
    request_policy = ProviderRequestPolicy(min_interval_seconds=4.0, max_concurrency=1)

    _SEARCH_BASE = "https://kararlar.uyusmazlik.gov.tr/aramalist"
    _DETAIL_BASE = "https://kararlar.uyusmazlik.gov.tr/getDokuman"

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
            download = str(a.get("data-download") or "") or None
            candidates.append(ProviderDiscoveryCandidate(
                provider_code=self.provider_code,
                source_type="court_of_jurisdictional_disputes_decision",
                detail_url=detail_url,
                download_url=download,
                external_id=karar_id or None,
                discovered_metadata={"snippet": a.get_text(" ", strip=True)[:200]},
            ))
        next_cursor = str(int(page) + 1) if len(candidates) >= limit else None
        return ProviderDiscoveryPage(candidates=candidates, next_cursor=next_cursor,
                                     exhausted=next_cursor is None)

    async def parse(self, candidate, fetch_result) -> ParsedOfficialSource:
        text = html_to_text(fetch_result.content)
        assert_meaningful_body(text)

        case_number = extract_docket(text, "E")
        decision_number = extract_docket(text, "K")
        date_m = _DATE_RE.search(text)
        decision_date = parse_iso_date(date_m.group(1)) if date_m else None
        section_m = _SECTION_RE.search(text)
        section = section_m.group(1).strip() if section_m else ""

        if not (case_number and decision_number):
            raise ProviderError(ERR_MISSING_IDENTIFIER, "uyusmazlik decision requires E and K numbers")

        title = f"Uyuşmazlık Mahkemesi E. {case_number} K. {decision_number}"
        return ParsedOfficialSource(
            provider_code=self.provider_code,
            source_type="court_of_jurisdictional_disputes_decision",
            title=title,
            official_url=fetch_result.final_url,
            raw_text=text,
            court="Uyuşmazlık Mahkemesi",
            chamber=section,
            case_number=case_number,
            decision_number=decision_number,
            decision_date=decision_date,
            provider_metadata={
                "external_id": candidate.external_id,
                "representation": "download" if candidate.download_url else "view",
            },
        )

    def build_exact_candidate(self, external_id: str) -> ProviderDiscoveryCandidate:
        return ProviderDiscoveryCandidate(
            provider_code=self.provider_code,
            source_type="court_of_jurisdictional_disputes_decision",
            detail_url=f"{self._DETAIL_BASE}?id={external_id}",
            external_id=external_id,
        )
