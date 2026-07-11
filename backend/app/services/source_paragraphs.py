"""P2.6 — Deterministic text normalization + paragraph splitting for sources.

Splits normalized source text into citable paragraphs, preserving article
numbers for legislation and section indices for decisions. Never fabricates a
page number; page is only set when a real per-page source provides it.
"""
from __future__ import annotations

import hashlib
import re

MAX_TEXT_CHARS = 5_000_000


def normalize_text(raw: str) -> str:
    text = (raw or "").replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:MAX_TEXT_CHARS]


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def text_hash(text: str) -> str:
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()


_ARTICLE_RE = re.compile(r"(?im)^\s*(madde|m\.)\s*(\d+[a-zçğıöşü]?)\b")


class SplitParagraph:
    __slots__ = ("paragraph_index", "heading_path", "text", "article_number", "page")

    def __init__(self, paragraph_index: int, text: str, *, heading_path: str = "",
                 article_number: str = "", page: int | None = None):
        self.paragraph_index = paragraph_index
        self.heading_path = heading_path
        self.text = text
        self.article_number = article_number
        self.page = page


def split_legislation(normalized: str) -> list[SplitParagraph]:
    """Split by 'Madde N' boundaries, preserving the article number."""
    lines = normalized.split("\n")
    blocks: list[tuple[str, list[str]]] = []
    current_article = ""
    current: list[str] = []
    for line in lines:
        m = _ARTICLE_RE.match(line)
        if m:
            if current:
                blocks.append((current_article, current))
            current_article = m.group(2)
            current = [line.strip()]
        else:
            if line.strip():
                current.append(line.strip())
    if current:
        blocks.append((current_article, current))
    out: list[SplitParagraph] = []
    for idx, (article, block_lines) in enumerate(blocks, start=1):
        text = " ".join(block_lines).strip()
        if text:
            out.append(SplitParagraph(idx, text, article_number=article))
    if not out:
        return split_generic(normalized)
    return out


def split_generic(normalized: str) -> list[SplitParagraph]:
    """Split by blank lines into ordered paragraphs (no fabricated page/article)."""
    chunks = [c.strip() for c in re.split(r"\n\s*\n", normalized) if c.strip()]
    return [SplitParagraph(i, c) for i, c in enumerate(chunks, start=1)]


def split_paragraphs(source_type: str, normalized: str) -> list[SplitParagraph]:
    from app.services.source_canonical_key import LEGISLATION_TYPES

    if source_type in LEGISLATION_TYPES:
        return split_legislation(normalized)
    return split_generic(normalized)
