"""P2.7 — Deterministic legal search query grammar + query plan.

This module implements the *official legal search operator semantics* for
Emsalist as a provider-agnostic query language. It is intentionally 100%
deterministic: NO LLM, NO embeddings, NO network. An LLM must never be used to
parse search operators (see Section C of the P2.7 grammar addendum).

Grammar (whitespace outside quotes separates clauses):

    term                plain unquoted term      -> optional_terms   (OR)
    "phrase"            quoted phrase            -> optional_phrases  (OR)
    +term               required unquoted term   -> required_terms    (AND)
    +"phrase"           required quoted phrase   -> required_phrases  (AND)
    -term               excluded unquoted term   -> excluded_terms    (NOT)
    -"phrase"           excluded quoted phrase   -> excluded_phrases   (NOT)

Key invariants enforced here and relied on by the search pipeline:

* Plain whitespace is OR over the written terms, NOT mandatory AND.
* Quotes are parsed as phrase boundaries; they are never stripped before
  phrase parsing.
* `+`/`-` clauses are HARD CONSTRAINTS, not ranking hints. They are enforced by
  ``matches``/``filter_candidates`` regardless of any lexical/semantic score.
* Malformed explicit operator syntax raises ``MalformedQueryError`` (mapped to a
  422 by the API layer) — it never silently changes the search meaning.
* The raw query is transient and is not part of the persisted safe summary.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

MAX_QUERY_CHARS = 2000
MAX_CLAUSES = 64

# --- Turkish-aware phrase normalization ----------------------------------
# NOTE: unlike the canonical-key fold, phrase normalization must NOT
# transliterate diacritics (ç→c, ş→s ...). Doing so would destroy legally
# meaningful distinctions. We only apply NFKC, Turkish-aware lowercasing and
# bounded whitespace normalization so that:
#     "ARSA   PAYI"  ==  "arsa payı"
_TURKISH_UPPER_MAP = {
    "İ": "i",
    "I": "ı",
}


def turkish_lower(text: str) -> str:
    """Turkish-aware lowercasing (dotless/dotted i handled explicitly)."""
    out = []
    for ch in text or "":
        out.append(_TURKISH_UPPER_MAP.get(ch, ch))
    # Remaining uppercase letters lower normally; the two Turkish special
    # cases were already resolved above so str.lower() won't clobber them.
    return "".join(out).lower()


def normalize_phrase(text: str) -> str:
    """Deterministic, Turkish-aware normalization for phrase/term matching.

    Applies: Unicode NFKC, Turkish-aware casefolding, and bounded whitespace
    normalization. Diacritics and legally meaningful characters are preserved.
    """
    value = unicodedata.normalize("NFKC", text or "")
    value = turkish_lower(value)
    return " ".join(value.split())


# Token pattern operates on already-normalized (lowercased) unicode text and
# keeps Turkish letters + digits together as tokens.
_TOKEN_RE = re.compile(r"[0-9a-zçğıöşü]+", flags=re.UNICODE)


def _tokens(normalized: str) -> list[str]:
    return _TOKEN_RE.findall(normalized)


def _tokenset(normalized: str) -> set[str]:
    return set(_TOKEN_RE.findall(normalized))


# --- Citation / legislation / article candidate extraction ---------------
# These operate on the raw (pre-fold) clause operands so number/punctuation
# meaning is preserved for citation parsing.
_ESAS_RE = re.compile(r"\bE\.?\s*(\d{4})\s*/\s*(\d+)", flags=re.IGNORECASE)
_KARAR_RE = re.compile(r"\bK\.?\s*(\d{4})\s*/\s*(\d+)", flags=re.IGNORECASE)
_BARE_DOCKET_RE = re.compile(r"\b(\d{4})\s*/\s*(\d+)\b")
_ARTICLE_RE = re.compile(
    r"\b(TMK|TBK|HMK|HUMK|TCK|CMK|İİK|IIK|TTK|İYUK|IYUK|TKHK|AY)\s*"
    r"(?:m\.?|madde)?\s*(\d{1,4})(?:\s*/\s*\d+)?",
    flags=re.IGNORECASE,
)
_MADDE_RE = re.compile(r"\b(?:m\.?|madde)\s*(\d{1,4})(?:\s*/\s*\d+)?", flags=re.IGNORECASE)
_SAYILI_RE = re.compile(r"\b(\d{3,5})\s*sayılı\b", flags=re.IGNORECASE)


def _extract_citation_candidates(operands: list[str]) -> tuple[list[str], list[str], list[str]]:
    exact: list[str] = []
    legislation: list[str] = []
    article: list[str] = []
    # Join clauses so multi-token citations (e.g. "TBK 227") that were split
    # across whitespace-separated clauses are still detected, while quoted
    # phrases (already single operands like "E. 2020/123") stay intact.
    haystack = " ".join(operands)
    for y, n in _ESAS_RE.findall(haystack):
        _add(exact, f"E. {y}/{int(n)}")
    for y, n in _KARAR_RE.findall(haystack):
        _add(exact, f"K. {y}/{int(n)}")
    for y, n in _BARE_DOCKET_RE.findall(haystack):
        _add(exact, f"{y}/{int(n)}")
    for code, num in _ARTICLE_RE.findall(haystack):
        _add(article, f"{code.upper().replace('IIK', 'İİK').replace('IYUK', 'İYUK')} {int(num)}")
    for num in _MADDE_RE.findall(haystack):
        _add(article, f"madde {int(num)}")
    for num in _SAYILI_RE.findall(haystack):
        _add(legislation, f"{int(num)} sayılı")
    return exact, legislation, article


def _add(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


# --- Errors ---------------------------------------------------------------
class MalformedQueryError(ValueError):
    """Raised for structurally malformed explicit operator syntax.

    The API layer maps this to a 422 semantic validation error (the documented
    behavior chosen over silent literal-text fallback).
    """

    def __init__(self, reason: str, *, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(reason)


# --- Query plan -----------------------------------------------------------
@dataclass
class SearchQueryPlan:
    """Deterministic representation of a parsed search query.

    ``raw_query_transient`` is intentionally excluded from ``safe_summary`` and
    must not be persisted by default.
    """

    raw_query_transient: str = ""
    normalized_query: str = ""

    optional_terms: list[str] = field(default_factory=list)
    optional_phrases: list[str] = field(default_factory=list)
    required_terms: list[str] = field(default_factory=list)
    required_phrases: list[str] = field(default_factory=list)
    excluded_terms: list[str] = field(default_factory=list)
    excluded_phrases: list[str] = field(default_factory=list)

    exact_citation_candidates: list[str] = field(default_factory=list)
    legislation_number_candidates: list[str] = field(default_factory=list)
    article_candidates: list[str] = field(default_factory=list)

    # ----- Derived views --------------------------------------------------
    def has_constraints(self) -> bool:
        return bool(
            self.required_terms
            or self.required_phrases
            or self.excluded_terms
            or self.excluded_phrases
        )

    def positive_clauses(self) -> list[str]:
        """Positive (non-excluded) clauses, operators stripped.

        Used to derive a natural-language semantic query. Plus/minus signs and
        quotation syntax are NEVER embedded as if they were legal concepts.
        """
        seen: list[str] = []
        for value in (
            *self.required_phrases,
            *self.required_terms,
            *self.optional_phrases,
            *self.optional_terms,
        ):
            if value and value not in seen:
                seen.append(value)
        return seen

    def semantic_query(self) -> str:
        """Derive the plain-text query handed to semantic retrieval.

        Semantic retrieval may expand recall for the positive clauses, but it
        must NOT reinterpret the boolean grammar; enforcement of required and
        excluded constraints happens separately in ``matches``.
        """
        return " ".join(self.positive_clauses()).strip()

    def safe_summary(self) -> dict:
        """Persistable summary WITHOUT the transient raw query."""
        return {
            "normalized_query": self.normalized_query,
            "optional_terms": list(self.optional_terms),
            "optional_phrases": list(self.optional_phrases),
            "required_terms": list(self.required_terms),
            "required_phrases": list(self.required_phrases),
            "excluded_terms": list(self.excluded_terms),
            "excluded_phrases": list(self.excluded_phrases),
            "exact_citation_candidates": list(self.exact_citation_candidates),
            "legislation_number_candidates": list(self.legislation_number_candidates),
            "article_candidates": list(self.article_candidates),
        }

    # ----- Hard-constraint enforcement (steps 8-9) ------------------------
    def matches(self, candidate_text: str) -> bool:
        """True if a candidate satisfies ALL required and NO excluded clauses.

        This is a HARD filter. A perfect semantic or lexical score cannot
        rescue a candidate that violates it. Optional clauses do not affect the
        boolean outcome — they only influence recall/ranking elsewhere.
        """
        normalized = normalize_phrase(candidate_text)
        tokens = _tokenset(normalized)

        for phrase in self.required_phrases:
            if not _phrase_present(phrase, normalized):
                return False
        for term in self.required_terms:
            if normalize_phrase(term) not in tokens:
                return False
        for phrase in self.excluded_phrases:
            if _phrase_present(phrase, normalized):
                return False
        for term in self.excluded_terms:
            if normalize_phrase(term) in tokens:
                return False
        return True

    def explain_match(self, candidate_text: str) -> list[str]:
        """Deterministic, user-facing Turkish match reasons (no AST/token IDs)."""
        normalized = normalize_phrase(candidate_text)
        tokens = _tokenset(normalized)
        reasons: list[str] = []
        for phrase in self.required_phrases:
            if _phrase_present(phrase, normalized):
                reasons.append(f"Zorunlu '{phrase}' ifadesi eşleşti.")
        for term in self.required_terms:
            if normalize_phrase(term) in tokens:
                reasons.append(f"Zorunlu '{term}' terimi eşleşti.")
        for phrase in self.optional_phrases:
            if _phrase_present(phrase, normalized):
                reasons.append(f"'{phrase}' tam ifade eşleşmesi bulundu.")
        for term in self.optional_terms:
            if normalize_phrase(term) in tokens:
                reasons.append(f"'{term}' terimi eşleşti.")
        for phrase in self.excluded_phrases:
            reasons.append(f"'{phrase}' hariç tutma koşulu uygulandı.")
        for term in self.excluded_terms:
            reasons.append(f"'{term}' hariç tutma koşulu uygulandı.")
        return reasons


def _phrase_present(phrase: str, normalized_text: str) -> bool:
    """Phrase match = normalized phrase occurs as a contiguous substring.

    A phrase match is intentionally different from independent token matches:
    the words must appear adjacently in the normalized text.
    """
    needle = normalize_phrase(phrase)
    if not needle:
        return False
    return needle in normalized_text


def phrase_matches(phrase: str, candidate_text: str) -> bool:
    """Public helper: does ``phrase`` occur (normalized, contiguous) in text.

    A quoted phrase must NOT be considered matched merely because its tokens
    appear separately in unrelated locations.
    """
    return _phrase_present(phrase, normalize_phrase(candidate_text))


def term_matches(term: str, candidate_text: str) -> bool:
    """Public helper: does ``term`` occur as a standalone token in text."""
    return normalize_phrase(term) in _tokenset(normalize_phrase(candidate_text))


def filter_candidates(plan: SearchQueryPlan, candidates, *, text_getter=None):
    """Apply the plan's hard boolean constraints to a candidate iterable.

    ``text_getter`` extracts the searchable text from a candidate; defaults to
    treating the candidate itself as a string.
    """
    getter = text_getter or (lambda c: c if isinstance(c, str) else str(c))
    return [c for c in candidates if plan.matches(getter(c))]


# --- Parser ---------------------------------------------------------------
def parse_query(raw: str) -> SearchQueryPlan:
    """Parse a raw search string into a deterministic ``SearchQueryPlan``.

    Raises ``MalformedQueryError`` for structurally malformed explicit operator
    syntax (unterminated quotes, dangling +/- prefixes).
    """
    if raw is None:
        raw = ""
    if len(raw) > MAX_QUERY_CHARS:
        raise MalformedQueryError("query_too_long", detail=f"max {MAX_QUERY_CHARS} chars")

    clauses = _tokenize(raw)
    if len(clauses) > MAX_CLAUSES:
        raise MalformedQueryError("too_many_clauses", detail=f"max {MAX_CLAUSES} clauses")

    plan = SearchQueryPlan(raw_query_transient=raw)
    operands: list[str] = []

    for prefix, quoted, text in clauses:
        operand = text.strip()
        if not operand:
            if quoted:
                # An explicitly empty quoted phrase ("") carries no meaning.
                continue
            if prefix:
                raise MalformedQueryError(
                    "dangling_operator",
                    detail=f"'{prefix}' has no following term or phrase",
                )
            continue
        operands.append(operand)

        if quoted:
            normalized = normalize_phrase(operand)
            if not normalized:
                continue
            if prefix == "+":
                _add(plan.required_phrases, normalized)
            elif prefix == "-":
                _add(plan.excluded_phrases, normalized)
            else:
                _add(plan.optional_phrases, normalized)
        else:
            normalized = normalize_phrase(operand)
            if not normalized:
                continue
            if prefix == "+":
                _add(plan.required_terms, normalized)
            elif prefix == "-":
                _add(plan.excluded_terms, normalized)
            else:
                # Space-separated unquoted text: EACH token is an optional (OR)
                # term. Whitespace is never mandatory AND.
                for token in normalized.split(" "):
                    _add(plan.optional_terms, token)

    plan.normalized_query = " ".join(
        normalize_phrase(op) for op in operands if normalize_phrase(op)
    )
    (
        plan.exact_citation_candidates,
        plan.legislation_number_candidates,
        plan.article_candidates,
    ) = _extract_citation_candidates(operands)
    return plan


def _tokenize(raw: str) -> list[tuple[str, bool, str]]:
    """Split into clauses of (prefix, is_quoted, text).

    prefix is '', '+' or '-'. Whitespace outside quotes separates clauses. A
    +/- prefix applies only to the immediately following term/phrase.
    """
    clauses: list[tuple[str, bool, str]] = []
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        if ch.isspace():
            i += 1
            continue

        prefix = ""
        if ch in "+-":
            prefix = ch
            i += 1
            if i >= n or raw[i].isspace():
                raise MalformedQueryError(
                    "dangling_operator",
                    detail=f"'{prefix}' must be immediately followed by a term or phrase",
                )
            ch = raw[i]

        if ch == '"':
            end = raw.find('"', i + 1)
            if end == -1:
                raise MalformedQueryError(
                    "unterminated_quote",
                    detail="a quoted phrase is missing its closing quotation mark",
                )
            text = raw[i + 1 : end]
            clauses.append((prefix, True, text))
            i = end + 1
        else:
            start = i
            while i < n and not raw[i].isspace() and raw[i] != '"':
                i += 1
            text = raw[start:i]
            clauses.append((prefix, False, text))
    return clauses
