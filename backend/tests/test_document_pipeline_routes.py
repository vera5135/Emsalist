"""P2.5 — Document pipeline route integration tests.

Runs against the real DB layer in local auth mode (ctx = local-user / local),
with an isolated on-disk blob store per test process. Uses real PDF (pymupdf),
DOCX (zip) and TXT fixtures; UDF is exercised with both a readable-XML zip and
a binary blob to verify honest failure behavior.
"""
from __future__ import annotations

import os
import tempfile
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
import pytest_asyncio

# Isolate the document blob store BEFORE app import uses it.
_BLOB_DIR = tempfile.TemporaryDirectory(prefix="emsalist-p25-blobs-")
os.environ["EMSALIST_DOCUMENT_STORE_DIR"] = _BLOB_DIR.name

import fitz  # noqa: E402  (pymupdf, dev/test dependency)
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.db.models import (  # noqa: E402
    AuditEvent,
    Case,
    CaseFact,
    CaseMember,
    Contradiction,
    Document,
    DocumentExtraction,
    DocumentPage,
    Tenant,
    User,
)
from app.db.session import get_sessionmaker  # noqa: E402
from app.main import app  # noqa: E402

OTHER_TENANT = "tenant-doc-other"
OTHER_USER = "user-doc-other"


def make_pdf(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


def make_docx(paragraphs: list[str]) -> bytes:
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(
        f'<w:p><w:r><w:t>{p}</w:t></w:r></w:p>' for p in paragraphs
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>'
    )
    package = BytesIO()
    with ZipFile(package, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        archive.writestr("word/document.xml", document_xml)
    return package.getvalue()


def make_udf_zip(text: str) -> bytes:
    package = BytesIO()
    with ZipFile(package, "w", ZIP_DEFLATED) as archive:
        archive.writestr("content.xml", f"<root>{text}</root>")
    return package.getvalue()


@pytest_asyncio.fixture(autouse=True)
async def db_setup():
    maker = get_sessionmaker()
    tenants = ["local", OTHER_TENANT]
    async with maker() as session:
        for model in (DocumentExtraction, DocumentPage, Document, CaseFact, Contradiction):
            await session.execute(delete(model).where(model.tenant_id.in_(tenants)))
        await session.execute(delete(CaseMember).where(CaseMember.tenant_id.in_(tenants)))
        await session.execute(delete(Case).where(Case.tenant_id.in_(tenants)))
        await session.execute(delete(AuditEvent).where(AuditEvent.tenant_id.in_(tenants)))
        await session.execute(delete(User).where(User.id.in_(["local-user", OTHER_USER])))
        await session.execute(delete(Tenant).where(Tenant.id.in_(tenants)))
        await session.flush()
        session.add(Tenant(id="local", name="Local", slug="local-doc", status="active"))
        session.add(Tenant(id=OTHER_TENANT, name="Other", slug="other-doc", status="active"))
        session.add(User(id="local-user", tenant_id="local", email_normalized="doc@local", display_name="L", status="active", role="lawyer"))
        session.add(User(id=OTHER_USER, tenant_id=OTHER_TENANT, email_normalized="doc@other", display_name="O", status="active", role="lawyer"))
        await session.commit()
    yield
    async with maker() as session:
        for model in (DocumentExtraction, DocumentPage, Document, CaseFact, Contradiction):
            await session.execute(delete(model).where(model.tenant_id.in_(tenants)))
        await session.execute(delete(CaseMember).where(CaseMember.tenant_id.in_(tenants)))
        await session.execute(delete(Case).where(Case.tenant_id.in_(tenants)))
        await session.execute(delete(AuditEvent).where(AuditEvent.tenant_id.in_(tenants)))
        await session.execute(delete(User).where(User.id.in_(["local-user", OTHER_USER])))
        await session.execute(delete(Tenant).where(Tenant.id.in_(tenants)))
        await session.commit()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _make_case(client: AsyncClient, title: str = "Doc Case") -> str:
    r = await client.post("/api/v1/cases", json={"title": title})
    assert r.status_code == 201
    return r.json()["id"]


async def _seed_foreign_case(case_id: str = "foreign-doc-case") -> str:
    maker = get_sessionmaker()
    async with maker() as session:
        session.add(Case(
            id=case_id, tenant_id=OTHER_TENANT, owner_user_id=OTHER_USER,
            title="Foreign", legal_topic="x", status="active", version=1,
        ))
        await session.commit()
    return case_id


def _upload(client, case_id, name, content, mime, dtype=None):
    files = {"file": (name, content, mime)}
    data = {"document_type": dtype} if dtype else None
    return client.post(f"/api/v1/cases/{case_id}/documents", files=files, data=data)


# ---------------------------------------------------------------------------
# Upload + formats
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_upload_txt_extracts_and_awaits_confirmation(client: AsyncClient):
    case_id = await _make_case(client)
    text = "Satış bedeli: 850.000 TL\nSatış tarihi: 12.06.2026\nPlaka: 34 ABC 123"
    r = await _upload(client, case_id, "sozlesme.txt", text.encode(), "text/plain")
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["extension"] == ".txt"
    assert data["support_level"] == "fully_supported"
    assert data["extracted_text_available"] is True
    # Has deterministic extractions → awaiting_confirmation.
    assert data["status"] == "awaiting_confirmation"


@pytest.mark.asyncio
async def test_upload_pdf_page_extraction(client: AsyncClient):
    case_id = await _make_case(client)
    r = await _upload(client, case_id, "karar.pdf", make_pdf("Esas No: 2023/456 Karar"), "application/pdf")
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["support_level"] == "text_extraction_only"
    assert data["page_count"] >= 1
    pages = await client.get(f"/api/v1/cases/{case_id}/documents/{data['id']}/pages")
    assert pages.status_code == 200
    assert len(pages.json()) >= 1
    assert pages.json()[0]["page_number"] == 1


@pytest.mark.asyncio
async def test_upload_docx_paragraphs_no_fake_page(client: AsyncClient):
    case_id = await _make_case(client)
    r = await _upload(
        client, case_id, "dilekce.docx",
        make_docx(["Dava dilekçesi", "Talep: 100.000 TL"]),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["support_level"] == "text_extraction_only"
    pages = await client.get(f"/api/v1/cases/{case_id}/documents/{data['id']}/pages")
    # DOCX has no real page numbers; a single synthetic page index is used, not a fabricated PDF page.
    assert len(pages.json()) == 1


@pytest.mark.asyncio
async def test_upload_image_is_upload_only(client: AsyncClient):
    case_id = await _make_case(client)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    r = await _upload(client, case_id, "foto.png", png, "image/png")
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["support_level"] == "upload_only"
    assert data["extracted_text_available"] is False
    assert data["status"] == "unsupported"  # no OCR; honest status


@pytest.mark.asyncio
async def test_upload_udf_binary_is_unsupported(client: AsyncClient):
    case_id = await _make_case(client)
    r = await _upload(client, case_id, "evrak.udf", bytes(range(1, 256)) * 8, "application/octet-stream")
    assert r.status_code == 201, r.text
    assert r.json()["status"] in ("unsupported", "failed")


@pytest.mark.asyncio
async def test_upload_udf_readable_zip_extracts(client: AsyncClient):
    case_id = await _make_case(client)
    r = await _upload(
        client, case_id, "evrak.udf",
        make_udf_zip("Mahkeme kararı metni yeterince uzun içerik burada."),
        "application/octet-stream",
    )
    assert r.status_code == 201, r.text
    assert r.json()["extracted_text_available"] is True


# ---------------------------------------------------------------------------
# Validation / security
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unsupported_extension_rejected(client: AsyncClient):
    case_id = await _make_case(client)
    r = await _upload(client, case_id, "malware.exe", b"MZ\x90\x00", "application/octet-stream")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_mime_spoof_pdf_extension_wrong_content(client: AsyncClient):
    case_id = await _make_case(client)
    r = await _upload(client, case_id, "fake.pdf", b"this is not a pdf", "application/pdf")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_zero_byte_rejected(client: AsyncClient):
    case_id = await _make_case(client)
    r = await _upload(client, case_id, "empty.txt", b"", "text/plain")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_path_traversal_filename_stored_safely(client: AsyncClient):
    case_id = await _make_case(client)
    r = await _upload(client, case_id, "../../etc/passwd.txt", b"hello world content", "text/plain")
    # Filename is sanitized; upload succeeds and storage key is server-generated.
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]
    maker = get_sessionmaker()
    async with maker() as session:
        doc = (await session.execute(select(Document).where(Document.id == doc_id))).scalar_one()
    assert ".." not in doc.storage_key
    assert doc.storage_key.startswith(f"local/{case_id}/")


# ---------------------------------------------------------------------------
# Duplicate handling
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_duplicate_same_case_returns_409(client: AsyncClient):
    case_id = await _make_case(client)
    content = b"duplicate document body content"
    r1 = await _upload(client, case_id, "a.txt", content, "text/plain")
    assert r1.status_code == 201
    r2 = await _upload(client, case_id, "b.txt", content, "text/plain")
    assert r2.status_code == 409
    assert "X-Duplicate-Document-Id" in r2.headers


@pytest.mark.asyncio
async def test_same_hash_different_case_no_disclosure(client: AsyncClient):
    case_a = await _make_case(client, "A")
    case_b = await _make_case(client, "B")
    content = b"shared content across cases here"
    assert (await _upload(client, case_a, "x.txt", content, "text/plain")).status_code == 201
    # Same binary in a different (owned) case is allowed as an independent doc.
    assert (await _upload(client, case_b, "x.txt", content, "text/plain")).status_code == 201


# ---------------------------------------------------------------------------
# List / detail / soft delete / state machine
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_and_soft_delete(client: AsyncClient):
    case_id = await _make_case(client)
    doc = (await _upload(client, case_id, "a.txt", b"content here now", "text/plain")).json()
    lst = await client.get(f"/api/v1/cases/{case_id}/documents")
    assert lst.json()["total"] == 1

    d = await client.delete(f"/api/v1/cases/{case_id}/documents/{doc['id']}")
    assert d.status_code == 204
    assert (await client.get(f"/api/v1/cases/{case_id}/documents/{doc['id']}")).status_code == 404
    assert (await client.get(f"/api/v1/cases/{case_id}/documents")).json()["total"] == 0


@pytest.mark.asyncio
async def test_retry_transitions_and_reprocesses(client: AsyncClient):
    case_id = await _make_case(client)
    doc = (await _upload(client, case_id, "foto.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, "image/png")).json()
    assert doc["status"] == "unsupported"
    r = await client.post(f"/api/v1/cases/{case_id}/documents/{doc['id']}/retry")
    assert r.status_code == 200
    assert r.json()["status"] == "unsupported"  # still no OCR, but transition allowed


@pytest.mark.asyncio
async def test_content_download_authenticated(client: AsyncClient):
    case_id = await _make_case(client)
    doc = (await _upload(client, case_id, "a.txt", b"downloadable text body", "text/plain")).json()
    r = await client.get(f"/api/v1/cases/{case_id}/documents/{doc['id']}/content")
    assert r.status_code == 200
    assert r.content == b"downloadable text body"


# ---------------------------------------------------------------------------
# Provenance + extraction confirm/reject → P2.4
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_extraction_provenance(client: AsyncClient):
    case_id = await _make_case(client)
    text = "Satış bedeli: 850.000 TL geçerlidir."
    doc = (await _upload(client, case_id, "s.txt", text.encode(), "text/plain")).json()
    analysis = await client.get(f"/api/v1/cases/{case_id}/documents/{doc['id']}/analysis")
    assert analysis.status_code == 200
    extractions = analysis.json()["extractions"]
    assert any(e["field_key"] == "amount" for e in extractions)
    amount = next(e for e in extractions if e["field_key"] == "amount")
    assert amount["verification_status"] == "detected"
    assert amount["document_id"] == doc["id"]


@pytest.mark.asyncio
async def test_confirm_extraction_creates_document_verified_fact(client: AsyncClient):
    case_id = await _make_case(client)
    doc = (await _upload(client, case_id, "s.txt", "Esas No: 2023/456".encode(), "text/plain")).json()
    analysis = await client.get(f"/api/v1/cases/{case_id}/documents/{doc['id']}/analysis")
    extraction = analysis.json()["extractions"][0]

    confirm = await client.post(
        f"/api/v1/cases/{case_id}/documents/{doc['id']}/extractions/{extraction['id']}/confirm"
    )
    assert confirm.status_code == 200
    assert confirm.json()["verification_status"] == "user_confirmed"
    assert confirm.json()["memory_fact_id"]

    # The P2.4 memory now has a document_verified fact.
    mem = await client.get(f"/api/v1/cases/{case_id}/memory")
    facts = mem.json()["facts"]
    assert any(f["verification_status"] == "document_verified" for f in facts)


@pytest.mark.asyncio
async def test_conflicting_extraction_triggers_contradiction(client: AsyncClient):
    case_id = await _make_case(client)
    # Two documents with different amounts of the same field.
    d1 = (await _upload(client, case_id, "a.txt", "Satış bedeli: 100.000 TL".encode(), "text/plain")).json()
    d2 = (await _upload(client, case_id, "b.txt", "Satış bedeli: 200.000 TL".encode(), "text/plain")).json()
    a1 = (await client.get(f"/api/v1/cases/{case_id}/documents/{d1['id']}/analysis")).json()["extractions"]
    a2 = (await client.get(f"/api/v1/cases/{case_id}/documents/{d2['id']}/analysis")).json()["extractions"]
    e1 = next(e for e in a1 if e["field_key"] == "amount")
    e2 = next(e for e in a2 if e["field_key"] == "amount")

    await client.post(f"/api/v1/cases/{case_id}/documents/{d1['id']}/extractions/{e1['id']}/confirm")
    await client.post(f"/api/v1/cases/{case_id}/documents/{d2['id']}/extractions/{e2['id']}/confirm")

    contradictions = await client.get(f"/api/v1/cases/{case_id}/memory/contradictions")
    assert len(contradictions.json()) >= 1


@pytest.mark.asyncio
async def test_reject_extraction_preserves_and_no_fact(client: AsyncClient):
    case_id = await _make_case(client)
    doc = (await _upload(client, case_id, "s.txt", "Esas No: 2023/456".encode(), "text/plain")).json()
    extraction = (await client.get(f"/api/v1/cases/{case_id}/documents/{doc['id']}/analysis")).json()["extractions"][0]
    r = await client.post(
        f"/api/v1/cases/{case_id}/documents/{doc['id']}/extractions/{extraction['id']}/reject"
    )
    assert r.status_code == 200
    assert r.json()["verification_status"] == "rejected"
    # Still present in analysis (preserved), and no memory fact created.
    still = (await client.get(f"/api/v1/cases/{case_id}/documents/{doc['id']}/analysis")).json()["extractions"]
    assert any(e["id"] == extraction["id"] for e in still)
    mem = await client.get(f"/api/v1/cases/{case_id}/memory")
    assert mem.json()["counts"]["facts"] == 0


# ---------------------------------------------------------------------------
# Isolation / IDOR
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_foreign_case_documents_404(client: AsyncClient):
    foreign = await _seed_foreign_case()
    assert (await client.get(f"/api/v1/cases/{foreign}/documents")).status_code == 404
    assert (await _upload(client, foreign, "a.txt", b"content body xx", "text/plain")).status_code == 404


@pytest.mark.asyncio
async def test_foreign_document_404(client: AsyncClient):
    case_id = await _make_case(client)
    doc = (await _upload(client, case_id, "a.txt", b"content body zz", "text/plain")).json()
    foreign = await _seed_foreign_case("foreign-doc-2")
    # Accessing an owned doc under a foreign case id must 404.
    assert (await client.get(f"/api/v1/cases/{foreign}/documents/{doc['id']}")).status_code == 404


@pytest.mark.asyncio
async def test_missing_document_404(client: AsyncClient):
    case_id = await _make_case(client)
    assert (await client.get(f"/api/v1/cases/{case_id}/documents/nope")).status_code == 404


@pytest.mark.asyncio
async def test_audit_excludes_document_content(client: AsyncClient):
    case_id = await _make_case(client)
    secret = "ÇOKGİZLİİÇERİK-98765"
    await _upload(client, case_id, "s.txt", f"Satış bedeli: {secret}".encode(), "text/plain")
    maker = get_sessionmaker()
    async with maker() as session:
        rows = (await session.execute(
            select(AuditEvent).where(AuditEvent.tenant_id == "local", AuditEvent.case_id == case_id)
        )).scalars().all()
    assert rows
    for row in rows:
        assert secret not in str(row.safe_metadata)
