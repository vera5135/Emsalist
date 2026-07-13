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

from dataclasses import dataclass
import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from app.services.source_providers.base import (
    ERR_MANUAL_REVIEW_REQUIRED,
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

_ISSUE_HEADING_RE = re.compile(
    r"^(?:t\.?\s*c\.?\s+)?resm[iî]\s+gazete(?:si)?$",
    re.IGNORECASE,
)
_ISSUE_NO_RE = re.compile(r"(?im)^\s*(?:sayı|sayi)\s*[:\-]\s*(\d{4,6})\b")
_DATE_RE = re.compile(r"(?i)(?:tarih|yayım\s*tarihi)\s*[:\-]?\s*(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4})")

_INSTRUMENT_HEADING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("presidential_decree", re.compile(
        r"^(?:.+\s+)?(?:cumhurbaşkan(?:ı|lığı)\s+(?:kararı|kararnamesi)|kararname)$",
        re.IGNORECASE,
    )),
    ("regulation", re.compile(r"^(?:.+\s+)?yönetmeli(?:k|ği)$", re.IGNORECASE)),
    ("communique", re.compile(r"^(?:.+\s+)?tebli(?:ğ|ği)$", re.IGNORECASE)),
    ("circular", re.compile(r"^(?:.+\s+)?genelge(?:si)?$", re.IGNORECASE)),
    ("legislation", re.compile(r"^(?:.+\s+)?kanun(?:u)?$", re.IGNORECASE)),
)

_INSTRUMENT_NUMBER_PATTERNS: dict[str, re.Pattern[str]] = {
    "legislation": re.compile(
        r"(?im)^\s*kanun\s*(?:numarası|no)\s*[:\-]\s*(\d+)\b"
    ),
    "regulation": re.compile(
        r"(?im)^\s*(?:yönetmelik\s*(?:numarası|no)|mevzuat\s*no)\s*[:\-]\s*(\d+)\b"
    ),
    "communique": re.compile(
        r"(?im)^\s*tebliğ\s*(?:numarası|no)\s*[:\-]\s*(\d+)\b"
    ),
    "circular": re.compile(
        r"(?im)^\s*genelge\s*(?:numarası|no)\s*[:\-]\s*(\d+)\b"
    ),
    "presidential_decree": re.compile(
        r"(?im)^\s*(?:cumhurbaşkanı\s+kararı|kararname|karar)\s*(?:numarası|sayısı|no)\s*[:\-]\s*(\d+)\b"
    ),
}


@dataclass(frozen=True)
class GazetteDocumentIdentity:
    source_type: str
    number: str
    title: str
    normalized_text: str


def classify_fetched_gazette_document(content: bytes) -> GazetteDocumentIdentity:
    """Classify canonical Gazette identity from exact fetched bytes only.

    Discovery candidate fields are routing hints. They are deliberately absent
    from this classifier and cannot select canonical source type or number.
    """
    raw = content.decode("utf-8", errors="replace")
    soup = BeautifulSoup(raw, "lxml")
    heading_node = soup.find(["h1", "h2"])
    title = heading_node.get_text(" ", strip=True) if heading_node else ""
    normalized_title = re.sub(r"\s+", " ", title).strip()
    text = html_to_text(raw)
    assert_meaningful_body(text)

    if _ISSUE_HEADING_RE.fullmatch(normalized_title):
        issue_match = _ISSUE_NO_RE.search(text)
        if issue_match is None:
            raise ProviderError(
                ERR_MANUAL_REVIEW_REQUIRED,
                "gazette issue bytes lack a deterministic issue number",
            )
        return GazetteDocumentIdentity(
            source_type="official_gazette_issue",
            number=issue_match.group(1),
            title=title or f"Resmî Gazete Sayı {issue_match.group(1)}",
            normalized_text=text,
        )

    source_type = ""
    for controlled_type, pattern in _INSTRUMENT_HEADING_PATTERNS:
        if pattern.fullmatch(normalized_title):
            source_type = controlled_type
            break
    if not source_type:
        raise ProviderError(
            ERR_MANUAL_REVIEW_REQUIRED,
            "gazette bytes do not prove a controlled document type",
        )

    number_match = _INSTRUMENT_NUMBER_PATTERNS[source_type].search(text)
    if number_match is None:
        raise ProviderError(
            ERR_MANUAL_REVIEW_REQUIRED,
            "gazette instrument bytes lack a deterministic canonical number",
        )
    return GazetteDocumentIdentity(
        source_type=source_type,
        number=number_match.group(1),
        title=title,
        normalized_text=text,
    )


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
                # Untrusted routing/observability hints only. parse() derives
                # canonical identity again from the exact fetched bytes.
                discovered_metadata={"kind": CANDIDATE_INSTRUMENT, "instrument_type": itype},
            ))
        return ProviderDiscoveryPage(candidates=candidates, next_cursor=None, exhausted=True)

    async def parse(self, candidate, fetch_result) -> ParsedOfficialSource:
        identity = classify_fetched_gazette_document(fetch_result.content)
        date_m = _DATE_RE.search(identity.normalized_text)
        publication_date = parse_iso_date(date_m.group(1)) if date_m else None
        return ParsedOfficialSource(
            provider_code=self.provider_code,
            source_type=identity.source_type,
            title=identity.title or f"Resmî Gazete Yayımı No. {identity.number}",
            official_url=fetch_result.final_url,
            raw_text=identity.normalized_text,
            issuing_authority=(
                "Resmî Gazete"
                if identity.source_type == "official_gazette_issue"
                else ""
            ),
            number=identity.number,
            publication_date=publication_date,
            provider_metadata={
                "external_id": candidate.external_id,
                "kind": (
                    CANDIDATE_ISSUE
                    if identity.source_type == "official_gazette_issue"
                    else CANDIDATE_INSTRUMENT
                ),
            },
        )

    def build_exact_candidate(self, external_id: str) -> ProviderDiscoveryCandidate:
        return ProviderDiscoveryCandidate(
            provider_code=self.provider_code,
            source_type="official_gazette_issue",
            detail_url=f"{self._ISSUE_BASE}?id={external_id}",
            external_id=external_id,
        )
