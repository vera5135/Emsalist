"""P2.6C — Deterministic extracted-legal-content provenance.

Every official fetch produces raw bytes (HTML/PDF/XML). The P2.6 ingestion
engine uses ``ingest_official_fetch(FetchResult)`` which computes
content_hash from fetch_result.content — the raw bytes.

For provider HTML responses this would produce a SourceVersion whose text
is the original plain-HTML extracted text (not site chrome), but whose
content_hash is the hash of the raw HTML bytes. That breaks the
evidence_hash == content_hash invariant because:

- raw HTML hash ≠ extracted legal text hash
- navigation/cookie/sidebar changes in raw HTML would create new
  SourceVersions even though the legal text is identical
- evidence_hash == content_hash must hold for version-scoped trust

This module resolves the problem by introducing ``extract_content_from_fetch``:

  raw fetched bytes
    → provider/deterministic HTML extraction (extracted legal text only)
    → normalize + content_hash on extracted text
    → replace fetch_result.content with normalized extracted text

The ``raw_document_hash`` (SHA-256 of the original raw fetched bytes) is
preserved as provenance but does NOT participate in canonical dedupe or
version-scoped evidence matching.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.services.source_fetcher import FetchResult
from app.services.source_providers.shared import html_to_text

EXTRACTION_METHOD_PROVIDER_HTML = "provider_html_extract"
EXTRACTION_METHOD_RAW_TEXT = "raw_text"

ALLOWED_EXTRACTION_METHODS: frozenset[str] = frozenset({
    EXTRACTION_METHOD_PROVIDER_HTML,
    EXTRACTION_METHOD_RAW_TEXT,
})

_EXTRACTION_VERSION_MAX_LENGTH = 100

EXTRACTION_PARSER_VERSION_PREFIX = "p2.6c-extract-"


def validate_extraction_version(extraction_version: str) -> None:
    if not extraction_version:
        raise ValueError("extraction_version must not be empty")
    if len(extraction_version) > _EXTRACTION_VERSION_MAX_LENGTH:
        raise ValueError(f"extraction_version exceeds {_EXTRACTION_VERSION_MAX_LENGTH} chars")
    if any(ord(c) < 32 for c in extraction_version):
        raise ValueError("extraction_version contains control characters")


def is_extraction_aware_parser_version(parser_version: str | None) -> bool:
    if not parser_version:
        return False
    try:
        validate_extraction_version(parser_version)
    except ValueError:
        return False
    return parser_version.startswith(EXTRACTION_PARSER_VERSION_PREFIX)


@dataclass
class ExtractedContent:
    """Deterministic legal-text extraction with raw-fetch provenance."""

    extracted_text: str
    raw_document_hash: str
    extraction_method: str
    parser_version: str
    # extracted_hash is the P2.6 content_hash computed over extracted_text
    # after normalize_text (see source_paragraphs.py).
    extracted_hash: str


def extract_content_from_fetch(
    fetch_result: FetchResult,
    *,
    parser_version: str = "p2.6c-extract-1",
) -> ExtractedContent:
    """Extract legal content from fetched bytes, replacing chrome with clean text.

    Returns extracted legal body ready for canonical ingestion. The returned
    ``extracted_text`` replaces ``fetch_result.content`` in the canonical
    ingestion path so SourceVersion.content_hash equals the hash of the
    extracted legal text, not site chrome.
    """
    from app.services import source_paragraphs as para

    content_type = (fetch_result.content_type or "").lower()
    is_html = "html" in content_type
    raw_document_hash = hashlib.sha256(fetch_result.content).hexdigest()

    if is_html:
        extracted = html_to_text(fetch_result.content)
        extraction_method = "provider_html_extract"
    else:
        # Non-HTML (plain text, XML, PDF raw, JSON) → extract as-is.
        try:
            extracted = fetch_result.content.decode("utf-8", errors="replace")
        except Exception:
            extracted = fetch_result.content.decode("latin-1", errors="replace")
        extraction_method = "raw_text"

    normalized = para.normalize_text(extracted)
    content_hash = para.content_hash(normalized)

    return ExtractedContent(
        extracted_text=normalized,
        raw_document_hash=raw_document_hash,
        extraction_method=extraction_method,
        parser_version=parser_version,
        extracted_hash=content_hash,
    )


def make_extracted_fetch_result(
    fetch_result: FetchResult,
    extracted: ExtractedContent,
) -> FetchResult:
    """Produce a fetch_result where ``content`` is the extracted legal text
    bytes suitable for canonical ingestion. The original raw fetched bytes
    provenance is preserved in ``extracted.raw_document_hash``."""
    return FetchResult(
        final_url=fetch_result.final_url,
        status_code=fetch_result.status_code,
        content=extracted.extracted_text.encode("utf-8"),
        content_type=fetch_result.content_type,
        redirect_chain=fetch_result.redirect_chain,
    )
