"""P2.6C — Anayasa Mahkemesi (Constitutional Court) official source provider.

The public Kararlar Bilgi Bankası is a JavaScript surface (``requires_browser``).
AYM records do NOT have Yargıtay-style E./K. by default. This provider maps
ONLY real fields:

- Norm-control (norm denetimi) decisions expose Esas (E.) + Karar (K.) numbers
  → mapped to case_number/decision_number, canonical form as a court decision.
- Individual applications (bireysel başvuru) expose an Application Number (Başvuru
  No) + decision date. This is preserved in provider_metadata and ALSO mapped to
  ``case_number`` as the documented AYM canonical decision identifier. When no
  Karar number is present the record CANNOT form a court-decision canonical key
  and is returned as manual_review_required (never fabricated).
"""
from __future__ import annotations

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
    extract_docket,
    html_to_text,
    parse_iso_date,
)

_APP_NO_RE = re.compile(r"(?i)başvuru\s*(?:numarası|no)\s*[:\-]?\s*(\d{4}\s*[/-]\s*\d+)")
_DATE_RE = re.compile(
    r"(?i)(?:karar\s*tarihi|tarih)\s*[:\-]?\s*(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4})"
)
_SECTION_RE = re.compile(
    r"(?i)(genel\s*kurul|birinci\s*bölüm|ikinci\s*bölüm|birinci\s*bolum|ikinci\s*bolum)"
)
_PARA_NUM_RE = re.compile(r"(?m)^\s*(\d{1,3})\.\s+\S")


def _normalize_app_no(raw: str) -> str:
    m = re.search(r"(\d{4})\s*[/-]\s*(\d+)", raw or "")
    return f"{m.group(1)}/{int(m.group(2))}" if m else (raw or "").strip()


class AymProvider(OfficialSourceProvider):
    provider_code = "aym"
    provider_name = "Anayasa Mahkemesi Kararlar Bilgi Bankası"
    source_types = ("constitutional_court_decision",)
    official_domains = ("kararlarbilgibankasi.anayasa.gov.tr", "anayasa.gov.tr")
    capabilities = ProviderCapabilities(
        discovery=True, fetch=True, parse=True,
        incremental=False, bounded_window=True, requires_browser=True,
    )
    request_policy = ProviderRequestPolicy(min_interval_seconds=3.0, max_concurrency=1)

    _SEARCH_BASE = "https://kararlarbilgibankasi.anayasa.gov.tr/Ara"
    _DETAIL_BASE = "https://kararlarbilgibankasi.anayasa.gov.tr/BB"

    async def discover(self, *, query=None, cursor=None, limit=20, from_date=None,
                       to_date=None, transport=None, resolver=None) -> ProviderDiscoveryPage:
        q = quote((query or "").strip())
        page = cursor or "1"
        url = f"{self._SEARCH_BASE}?q={q}&page={page}"
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
                source_type="constitutional_court_decision",
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

        esas = extract_docket(text, "E")
        karar = extract_docket(text, "K")
        app_m = _APP_NO_RE.search(text)
        application_number = _normalize_app_no(app_m.group(1)) if app_m else None
        section_m = _SECTION_RE.search(text)
        section = section_m.group(1).strip() if section_m else ""
        date_m = _DATE_RE.search(text)
        decision_date = parse_iso_date(date_m.group(1)) if date_m else None
        para_numbers = [int(m) for m in _PARA_NUM_RE.findall(text)]

        provider_metadata = {
            "external_id": candidate.external_id,
            "application_number": application_number,
            "section": section,
            "numbered_paragraphs": len(para_numbers),
        }

        # Prefer norm-control E./K.; else fall back to application number as the
        # documented AYM canonical decision identifier (case_number).
        case_number = esas or application_number
        decision_number = karar

        if not (case_number and decision_number):
            # No canonical court-decision identifier pair — do NOT fabricate.
            raise ProviderError(
                ERR_MANUAL_REVIEW_REQUIRED,
                "aym record lacks a canonical (esas/başvuru + karar) identifier pair",
            )

        if esas:
            title = f"Anayasa Mahkemesi E. {esas} K. {karar}"
        else:
            title = f"Anayasa Mahkemesi Başvuru No. {application_number} K. {karar}"

        return ParsedOfficialSource(
            provider_code=self.provider_code,
            source_type="constitutional_court_decision",
            title=title,
            official_url=fetch_result.final_url,
            raw_text=text,
            court="Anayasa Mahkemesi",
            chamber=section,
            case_number=case_number,
            decision_number=decision_number,
            decision_date=decision_date,
            paragraph_hints=para_numbers or None,
            provider_metadata=provider_metadata,
        )
