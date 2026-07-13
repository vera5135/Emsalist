"""P2.6C — Mevzuat (legislation) official source provider.

Legislation preserves article-level provenance via the P2.6 paragraph parser
(Madde / Ek Madde / Geçici Madde / Mükerrer Madde). Navigation / cookie / menu
chrome is stripped and never ingested as legal content. Amendment / repeal
dates are only set when deterministically present in official content — repeal
status is NEVER inferred from age.
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
    html_to_text,
    parse_iso_date,
)

_NUMBER_RE = re.compile(r"(?i)(?:kanun|mevzuat|k\.)\s*(?:numarası|no)\s*[:\-]?\s*(\d+)")
_PUB_DATE_RE = re.compile(
    r"(?i)(?:resmî?\s*gazete\s*tarihi|yayım\s*tarihi|yayimlanma\s*tarihi)\s*[:\-]?\s*(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4})"
)
_AUTHORITY_RE = re.compile(r"(?i)(?:kabul\s*eden|makam|çıkaran\s*makam)\s*[:\-]?\s*([^\n]{2,80})")
_REPEAL_RE = re.compile(
    r"(?i)(?:yürürlükten\s*kalkma\s*tarihi|mülga\s*tarihi|ilga\s*tarihi)\s*[:\-]?\s*(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4})"
)
_EFFECTIVE_RE = re.compile(
    r"(?i)(?:yürürlük\s*tarihi|yürürlüğe\s*giriş)\s*[:\-]?\s*(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4})"
)


class MevzuatProvider(OfficialSourceProvider):
    provider_code = "mevzuat"
    provider_name = "Mevzuat Bilgi Sistemi"
    source_types = ("legislation",)
    official_domains = ("mevzuat.gov.tr", "mevzuat.adalet.gov.tr")
    capabilities = ProviderCapabilities(
        discovery=True, fetch=True, parse=True,
        incremental=False, bounded_window=True, requires_browser=False,
    )
    request_policy = ProviderRequestPolicy(min_interval_seconds=2.0, max_concurrency=1)

    _SEARCH_BASE = "https://mevzuat.gov.tr/Ara"
    _DETAIL_BASE = "https://mevzuat.gov.tr/MevzuatMetin"

    async def discover(self, *, query=None, cursor=None, limit=20, from_date=None,
                       to_date=None, transport=None, resolver=None) -> ProviderDiscoveryPage:
        q = quote((query or "").strip())
        page = cursor or "1"
        url = f"{self._SEARCH_BASE}?q={q}&page={page}"
        result = self._secure_fetch(url, transport=transport, resolver=resolver)
        soup = BeautifulSoup(result.content.decode("utf-8", errors="replace"), "lxml")
        candidates: list[ProviderDiscoveryCandidate] = []
        for a in soup.select("a.mevzuat-link, a[data-mevzuat-id]")[:limit]:
            mid = str(a.get("data-mevzuat-id") or "")
            href = str(a.get("href") or "")
            if not mid and not href:
                continue
            detail_url = f"{self._DETAIL_BASE}?id={quote(mid)}" if mid else href
            candidates.append(ProviderDiscoveryCandidate(
                provider_code=self.provider_code,
                source_type="legislation",
                detail_url=detail_url,
                external_id=mid or None,
                discovered_metadata={"snippet": a.get_text(" ", strip=True)[:200]},
            ))
        next_cursor = str(int(page) + 1) if len(candidates) >= limit else None
        return ProviderDiscoveryPage(candidates=candidates, next_cursor=next_cursor,
                                     exhausted=next_cursor is None)

    async def parse(self, candidate, fetch_result) -> ParsedOfficialSource:
        raw = fetch_result.content.decode("utf-8", errors="replace")
        soup = BeautifulSoup(raw, "lxml")
        heading = soup.find(["h1", "h2"])
        title = heading.get_text(" ", strip=True) if heading else ""
        text = html_to_text(raw)
        assert_meaningful_body(text)

        num_m = _NUMBER_RE.search(text)
        number = num_m.group(1) if num_m else None
        if not number:
            raise ProviderError(ERR_MISSING_IDENTIFIER, "legislation requires a number")

        auth_m = _AUTHORITY_RE.search(text)
        issuing_authority = auth_m.group(1).strip() if auth_m else ""
        pub_m = _PUB_DATE_RE.search(text)
        publication_date = parse_iso_date(pub_m.group(1)) if pub_m else None
        eff_m = _EFFECTIVE_RE.search(text)
        effective_date = parse_iso_date(eff_m.group(1)) if eff_m else None
        repeal_m = _REPEAL_RE.search(text)
        repeal_date = parse_iso_date(repeal_m.group(1)) if repeal_m else None  # unknown stays None

        if not title:
            title = f"Mevzuat No. {number}"

        return ParsedOfficialSource(
            provider_code=self.provider_code,
            source_type="legislation",
            title=title,
            official_url=fetch_result.final_url,
            raw_text=text,
            issuing_authority=issuing_authority,
            number=number,
            publication_date=publication_date,
            effective_date=effective_date,
            repeal_date=repeal_date,
            provider_metadata={"external_id": candidate.external_id},
        )

    def build_exact_candidate(self, external_id: str) -> ProviderDiscoveryCandidate:
        return ProviderDiscoveryCandidate(
            provider_code=self.provider_code,
            source_type="legislation",
            detail_url=f"{self._DETAIL_BASE}?id={external_id}",
            external_id=external_id,
        )