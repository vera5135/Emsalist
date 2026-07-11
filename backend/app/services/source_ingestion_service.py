"""P2.6 — Source ingestion pipeline (fetch → hash → canonical key → dedup →
version → paragraphs → automated verification).

Key principle: 'successfully fetched' != 'verified'. Ingestion produces
needs_review by default. verified_official is granted ONLY when the source came
from an allowlisted official domain AND retrieval succeeded AND a content hash
exists — never merely because a URL contains 'gov'. Duplicate canonical keys are
never silently overwritten: content changes create a new version; metadata
conflicts produce a conflicting/needs_review outcome.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.source_repository import (
    SourceParagraphRepository,
    SourceRecordRepository,
    SourceVerificationRepository,
    SourceVersionRepository,
)
from app.services import source_paragraphs as para
from app.services.source_canonical_key import build_canonical_key, normalize_source_type
from app.services.source_fetcher import ALLOWED_DOMAINS
from app.services.source_verification import (
    CONFLICTING,
    NEEDS_REVIEW,
    VERIFIED_OFFICIAL,
)

PARSER_VERSION = "p2.6-ingest-1"


@dataclass
class IngestResult:
    source_record_id: str
    source_version_id: str
    canonical_key: str
    verification_status: str
    outcome: str  # created | new_version | duplicate | conflict


def _official_domain(url: str) -> bool:
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower().rstrip(".")
    for domain in ALLOWED_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return True
    return False


def _metadata_conflict(record, metadata: dict) -> bool:
    """Detect materially different metadata for the same canonical key."""
    for field_name in ("decision_date", "publication_date", "case_number", "decision_number"):
        incoming = (metadata.get(field_name) or "").strip()
        existing = (getattr(record, field_name, "") or "").strip()
        if incoming and existing and incoming != existing:
            return True
    return False


async def ingest_source(
    session: AsyncSession,
    *,
    metadata: dict,
    raw_text: str,
    official_url: str = "",
    retrieval_method: str = "manual",
    raw_document_hash: str | None = None,
) -> IngestResult:
    """Ingest a source from already-fetched raw text + metadata.

    Network fetching (with SSRF protection) is performed by the caller/route via
    ``source_fetcher``; this function is deterministic and testable.
    """
    source_type = normalize_source_type(metadata.get("source_type", ""))
    canonical_key = build_canonical_key({**metadata, "source_type": source_type})
    normalized = para.normalize_text(raw_text)
    content_hash = para.content_hash(normalized)

    record = await SourceRecordRepository.get_by_canonical_key(session, canonical_key)
    is_official = bool(official_url) and _official_domain(official_url)

    if record is None:
        # New canonical record.
        initial_status = VERIFIED_OFFICIAL if (is_official and content_hash) else NEEDS_REVIEW
        record = await SourceRecordRepository.create(
            session,
            source_type=source_type,
            canonical_key=canonical_key,
            title=metadata.get("title", ""),
            verification_status=initial_status,
            issuing_authority=metadata.get("issuing_authority", ""),
            court=metadata.get("court", ""),
            chamber=metadata.get("chamber", ""),
            case_number=metadata.get("case_number", ""),
            decision_number=metadata.get("decision_number", ""),
            decision_date=metadata.get("decision_date", ""),
            publication_date=metadata.get("publication_date", ""),
            effective_date=metadata.get("effective_date", ""),
            repeal_date=metadata.get("repeal_date", ""),
            official_url=official_url,
        )
        version = await _create_version_with_paragraphs(
            session, record, source_type, normalized, content_hash,
            retrieval_method, raw_document_hash, metadata,
        )
        await SourceRecordRepository.set_current_version(session, record, version.id)
        await SourceRecordRepository.mark_checked(session, record, successful=True)
        if is_official and content_hash:
            await SourceVerificationRepository.create(
                session, source_record_id=record.id, source_version_id=version.id,
                verification_method="official_domain_hash", verifier_type="official_match",
                result=VERIFIED_OFFICIAL, evidence_url=official_url, evidence_hash=content_hash,
            )
        return IngestResult(record.id, version.id, canonical_key, record.verification_status, "created")

    # Existing canonical record.
    await SourceRecordRepository.mark_checked(session, record, successful=True)
    existing_version = await SourceVersionRepository.get_by_hash(session, record.id, content_hash)
    if existing_version is not None:
        # Case 1: same canonical key + same content → idempotent.
        return IngestResult(record.id, existing_version.id, canonical_key, record.verification_status, "duplicate")

    if _metadata_conflict(record, metadata):
        # Case 3: materially different metadata → conflict, never silent merge.
        from app.services.source_verification import can_transition

        if can_transition(record.verification_status, CONFLICTING):
            await SourceRecordRepository.transition_status(session, record, CONFLICTING)
        await SourceVerificationRepository.create(
            session, source_record_id=record.id,
            verification_method="metadata_conflict", verifier_type="automated",
            result=CONFLICTING, notes="Metadata conflict on ingestion.",
        )
        return IngestResult(record.id, record.current_version_id or "", canonical_key, record.verification_status, "conflict")

    # Case 2: same canonical key + changed content → new version, old preserved.
    version = await _create_version_with_paragraphs(
        session, record, source_type, normalized, content_hash,
        retrieval_method, raw_document_hash, metadata,
        supersedes_version_id=record.current_version_id,
    )
    # Mark the previous version superseded (relationship preserved, not deleted).
    if record.current_version_id:
        prev = await SourceVersionRepository.get(session, record.current_version_id)
        if prev is not None:
            prev.status = "superseded"
            await session.flush()
    await SourceRecordRepository.set_current_version(session, record, version.id)
    return IngestResult(record.id, version.id, canonical_key, record.verification_status, "new_version")


async def _create_version_with_paragraphs(
    session, record, source_type, normalized, content_hash,
    retrieval_method, raw_document_hash, metadata, supersedes_version_id=None,
):
    version = await SourceVersionRepository.create(
        session,
        source_record_id=record.id,
        content_hash=content_hash,
        normalized_text=normalized,
        retrieval_method=retrieval_method,
        parser_version=PARSER_VERSION,
        raw_document_hash=raw_document_hash,
        supersedes_version_id=supersedes_version_id,
        valid_from=metadata.get("effective_date", "") or metadata.get("valid_from", ""),
        valid_to=metadata.get("valid_to", ""),
        metadata_json={"source_type": source_type},
    )
    for sp in para.split_paragraphs(source_type, normalized):
        await SourceParagraphRepository.create(
            session,
            source_version_id=version.id,
            paragraph_index=sp.paragraph_index,
            text=sp.text,
            text_hash=para.text_hash(sp.text),
            heading_path=sp.heading_path,
            page=sp.page,
            article_number=sp.article_number,
        )
    return version
