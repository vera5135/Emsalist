"""P2.6C — Resmî Gazete official source provider.

Distinguishes a Gazette ISSUE from a legal INSTRUMENT published inside an issue.
An entire daily gazette is NEVER modeled as one legislation source. The
canonical ingestion target is the individual instrument when it can be
deterministically segmented (with a real instrument number); otherwise the
issue is ingested as ``official_gazette_issue``. Instrument boundaries and
numbers are never fabricated. Publication does not imply perpetual validity —
temporal status remains P2.6-controlled.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from app.services.source_providers.base import (
    ERR_MANUAL_REVIEW_REQUIRED,
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

CANDIDATE_ISSUE = "gazette_issue"
CANDIDATE_INSTRUMENT = "published_instrument"

_INSTRUMENT_TYPE_MAP = {
    "kanun": "legislation",
    "yönetmelik": "regulation",
    "yonetmelik": "regulation",
    "tebliğ": "communique",
    "teblig": "communique",
    "genelge": "circular",
    "cumhurbaşkanı kararı": "presidential_decree",
    "cumhurbaskani karari": "presidential_decree",
    "cumhurbaşkanlığı kararnamesi": "presidential_decree",
    "kararname": "presidential_decree",
}

_ISSUE_NO_RE = re.compile(r"(?i)(?:sayı|sayi)\s*[:\-]?\s*(\d{4,6})")
_DATE_RE = re.compile(r"(?i)(?:tarih|yayım\s*tarihi)\s*[:\-]?\s*(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4})")
_INSTRUMENT_NO_RE = re.compile(r"(?i)(?:karar|kanun|mevzuat|k\.)\s*(?:numarası|sayısı|no)\s*[:\-]?\s*(\d+)")


class ResmiGazeteProvider(OfficialSourceProvider):
    provider_code = "resmi_gazete"
    provider_name = "Resmî Gazete"
    source_types = ("official_gazette_issue", "legislation", "regulation",
                    "communique", "circular", "presidential_decree")
    official_domains = ("resmigazete.gov.tr",)
    capabilities = ProviderCapabilities(
        discovery=True, fetch=True, parse=True,
        incremental=False, bounded_window=True, requires_browser=False,
    )
    request_policy = ProviderRequestPolicy(min_interval_seconds=2.0, max_concurrency=1)

    _INDEX_BASE = "https://resmigazete.gov.tr/fihrist"
    _ISSUE_BASE = "https://resmigazete.gov.tr/eskiler"

    async def discover(self, *, query=None, cursor=None, limit=20, from_date=None,
                       to_date=None, transport=None, resolver=None) -> ProviderDiscoveryPage:
        day = from_date or (query or "")
        url = f"{self._INDEX_BASE}?date={quote(day.strip())}"
        result = self._secure_fetch(url, transport=transport, resolver=resolver)
        soup = BeautifulSoup(result.content.decode("utf-8", errors="replace"), "lxml")
        candidates: list[ProviderDiscoveryCandidate] = []
        # Issue candidates.
        for a in soup.select("a.gazete-issue")[:limit]:
            href = str(a.get("href") or "")
            if not href:
                continue
            candidates.append(ProviderDiscoveryCandidate(
                provider_code=self.provider_code,
                source_type="official_gazette_issue",
                detail_url=href,
                external_id=str(a.get("data-issue-no") or "") or None,
                discovered_metadata={"kind": CANDIDATE_ISSUE},
            ))
        # Individual instrument candidates (only when explicitly segmented).
        for a in soup.select("a.gazete-instrument[data-instrument-type]")[:limit]:
            href = str(a.get("href") or "")
            itype = str(a.get("data-instrument-type") or "").strip().casefold()
            if not href:
                continue
            source_type = _INSTRUMENT_TYPE_MAP.get(itype, "official_gazette_issue")
            candidates.append(ProviderDiscoveryCandidate(
                provider_code=self.provider_code,
                source_type=source_type,
                detail_url=href,
                external_id=str(a.get("data-instrument-id") or "") or None,
                discovered_metadata={"kind": CANDIDATE_INSTRUMENT, "instrument_type": itype},
            ))
        return ProviderDiscoveryPage(candidates=candidates, next_cursor=None, exhausted=True)

    async def parse(self, candidate, fetch_result) -> ParsedOfficialSource:
        raw = fetch_result.content.decode("utf-8", errors="replace")
        soup = BeautifulSoup(raw, "lxml")
        heading = soup.find(["h1", "h2"])
        title = heading.get_text(" ", strip=True) if heading else ""
        text = html_to_text(raw)
        assert_meaningful_body(text)

        date_m = _DATE_RE.search(text)
        publication_date = parse_iso_date(date_m.group(1)) if date_m else None
        kind = (candidate.discovered_metadata or {}).get("kind", CANDIDATE_ISSUE)

        if candidate.source_type == "official_gazette_issue" or kind == CANDIDATE_ISSUE:
            issue_m = _ISSUE_NO_RE.search(text)
            issue_no = issue_m.group(1) if issue_m else candidate.external_id
            if not issue_no:
                raise ProviderError(ERR_MISSING_IDENTIFIER, "gazette issue requires an issue number")
            return ParsedOfficialSource(
                provider_code=self.provider_code,
                source_type="official_gazette_issue",
                title=title or f"Resmî Gazete Sayı {issue_no}",
                official_url=fetch_result.final_url,
                raw_text=text,
                issuing_authority="Resmî Gazete",
                number=issue_no,
                publication_date=publication_date,
                provider_metadata={"external_id": candidate.external_id, "kind": CANDIDATE_ISSUE},
            )

        # Published instrument path — requires a real instrument number.
        inst_m = _INSTRUMENT_NO_RE.search(text)
        number = inst_m.group(1) if inst_m else None
        if not number:
            # Segmentation/number uncertain — do NOT fabricate an instrument boundary.
            raise ProviderError(
                ERR_MANUAL_REVIEW_REQUIRED,
                "gazette instrument has no deterministic number; not fabricating",
            )
        return ParsedOfficialSource(
            provider_code=self.provider_code,
            source_type=candidate.source_type,
            title=title or f"Resmî Gazete Yayımı No. {number}",
            official_url=fetch_result.final_url,
            raw_text=text,
            issuing_authority="",
            number=number,
            publication_date=publication_date,
            provider_metadata={
                "external_id": candidate.external_id,
                "kind": CANDIDATE_INSTRUMENT,
                "gazette_issue_number": (candidate.discovered_metadata or {}).get("gazette_issue_number"),
            },
        )
