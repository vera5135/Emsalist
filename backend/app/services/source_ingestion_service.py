"""P2.6 — Source ingestion pipeline.

TRUST MODEL (P2.6v3):
- editor_submit / manual: ALWAYS starts as needs_review. Raw text from client.
- official_fetch: server-fetched bytes from allowlisted URL via SSRF-validated
  transport. The fetched bytes are the ONLY canonical source; caller-supplied
  raw_text is NEVER used in this path. Official trust requires:
  1. Successful fetch_result (status=2xx, non-empty content, supported content-type)
  2. allowlisted final_url domain
  3. content_hash computed from fetch_result.content (not caller raw_text)
  4. evidence_hash == SourceVersion.content_hash (exact match)
  5. evidence_url == final_fetched_url (binding)
- New version resets trust unless accompanied by official_fetch evidence.
- Previous version evidence preserved.
- P2.6C extraction provenance: provider-extracted versions carry provenance
  metadata (extraction_method, raw_document_hash, extraction-aware parser_version)
  that is validated during trust resolution.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.source_repository import (
    SourceParagraphRepository,
    SourceRecordRepository,
    SourceVerificationRepository,
    SourceVersionRepository,
)
from app.services import source_paragraphs as para
from app.services.source_canonical_key import build_canonical_key, normalize_source_type
from app.services.source_extraction import (
    ALLOWED_EXTRACTION_METHODS,
    is_extraction_aware_parser_version,
    validate_extraction_version,
)
from app.services.source_fetcher import (
    ALLOWED_CONTENT_TYPES,
    ALLOWED_DOMAINS,
    FetchResult,
    domains_within_global_allowlist,
    url_matches_allowed_domains,
)
from app.services.source_verification import (
    CONFLICTING,
    NEEDS_REVIEW,
    VERIFIED_OFFICIAL,
    can_transition,
)

OUTCOME_CREATED = "created"
OUTCOME_NEW_VERSION = "new_version"
OUTCOME_DUPLICATE = "duplicate"
OUTCOME_DUPLICATE_VERIFIED = "duplicate_verified"
OUTCOME_CONFLICT = "conflict"

OUTCOMES = frozenset({
    OUTCOME_CREATED, OUTCOME_NEW_VERSION, OUTCOME_DUPLICATE,
    OUTCOME_DUPLICATE_VERIFIED, OUTCOME_CONFLICT,
})

PARSER_VERSION = "p2.6-ingest-3"

OFFICIAL_FETCH_METHOD = "official_fetch_match"
OFFICIAL_VERIFIER_TYPE = "official_match"

_RAW_HASH_RE = re.compile(r"^[a-f0-9]{64}$")


def _validate_raw_document_hash(raw_document_hash: str) -> None:
    if not isinstance(raw_document_hash, str):
        raise ValueError("raw_document_hash must be a string")
    if not _RAW_HASH_RE.match(raw_document_hash):
        raise ValueError("raw_document_hash must be exactly 64 lowercase hex chars (SHA-256)")


def _validate_extraction_method(extraction_method: str) -> None:
    if not isinstance(extraction_method, str):
        raise ValueError("extraction_method must be a string")
    if extraction_method not in ALLOWED_EXTRACTION_METHODS:
        raise ValueError(
            f"unknown extraction_method: {extraction_method!r} "
            f"(allowed: {sorted(ALLOWED_EXTRACTION_METHODS)})"
        )


def _validate_extraction_provenance(
    raw_document_hash: str | None,
    extraction_method: str | None,
    extraction_version: str | None,
) -> None:
    _prov = (
        raw_document_hash is not None,
        extraction_method is not None,
        extraction_version is not None,
    )
    if any(_prov) and not all(_prov):
        raise ValueError(
            "extraction provenance is all-or-none: "
            "raw_document_hash, extraction_method, and extraction_version "
            "must all be present or all be absent"
        )
    if all(_prov):
        assert raw_document_hash is not None
        assert extraction_method is not None
        assert extraction_version is not None
        _validate_raw_document_hash(raw_document_hash)
        _validate_extraction_method(extraction_method)
        validate_extraction_version(extraction_version)


@dataclass
class IngestResult:
    source_record_id: str
    source_version_id: str
    canonical_key: str
    verification_status: str
    outcome: str


def _official_domain(
    url: str,
    expected_official_domains: tuple[str, ...] | None = None,
) -> bool:
    if not url_matches_allowed_domains(url, ALLOWED_DOMAINS):
        return False
    if expected_official_domains is None:
        return True
    if not domains_within_global_allowlist(expected_official_domains):
        return False
    return url_matches_allowed_domains(url, expected_official_domains)


_METADATA_CONFLICT_FIELDS = frozenset({
    "publication_date", "issuing_authority", "court", "chamber",
})


def _metadata_conflict(record, metadata: dict) -> bool:
    for field_name in _METADATA_CONFLICT_FIELDS:
        incoming = (metadata.get(field_name) or "").strip()
        existing = (getattr(record, field_name, "") or "").strip()
        if incoming and existing and incoming != existing:
            return True
    return False


@dataclass
class VersionEvidence:
    """Typed result of a version-scoped official evidence lookup.

    Contains the full validation verdict with failure reason when rejected.
    """

    valid: bool
    version_id: str | None
    evidence_url: str | None
    evidence_hash: str | None
    failure_reason: str | None

    @classmethod
    def success(cls, version_id, evidence_url, evidence_hash):
        return cls(True, version_id, evidence_url, evidence_hash, None)

    @classmethod
    def fail(cls, reason):
        return cls(False, None, None, None, reason)


@dataclass(frozen=True)
class VersionExtractionProvenanceState:
    present: bool
    valid: bool
    failure_reason: str | None = None


def version_extraction_provenance_state(version) -> VersionExtractionProvenanceState:
    """Return the authoritative immutable extraction-provenance state."""
    metadata = version.metadata_json or {}
    raw_document_hash = version.raw_document_hash
    extraction_method = metadata.get("extraction_method")
    extraction_parser = is_extraction_aware_parser_version(version.parser_version)
    present = (
        raw_document_hash is not None
        or extraction_method is not None
        or extraction_parser
    )
    if not present:
        return VersionExtractionProvenanceState(present=False, valid=False)
    if not _RAW_HASH_RE.fullmatch(raw_document_hash or ""):
        return VersionExtractionProvenanceState(
            present=True,
            valid=False,
            failure_reason="provider-extracted version: raw_document_hash missing or malformed",
        )
    if extraction_method not in ALLOWED_EXTRACTION_METHODS:
        return VersionExtractionProvenanceState(
            present=True,
            valid=False,
            failure_reason="provider-extracted version: extraction_method missing or unknown",
        )
    if not extraction_parser:
        return VersionExtractionProvenanceState(
            present=True,
            valid=False,
            failure_reason="provider-extracted version: parser_version is not extraction-aware",
        )
    return VersionExtractionProvenanceState(present=True, valid=True)


async def get_version_official_evidence(
    session: AsyncSession, record_id: str, version_id: str
) -> VersionEvidence:
    """Exact-match check: does [version_id] have a valid official_fetch_match
    verification record whose evidence_hash equals the SourceVersion's
    content_hash, evidence_url is an allowlisted official domain, and the
    verifier fields match the canonical official-match signature?

    ALL of these must hold for the verdict to be valid. ANY mismatch returns
    :class:`VersionEvidence` with ``valid=False`` and a descriptive reason.

    For provider-extracted versions (P2.6C), additional extraction provenance
    validation is applied: raw_document_hash must be valid SHA-256,
    extraction_method must be a known controlled value, and parser_version
    must be extraction-aware.
    """
    if not version_id:
        return VersionEvidence.fail("no version_id")
    version = await SourceVersionRepository.get(session, version_id)
    if version is None:
        return VersionEvidence.fail("version not found")

    provenance = version_extraction_provenance_state(version)
    if provenance.present and not provenance.valid:
        return VersionEvidence.fail(provenance.failure_reason or "invalid extraction provenance")

    verifications = await SourceVerificationRepository.list_for_record(
        session, record_id
    )
    for v in verifications:
        if v.source_version_id != version_id:
            continue
        if v.verifier_type != OFFICIAL_VERIFIER_TYPE:
            continue
        if v.verification_method != OFFICIAL_FETCH_METHOD:
            continue
        if v.result != VERIFIED_OFFICIAL:
            return VersionEvidence.fail("verification result is not verified_official")
        if not v.evidence_hash:
            return VersionEvidence.fail("empty evidence_hash")
        if v.evidence_hash != version.content_hash:
            return VersionEvidence.fail("evidence_hash does not match version content_hash")
        if not v.evidence_url:
            return VersionEvidence.fail("empty evidence_url")
        if not _official_domain(v.evidence_url):
            return VersionEvidence.fail("evidence_url is not allowlisted official domain")
        return VersionEvidence.success(version_id, v.evidence_url, v.evidence_hash)
    return VersionEvidence.fail("no official_match verification found for this version")


async def resolve_version_verification_status(
    session: AsyncSession,
    record_id: str,
    version_id: str | None,
    record_status: str,
) -> str:
    """Authoritative user-facing trust status for a specific version of a source.

    - Returns the effective status for [version_id] by checking version-scoped
      evidence. [record_status] is the fallback only when the version has no
      version-specific evidence.
    - This is the SINGLE function that computes what the API, SourceUsage cards
      and index eligibility should display. Different callers must not compute
      trust independently.
    """
    if not version_id:
        # No version → fall through to record-level with effective logic.
        if record_status == VERIFIED_OFFICIAL:
            return NEEDS_REVIEW  # no current version, cannot be verified_official
        return record_status
    evidence = await get_version_official_evidence(session, record_id, version_id)
    if evidence.valid:
        return VERIFIED_OFFICIAL
    # No official evidence — check the record status with effective logic.
    if record_status == VERIFIED_OFFICIAL:
        return NEEDS_REVIEW
    return record_status


def effective_verification_status(
    record_verification_status: str,
    current_version_id: str | None,
    version_has_official_evidence: bool,
) -> str:
    """User-facing / search-index trust status for the current source.

    verified_official at the record level is a ceiling, not a guarantee.
    The effective trust requires the current version to have its own
    valid official_fetch_match evidence.
    """
    if record_verification_status == VERIFIED_OFFICIAL:
        if not current_version_id:
            return NEEDS_REVIEW
        if not version_has_official_evidence:
            return NEEDS_REVIEW
        return VERIFIED_OFFICIAL
    return record_verification_status


# ── Editor-submitted content (manual/editor path) ─────────────────────────
async def ingest_editor_candidate(
    session: AsyncSession,
    *,
    metadata: dict,
    raw_text: str,
    official_url: str = "",
) -> IngestResult:
    """Ingest a source from editor-submitted raw text.

    Trust starts at needs_review — never verified_official.
    The caller's raw_text is the canonical content for this ingestion.
    """
    return await _ingest(
        session,
        metadata=metadata,
        trusted_text=para.normalize_text(raw_text),
        raw_document_hash=None,
        extraction_method=None,
        official_url=official_url,
        retrieval_method="editor_submit",
        # No fetch_result — trusted text comes from the raw_text parameter.
        fetch_result=None,
    )


# ── Official fetch path ───────────────────────────────────────────────────
async def ingest_official_fetch(
    session: AsyncSession,
    *,
    metadata: dict,
    fetch_result: FetchResult,
    raw_document_hash: str | None = None,
    extraction_method: str | None = None,
    extraction_version: str | None = None,
    expected_official_domains: tuple[str, ...] | None = None,
) -> IngestResult:
    """Ingest via server-side secure official fetch.

    - fetch_result.content is the sole canonical content.
    - When [raw_document_hash] is passed (P2.6C extraction), it is persisted
      as the raw-fetch provenance hash. [extraction_version] becomes the
      parser_version on the SourceVersion row so the extraction provenance
      chain is verifiable.
    """
    # Validate fetch_result integrity.
    if not fetch_result:
        raise ValueError("fetch_result required for official_fetch")
    if fetch_result.status_code < 200 or fetch_result.status_code >= 300:
        raise ValueError("fetch_result status must be 2xx")
    content = fetch_result.content
    if not content:
        raise ValueError("fetch_result content is empty")
    final_url = fetch_result.final_url
    if not final_url:
        raise ValueError("fetch_result final_url is empty")
    if not _official_domain(final_url, expected_official_domains):
        raise ValueError("fetch_result final_url is not allowlisted official domain")
    content_type = (fetch_result.content_type or "").split(";")[0].strip().lower()
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError(f"unsupported content_type: {content_type}")

    # Validate extraction provenance (P2.6C).
    _validate_extraction_provenance(raw_document_hash, extraction_method, extraction_version)

    # Compute canonical content from the fetched bytes ONLY.
    text = _decode_fetched_bytes(content)
    trusted = para.normalize_text(text)

    return await _ingest(
        session,
        metadata=metadata,
        trusted_text=trusted,
        raw_document_hash=raw_document_hash,
        extraction_method=extraction_method,
        official_url=final_url,
        retrieval_method="official_fetch",
        fetch_result=fetch_result,
        extraction_version=extraction_version or PARSER_VERSION,
    )


def _decode_fetched_bytes(content: bytes) -> str:
    """Decode fetched bytes with multi-encoding Turkish-safe fallback."""
    for encoding in ("utf-8", "cp1254", "iso-8859-9", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("latin-1")  # fallback, never lose bytes


# ── Shared ingestion engine ───────────────────────────────────────────────
async def _ingest(
    session: AsyncSession,
    *,
    metadata: dict,
    trusted_text: str,
    raw_document_hash: str | None,
    extraction_method: str | None,
    official_url: str,
    retrieval_method: str,
    fetch_result: FetchResult | None,
    extraction_version: str = PARSER_VERSION,
) -> IngestResult:
    """Core ingestion engine. [trusted_text] is the canonical content."""
    source_type = normalize_source_type(metadata.get("source_type", ""))
    canonical_key = build_canonical_key({**metadata, "source_type": source_type})
    content_hash = para.content_hash(trusted_text)

    is_official_fetch = (
        retrieval_method == "official_fetch"
        and fetch_result is not None
        and bool(official_url)
        and _official_domain(official_url)
    )
    incoming_provider_extracted = all((
        raw_document_hash is not None,
        extraction_method is not None,
        extraction_version is not None,
    ))

    record = await SourceRecordRepository.get_by_canonical_key(session, canonical_key)

    if record is None:
        return await _create_new_record(
            session, metadata, source_type, canonical_key,
            trusted_text, content_hash, official_url,
            retrieval_method, raw_document_hash, extraction_method, is_official_fetch,
            extraction_version=extraction_version,
        )
    return await _ingest_into_existing(
        session, record, metadata, source_type, canonical_key,
        trusted_text, content_hash, official_url,
        retrieval_method, raw_document_hash, extraction_method, is_official_fetch,
        incoming_provider_extracted=incoming_provider_extracted,
        extraction_version=extraction_version,
    )


async def _create_new_record(
    session, metadata, source_type, canonical_key,
    trusted_text, content_hash, official_url,
    retrieval_method, raw_document_hash, extraction_method, is_official_fetch,
    extraction_version: str = PARSER_VERSION,
):
    record = await SourceRecordRepository.create(
        session,
        source_type=source_type, canonical_key=canonical_key,
        title=metadata.get("title", ""), verification_status=NEEDS_REVIEW,
        issuing_authority=metadata.get("issuing_authority", ""),
        court=metadata.get("court", ""), chamber=metadata.get("chamber", ""),
        case_number=metadata.get("case_number", ""),
        decision_number=metadata.get("decision_number", ""),
        decision_date=metadata.get("decision_date", ""),
        publication_date=metadata.get("publication_date", ""),
        effective_date=metadata.get("effective_date", ""),
        repeal_date=metadata.get("repeal_date", ""),
        official_url=official_url,
    )
    version = await _create_version_with_paragraphs(
        session, record, source_type, trusted_text, content_hash,
        retrieval_method, raw_document_hash, metadata,
        extraction_method=extraction_method,
        parser_version=extraction_version,
    )
    await SourceRecordRepository.set_current_version(session, record, version.id)
    await SourceRecordRepository.mark_checked(session, record, successful=True)
    status = NEEDS_REVIEW
    if is_official_fetch:
        await _produce_official_verification(
            session, record.id, version.id, content_hash, official_url
        )
        await SourceRecordRepository.transition_status(session, record, VERIFIED_OFFICIAL)
        status = VERIFIED_OFFICIAL
    return IngestResult(record.id, version.id, canonical_key, status, OUTCOME_CREATED)


async def _ingest_into_existing(
    session, record, metadata, source_type, canonical_key,
    trusted_text, content_hash, official_url,
    retrieval_method, raw_document_hash, extraction_method, is_official_fetch,
    incoming_provider_extracted: bool,
    extraction_version: str = PARSER_VERSION,
):
    await SourceRecordRepository.mark_checked(session, record, successful=True)
    existing = await SourceVersionRepository.get_by_hash(session, record.id, content_hash)
    if existing is not None:
        # Same canonical key + same content_hash → idempotent. However, if this
        # is an official_fetch and the existing version lacks official_fetch_match
        # evidence, produce the evidence for it (never create a duplicate version).
        if is_official_fetch:
            evidence = await get_version_official_evidence(session, record.id, existing.id)
            if not evidence.valid:
                if incoming_provider_extracted:
                    provenance = version_extraction_provenance_state(existing)
                    if not (provenance.present and provenance.valid):
                        # Immutable legacy/suspect versions cannot be retroactively
                        # upgraded with provenance from a later extracted fetch.
                        return IngestResult(
                            record.id,
                            existing.id,
                            canonical_key,
                            record.verification_status,
                            OUTCOME_DUPLICATE,
                        )
                await _produce_official_verification(
                    session, record.id, existing.id, content_hash, official_url,
                )
                # If this version is the current version, promote trust.
                if (record.current_version_id == existing.id
                        and can_transition(record.verification_status, VERIFIED_OFFICIAL)):
                    await SourceRecordRepository.transition_status(session, record, VERIFIED_OFFICIAL)
            # outcome is always duplicate_verified when official_fetch matches
            # an existing version (evidence was already there or just produced).
            return IngestResult(record.id, existing.id, canonical_key, record.verification_status, OUTCOME_DUPLICATE_VERIFIED)
        return IngestResult(record.id, existing.id, canonical_key, record.verification_status, OUTCOME_DUPLICATE)

    if _metadata_conflict(record, metadata):
        if can_transition(record.verification_status, CONFLICTING):
            await SourceRecordRepository.transition_status(session, record, CONFLICTING)
        await SourceVerificationRepository.create(
            session, source_record_id=record.id,
            verification_method="metadata_conflict", verifier_type="automated",
            result=CONFLICTING, notes="Metadata conflict on ingestion.",
        )
        return IngestResult(record.id, record.current_version_id or "", canonical_key, record.verification_status, OUTCOME_CONFLICT)

    version = await _create_version_with_paragraphs(
        session, record, source_type, trusted_text, content_hash,
        retrieval_method, raw_document_hash, metadata,
        extraction_method=extraction_method,
        supersedes_version_id=record.current_version_id,
        parser_version=extraction_version,
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
        if record.verification_status == VERIFIED_OFFICIAL and can_transition(record.verification_status, NEEDS_REVIEW):
            await SourceRecordRepository.transition_status(session, record, NEEDS_REVIEW)
        new_status = record.verification_status

    return IngestResult(record.id, version.id, canonical_key, new_status, OUTCOME_NEW_VERSION)


async def _produce_official_verification(session, record_id, version_id, content_hash, official_url):
    await SourceVerificationRepository.create(
        session,
        source_record_id=record_id,
        source_version_id=version_id,
        verification_method=OFFICIAL_FETCH_METHOD,
        verifier_type=OFFICIAL_VERIFIER_TYPE,
        result=VERIFIED_OFFICIAL,
        evidence_url=official_url,
        evidence_hash=content_hash,
    )


async def _create_version_with_paragraphs(
    session, record, source_type, normalized, content_hash,
    retrieval_method, raw_document_hash, metadata,
    extraction_method: str | None = None,
    supersedes_version_id=None,
    parser_version: str = PARSER_VERSION,
):
    mjson: dict = {"source_type": source_type}
    if extraction_method is not None:
        mjson["extraction_method"] = extraction_method
    if source_type in para.ARTICLE_BEARING_SOURCE_TYPES:
        mjson["paragraph_locator_version"] = para.ARTICLE_LOCATOR_VERSION

    split_paragraphs = para.split_paragraphs(source_type, normalized)

    version = await SourceVersionRepository.create(
        session,
        source_record_id=record.id,
        content_hash=content_hash,
        normalized_text=normalized,
        retrieval_method=retrieval_method,
        parser_version=parser_version,
        raw_document_hash=raw_document_hash,
        supersedes_version_id=supersedes_version_id,
        valid_from=metadata.get("effective_date", "") or metadata.get("valid_from", ""),
        valid_to=metadata.get("valid_to", ""),
        metadata_json=mjson,
    )
    for sp in split_paragraphs:
        await SourceParagraphRepository.create(
            session,
            source_version_id=version.id,
            paragraph_index=sp.paragraph_index,
            text=sp.text,
            text_hash=para.text_hash(sp.text),
            heading_path=sp.heading_path,
            page=sp.page,
            article_number=sp.article_number,
            locator_json=sp.locator_json,
        )
    return version
