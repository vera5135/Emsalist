"""P2.8S — Yargıtay (Court of Cassation) official source provider.

Discovery and detail fetch operate on EXACT official content fetched through
the P2.6 SSRF seam. The current public Karar Arama surface is a JSON/AJAX API
(verified by bounded live reconnaissance):

- Discovery: ``POST /aramalist`` with provider-owned JSON
  ``{"data": {"arananKelime": <q>, "pageSize": <N>, "pageNumber": <1-based>}}``
  → JSON ``{"data": {"data": [records], "recordsTotal": N}, "metadata": ...}``.
- Detail: ``GET /getDokuman?id=<id>`` → an ``AdaletResponseDto`` envelope whose
  ``<data>`` element carries the escaped decision HTML (or, under JSON content
  negotiation, ``{"data": "<decision html>"}``). The outer envelope carries
  request-specific ``TID``/``SID`` metadata that must NEVER become legal body.

Because discovery is a plain HTTP JSON API, ``requires_browser`` is False; no
browser automation is used for canonical discovery.
"""
from __future__ import annotations

import hashlib
import html as html_module
import json
import re

from app.services.source_fetcher import FetchResult, SourceFetchRequest
from app.services.source_providers.base import (
    ERR_ACCESS_DENIED,
    ERR_CHALLENGE,
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
# Envelope <data>...</data> capture (non-greedy; there is exactly one data node).
_ENVELOPE_DATA_RE = re.compile(r"<data>(.*?)</data>", re.DOTALL | re.IGNORECASE)
# Safe candidate id shape (server ids are numeric strings).
_CANDIDATE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
# Active-challenge markers observed in the surface JSON metadata/status.
_CHALLENGE_MARKERS = ("captcha", "displaycaptcha", "recaptcha")
_ACCESS_DENIED_MARKERS = ("access denied", "forbidden", "erişim engellendi")

_MAX_PAGE_SIZE = 100


class YargitayProvider(OfficialSourceProvider):
    provider_code = "yargitay"
    provider_name = "Yargıtay Karar Arama"
    source_types = ("supreme_court_decision",)
    official_domains = ("karararama.yargitay.gov.tr", "yargitay.gov.tr")
    capabilities = ProviderCapabilities(
        discovery=True, fetch=True, parse=True,
        incremental=False, bounded_window=False, requires_browser=False,
    )
    request_policy = ProviderRequestPolicy(min_interval_seconds=3.0, max_concurrency=1)

    _SEARCH_BASE = "https://karararama.yargitay.gov.tr/aramalist"
    _DETAIL_BASE = "https://karararama.yargitay.gov.tr/getDokuman"

    # ── discovery ──────────────────────────────────────────────────────────
    async def discover(self, *, query=None, cursor=None, limit=20, from_date=None,
                       to_date=None, transport=None, resolver=None) -> ProviderDiscoveryPage:
        page = self._coerce_page(cursor)
        page_size = max(1, min(int(limit or 1), _MAX_PAGE_SIZE))
        request = SourceFetchRequest.post_json(
            self._SEARCH_BASE,
            {"data": {
                "arananKelime": (query or "").strip(),
                "pageSize": page_size,
                "pageNumber": page,
            }},
            accept="application/json",
        )
        result = self._secure_fetch_request(request, transport=transport, resolver=resolver)
        return self._parse_search(result.content, limit=page_size, page=page)

    @staticmethod
    def _coerce_page(cursor) -> int:
        if cursor in (None, ""):
            return 1
        try:
            page = int(str(cursor))
        except (TypeError, ValueError):
            raise ProviderError(ERR_STRUCTURE_CHANGED, "yargitay invalid page cursor") from None
        return page if page >= 1 else 1

    def _parse_search(self, content: bytes, *, limit: int, page: int) -> ProviderDiscoveryPage:
        try:
            payload = json.loads(content.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, ValueError):
            raise ProviderError(ERR_STRUCTURE_CHANGED, "yargitay search response not json") from None
        if not isinstance(payload, dict):
            raise ProviderError(ERR_STRUCTURE_CHANGED, "yargitay search response shape changed")

        self._raise_for_challenge(payload)
        self._raise_for_error_metadata(payload)

        envelope = payload.get("data")
        if not isinstance(envelope, dict):
            raise ProviderError(ERR_STRUCTURE_CHANGED, "yargitay search envelope shape changed")
        records = envelope.get("data")
        if not isinstance(records, list):
            raise ProviderError(ERR_STRUCTURE_CHANGED, "yargitay search records shape changed")

        candidates: list[ProviderDiscoveryCandidate] = []
        for rec in records[:limit]:
            if not isinstance(rec, dict):
                raise ProviderError(ERR_STRUCTURE_CHANGED, "yargitay search record shape changed")
            external_id = self._safe_candidate_id(rec.get("id"))
            if external_id is None:
                continue
            candidates.append(ProviderDiscoveryCandidate(
                provider_code=self.provider_code,
                source_type="supreme_court_decision",
                detail_url=f"{self._DETAIL_BASE}?id={external_id}",
                external_id=external_id,
                discovered_metadata=self._safe_listing_metadata(rec),
            ))

        next_cursor = self._next_cursor(
            envelope, page=page, page_size=limit, page_count=len(records),
        )
        return ProviderDiscoveryPage(
            candidates=candidates,
            next_cursor=next_cursor,
            exhausted=next_cursor is None,
        )

    @staticmethod
    def _safe_candidate_id(raw) -> str | None:
        if isinstance(raw, int) and not isinstance(raw, bool):
            raw = str(raw)
        if not isinstance(raw, str):
            return None
        value = raw.strip()
        if not value or not _CANDIDATE_ID_RE.fullmatch(value):
            return None
        return value

    @staticmethod
    def _safe_listing_metadata(rec: dict) -> dict:
        """Preserve only safe, bounded listing identity fields (no full JSON)."""
        out: dict[str, str] = {}
        for key in ("daire", "esasNo", "kararNo", "kararTarihi"):
            value = rec.get(key)
            if isinstance(value, (str, int)) and not isinstance(value, bool):
                out[key] = str(value).strip()[:120]
        return out

    def _next_cursor(self, envelope: dict, *, page: int, page_size: int, page_count: int) -> str | None:
        """Derive the next page from recordsTotal — not from a full page alone."""
        total = envelope.get("recordsTotal")
        if not isinstance(total, int) or total < 0:
            # Without a trustworthy total, only advance when a full page arrived.
            return str(page + 1) if page_count >= page_size and page_count > 0 else None
        seen = page * page_size
        return str(page + 1) if seen < total and page_count > 0 else None

    def _raise_for_challenge(self, payload: dict) -> None:
        status = str(payload.get("status") or "").casefold()
        detail = str(payload.get("detailMessage") or "").casefold()
        combined = f"{status} {detail}"
        if any(marker in combined for marker in _CHALLENGE_MARKERS):
            raise ProviderError(ERR_CHALLENGE, "yargitay challenge active")
        if any(marker in combined for marker in _ACCESS_DENIED_MARKERS):
            raise ProviderError(ERR_ACCESS_DENIED, "yargitay access denied")

    @staticmethod
    def _raise_for_error_metadata(payload: dict) -> None:
        meta = payload.get("metadata")
        if isinstance(meta, dict) and str(meta.get("FMTY", "")).upper() == "ERROR":
            raise ProviderError(ERR_STRUCTURE_CHANGED, "yargitay search returned error metadata")

    # ── detail fetch (envelope-unwrapping) ─────────────────────────────────
    async def fetch(self, candidate, *, transport=None, resolver=None):
        """Fetch the decision through the SSRF seam and return the INNER decision
        HTML as the canonical fetch content.

        The official response is an outer ``AdaletResponseDto`` envelope carrying
        request-specific ``TID``/``SID`` metadata. Unwrapping the inner decision
        HTML here (immediately after the SSRF seam) means the downstream
        canonical content hash binds the stable legal body and never the volatile
        envelope metadata. The SSRF boundary itself is unchanged — the network
        access still flows through ``_secure_fetch``.
        """
        raw = await super().fetch(candidate, transport=transport, resolver=resolver)
        inner_html = unwrap_decision_html(raw.content, raw.content_type)
        return FetchResult(
            final_url=raw.final_url,
            status_code=raw.status_code,
            content=inner_html.encode("utf-8"),
            content_type="text/html",
            redirect_chain=list(raw.redirect_chain),
        )

    async def parse(self, candidate, fetch_result) -> ParsedOfficialSource:
        # ``fetch`` already unwrapped the envelope; ``parse`` is defensive and
        # unwraps again only if it is ever handed a raw envelope directly.
        inner_html = unwrap_decision_html(fetch_result.content, fetch_result.content_type)
        text = html_to_text(inner_html)
        assert_meaningful_body(text)

        chamber_m = _CHAMBER_RE.search(text)
        chamber = normalize_chamber(chamber_m.group(1)) if chamber_m else ""
        case_number = extract_docket(text, "E")
        decision_number = extract_docket(text, "K")
        decision_date = self._resolve_decision_date(text, candidate)

        if not (case_number and decision_number):
            raise ProviderError(ERR_MISSING_IDENTIFIER, "yargitay decision requires E and K numbers")
        if not chamber:
            raise ProviderError(ERR_STRUCTURE_CHANGED, "yargitay chamber not found")

        inner_content_hash = compute_inner_content_hash(inner_html)
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
            provider_metadata={
                "external_id": candidate.external_id,
                "inner_content_hash": inner_content_hash,
            },
        )

    @staticmethod
    def _resolve_decision_date(text: str, candidate) -> str | None:
        """Prefer an explicit labelled body date; else the listing metadata date.

        The decision date is never fabricated from E/K years. When the body has
        no recognizable labelled date, the discovery listing ``kararTarihi`` is
        used only if it parses deterministically.
        """
        body_match = _DECISION_DATE_RE.search(text)
        if body_match:
            parsed = parse_iso_date(body_match.group(1))
            if parsed:
                return parsed
        listing = ""
        if candidate is not None and isinstance(candidate.discovered_metadata, dict):
            listing = str(candidate.discovered_metadata.get("kararTarihi") or "").strip()
        return parse_iso_date(listing) if listing else None

    def build_exact_candidate(self, external_id: str) -> ProviderDiscoveryCandidate:
        safe_id = self._safe_candidate_id(external_id)
        if safe_id is None:
            raise ProviderError(ERR_MISSING_IDENTIFIER, "yargitay external_id invalid")
        return ProviderDiscoveryCandidate(
            provider_code=self.provider_code,
            source_type="supreme_court_decision",
            detail_url=f"{self._DETAIL_BASE}?id={safe_id}",
            external_id=safe_id,
        )


def unwrap_decision_html(content: bytes | str, content_type: str | None) -> str:
    """Return the inner decision HTML from a getDokuman response.

    Supports the two observed official representations:

    - XML ``AdaletResponseDto`` envelope: extract the ``<data>`` element and
      HTML-unescape the escaped decision HTML.
    - JSON ``{"data": "<decision html>"}``: extract the string ``data`` field.

    If the input is already inner decision HTML (no envelope), it is returned
    as-is (this makes ``parse`` robust when ``fetch`` has already unwrapped).

    Raises ``ProviderError`` on missing / non-string / empty decision HTML or an
    unexpected envelope structure.
    """
    if isinstance(content, bytes):
        text = _decode_official_bytes(content)
    else:
        text = content or ""
    stripped = text.lstrip()
    ctype = (content_type or "").split(";")[0].strip().lower()

    # JSON representation.
    if stripped.startswith("{") or ctype == "application/json":
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            raise ProviderError(ERR_STRUCTURE_CHANGED, "yargitay detail json invalid") from None
        if not isinstance(payload, dict) or "data" not in payload:
            raise ProviderError(ERR_STRUCTURE_CHANGED, "yargitay detail json shape changed")
        data = payload.get("data")
        if not isinstance(data, str):
            raise ProviderError(ERR_STRUCTURE_CHANGED, "yargitay detail data not string")
        inner = data.strip()
        if not inner:
            raise ProviderError(ERR_STRUCTURE_CHANGED, "yargitay detail data empty")
        return inner

    # XML AdaletResponseDto envelope.
    if "<data>" in text.lower() or "adaletresponsedto" in text.lower():
        m = _ENVELOPE_DATA_RE.search(text)
        if not m:
            raise ProviderError(ERR_STRUCTURE_CHANGED, "yargitay detail envelope shape changed")
        inner = html_module.unescape(m.group(1)).strip()
        if not inner:
            raise ProviderError(ERR_STRUCTURE_CHANGED, "yargitay detail envelope empty")
        return inner

    # Already inner decision HTML.
    inner = text.strip()
    if not inner:
        raise ProviderError(ERR_STRUCTURE_CHANGED, "yargitay detail empty")
    return inner


def compute_inner_content_hash(inner_html: str) -> str:
    """Deterministic diagnostic identity of the extracted inner decision HTML.

    Representation (documented, single choice): SHA-256 over the UTF-8 bytes of
    the extracted inner decision HTML string (the unescaped ``<data>`` content),
    BEFORE any text normalization. This is provider metadata / diagnostic
    identity only — it is NEVER treated as official verification evidence and
    never replaces the P2.6 canonical ``SourceVersion.content_hash``.
    """
    return hashlib.sha256((inner_html or "").encode("utf-8")).hexdigest()


def _decode_official_bytes(content: bytes) -> str:
    for encoding in ("utf-8", "iso-8859-9", "cp1254", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("latin-1", errors="replace")
