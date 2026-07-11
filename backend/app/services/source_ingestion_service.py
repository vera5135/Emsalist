"""P2.6 — Source ingestion pipeline.

TRUST MODEL (P2.6v2):
- editor_submit / manual: ALWAYS starts as needs_review. Even if the user
  provides an official URL, the raw text came from the client — 'URL present'
  is not evidence.
- official_fetch (secure_fetch): when the server itself fetches bytes from an
  allowlisted official URL with successful SSRF-safe retrieval, those exact
  bytes + the fetched content hash constitute official-match evidence. Only
  this path can produce verified_official.
- A new SourceVersion with changed content does NOT inherit the previous
  version's trust. If no new official-fetch evidence is provided, the
  verification_status resets to needs_review.
- Previous version's evidence is preserved (never deleted).
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
from app.services.source_fetcher import ALLOWED_DOMAINS, FetchResult
from app.services.source_verification import (
    CONFLICTING,
    NEEDS_REVIEW,
    VERIFIED_OFFICIAL,
    can_transition,
)

PARSER_VERSION = "p2.6-ingest-2"


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


_METADATA_CONFLICT_FIELDS = frozenset({
    "publication_date", "issuing_authority", "court", "chamber",
})


def _metadata_conflict(record, metadata: dict) -> bool:
    """Detect materially different metadata fields (those NOT part of
    canonical key identity).
    """
    for field_name in _METADATA_CONFLICT_FIELDS:
        incoming = (metadata.get(field_name) or "").strip()
        existing = (getattr(record, field_name, "") or "").strip()
        if incoming and existing and incoming != existing:
            return True
    return False


def _version_has_fetch_evidence(session, version_id: str) -> bool:
    """Check whether the given version has official_fetch_match evidence.

    This prevents a newly-created version from inheriting an older version's
    verified_official status — only explicit matching evidence counts.
    """
    from app.db.source_repository import SourceVerificationRepository

    # We cannot await here syntactically; callers that need this do it themselves.
    return False  # stub for sync access


async def _version_has_verification_evidence(
    session: AsyncSession, record_id: str, version_id: str
) -> bool:
    """True when at least one official_match verification exists that references
    this exact version_id.
    """
    verifications = await SourceVerificationRepository.list_for_record(session, record_id)
    for v in verifications:
        if v.verifier_type == "official_match" and v.source_version_id == version_id:
            return True
    return False


def effective_verification_status(
    record_verification_status: str,
    current_version_id: str | None,
    version: tuple | None,  # (version_id, has_fetch_evidence for current version)
) -> str:
    """The user-facing / search-index trust status for the current source.

    A SourceRecord.verification_status of 'verified_official' is a ceiling, not
    a guarantee. The effective trust is bounded by the latest version's own
    evidence: if the current version has no official_fetch_match verification
    evidence, the source cannot be treated as verified_official.
    """
    if record_verification_status == VERIFIED_OFFICIAL:
        if version is None:
            return NEEDS_REVIEW
        vid, has_evidence = version
        if vid and has_evidence:
            return VERIFIED_OFFICIAL
        return NEEDS_REVIEW
    return record_verification_status


async def ingest_source(
    session: AsyncSession,
    *,
    metadata: dict,
    raw_text: str,
    official_url: str = "",
    retrieval_method: str = "manual",
    raw_document_hash: str | None = None,
    fetch_result: FetchResult | None = None,
) -> IngestResult:
    """Ingest a source.

    - retrieval_method='editor_submit' or 'manual': starts as needs_review.
      official_url alone DOES NOT auto-verify.
    - retrieval_method='official_fetch': caller has securely fetched bytes
      from an allowlisted official URL (SSRF-validated). A non-None
      [fetch_result] provides the canonical evidence. This path can produce
      verified_official.
    """
    source_type = normalize_source_type(metadata.get("source_type", ""))
    canonical_key = build_canonical_key({**metadata, "source_type": source_type})
    normalized = para.normalize_text(raw_text)
    content_hash = para.content_hash(normalized)

    is_official_fetch = (
        retrieval_method == "official_fetch"
        and fetch_result is not None
        and bool(official_url)
        and _official_domain(official_url)
    )

    record = await SourceRecordRepository.get_by_canonical_key(session, canonical_key)

    if record is None:
        # New canonical record.
        initial_status = NEEDS_REVIEW
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

        if is_official_fetch:
            await _produce_official_verification(
                session, record.id, version.id, content_hash, official_url
            )
            await SourceRecordRepository.transition_status(session, record, VERIFIED_OFFICIAL)
            initial_status = VERIFIED_OFFICIAL

        return IngestResult(record.id, version.id, canonical_key, record.verification_status, "created")

    # Existing canonical record.
    await SourceRecordRepository.mark_checked(session, record, successful=True)
    existing_version = await SourceVersionRepository.get_by_hash(session, record.id, content_hash)
    if existing_version is not None:
        return IngestResult(record.id, existing_version.id, canonical_key, record.verification_status, "duplicate")

    if _metadata_conflict(record, metadata):
        from app.services.source_verification import can_transition as _ct

        if _ct(record.verification_status, CONFLICTING):
            await SourceRecordRepository.transition_status(session, record, CONFLICTING)
        await SourceVerificationRepository.create(
            session, source_record_id=record.id,
            verification_method="metadata_conflict", verifier_type="automated",
            result=CONFLICTING, notes="Metadata conflict on ingestion.",
        )
        return IngestResult(record.id, record.current_version_id or "", canonical_key, record.verification_status, "conflict")

    # New version (changed content from same canonical key).
    # Always reset to needs_review unless official_fetch evidence is also provided.
    version = await _create_version_with_paragraphs(
        session, record, source_type, normalized, content_hash,
        retrieval_method, raw_document_hash, metadata,
        supersedes_version_id=record.current_version_id,
    )
    if record.current_version_id:
        prev = await SourceVersionRepository.get(session, record.current_version_id)
        if prev is not None:
            prev.status = "superseded"
            await session.flush()
    await SourceRecordRepository.set_current_version(session, record, version.id)

    new_status = NEEDS_REVIEW
    if is_official_fetch:
        await _produce_official_verification(
            session, record.id, version.id, content_hash, official_url
        )
        if can_transition(record.verification_status, VERIFIED_OFFICIAL):
            await SourceRecordRepository.transition_status(session, record, VERIFIED_OFFICIAL)
            new_status = VERIFIED_OFFICIAL
    else:
        # Changed content without fetch evidence — reset trust.
        if record.verification_status in (VERIFIED_OFFICIAL,):
            if can_transition(record.verification_status, NEEDS_REVIEW):
                await SourceRecordRepository.transition_status(session, record, NEEDS_REVIEW)
            new_status = record.verification_status

    return IngestResult(record.id, version.id, canonical_key, new_status, "new_version")


async def _produce_official_verification(
    session, record_id, version_id, content_hash, official_url,
):
    from app.services.source_verification import VERIFIED_OFFICIAL as VO

    await SourceVerificationRepository.create(
        session,
        source_record_id=record_id,
        source_version_id=version_id,
        verification_method="official_fetch_match",
        verifier_type="official_match",
        result=VO,
        evidence_url=official_url,
        evidence_hash=content_hash,
    )


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
