"""P2.6 — Deterministic canonical key engine + controlled vocabulary.

Produces a single, stable canonical key per legal source so the same decision or
statute (regardless of which page/PDF/re-fetch it came from) maps to ONE
canonical SourceRecord. All normalization is deterministic and centralized here.
"""
from __future__ import annotations

import re
import unicodedata

# --- Controlled source-type vocabulary -----------------------------------
SOURCE_TYPES = frozenset({
    "legislation",
    "regulation",
    "communique",
    "circular",
    "presidential_decree",
    "official_gazette_issue",
    "supreme_court_decision",
    "council_of_state_decision",
    "constitutional_court_decision",
    "court_of_jurisdictional_disputes_decision",
    "regional_court_decision",
    "first_instance_decision",
    "doctrine_article",
    "doctrine_book",
    "institutional_guidance",
    "user_uploaded_source",
})

COURT_DECISION_TYPES = frozenset({
    "supreme_court_decision",
    "council_of_state_decision",
    "constitutional_court_decision",
    "court_of_jurisdictional_disputes_decision",
    "regional_court_decision",
    "first_instance_decision",
})

LEGISLATION_TYPES = frozenset({
    "legislation",
    "regulation",
    "communique",
    "circular",
    "presidential_decree",
    "official_gazette_issue",
})

# Aliases → controlled type (normalize legacy/free-string variants).
_SOURCE_TYPE_ALIASES = {
    "yargitay": "supreme_court_decision",
    "yargıtay": "supreme_court_decision",
    "supreme_court": "supreme_court_decision",
    "danistay": "council_of_state_decision",
    "danıştay": "council_of_state_decision",
    "council_of_state": "council_of_state_decision",
    "anayasa_mahkemesi": "constitutional_court_decision",
    "aym": "constitutional_court_decision",
    "constitutional_court": "constitutional_court_decision",
    "uyusmazlik": "court_of_jurisdictional_disputes_decision",
    "bam": "regional_court_decision",
    "bolge_adliye": "regional_court_decision",
    "istinaf": "regional_court_decision",
    "ilk_derece": "first_instance_decision",
    "kanun": "legislation",
    "mevzuat": "legislation",
    "yonetmelik": "regulation",
    "teblig": "communique",
    "genelge": "circular",
    "chk": "presidential_decree",
    "cumhurbaskanligi_kararnamesi": "presidential_decree",
    "resmi_gazete": "official_gazette_issue",
    "doktrin": "doctrine_article",
    "makale": "doctrine_article",
    "kitap": "doctrine_book",
    "kurum_rehberi": "institutional_guidance",
    "kullanici": "user_uploaded_source",
}


class CanonicalKeyError(ValueError):
    pass


def normalize_source_type(raw: str) -> str:
    value = (raw or "").strip()
    lowered = value.casefold()
    if lowered in {t.casefold() for t in SOURCE_TYPES}:
        # Match canonical spelling.
        for t in SOURCE_TYPES:
            if t.casefold() == lowered:
                return t
    folded = _fold_key(value).replace(" ", "_")
    if folded in _SOURCE_TYPE_ALIASES:
        return _SOURCE_TYPE_ALIASES[folded]
    if lowered in _SOURCE_TYPE_ALIASES:
        return _SOURCE_TYPE_ALIASES[lowered]
    raise CanonicalKeyError(f"unknown source_type: {raw!r}")


def _fold_key(value: str) -> str:
    """Turkish-aware fold: casefold, transliterate, drop combining, collapse."""
    translated = (
        str(value or "")
        .replace("İ", "i")
        .replace("I", "i")
        .casefold()
        .translate(str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ç": "c", "ö": "o", "ü": "u"}))
    )
    decomposed = "".join(
        ch for ch in unicodedata.normalize("NFKD", translated)
        if not unicodedata.combining(ch)
    )
    cleaned = re.sub(r"[^a-z0-9]+", " ", decomposed)
    return " ".join(cleaned.split())


def _normalize_docket(raw: str) -> str:
    """Normalize an 'esas/karar' number like '2020/123', 'E.2020/123' → '2020/123'."""
    value = (raw or "").strip()
    value = re.sub(r"(?i)\b(esas|karar|e|k)\.?\s*(no)?\.?\s*[:.]?\s*", "", value)
    value = value.replace("-", "/").replace(" ", "")
    m = re.search(r"(\d{4})\s*/\s*(\d+)", value)
    if m:
        return f"{m.group(1)}/{int(m.group(2))}"
    return value


def _normalize_date(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", value)
    if m:
        return value
    m = re.match(r"^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})$", value)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= d <= 31 and 1 <= mo <= 12:
            return f"{y:04d}-{mo:02d}-{d:02d}"
    return value


def _chamber_token(court: str, chamber: str) -> str:
    combined = _fold_key(f"{court} {chamber}")
    # Extract a chamber number + type token, e.g. "13 hd".
    m = re.search(r"(\d{1,2})\s*(hukuk|ceza|hd|cd|h d|c d)?", combined)
    if m and m.group(1):
        kind = (m.group(2) or "").replace(" ", "")
        kind = "hd" if kind.startswith("hukuk") or kind == "hd" else ("cd" if kind.startswith("ceza") or kind == "cd" else kind)
        return f"{int(m.group(1))}{kind}"
    return combined.replace(" ", "")


def canonical_key_for_decision(
    *, source_type: str, court: str, chamber: str,
    case_number: str, decision_number: str, decision_date: str,
) -> str:
    st = normalize_source_type(source_type)
    if st not in COURT_DECISION_TYPES:
        raise CanonicalKeyError(f"{st} is not a court decision type")
    court_token = _fold_key(court).replace(" ", "_") or "court"
    chamber_token = _chamber_token(court, chamber)
    case_no = _normalize_docket(case_number)
    dec_no = _normalize_docket(decision_number)
    date = _normalize_date(decision_date)
    if not (case_no and dec_no):
        raise CanonicalKeyError("decision requires case_number and decision_number")
    return f"{st}|{court_token}|{chamber_token}|{case_no}|{dec_no}|{date}"


def canonical_key_for_legislation(
    *, source_type: str, issuing_authority: str, number: str, publication_date: str,
) -> str:
    st = normalize_source_type(source_type)
    if st not in LEGISLATION_TYPES:
        raise CanonicalKeyError(f"{st} is not a legislation type")
    authority = _fold_key(issuing_authority).replace(" ", "_") or "authority"
    num = _fold_key(number).replace(" ", "")
    date = _normalize_date(publication_date)
    if not num:
        raise CanonicalKeyError("legislation requires a number")
    return f"{st}|{authority}|{num}|{date}"


def build_canonical_key(metadata: dict) -> str:
    """Dispatch canonical key generation from a metadata dict."""
    st = normalize_source_type(metadata.get("source_type", ""))
    if st in COURT_DECISION_TYPES:
        return canonical_key_for_decision(
            source_type=st,
            court=metadata.get("court", ""),
            chamber=metadata.get("chamber", ""),
            case_number=metadata.get("case_number", ""),
            decision_number=metadata.get("decision_number", ""),
            decision_date=metadata.get("decision_date", ""),
        )
    if st in LEGISLATION_TYPES:
        return canonical_key_for_legislation(
            source_type=st,
            issuing_authority=metadata.get("issuing_authority", ""),
            number=metadata.get("number", "") or metadata.get("case_number", ""),
            publication_date=metadata.get("publication_date", ""),
        )
    # Doctrine / institutional / user-uploaded: title-hash-based stable key.
    title_token = _fold_key(metadata.get("title", "")).replace(" ", "_")
    if not title_token:
        raise CanonicalKeyError("non-decision/legislation source requires a title")
    return f"{st}|{title_token}"
