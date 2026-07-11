"""P2.5 — Deterministic, rule-based extractor for high-confidence identifiers.

Only patterns that can be matched reliably without any LLM are produced here:
dates, monetary amounts, case/file numbers, Turkish vehicle plates and VIN/
chassis numbers. Every result is a *suggestion* (verification_status =
"detected") bound to a page/position and a source-quote hash — never a
confirmed fact. Parties, claims, defenses and legal conclusions are NOT
inferred here (no verified analyzer exists in P2.5).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.services.document_parsing import ParsedPage


@dataclass
class ExtractionCandidate:
    extraction_type: str
    field_key: str
    value: str
    normalized_value: str
    page_number: int | None
    text_span: str
    source_quote: str
    confidence: float


# --- Patterns -------------------------------------------------------------
_DATE_RE = re.compile(
    r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b"
)
_MONEY_RE = re.compile(
    r"\b(\d{1,3}(?:[.\s]\d{3})*(?:,\d{1,2})?)\s?(TL|TRY|₺|USD|EUR|\$|€)\b",
    re.IGNORECASE,
)
_PLATE_RE = re.compile(
    r"\b(0[1-9]|[1-7][0-9]|8[01])\s?[A-ZÇĞİÖŞÜ]{1,3}\s?\d{2,4}\b"
)
_VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")
_CASE_NO_RE = re.compile(
    r"\b(\d{4})/(\d{1,6})\s*(E\.?|K\.?|Esas|Karar)?",
    re.IGNORECASE,
)


def _quote_hash(quote: str) -> str:
    return hashlib.sha256(quote.strip().encode("utf-8")).hexdigest()


def _window(text: str, start: int, end: int, pad: int = 40) -> str:
    return text[max(0, start - pad):min(len(text), end + pad)].strip()


def _norm_money(amount: str) -> str:
    cleaned = amount.replace(" ", "").replace(".", "").replace(",", ".")
    return cleaned


def extract_from_pages(pages: list[ParsedPage]) -> list[ExtractionCandidate]:
    """Runs deterministic matchers over each page, preserving page provenance.

    Duplicate (field_key, normalized_value) pairs are collapsed so re-running is
    idempotent at the value level.
    """
    out: list[ExtractionCandidate] = []
    seen: set[tuple[str, str]] = set()

    def _add(cand: ExtractionCandidate) -> None:
        key = (cand.field_key, cand.normalized_value)
        if cand.normalized_value and key not in seen:
            seen.add(key)
            out.append(cand)

    for page in pages:
        text = page.text
        if not text:
            continue

        for m in _DATE_RE.finditer(text):
            d, mo, y = m.group(1), m.group(2), m.group(3)
            try:
                di, moi = int(d), int(mo)
                if not (1 <= di <= 31 and 1 <= moi <= 12):
                    continue
            except ValueError:
                continue
            iso = f"{y}-{int(mo):02d}-{int(d):02d}"
            _add(ExtractionCandidate(
                extraction_type="date", field_key="date", value=m.group(0),
                normalized_value=iso, page_number=page.page_number,
                text_span=f"{m.start()}:{m.end()}",
                source_quote=_window(text, m.start(), m.end()), confidence=0.6,
            ))

        for m in _MONEY_RE.finditer(text):
            _add(ExtractionCandidate(
                extraction_type="money", field_key="amount", value=m.group(0),
                normalized_value=f"{_norm_money(m.group(1))} {m.group(2).upper()}",
                page_number=page.page_number, text_span=f"{m.start()}:{m.end()}",
                source_quote=_window(text, m.start(), m.end()), confidence=0.6,
            ))

        for m in _PLATE_RE.finditer(text):
            plate = re.sub(r"\s+", "", m.group(0)).upper()
            _add(ExtractionCandidate(
                extraction_type="plate", field_key="vehicle_plate", value=m.group(0),
                normalized_value=plate, page_number=page.page_number,
                text_span=f"{m.start()}:{m.end()}",
                source_quote=_window(text, m.start(), m.end()), confidence=0.55,
            ))

        for m in _VIN_RE.finditer(text):
            vin = m.group(1).upper()
            # VIN excludes I,O,Q and is exactly 17 chars — the regex enforces this.
            _add(ExtractionCandidate(
                extraction_type="vin", field_key="vehicle_vin", value=vin,
                normalized_value=vin, page_number=page.page_number,
                text_span=f"{m.start()}:{m.end()}",
                source_quote=_window(text, m.start(), m.end()), confidence=0.5,
            ))

        for m in _CASE_NO_RE.finditer(text):
            marker = (m.group(3) or "").strip().lower()
            field = "decision_number" if marker.startswith("k") else "case_number"
            _add(ExtractionCandidate(
                extraction_type="case_number", field_key=field, value=m.group(0).strip(),
                normalized_value=f"{m.group(1)}/{m.group(2)}",
                page_number=page.page_number, text_span=f"{m.start()}:{m.end()}",
                source_quote=_window(text, m.start(), m.end()), confidence=0.5,
            ))

    return out
