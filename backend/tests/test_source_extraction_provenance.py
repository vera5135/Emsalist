"""P2.6C — Extraction provenance correctness and regression tests (PostgreSQL)."""
from __future__ import annotations

import hashlib

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.db.models import (
    SourceParagraph,
    SourceRecord,
    SourceRelationship,
    SourceUsage,
    SourceVerification,
    SourceVersion,
)
from app.db.session import get_sessionmaker
from app.services.source_extraction import (
    EXTRACTION_METHOD_PROVIDER_HTML,
    EXTRACTION_METHOD_RAW_TEXT,
    extract_content_from_fetch,
    make_extracted_fetch_result,
)
from app.services.source_fetcher import FetchResult
from app.services.source_ingestion_service import (
    PARSER_VERSION,
    VERIFIED_OFFICIAL,
    get_version_official_evidence,
    ingest_official_fetch,
    resolve_version_verification_status,
)

EXTRACTION_VERSION = "p2.6c-extract-1"

OFFICIAL_URL = "https://karararama.yargitay.gov.tr/karar/999"
OFFICIAL_META = {
    "source_type": "supreme_court_decision",
    "title": "Yargitay 13. HD E.2020/999 K.2021/888",
    "court": "Yargitay", "chamber": "13. HD",
    "case_number": "2020/999", "decision_number": "2021/888",
    "decision_date": "2021-06-12",
}


@pytest_asyncio.fixture(autouse=True)
async def clean_sources():
    maker = get_sessionmaker()
    async def _clean(session):
        await session.execute(delete(SourceUsage))
        await session.execute(delete(SourceParagraph))
        await session.execute(delete(SourceVerification))
        await session.execute(delete(SourceRelationship))
        await session.execute(delete(SourceVersion))
        await session.execute(delete(SourceRecord))
    async with maker() as session:
        await _clean(session)
        await session.commit()
    yield
    async with maker() as session:
        await _clean(session)
        await session.commit()


def _html_fixture(body: str = "Madde 1\nHukuki metin.") -> bytes:
    nav = '<nav><a href="/">Ana Sayfa</a></nav>'
    cookie = '<div class="cookie">Bu site çerez kullanır.</div>'
    return f"<html><head><title>Test</title></head><body>{nav}<article>{body}</article><footer>{cookie}</footer></body></html>".encode("utf-8")


async def _provider_ingest(
    session,
    body: str = "Madde 1\nHukuki metin.",
    raw_html: bytes | None = None,
    **overrides,
) -> dict:
    raw = raw_html if raw_html is not None else _html_fixture(body)
    fetch_result = FetchResult(
        final_url=OFFICIAL_URL,
        status_code=200,
        content=raw,
        content_type="text/html",
    )
    extracted = extract_content_from_fetch(
        fetch_result,
        source_type="supreme_court_decision",
        parser_version=EXTRACTION_VERSION,
    )
    extracted_fr = make_extracted_fetch_result(fetch_result, extracted)
    meta = {**OFFICIAL_META, **overrides}
    result = await ingest_official_fetch(
        session,
        metadata=meta,
        fetch_result=extracted_fr,
        raw_document_hash=extracted.raw_document_hash,
        extraction_method=extracted.extraction_method,
        extraction_version=extracted.parser_version,
    )
    await session.commit()
    return {
        "result": result,
        "raw_document_hash": extracted.raw_document_hash,
        "extracted_hash": extracted.extracted_hash,
        "raw_html": raw,
    }


# ── 1-2: HTML extraction preserves legal body, excludes chrome ──────────────
@pytest.mark.asyncio
async def test_html_extraction_preserves_legal_body():
    sm = get_sessionmaker()
    async with sm() as db:
        out = await _provider_ingest(db, body="Madde 1\nHukuki metin.")

    async with sm() as db:
        from app.db.source_repository import SourceVersionRepository
        version = await SourceVersionRepository.get(db, out["result"].source_version_id)
    assert version is not None
    assert "Madde 1" in version.normalized_text
    assert "Hukuki metin" in version.normalized_text


@pytest.mark.asyncio
async def test_html_extraction_excludes_chrome():
    sm = get_sessionmaker()
    async with sm() as db:
        out = await _provider_ingest(db, body="Legal text only.")

    async with sm() as db:
        from app.db.source_repository import SourceVersionRepository
        version = await SourceVersionRepository.get(db, out["result"].source_version_id)
    assert "Ana Sayfa" not in version.normalized_text
    assert "cookie" not in version.normalized_text.lower()


# ── 5-6: raw_document_hash is non-empty and equals sha256(original bytes) ───
@pytest.mark.asyncio
async def test_initial_raw_document_hash_nonempty():
    sm = get_sessionmaker()
    async with sm() as db:
        out = await _provider_ingest(db)

    async with sm() as db:
        from app.db.source_repository import SourceVersionRepository
        version = await SourceVersionRepository.get(db, out["result"].source_version_id)
    assert version.raw_document_hash
    assert len(version.raw_document_hash) == 64


@pytest.mark.asyncio
async def test_raw_document_hash_equals_sha256_original_bytes():
    raw_html = _html_fixture("Unique body text.")
    sm = get_sessionmaker()
    async with sm() as db:
        out = await _provider_ingest(db, raw_html=raw_html, body="Unique body text.")

    async with sm() as db:
        from app.db.source_repository import SourceVersionRepository
        version = await SourceVersionRepository.get(db, out["result"].source_version_id)
    expected = hashlib.sha256(raw_html).hexdigest()
    assert version.raw_document_hash == expected


# ── 7-8: content_hash is on normalized text, not raw HTML ───────────────────
@pytest.mark.asyncio
async def test_content_hash_matches_extracted_text():
    sm = get_sessionmaker()
    async with sm() as db:
        out = await _provider_ingest(db, body="Content hash test.")

    async with sm() as db:
        from app.db.source_repository import SourceVersionRepository
        version = await SourceVersionRepository.get(db, out["result"].source_version_id)
    assert version.content_hash == out["extracted_hash"]


@pytest.mark.asyncio
async def test_content_hash_not_equal_raw_document_hash():
    raw_html = _html_fixture("Distinct hash test.")
    sm = get_sessionmaker()
    async with sm() as db:
        out = await _provider_ingest(db, raw_html=raw_html, body="Distinct hash test.")

    async with sm() as db:
        from app.db.source_repository import SourceVersionRepository
        version = await SourceVersionRepository.get(db, out["result"].source_version_id)
    assert version.content_hash != version.raw_document_hash


# ── 9: initial CREATED SourceVersion.parser_version is extraction-aware ─────
@pytest.mark.asyncio
async def test_created_version_parser_version_is_extraction_aware():
    sm = get_sessionmaker()
    async with sm() as db:
        out = await _provider_ingest(db)

    async with sm() as db:
        from app.db.source_repository import SourceVersionRepository
        version = await SourceVersionRepository.get(db, out["result"].source_version_id)
    assert version.parser_version == EXTRACTION_VERSION
    assert version.parser_version != PARSER_VERSION


# ── 10: metadata_json contains controlled extraction_method ─────────────────
@pytest.mark.asyncio
async def test_metadata_json_contains_extraction_method():
    sm = get_sessionmaker()
    async with sm() as db:
        out = await _provider_ingest(db)

    async with sm() as db:
        from app.db.source_repository import SourceVersionRepository
        version = await SourceVersionRepository.get(db, out["result"].source_version_id)
    assert version.metadata_json.get("source_type") == "supreme_court_decision"
    assert version.metadata_json.get("extraction_method") == EXTRACTION_METHOD_PROVIDER_HTML


# ── 11-12: evidence_hash == content_hash, evidence_hash != raw_document_hash ─
@pytest.mark.asyncio
async def test_evidence_hash_equals_content_hash():
    sm = get_sessionmaker()
    async with sm() as db:
        out = await _provider_ingest(db)

    async with sm() as db:
        from app.db.source_repository import SourceVersionRepository, SourceVerificationRepository
        version = await SourceVersionRepository.get(db, out["result"].source_version_id)
        verifications = await SourceVerificationRepository.list_for_record(db, out["result"].source_record_id)
    official_ev = [v for v in verifications if v.verifier_type == "official_match"]
    assert official_ev
    assert official_ev[0].evidence_hash == version.content_hash


@pytest.mark.asyncio
async def test_evidence_hash_not_equal_raw_document_hash():
    sm = get_sessionmaker()
    async with sm() as db:
        out = await _provider_ingest(db)

    async with sm() as db:
        from app.db.source_repository import SourceVersionRepository, SourceVerificationRepository
        version = await SourceVersionRepository.get(db, out["result"].source_version_id)
        verifications = await SourceVerificationRepository.list_for_record(db, out["result"].source_record_id)
    official_ev = [v for v in verifications if v.verifier_type == "official_match"]
    assert official_ev
    assert official_ev[0].evidence_hash != version.raw_document_hash


# ── 13-15: nav-only change → no new version ─────────────────────────────────
@pytest.mark.asyncio
async def test_nav_only_change_no_new_version():
    sm = get_sessionmaker()
    async with sm() as db:
        out1 = await _provider_ingest(db, body="Stable legal body.")
        rec_id = out1["result"].source_record_id

    # Same legal body, different chrome around it.
    nav2 = _html_fixture("Stable legal body.")
    async with sm() as db:
        out2 = await _provider_ingest(db, raw_html=nav2, body="Stable legal body.")

    assert out2["result"].source_record_id == rec_id
    assert out2["result"].outcome in ("duplicate", "duplicate_verified")

    async with sm() as db:
        from app.db.source_repository import SourceVersionRepository
        versions = await SourceVersionRepository.list_for_record(db, rec_id)
    assert len(versions) == 1


# ── 16-18: changed legal body → new version, parser_version is extraction-aware ─
@pytest.mark.asyncio
async def test_changed_body_new_version_with_extraction_parser():
    sm = get_sessionmaker()
    async with sm() as db:
        out1 = await _provider_ingest(db, body="Original text.")
        rec_id = out1["result"].source_record_id
        v1_id = out1["result"].source_version_id

    async with sm() as db:
        out2 = await _provider_ingest(db, body="Changed legal body text.")
        v2_id = out2["result"].source_version_id

    assert out2["result"].outcome == "new_version"
    assert v2_id != v1_id

    async with sm() as db:
        from app.db.source_repository import SourceVersionRepository
        versions = await SourceVersionRepository.list_for_record(db, rec_id)
    assert len(versions) == 2

    async with sm() as db:
        from app.db.source_repository import SourceVersionRepository
        v2 = await SourceVersionRepository.get(db, v2_id)
    assert v2.parser_version == EXTRACTION_VERSION
    assert v2.parser_version != PARSER_VERSION


# ── 18: old version preserved ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_old_version_preserved_after_new_version():
    sm = get_sessionmaker()
    async with sm() as db:
        out1 = await _provider_ingest(db, body="V1 content.")
        v1_id = out1["result"].source_version_id

    async with sm() as db:
        out2 = await _provider_ingest(db, body="V2 content.")

    from app.db.source_repository import SourceVersionRepository
    async with sm() as db:
        v1 = await SourceVersionRepository.get(db, v1_id)
    assert v1 is not None
    assert v1.normalized_text is not None
    assert "V1 content" in v1.normalized_text


# ── 19-24: partial / invalid provenance rejection ───────────────────────────
@pytest.mark.asyncio
async def test_partial_provenance_raw_hash_only_rejected():
    sm = get_sessionmaker()
    async with sm() as db:
        fr = FetchResult(
            final_url=OFFICIAL_URL, status_code=200,
            content=_html_fixture("Body."), content_type="text/html",
        )
        with pytest.raises(ValueError, match="all-or-none"):
            await ingest_official_fetch(
                db, metadata=OFFICIAL_META, fetch_result=fr,
                raw_document_hash="a" * 64,
                extraction_method=None,
                extraction_version=None,
            )


@pytest.mark.asyncio
async def test_partial_provenance_extraction_method_only_rejected():
    sm = get_sessionmaker()
    async with sm() as db:
        fr = FetchResult(
            final_url=OFFICIAL_URL, status_code=200,
            content=_html_fixture("Body."), content_type="text/html",
        )
        with pytest.raises(ValueError, match="all-or-none"):
            await ingest_official_fetch(
                db, metadata=OFFICIAL_META, fetch_result=fr,
                raw_document_hash=None,
                extraction_method=EXTRACTION_METHOD_PROVIDER_HTML,
                extraction_version=None,
            )


@pytest.mark.asyncio
async def test_partial_provenance_extraction_version_only_rejected():
    sm = get_sessionmaker()
    async with sm() as db:
        fr = FetchResult(
            final_url=OFFICIAL_URL, status_code=200,
            content=_html_fixture("Body."), content_type="text/html",
        )
        with pytest.raises(ValueError, match="all-or-none"):
            await ingest_official_fetch(
                db, metadata=OFFICIAL_META, fetch_result=fr,
                raw_document_hash=None,
                extraction_method=None,
                extraction_version=EXTRACTION_VERSION,
            )


@pytest.mark.asyncio
async def test_malformed_raw_hash_rejected():
    sm = get_sessionmaker()
    async with sm() as db:
        fr = FetchResult(
            final_url=OFFICIAL_URL, status_code=200,
            content=_html_fixture("Body."), content_type="text/html",
        )
        with pytest.raises(ValueError, match="raw_document_hash"):
            await ingest_official_fetch(
                db, metadata=OFFICIAL_META, fetch_result=fr,
                raw_document_hash="short",
                extraction_method=EXTRACTION_METHOD_PROVIDER_HTML,
                extraction_version=EXTRACTION_VERSION,
            )


@pytest.mark.asyncio
async def test_unknown_extraction_method_rejected():
    sm = get_sessionmaker()
    async with sm() as db:
        fr = FetchResult(
            final_url=OFFICIAL_URL, status_code=200,
            content=_html_fixture("Body."), content_type="text/html",
        )
        with pytest.raises(ValueError, match="extraction_method"):
            await ingest_official_fetch(
                db, metadata=OFFICIAL_META, fetch_result=fr,
                raw_document_hash=hashlib.sha256(_html_fixture("Body.")).hexdigest(),
                extraction_method="bogus_unknown_method",
                extraction_version=EXTRACTION_VERSION,
            )


@pytest.mark.asyncio
async def test_invalid_extraction_version_rejected():
    sm = get_sessionmaker()
    async with sm() as db:
        fr = FetchResult(
            final_url=OFFICIAL_URL, status_code=200,
            content=_html_fixture("Body."), content_type="text/html",
        )
        with pytest.raises(ValueError, match="extraction_version"):
            await ingest_official_fetch(
                db, metadata=OFFICIAL_META, fetch_result=fr,
                raw_document_hash=hashlib.sha256(_html_fixture("Body.")).hexdigest(),
                extraction_method=EXTRACTION_METHOD_PROVIDER_HTML,
                extraction_version="",
            )


# ── 25-27: provider-extracted version trust provenance validation ───────────
@pytest.mark.asyncio
async def test_tampered_raw_hash_not_verified_official():
    sm = get_sessionmaker()
    async with sm() as db:
        out = await _provider_ingest(db)
        rec_id = out["result"].source_record_id
        vid = out["result"].source_version_id

    # Tamper: set raw_document_hash to invalid value in DB (non-hex chars).
    async with sm() as db:
        from app.db.source_repository import SourceVersionRepository
        version = await SourceVersionRepository.get(db, vid)
        version.raw_document_hash = "Z" * 64
        await db.commit()

    async with sm() as db:
        ev = await get_version_official_evidence(db, rec_id, vid)
    assert not ev.valid
    assert "raw_document_hash" in ev.failure_reason.lower()


@pytest.mark.asyncio
async def test_missing_extraction_method_not_verified_official():
    sm = get_sessionmaker()
    async with sm() as db:
        out = await _provider_ingest(db)
        rec_id = out["result"].source_record_id
        vid = out["result"].source_version_id

    # Tamper: remove extraction_method from metadata_json.
    async with sm() as db:
        from app.db.source_repository import SourceVersionRepository
        version = await SourceVersionRepository.get(db, vid)
        mj = dict(version.metadata_json or {})
        mj.pop("extraction_method", None)
        version.metadata_json = mj
        await db.commit()

    async with sm() as db:
        ev = await get_version_official_evidence(db, rec_id, vid)
    assert not ev.valid
    assert "extraction_method" in ev.failure_reason.lower()


@pytest.mark.asyncio
async def test_invalid_parser_version_not_verified_official():
    sm = get_sessionmaker()
    async with sm() as db:
        out = await _provider_ingest(db)
        rec_id = out["result"].source_record_id
        vid = out["result"].source_version_id

    # Tamper: set parser_version to default P2.6 parser (not extraction-aware).
    async with sm() as db:
        from app.db.source_repository import SourceVersionRepository
        version = await SourceVersionRepository.get(db, vid)
        version.parser_version = PARSER_VERSION
        await db.commit()

    async with sm() as db:
        ev = await get_version_official_evidence(db, rec_id, vid)
    assert not ev.valid
    assert "parser_version" in ev.failure_reason.lower()


# ── 28-29: legacy direct P2.6 official fetch remains accepted ───────────────
@pytest.mark.asyncio
async def test_legacy_direct_p2_6_ingest_still_accepted():
    sm = get_sessionmaker()
    async with sm() as db:
        result = await ingest_official_fetch(
            db,
            metadata={
                "source_type": "supreme_court_decision",
                "title": "Legacy Decision",
                "court": "Yargitay", "chamber": "13. HD",
                "case_number": "2020/555", "decision_number": "2021/666",
                "decision_date": "2021-06-12",
            },
            fetch_result=FetchResult(
                final_url=OFFICIAL_URL,
                status_code=200, content=b"LEGACY DIRECT FETCH CONTENT",
                content_type="text/html",
            ),
        )
        await db.commit()
    assert result.outcome == "created"
    assert result.verification_status == VERIFIED_OFFICIAL


@pytest.mark.asyncio
async def test_legacy_direct_p2_6_trust_remains_verified():
    sm = get_sessionmaker()
    async with sm() as db:
        result = await ingest_official_fetch(
            db,
            metadata={
                "source_type": "supreme_court_decision",
                "title": "Legacy Trust Test",
                "court": "Yargitay", "chamber": "13. HD",
                "case_number": "2020/777", "decision_number": "2021/888",
                "decision_date": "2021-06-12",
            },
            fetch_result=FetchResult(
                final_url=OFFICIAL_URL,
                status_code=200, content=b"LEGACY TRUST DIRECT CONTENT",
                content_type="text/html",
            ),
        )
        rec_id = result.source_record_id
        vid = result.source_version_id
        await db.commit()

    async with sm() as db:
        status = await resolve_version_verification_status(db, rec_id, vid, result.verification_status)
    assert status == VERIFIED_OFFICIAL


# ── Provider-extracted version: tampered raw_document_hash removed → not verified ─
@pytest.mark.asyncio
async def test_raw_hash_removed_not_verified_official():
    sm = get_sessionmaker()
    async with sm() as db:
        out = await _provider_ingest(db)
        rec_id = out["result"].source_record_id
        vid = out["result"].source_version_id

    async with sm() as db:
        from app.db.source_repository import SourceVersionRepository
        version = await SourceVersionRepository.get(db, vid)
        version.raw_document_hash = None
        await db.commit()

    async with sm() as db:
        ev = await get_version_official_evidence(db, rec_id, vid)
    assert not ev.valid
    assert "raw_document_hash" in ev.failure_reason.lower()


# ── Provider-extracted version: unknown extraction_method → not verified ────
@pytest.mark.asyncio
async def test_unknown_extraction_method_in_metadata_not_verified():
    sm = get_sessionmaker()
    async with sm() as db:
        out = await _provider_ingest(db)
        rec_id = out["result"].source_record_id
        vid = out["result"].source_version_id

    async with sm() as db:
        from app.db.source_repository import SourceVersionRepository
        version = await SourceVersionRepository.get(db, vid)
        mj = dict(version.metadata_json or {})
        mj["extraction_method"] = "bogus_method"
        version.metadata_json = mj
        await db.commit()

    async with sm() as db:
        ev = await get_version_official_evidence(db, rec_id, vid)
    assert not ev.valid
    assert "extraction_method" in ev.failure_reason.lower()


# ── Provider-extracted version: empty parser_version → not verified ─────────
@pytest.mark.asyncio
async def test_empty_parser_version_not_verified_official():
    sm = get_sessionmaker()
    async with sm() as db:
        out = await _provider_ingest(db)
        rec_id = out["result"].source_record_id
        vid = out["result"].source_version_id

    async with sm() as db:
        from app.db.source_repository import SourceVersionRepository
        version = await SourceVersionRepository.get(db, vid)
        version.parser_version = ""
        await db.commit()

    async with sm() as db:
        ev = await get_version_official_evidence(db, rec_id, vid)
    assert not ev.valid
    assert "parser_version" in ev.failure_reason.lower()


# ── raw_text extraction method validation ───────────────────────────────────
@pytest.mark.asyncio
async def test_raw_text_extraction_method_accepted():
    sm = get_sessionmaker()
    async with sm() as db:
        plain = b"Plain text legal body content."
        raw_hash = hashlib.sha256(plain).hexdigest()
        result = await ingest_official_fetch(
            db, metadata=OFFICIAL_META,
            fetch_result=FetchResult(
                final_url=OFFICIAL_URL, status_code=200,
                content=plain, content_type="text/plain",
            ),
            raw_document_hash=raw_hash,
            extraction_method=EXTRACTION_METHOD_RAW_TEXT,
            extraction_version="p2.6c-extract-1",
        )
        await db.commit()

    async with sm() as db:
        from app.db.source_repository import SourceVersionRepository
        version = await SourceVersionRepository.get(db, result.source_version_id)
    assert version.metadata_json.get("extraction_method") == EXTRACTION_METHOD_RAW_TEXT
    assert result.verification_status == VERIFIED_OFFICIAL
