"""P2.9C2 — Deterministic draft export integrity and security tests.

Proves DOCX/PDF export of finalized drafts only, with re-validated
finalize/provenance barriers, deterministic ordering + citations, Turkish
Unicode fidelity, safe headers/filenames and zero state/log leakage.
"""
from __future__ import annotations

import json
import logging
import uuid
from io import BytesIO
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update

from app.db.models import (
    AuditEvent,
    Case,
    CaseMember,
    DraftDocument,
    DraftParagraph,
    DraftParagraphIssueLink,
    DraftParagraphReviewEvent,
    DraftParagraphRevision,
    DraftParagraphSourceLink,
    LegalIssue,
    SourceParagraph,
    SourceRecord,
    SourceUsage,
    SourceVersion,
    Tenant,
    User,
)
from app.db.session import get_sessionmaker
from app.main import app
from app.routes import draft_routes
from app.services.draft_citation_renderer import render_citation
from app.services.source_paragraphs import text_hash

BACKEND_DIR = Path(__file__).resolve().parents[1]

TENANT = "local"
OTHER_TENANT = "tenant-exp-other"
OTHER_USER = "user-exp-other"
CASE_ID = "case-exp-main"
FOREIGN_CASE_ID = "case-exp-foreign"

SOURCE_TEXT = "Gizli ayıpta ihbar süresi makul ölçüler içinde değerlendirilir."
SOURCE_HASH = text_hash(SOURCE_TEXT)
TURKISH_SENTINEL = "Şüpheli ğüçlü İĞDIŞ örnek — ıspatlı öğreti çerçevesi."

_SUFFIX = uuid.uuid4().hex[:8]
REC = f"exp-rec-{_SUFFIX}"
VER = f"exp-ver-{_SUFFIX}"
PAR = f"exp-par-{_SUFFIX}"

BASE = f"/api/v1/cases/{CASE_ID}/drafts"

EXPECTED_CITATION = render_citation(
    court="Yargıtay", chamber="3. Hukuk Dairesi", case_number="2022/77",
    decision_number="2023/88", decision_date="2023-06-01", paragraph_index=1)


async def _cleanup(session) -> None:
    tenants = [TENANT, OTHER_TENANT]
    await session.execute(update(DraftDocument).where(
        DraftDocument.tenant_id.in_(tenants)).values(supersedes_draft_id=None))
    for model in (DraftParagraphReviewEvent, DraftParagraphRevision,
                  DraftParagraphSourceLink, DraftParagraphIssueLink, DraftParagraph,
                  DraftDocument, SourceUsage, LegalIssue):
        await session.execute(delete(model).where(model.tenant_id.in_(tenants)))
    await session.execute(delete(SourceParagraph).where(
        SourceParagraph.source_version_id == VER))
    await session.execute(delete(SourceVersion).where(
        SourceVersion.source_record_id == REC))
    await session.execute(delete(SourceRecord).where(SourceRecord.id == REC))
    await session.execute(delete(CaseMember).where(CaseMember.tenant_id.in_(tenants)))
    await session.execute(delete(Case).where(Case.tenant_id.in_(tenants)))
    await session.execute(delete(AuditEvent).where(AuditEvent.tenant_id.in_(tenants)))
    await session.execute(delete(User).where(User.id.in_(["local-user", OTHER_USER])))
    await session.execute(delete(Tenant).where(Tenant.id.in_(tenants)))


@pytest_asyncio.fixture(autouse=True)
async def db_setup():
    maker = get_sessionmaker()
    async with maker() as session:
        await _cleanup(session)
        await session.flush()
        session.add(Tenant(id=TENANT, name="Local", slug="local-exp", status="active"))
        session.add(Tenant(id=OTHER_TENANT, name="Other", slug="other-exp",
                           status="active"))
        await session.flush()
        session.add(User(id="local-user", tenant_id=TENANT,
                         email_normalized="exp@local", display_name="L",
                         status="active", role="lawyer"))
        session.add(User(id=OTHER_USER, tenant_id=OTHER_TENANT,
                         email_normalized="exp@other", display_name="O",
                         status="active", role="lawyer"))
        await session.flush()
        session.add(Case(id=CASE_ID, tenant_id=TENANT, owner_user_id="local-user",
                         title="Export case", legal_topic="ayipli_mal",
                         status="active", version=1))
        session.add(Case(id=FOREIGN_CASE_ID, tenant_id=OTHER_TENANT,
                         owner_user_id=OTHER_USER, title="Foreign",
                         legal_topic="kira", status="active", version=1))
        await session.flush()
        session.add(SourceRecord(id=REC, source_type="supreme_court_decision",
                                 canonical_key=f"exp-smoke-{REC}",
                                 title="Trusted decision", court="Yargıtay",
                                 chamber="3. Hukuk Dairesi", case_number="2022/77",
                                 decision_number="2023/88", decision_date="2023-06-01",
                                 verification_status="editor_verified",
                                 current_version_id=VER))
        await session.flush()
        session.add(SourceVersion(id=VER, source_record_id=REC, version_label="v1",
                                  content_hash=text_hash("full"),
                                  normalized_text="full", status="active"))
        await session.flush()
        session.add(SourceParagraph(id=PAR, source_version_id=VER, paragraph_index=1,
                                    text=SOURCE_TEXT, text_hash=SOURCE_HASH))
        await session.commit()
    yield
    async with maker() as session:
        await _cleanup(session)
        await session.commit()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _accept_paragraph(client: AsyncClient, draft_id: str, paragraph_id: str):
    revisions = (await client.get(
        f"{BASE}/{draft_id}/paragraphs/{paragraph_id}/revisions")).json()
    detail = (await client.get(f"{BASE}/{draft_id}")).json()
    paragraph = next(p for p in detail["paragraphs"] if p["id"] == paragraph_id)
    r = await client.post(f"{BASE}/{draft_id}/paragraphs/{paragraph_id}/accept", json={
        "draft_version": detail["version"], "paragraph_version": paragraph["version"],
        "revision_id": revisions[-1]["id"]})
    assert r.status_code == 200, r.text


async def _finalized_draft(client: AsyncClient, *, texts: list[str] | None = None,
                           with_source: bool = True) -> dict:
    r = await client.post(BASE, json={"title": "Export taslak",
                                      "draft_type": "ihtarname"})
    assert r.status_code == 201, r.text
    draft = r.json()
    paragraph_texts = texts or [TURKISH_SENTINEL]
    types = ["taraflar", "konu", "olaylar", "hukuki_degerlendirme", "sonuc_ve_talep"]
    paragraph_ids = []
    for index, text_value in enumerate(paragraph_texts):
        r = await client.post(f"{BASE}/{draft['id']}/paragraphs", json={
            "paragraph_order": index + 1, "paragraph_type": types[index],
            "text": text_value})
        assert r.status_code == 201, r.text
        paragraph_ids.append(r.json()["id"])
    if with_source:
        r = await client.post(
            f"{BASE}/{draft['id']}/paragraphs/{paragraph_ids[0]}/sources",
            json={"source_record_id": REC, "source_version_id": VER,
                  "source_paragraph_id": PAR, "usage_type": "citation",
                  "quote_hash": SOURCE_HASH})
        assert r.status_code == 201, r.text
    for paragraph_id in paragraph_ids:
        await _accept_paragraph(client, draft["id"], paragraph_id)
    detail = (await client.get(f"{BASE}/{draft['id']}")).json()
    r = await client.post(f"{BASE}/{draft['id']}/finalize",
                          json={"version": detail["version"]})
    assert r.status_code == 200, r.text
    return (await client.get(f"{BASE}/{draft['id']}")).json()


def _docx_text(content: bytes) -> str:
    from docx import Document as DocxDocument

    document = DocxDocument(BytesIO(content))
    return "\n".join(p.text for p in document.paragraphs)


def _pdf_text(content: bytes) -> str:
    import fitz

    with fitz.open(stream=content, filetype="pdf") as pdf:
        raw = "\n".join(page.get_text() for page in pdf)
    # Extraction quirk normalization only (nbsp / soft hyphen); Turkish
    # glyphs themselves round-trip exactly.
    return raw.replace("\xa0", " ").replace("\xad", "-")


# ---------------------------------------------------------------------------
# Success paths
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_docx_export_success_structure_and_headers(client: AsyncClient):
    draft = await _finalized_draft(client)
    r = await client.get(f"{BASE}/{draft['id']}/export/docx")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    expected_name = f"emsalist-ihtarname-{draft['id'][:8]}.docx"
    assert r.headers["content-disposition"] == f'attachment; filename="{expected_name}"'
    assert r.headers["cache-control"] == "no-store"
    assert r.content[:4] == b"PK\x03\x04"  # structurally valid zip/docx

    text = _docx_text(r.content)
    assert TURKISH_SENTINEL in text
    assert "TARAFLAR" in text
    assert f"Kaynak: {EXPECTED_CITATION}" in text


@pytest.mark.asyncio
async def test_pdf_export_success_selectable_turkish_text(client: AsyncClient):
    draft = await _finalized_draft(client)
    r = await client.get(f"{BASE}/{draft['id']}/export/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    expected_name = f"emsalist-ihtarname-{draft['id'][:8]}.pdf"
    assert r.headers["content-disposition"] == f'attachment; filename="{expected_name}"'
    assert r.headers["cache-control"] == "no-store"
    assert r.content[:5] == b"%PDF-"

    text = _pdf_text(r.content)  # selectable, not image-based
    assert TURKISH_SENTINEL in text
    assert "ğ" in text and "İ" in text and "ç" in text and "Ş" in text
    assert EXPECTED_CITATION in text
    assert "Sayfa 1" in text  # page footer

    # Same canonical input -> same content order.
    again = await client.get(f"{BASE}/{draft['id']}/export/pdf")
    assert _pdf_text(again.content) == text


@pytest.mark.asyncio
async def test_paragraph_order_preserved_in_both_formats(client: AsyncClient):
    draft = await _finalized_draft(client, texts=[
        "Birinci bölüm metni.", "İkinci bölüm metni.", "Üçüncü bölüm metni."])
    docx_text = _docx_text((await client.get(
        f"{BASE}/{draft['id']}/export/docx")).content)
    pdf_text = _pdf_text((await client.get(
        f"{BASE}/{draft['id']}/export/pdf")).content)
    for text in (docx_text, pdf_text):
        first = text.index("Birinci bölüm")
        second = text.index("İkinci bölüm")
        third = text.index("Üçüncü bölüm")
        assert first < second < third
    # Deterministic Turkish headings appear in plan order.
    assert docx_text.index("TARAFLAR") < docx_text.index("KONU") < \
        docx_text.index("OLAYLAR")


@pytest.mark.asyncio
async def test_latest_accepted_revision_is_exported(client: AsyncClient):
    draft = await _finalized_draft(client)
    # Un-finalize path is forbidden; build a NEW draft edited before finalize.
    r = await client.post(BASE, json={"title": "Rev export",
                                      "draft_type": "ihtarname"})
    fresh = r.json()
    r = await client.post(f"{BASE}/{fresh['id']}/paragraphs", json={
        "paragraph_order": 1, "paragraph_type": "konu",
        "text": "ESKI surum metni."})
    paragraph = r.json()
    detail = (await client.get(f"{BASE}/{fresh['id']}")).json()
    r = await client.post(
        f"{BASE}/{fresh['id']}/paragraphs/{paragraph['id']}/revisions",
        json={"draft_version": detail["version"],
              "paragraph_version": paragraph["version"],
              "text": "YENI surum metni."})
    assert r.status_code == 201
    await _accept_paragraph(client, fresh["id"], paragraph["id"])
    detail = (await client.get(f"{BASE}/{fresh['id']}")).json()
    assert (await client.post(f"{BASE}/{fresh['id']}/finalize",
                              json={"version": detail["version"]})).status_code == 200

    for suffix in ("docx", "pdf"):
        r = await client.get(f"{BASE}/{fresh['id']}/export/{suffix}")
        text = _docx_text(r.content) if suffix == "docx" else _pdf_text(r.content)
        assert "YENI surum metni." in text
        assert "ESKI surum metni." not in text


# ---------------------------------------------------------------------------
# Rejections + authorization
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_non_finalized_and_terminal_states_rejected(client: AsyncClient):
    r = await client.post(BASE, json={"title": "Taslak", "draft_type": "ihtarname"})
    draft = r.json()
    for suffix in ("docx", "pdf"):
        r = await client.get(f"{BASE}/{draft['id']}/export/{suffix}")
        assert r.status_code == 409
        assert r.json()["detail"] == "draft_export_requires_finalized_draft"

    maker = get_sessionmaker()
    async with maker() as session:
        await session.execute(update(DraftDocument).where(
            DraftDocument.id == draft["id"]).values(status="superseded"))
        await session.commit()
    assert (await client.get(f"{BASE}/{draft['id']}/export/docx")).status_code == 409

    async with maker() as session:
        await session.execute(update(DraftDocument).where(
            DraftDocument.id == draft["id"]).values(status="deleted"))
        await session.commit()
    assert (await client.get(f"{BASE}/{draft['id']}/export/docx")).status_code == 404


@pytest.mark.asyncio
async def test_foreign_and_non_member_access_404(client: AsyncClient,
                                                 monkeypatch: pytest.MonkeyPatch):
    assert (await client.get(
        f"/api/v1/cases/{FOREIGN_CASE_ID}/drafts/x/export/docx")).status_code == 404
    draft = await _finalized_draft(client)
    monkeypatch.setattr(draft_routes, "get_auth_mode", lambda: "jwt")
    assert (await client.get(
        f"{BASE}/{draft['id']}/export/pdf")).status_code == 404  # non-member

    maker = get_sessionmaker()
    async with maker() as session:
        session.add(CaseMember(case_id=CASE_ID, tenant_id=TENANT, user_id="local-user",
                               membership_role="viewer"))
        await session.commit()
    # Case read is sufficient for export.
    assert (await client.get(
        f"{BASE}/{draft['id']}/export/pdf")).status_code == 200


@pytest.mark.asyncio
async def test_broken_trust_or_hash_blocks_export(client: AsyncClient):
    draft = await _finalized_draft(client)
    maker = get_sessionmaker()
    async with maker() as session:
        record = (await session.execute(select(SourceRecord).where(
            SourceRecord.id == REC))).scalar_one()
        record.verification_status = "quarantined"
        await session.commit()
    for suffix in ("docx", "pdf"):
        r = await client.get(f"{BASE}/{draft['id']}/export/{suffix}")
        assert r.status_code == 422
        assert r.json()["detail"] == "draft_export_provenance_invalid"

    async with maker() as session:
        record = (await session.execute(select(SourceRecord).where(
            SourceRecord.id == REC))).scalar_one()
        record.verification_status = "editor_verified"
        paragraph = (await session.execute(select(SourceParagraph).where(
            SourceParagraph.id == PAR))).scalar_one()
        paragraph.text = "Sonradan degistirilmis kaynak metni."
        paragraph.text_hash = text_hash(paragraph.text)
        await session.commit()
    r = await client.get(f"{BASE}/{draft['id']}/export/docx")
    assert r.status_code == 422
    assert r.json()["detail"] == "draft_export_provenance_invalid"


# ---------------------------------------------------------------------------
# State + hygiene
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_export_changes_no_db_state(client: AsyncClient):
    draft = await _finalized_draft(client)
    maker = get_sessionmaker()
    async with maker() as session:
        audits_before = len((await session.execute(select(AuditEvent).where(
            AuditEvent.case_id == CASE_ID))).scalars().all())
    assert (await client.get(f"{BASE}/{draft['id']}/export/docx")).status_code == 200
    assert (await client.get(f"{BASE}/{draft['id']}/export/pdf")).status_code == 200
    after = (await client.get(f"{BASE}/{draft['id']}")).json()
    assert after["version"] == draft["version"]
    assert after["status"] == "finalized"
    async with maker() as session:
        audits_after = len((await session.execute(select(AuditEvent).where(
            AuditEvent.case_id == CASE_ID))).scalars().all())
    assert audits_after == audits_before  # read-only export


@pytest.mark.asyncio
async def test_export_leaks_no_text_or_bytes_into_logs(client: AsyncClient, caplog):
    caplog.set_level(logging.DEBUG)
    draft = await _finalized_draft(client)
    docx = await client.get(f"{BASE}/{draft['id']}/export/docx")
    pdf = await client.get(f"{BASE}/{draft['id']}/export/pdf")
    assert docx.status_code == 200 and pdf.status_code == 200
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert TURKISH_SENTINEL not in logs
    assert SOURCE_TEXT not in logs
    assert EXPECTED_CITATION not in logs
    assert "%PDF" not in logs and "PK\x03\x04" not in logs
    assert "draft_exported" in logs  # safe structured line only


def test_export_filename_is_safe_and_deterministic():
    from app.services.draft_export import export_filename

    name = export_filename("dava_dilekcesi", "abcdef1234567890", "pdf")
    assert name == "emsalist-dava_dilekcesi-abcdef12.pdf"
    assert name == export_filename("dava_dilekcesi", "abcdef1234567890", "pdf")


def test_openapi_snapshot_is_drift_free_with_export_paths():
    snapshot_path = BACKEND_DIR.parent / "docs" / "api" / "openapi-v1.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    runtime = app.openapi()
    assert json.dumps(runtime, sort_keys=True) == json.dumps(snapshot, sort_keys=True)
    base = "/api/v1/cases/{case_id}/drafts/{draft_id}/export"
    assert f"{base}/docx" in runtime["paths"]
    assert f"{base}/pdf" in runtime["paths"]
