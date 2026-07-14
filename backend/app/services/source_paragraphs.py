"""Deterministic text normalization and citable source paragraph splitting.

Article locator provenance is derived only from anchored headings in canonical
normalized legal text. Provider discovery metadata is never an input.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

MAX_TEXT_CHARS = 5_000_000

ARTICLE_KIND_REGULAR = "regular_article"
ARTICLE_KIND_ADDITIONAL = "additional_article"
ARTICLE_KIND_PROVISIONAL = "provisional_article"
ARTICLE_KIND_REPEATED = "repeated_article"
ARTICLE_KINDS = frozenset({
    ARTICLE_KIND_REGULAR,
    ARTICLE_KIND_ADDITIONAL,
    ARTICLE_KIND_PROVISIONAL,
    ARTICLE_KIND_REPEATED,
})

ARTICLE_LOCATOR_VERSION = "p2.6c-article-locator-1"
ARTICLE_LOCATOR_METHOD = "deterministic_heading"

# A Resmi Gazete issue is a publication container, not an instrument article
# namespace. Only individually modeled legal instruments use article splitting.
ARTICLE_BEARING_SOURCE_TYPES = frozenset({
    "legislation",
    "regulation",
    "communique",
    "circular",
    "presidential_decree",
})

_ARTICLE_LABEL_PREFIXES = {
    ARTICLE_KIND_REGULAR: "Madde",
    ARTICLE_KIND_ADDITIONAL: "Ek Madde",
    ARTICLE_KIND_PROVISIONAL: "Geçici Madde",
    ARTICLE_KIND_REPEATED: "Mükerrer Madde",
}

_ARTICLE_NUMBER_RE = re.compile(
    r"^(?P<number>\d+)(?:\s*/\s*(?P<suffix>[a-zçğıöşü]))?$",
    re.IGNORECASE,
)
_ARTICLE_HEADING_RE = re.compile(
    r"^\s*(?:"
    r"(?P<additional>ek\s+madde)|"
    r"(?P<provisional>geçici\s+madde)|"
    r"(?P<repeated>mükerrer\s+madde)|"
    r"(?P<regular>madde|m\.)"
    r")\s*(?P<number>\d+(?:\s*/\s*[a-zçğıöşü])?)"
    r"(?=\s*(?:[-–—.:)(]|$))",
    re.IGNORECASE,
)


def normalize_text(raw: str) -> str:
    text = (raw or "").replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:MAX_TEXT_CHARS]


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def text_hash(text: str) -> str:
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ArticleLocator:
    article_kind: str
    article_number: str
    article_label: str
    article_locator_key: str

    def to_json(self) -> dict[str, str]:
        return {
            "locator_type": "article",
            "article_kind": self.article_kind,
            "article_number": self.article_number,
            "article_label": self.article_label,
            "article_locator_key": self.article_locator_key,
            "article_locator_method": ARTICLE_LOCATOR_METHOD,
            "article_locator_version": ARTICLE_LOCATOR_VERSION,
        }


def normalize_article_number(raw: str) -> str | None:
    """Normalize spacing/case without collapsing legal numbering identity."""
    if not isinstance(raw, str):
        return None
    match = _ARTICLE_NUMBER_RE.fullmatch(raw.strip())
    if match is None:
        return None
    number = match.group("number")
    suffix = match.group("suffix")
    return f"{number}/{suffix.upper()}" if suffix else number


def build_article_locator(article_kind: str, article_number: str) -> ArticleLocator:
    """Build a controlled, collision-safe article locator."""
    if article_kind not in ARTICLE_KINDS:
        raise ValueError("unknown article kind")
    normalized_number = normalize_article_number(article_number)
    if normalized_number is None:
        raise ValueError("invalid article number")
    label = f"{_ARTICLE_LABEL_PREFIXES[article_kind]} {normalized_number}"
    return ArticleLocator(
        article_kind=article_kind,
        article_number=normalized_number,
        article_label=label,
        article_locator_key=f"{article_kind}:{normalized_number}",
    )


def parse_article_heading(line: str) -> ArticleLocator | None:
    """Parse an anchored Turkish legal article heading, or fail closed."""
    if not isinstance(line, str):
        return None
    match = _ARTICLE_HEADING_RE.match(line)
    if match is None:
        return None
    if match.group("additional"):
        kind = ARTICLE_KIND_ADDITIONAL
    elif match.group("provisional"):
        kind = ARTICLE_KIND_PROVISIONAL
    elif match.group("repeated"):
        kind = ARTICLE_KIND_REPEATED
    else:
        kind = ARTICLE_KIND_REGULAR
    try:
        return build_article_locator(kind, match.group("number"))
    except ValueError:
        return None


def controlled_article_locator(
    locator_json: object,
    *,
    stored_article_number: str | None = None,
) -> ArticleLocator | None:
    """Validate persisted locator provenance before exposing safe API fields.

    Legacy, malformed, arbitrary, or internally inconsistent data is not
    upgraded or echoed as controlled subtype provenance.
    """
    if not isinstance(locator_json, dict):
        return None
    kind = locator_json.get("article_kind")
    number = locator_json.get("article_number")
    if not isinstance(kind, str) or not isinstance(number, str):
        return None
    try:
        expected = build_article_locator(kind, number)
    except ValueError:
        return None
    if stored_article_number is not None and stored_article_number != expected.article_number:
        return None
    expected_json = expected.to_json()
    if any(locator_json.get(key) != value for key, value in expected_json.items()):
        return None
    return expected


class SplitParagraph:
    __slots__ = (
        "paragraph_index",
        "heading_path",
        "text",
        "article_number",
        "page",
        "locator_json",
    )

    def __init__(
        self,
        paragraph_index: int,
        text: str,
        *,
        heading_path: str = "",
        article_number: str = "",
        page: int | None = None,
        locator_json: dict[str, str] | None = None,
    ):
        self.paragraph_index = paragraph_index
        self.heading_path = heading_path
        self.text = text
        self.article_number = article_number
        self.page = page
        self.locator_json = locator_json or {}


def split_legislation(normalized: str) -> list[SplitParagraph]:
    """Split at deterministic article headings and preserve subtype provenance."""
    lines = normalized.split("\n")
    blocks: list[tuple[ArticleLocator | None, list[str]]] = []
    current_locator: ArticleLocator | None = None
    current: list[str] = []
    for line in lines:
        locator = parse_article_heading(line)
        if locator is not None:
            if current:
                blocks.append((current_locator, current))
            current_locator = locator
            current = [line.strip()]
        elif line.strip():
            current.append(line.strip())
    if current:
        blocks.append((current_locator, current))

    out: list[SplitParagraph] = []
    for idx, (locator, block_lines) in enumerate(blocks, start=1):
        text = " ".join(block_lines).strip()
        if not text:
            continue
        if locator is None:
            out.append(SplitParagraph(idx, text))
            continue
        out.append(SplitParagraph(
            idx,
            text,
            heading_path=locator.article_label,
            article_number=locator.article_number,
            locator_json=locator.to_json(),
        ))
    if not out:
        return split_generic(normalized)
    return out


def split_generic(normalized: str) -> list[SplitParagraph]:
    """Split by blank lines into ordered paragraphs without fabricated locators."""
    chunks = [c.strip() for c in re.split(r"\n\s*\n", normalized) if c.strip()]
    return [SplitParagraph(i, c) for i, c in enumerate(chunks, start=1)]


def split_paragraphs(source_type: str, normalized: str) -> list[SplitParagraph]:
    if source_type in ARTICLE_BEARING_SOURCE_TYPES:
        return split_legislation(normalized)
    return split_generic(normalized)
