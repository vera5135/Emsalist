"""P2.6C — Shared provider utilities (deterministic, no network).

HTML → legal text extraction, court/chamber/date/docket normalization and the
content-quality gate. All functions are pure and unit-testable.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from app.services.source_providers.base import (
    ERR_EMPTY_LEGAL_BODY,
    ProviderError,
)

# Non-content elements never treated as legal body.
_STRIP_TAGS = ("script", "style", "nav", "footer", "header", "noscript", "form", "button", "svg")

# UI-only strings that must never become source content on their own.
_UI_ONLY_MARKERS = frozenset({
    "arama", "temizle", "loading...", "yükleniyor", "javascript'i etkinleştirin",
    "javascripti etkinlestirin", "please enable javascript", "menü", "ana sayfa",
})


def html_to_text(raw: str | bytes) -> str:
    """Extract human-readable legal text from an HTML document.

    Removes scripts/styles/navigation/footer chrome so UI-only text does not
    become source content.
    """
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(list(_STRIP_TAGS)):
        tag.decompose()
    # Prefer a main/article container when present.
    container = soup.find("main") or soup.find("article") or soup.body or soup
    text = container.get_text("\n")
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


def assert_meaningful_body(text: str, *, min_chars: int = 40, min_words: int = 8) -> None:
    """Content-quality gate. Rejects empty / UI-only payloads before ingestion.

    Raises ProviderError(empty_legal_body) when the extracted text is not a
    plausible legal body. This is a structural gate, not a one-word blacklist:
    it requires real length AND word count AND non-UI content.
    """
    normalized = (text or "").strip()
    if not normalized:
        raise ProviderError(ERR_EMPTY_LEGAL_BODY, "empty body")
    collapsed = normalized.casefold()
    if collapsed in _UI_ONLY_MARKERS:
        raise ProviderError(ERR_EMPTY_LEGAL_BODY, "ui-only body")
    if len(normalized) < min_chars:
        raise ProviderError(ERR_EMPTY_LEGAL_BODY, "body too short")
    if len(normalized.split()) < min_words:
        raise ProviderError(ERR_EMPTY_LEGAL_BODY, "body too few words")
    # Reject a body that is only UI markers repeated.
    words = {w.casefold().strip(".:") for w in normalized.split()}
    if words and words.issubset(_UI_ONLY_MARKERS | {"", "..."}):
        raise ProviderError(ERR_EMPTY_LEGAL_BODY, "ui-only tokens")


# ── Court / chamber normalization (preserve legal identity) ────────────────
_COURT_CANONICAL = {
    "yargitay": "Yargıtay",
    "yargıtay": "Yargıtay",
    "danistay": "Danıştay",
    "danıştay": "Danıştay",
    "anayasa mahkemesi": "Anayasa Mahkemesi",
    "aym": "Anayasa Mahkemesi",
    "uyusmazlik mahkemesi": "Uyuşmazlık Mahkemesi",
    "uyuşmazlık mahkemesi": "Uyuşmazlık Mahkemesi",
}


def normalize_court(name: str | None) -> str:
    value = (name or "").strip()
    if not value:
        return ""
    key = value.casefold()
    return _COURT_CANONICAL.get(key, value)


# Board/kurul identities that must NEVER collapse into a numbered chamber.
_BOARD_KEYWORDS = (
    "genel kurul", "daireleri kurul", "içtihatları birleştirme",
    "ictihatlari birlestirme", "büyük genel kurul", "buyuk genel kurul",
    "genel kurulu", "kurulu", "kurul",
)


def normalize_chamber(chamber: str | None) -> str:
    """Normalize chamber text while preserving legal-body identity.

    A numbered *Daire* like "13. HD" / "13.HD" / "13. Hukuk Dairesi" normalizes
    to a canonical "13. Hukuk Dairesi" form. Boards/kurul names are preserved
    verbatim (trimmed) and never collapsed into a numbered chamber.
    """
    value = (chamber or "").strip()
    if not value:
        return ""
    low = value.casefold()
    if any(k in low for k in _BOARD_KEYWORDS):
        # Preserve board identity; just collapse whitespace.
        return re.sub(r"\s+", " ", value).strip()
    m = re.match(r"^\s*(\d{1,2})\s*\.?\s*(hd|cd|hukuk\s*dairesi|ceza\s*dairesi|hukuk|ceza|daire|d)?\s*$", low)
    if m:
        num = int(m.group(1))
        kind = (m.group(2) or "").replace(" ", "")
        if kind.startswith("hukuk") or kind == "hd":
            return f"{num}. Hukuk Dairesi"
        if kind.startswith("ceza") or kind == "cd":
            return f"{num}. Ceza Dairesi"
        if kind in ("daire", "d", ""):
            return f"{num}. Daire"
    return re.sub(r"\s+", " ", value).strip()


def parse_iso_date(raw: str | None) -> str | None:
    """Return YYYY-MM-DD for a recognizable date, else None. Never guesses."""
    value = (raw or "").strip()
    if not value:
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", value)
    if m:
        return value
    m = re.match(r"^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})$", value)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= d <= 31 and 1 <= mo <= 12:
            return f"{y:04d}-{mo:02d}-{d:02d}"
    return None


_DOCKET_RE = re.compile(r"(?i)\b(?:E|K|Esas|Karar)\.?\s*(?:No)?\.?\s*[:.]?\s*(\d{4})\s*[/-]\s*(\d+)")


def extract_docket(text: str, kind: str) -> str | None:
    """Extract an E. (esas) or K. (karar) docket like '2020/123' from text.

    kind ∈ {"E", "K"}. Matches both the abbreviated ("E." / "K.") and the full
    Turkish word forms ("Esas No:" / "Karar No:"). Requires a YYYY/N pattern
    immediately after (so "Karar Tarihi: 12.06.2021" never matches). Returns
    'YYYY/N' or None. Does not fabricate.
    """
    if kind.upper() == "E":
        alts = "Esas|E"
    else:
        alts = "Karar|K"
    pat = re.compile(
        rf"(?i)\b(?:{alts})\.?\s*(?:no)?\.?\s*[:.]?\s*(\d{{4}})\s*[/-]\s*(\d+)"
    )
    m = pat.search(text or "")
    if m:
        return f"{m.group(1)}/{int(m.group(2))}"
    return None
