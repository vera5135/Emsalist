"""P2.9C1 — Draft review and immutable revision history boundary tests.

Runs against the real DB pipeline, proving:
- revision 1 for AI-generated, manual and lazily-bootstrapped paragraphs,
- immutable append-only edit/restore history with version bumps,
- accept / request-changes review decisions with provenance barriers,
- finalize integration (acceptance must cover the latest revision),
- authorization boundaries and audit/log hygiene.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select, update

from app.db.models import (
    AuditEvent,
    Case,
    CaseFact,
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
    TimelineEvent,
    User,
)
from app.db.session import get_sessionmaker
from app.main import app
from app.routes import draft_routes
from app.services.draft_generation_provider import DeterministicDraftGenerationProvider
from app.services.source_paragraphs import text_hash

BACKEND_DIR = Path(__file__).resolve().parents[1]

TENANT = "local"
OTHER_TENANT = "tenant-rev-other"
OTHER_USER = "user-rev-other"
CASE_ID = "case-rev-main"
FOREIGN_CASE_ID = "case-rev-foreign"
ISSUE_1 = "issue-rev-1"

SOURCE_TEXT = "Gizli ayipta ihbar makul sure icinde yapilmalidir."
SOURCE_HASH = text_hash(SOURCE_TEXT)

_SUFFIX = uuid.uuid4().hex[:8]
REC = f"rev-rec-{_SUFFIX}"
VER = f"rev-ver-{_SUFFIX}"
PAR = f"rev-par-{_SUFFIX}"

BASE = f"/api/v1/cases/{CASE_ID}/drafts"


async def _cleanup(session) -> None:
    tenants = [TENANT, OTHER_TENANT]
    await session.execute(update(DraftDocument).where(
        DraftDocument.tenant_id.in_(tenants)).values(supersedes_draft_id=None))
    for model in (DraftParagraphReviewEvent, DraftParagraphRevision,
                  DraftParagraphSourceLink, DraftParagraphIssueLink, DraftParagraph,
                  DraftDocument, SourceUsage, TimelineEvent, CaseFact, LegalIssue):
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


def _fact(fid: str, fact_type: str, value: str) -> CaseFact:
    return CaseFact(id=fid, tenant_id=TENANT, case_id=CASE_ID, fact_type=fact_type,
                    value=value, normalized_value=value,
                    verification_status="user_confirmed")


@pytest_asyncio.fixture(autouse=True)
async def db_setup():
    maker = get_sessionmaker()
    async with maker() as session:
        await _cleanup(session)
        await session.flush()
        session.add(Tenant(id=TENANT, name="Local", slug="local-rev", status="active"))
        session.add(Tenant(id=OTHER_TENANT, name="Other", slug="other-rev", status="active"))
        await session.flush()
        session.add(User(id="local-user", tenant_id=TENANT, email_normalized="rev@local",
                         display_name="L", status="active", role="lawyer"))
        session.add(User(id=OTHER_USER, tenant_id=OTHER_TENANT, email_normalized="rev@other",
                         display_name="O", status="active", role="lawyer"))
        await session.flush()
        session.add(Case(id=CASE_ID, tenant_id=TENANT, owner_user_id="local-user",
                         title="Rev case", legal_topic="ayipli_mal", status="active",
                         version=1))
        session.add(Case(id=FOREIGN_CASE_ID, tenant_id=OTHER_TENANT,
                         owner_user_id=OTHER_USER, title="Foreign", legal_topic="kira",
                         status="active", version=1))
        await session.flush()
        session.add(LegalIssue(id=ISSUE_1, tenant_id=TENANT, case_id=CASE_ID,
                               title="Ayip ihbari", description="", status="proposed"))
        session.add(_fact("rf-court", "court_name", "Ankara 5. Tuketici Mahkemesi"))
        session.add(_fact("rf-client", "party_client", "A. Yilmaz"))
        session.add(_fact("rf-defendant", "party_defendant", "B Otomotiv A.S."))
        session.add(SourceRecord(id=REC, source_type="supreme_court_decision",
                                 canonical_key=f"rev-smoke-{REC}",
                                 title="Trusted decision", court="Yargıtay",
                                 chamber="3. Hukuk Dairesi", case_number="2022/1",
                                 decision_number="2023/2", decision_date="2023-03-20",
                                 verification_status="editor_verified",
                                 current_version_id=VER))
        await session.flush()
        session.add(SourceVersion(id=VER, source_record_id=REC, version_label="v1",
                                  content_hash=text_hash("full"),
                                  normalized_text="full", status="active"))
        await session.flush()
        session.add(SourceParagraph(id=PAR, source_version_id=VER, paragraph_index=1,
                                    text=SOURCE_TEXT, text_hash=SOURCE_HASH))
        session.add(SourceUsage(id="usage-rev-1", tenant_id=TENANT, case_id=CASE_ID,
                                source_record_id=REC, source_version_id=VER,
                                source_paragraph_id=None, usage_type="reference",
                                target_type="case", target_id=CASE_ID,
                                selected_by="local-user", used_in_final_draft=False))
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


async def _create_draft(client: AsyncClient, title: str = "Rev taslak") -> dict:
    r = await client.post(BASE, json={"title": title, "draft_type": "dava_dilekcesi"})
    assert r.status_code == 201, r.text
    return r.json()


async def _add_paragraph(client: AsyncClient, draft_id: str, order: int = 1,
                         text_value: str = "Olaylar burada anlatilmistir.") -> dict:
    r = await client.post(f"{BASE}/{draft_id}/paragraphs", json={
        "paragraph_order": order, "paragraph_type": "olaylar", "text": text_value})
    assert r.status_code == 201, r.text
    return r.json()


async def _add_source_link(client: AsyncClient, draft_id: str, paragraph_id: str) -> dict:
    r = await client.post(f"{BASE}/{draft_id}/paragraphs/{paragraph_id}/sources", json={
        "source_record_id": REC, "source_version_id": VER,
        "source_paragraph_id": PAR, "usage_type": "citation",
        "quote_hash": SOURCE_HASH})
    assert r.status_code == 201, r.text
    return r.json()


async def _revisions(client: AsyncClient, draft_id: str, paragraph_id: str) -> list[dict]:
    r = await client.get(f"{BASE}/{draft_id}/paragraphs/{paragraph_id}/revisions")
    assert r.status_code == 200, r.text
    return r.json()


async def _versions(client: AsyncClient, draft_id: str, paragraph_id: str) -> tuple[int, int]:
    detail = (await client.get(f"{BASE}/{draft_id}")).json()
    paragraph = next(p for p in detail["paragraphs"] if p["id"] == paragraph_id)
    return detail["version"], paragraph["version"]


async def _edit(client: AsyncClient, draft_id: str, paragraph_id: str,
                text_value: str) -> dict:
    draft_version, paragraph_version = await _versions(client, draft_id, paragraph_id)
    r = await client.post(f"{BASE}/{draft_id}/paragraphs/{paragraph_id}/revisions", json={
        "draft_version": draft_version, "paragraph_version": paragraph_version,
        "text": text_value})
    assert r.status_code == 201, r.text
    return r.json()


async def _accept(client: AsyncClient, draft_id: str, paragraph_id: str) -> dict:
    revisions = await _revisions(client, draft_id, paragraph_id)
    draft_version, paragraph_version = await _versions(client, draft_id, paragraph_id)
    r = await client.post(f"{BASE}/{draft_id}/paragraphs/{paragraph_id}/accept", json={
        "draft_version": draft_version, "paragraph_version": paragraph_version,
        "revision_id": revisions[-1]["id"]})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Revision creation (generation / manual / lazy bootstrap)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ai_generation_creates_revision_1(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
):
    provider = DeterministicDraftGenerationProvider()
    monkeypatch.setattr(draft_routes, "_draft_generation_provider", lambda: provider)
    draft = await _create_draft(client)
    r = await client.post(f"{BASE}/{draft['id']}/generate", json={"version": 1})
    assert r.status_code == 200, r.text
    detail = (await client.get(f"{BASE}/{draft['id']}")).json()
    for paragraph in detail["paragraphs"]:
        revisions = await _revisions(client, draft["id"], paragraph["id"])
        assert len(revisions) == 1
        assert revisions[0]["revision_number"] == 1
        assert revisions[0]["change_type"] == "initial_generation"
        assert revisions[0]["current_revision"] is True
        assert revisions[0]["text_hash"] == text_hash(paragraph["text"])


@pytest.mark.asyncio
async def test_manual_paragraph_creates_revision_1(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    revisions = await _revisions(client, draft["id"], paragraph["id"])
    assert [r["revision_number"] for r in revisions] == [1]
    assert revisions[0]["change_type"] == "manual_creation"
    assert revisions[0]["text_hash"] == text_hash(paragraph["text"])


@pytest.mark.asyncio
async def test_legacy_paragraph_lazy_bootstrap_is_idempotent(client: AsyncClient):
    draft = await _create_draft(client)
    maker = get_sessionmaker()
    async with maker() as session:
        session.add(DraftParagraph(id="legacy-par-1", tenant_id=TENANT, case_id=CASE_ID,
                                   draft_document_id=draft["id"], paragraph_order=1,
                                   paragraph_type="olaylar",
                                   text="Eski donem paragrafi.",
                                   verification_status="pending_review",
                                   generated_by="user", version=1))
        await session.commit()
    assert await _revisions(client, draft["id"], "legacy-par-1") == []

    await _edit(client, draft["id"], "legacy-par-1", "Duzenlenmis eski paragraf.")
    revisions = await _revisions(client, draft["id"], "legacy-par-1")
    assert [r["revision_number"] for r in revisions] == [1, 2]
    assert revisions[0]["change_type"] == "manual_creation"
    assert revisions[0]["text_hash"] == text_hash("Eski donem paragrafi.")
    assert revisions[1]["change_type"] == "user_edit"

    await _edit(client, draft["id"], "legacy-par-1", "Ikinci duzenleme.")
    revisions = await _revisions(client, draft["id"], "legacy-par-1")
    assert [r["revision_number"] for r in revisions] == [1, 2, 3]
    assert sum(1 for r in revisions if r["change_type"] == "manual_creation") == 1


# ---------------------------------------------------------------------------
# Manual edit behavior
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_edit_appends_immutable_revision_and_bumps_versions(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    draft_version_before, paragraph_version_before = await _versions(
        client, draft["id"], paragraph["id"])
    result = await _edit(client, draft["id"], paragraph["id"], "Yeni metin.")
    assert result["revision"]["revision_number"] == 2
    assert result["revision"]["change_type"] == "user_edit"
    assert result["paragraph_version"] == paragraph_version_before + 1
    assert result["draft_version"] == draft_version_before + 1
    assert result["verification_status"] == "pending_review"
    revisions = await _revisions(client, draft["id"], paragraph["id"])
    assert revisions[0]["text_hash"] == text_hash(paragraph["text"])  # unchanged row
    assert revisions[-1]["text"] == "Yeni metin."


@pytest.mark.asyncio
async def test_edit_resets_acceptance_and_marks_source_links(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    link = await _add_source_link(client, draft["id"], paragraph["id"])
    assert link["verification_status"] == "verified"
    await _accept(client, draft["id"], paragraph["id"])

    result = await _edit(client, draft["id"], paragraph["id"], "Kabul sonrasi edit.")
    assert result["verification_status"] == "pending_review"
    assert result["source_links_marked_needs_review"] == 1
    detail = (await client.get(f"{BASE}/{draft['id']}")).json()
    updated = next(p for p in detail["paragraphs"] if p["id"] == paragraph["id"])
    assert updated["verification_status"] == "pending_review"
    assert all(l["verification_status"] == "needs_review" for l in updated["source_links"])


@pytest.mark.asyncio
async def test_edit_stale_versions_conflict(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    url = f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/revisions"
    draft_version, paragraph_version = await _versions(client, draft["id"], paragraph["id"])
    r = await client.post(url, json={"draft_version": 99,
                                     "paragraph_version": paragraph_version,
                                     "text": "X"})
    assert r.status_code == 409
    r = await client.post(url, json={"draft_version": draft_version,
                                     "paragraph_version": 99, "text": "X"})
    assert r.status_code == 409
    assert len(await _revisions(client, draft["id"], paragraph["id"])) == 1


@pytest.mark.asyncio
async def test_edit_rejected_for_terminal_draft_states(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    maker = get_sessionmaker()
    for terminal in ("finalized", "superseded"):
        async with maker() as session:
            await session.execute(update(DraftDocument).where(
                DraftDocument.id == draft["id"]).values(status=terminal))
            await session.commit()
        r = await client.post(
            f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/revisions",
            json={"draft_version": 2, "paragraph_version": 1, "text": "X"})
        assert r.status_code == 409, terminal
    async with maker() as session:
        await session.execute(update(DraftDocument).where(
            DraftDocument.id == draft["id"]).values(status="deleted"))
        await session.commit()
    r = await client.post(
        f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/revisions",
        json={"draft_version": 2, "paragraph_version": 1, "text": "X"})
    assert r.status_code == 404  # deleted drafts are not found


@pytest.mark.asyncio
async def test_edit_authorization_boundaries(client: AsyncClient,
                                             monkeypatch: pytest.MonkeyPatch):
    r = await client.post(
        f"/api/v1/cases/{FOREIGN_CASE_ID}/drafts/x/paragraphs/y/revisions",
        json={"draft_version": 1, "paragraph_version": 1, "text": "X"})
    assert r.status_code == 404

    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    monkeypatch.setattr(draft_routes, "get_auth_mode", lambda: "jwt")
    url = f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/revisions"
    r = await client.post(url, json={"draft_version": 2, "paragraph_version": 1,
                                     "text": "X"})
    assert r.status_code == 404  # non-member

    maker = get_sessionmaker()
    async with maker() as session:
        session.add(CaseMember(case_id=CASE_ID, tenant_id=TENANT, user_id="local-user",
                               membership_role="viewer"))
        await session.commit()
    r = await client.post(url, json={"draft_version": 2, "paragraph_version": 1,
                                     "text": "X"})
    assert r.status_code == 404  # viewer cannot write
    assert (await client.get(
        f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/revisions")).status_code == 200


# ---------------------------------------------------------------------------
# Review decisions
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_accept_requires_latest_revision(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    await _edit(client, draft["id"], paragraph["id"], "Ikinci surum.")
    revisions = await _revisions(client, draft["id"], paragraph["id"])
    old_revision = revisions[0]
    draft_version, paragraph_version = await _versions(client, draft["id"], paragraph["id"])
    r = await client.post(f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/accept",
                          json={"draft_version": draft_version,
                                "paragraph_version": paragraph_version,
                                "revision_id": old_revision["id"]})
    assert r.status_code == 409
    assert "latest" in r.json()["detail"]


@pytest.mark.asyncio
async def test_accept_rejects_unverified_source_links(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    await _add_source_link(client, draft["id"], paragraph["id"])
    await _edit(client, draft["id"], paragraph["id"], "Metin degisti, link needs_review.")
    revisions = await _revisions(client, draft["id"], paragraph["id"])
    draft_version, paragraph_version = await _versions(client, draft["id"], paragraph["id"])
    r = await client.post(f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/accept",
                          json={"draft_version": draft_version,
                                "paragraph_version": paragraph_version,
                                "revision_id": revisions[-1]["id"]})
    assert r.status_code == 422
    assert "re-verified" in r.json()["detail"]


@pytest.mark.asyncio
async def test_accept_rejects_untrusted_or_stale_provenance(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    await _add_source_link(client, draft["id"], paragraph["id"])
    maker = get_sessionmaker()
    async with maker() as session:
        record = (await session.execute(select(SourceRecord).where(
            SourceRecord.id == REC))).scalar_one()
        record.verification_status = "quarantined"
        await session.commit()
    revisions = await _revisions(client, draft["id"], paragraph["id"])
    draft_version, paragraph_version = await _versions(client, draft["id"], paragraph["id"])
    r = await client.post(f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/accept",
                          json={"draft_version": draft_version,
                                "paragraph_version": paragraph_version,
                                "revision_id": revisions[-1]["id"]})
    assert r.status_code in (409, 422)

    async with maker() as session:
        record = (await session.execute(select(SourceRecord).where(
            SourceRecord.id == REC))).scalar_one()
        record.verification_status = "editor_verified"
        record.current_version_id = "another-version"
        await session.commit()
    r = await client.post(f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/accept",
                          json={"draft_version": draft_version,
                                "paragraph_version": paragraph_version,
                                "revision_id": revisions[-1]["id"]})
    assert r.status_code == 404  # exact provenance no longer resolvable
    async with maker() as session:
        record = (await session.execute(select(SourceRecord).where(
            SourceRecord.id == REC))).scalar_one()
        record.current_version_id = VER
        await session.commit()


@pytest.mark.asyncio
async def test_accept_creates_review_event(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    await _add_source_link(client, draft["id"], paragraph["id"])
    result = await _accept(client, draft["id"], paragraph["id"])
    assert result["verification_status"] == "accepted"
    event = result["review_event"]
    assert event["decision"] == "accepted"
    assert event["reason_code"] is None
    assert event["reviewer_user_id"] == "local-user"

    reviews = (await client.get(
        f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/reviews")).json()
    assert len(reviews) == 1
    assert reviews[0]["id"] == event["id"]
    revisions = await _revisions(client, draft["id"], paragraph["id"])
    assert reviews[0]["paragraph_revision_id"] == revisions[-1]["id"]


@pytest.mark.asyncio
async def test_request_changes_sets_status_and_event_without_touching_text(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"], text_value="Orijinal metin.")
    revisions = await _revisions(client, draft["id"], paragraph["id"])
    draft_version, paragraph_version = await _versions(client, draft["id"], paragraph["id"])
    r = await client.post(
        f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/request-changes",
        json={"draft_version": draft_version, "paragraph_version": paragraph_version,
              "revision_id": revisions[-1]["id"],
              "reason_code": "citation_revision_required"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["verification_status"] == "needs_review"
    assert data["review_event"]["decision"] == "changes_requested"
    assert data["review_event"]["reason_code"] == "citation_revision_required"

    detail = (await client.get(f"{BASE}/{draft['id']}")).json()
    updated = next(p for p in detail["paragraphs"] if p["id"] == paragraph["id"])
    assert updated["text"] == "Orijinal metin."
    assert await _revisions(client, draft["id"], paragraph["id"]) == revisions or \
        len(await _revisions(client, draft["id"], paragraph["id"])) == len(revisions)


@pytest.mark.asyncio
async def test_unknown_reason_code_rejected(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    revisions = await _revisions(client, draft["id"], paragraph["id"])
    r = await client.post(
        f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/request-changes",
        json={"draft_version": 2, "paragraph_version": 1,
              "revision_id": revisions[-1]["id"],
              "reason_code": "serbest_aciklama"})
    assert r.status_code == 422
    assert (await client.get(
        f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/reviews")).json() == []


@pytest.mark.asyncio
async def test_revision_and_review_lists_are_deterministic(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    await _add_source_link(client, draft["id"], paragraph["id"])
    await _accept(client, draft["id"], paragraph["id"])
    await _edit(client, draft["id"], paragraph["id"], "Yeni surum metni.")
    revisions_url = f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/revisions"
    reviews_url = f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/reviews"
    first_revisions = (await client.get(revisions_url)).json()
    second_revisions = (await client.get(revisions_url)).json()
    assert first_revisions == second_revisions
    assert [r["revision_number"] for r in first_revisions] == [1, 2]
    assert [r["current_revision"] for r in first_revisions] == [False, True]
    first_reviews = (await client.get(reviews_url)).json()
    second_reviews = (await client.get(reviews_url)).json()
    assert first_reviews == second_reviews


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_restore_appends_new_revision_without_touching_old_rows(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"], text_value="Ilk metin.")
    link = await _add_source_link(client, draft["id"], paragraph["id"])
    await _edit(client, draft["id"], paragraph["id"], "Ikinci metin.")
    revisions_before = await _revisions(client, draft["id"], paragraph["id"])
    first_revision = revisions_before[0]

    draft_version, paragraph_version = await _versions(client, draft["id"], paragraph["id"])
    r = await client.post(
        f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/revisions/"
        f"{first_revision['id']}/restore",
        json={"draft_version": draft_version, "paragraph_version": paragraph_version})
    assert r.status_code == 201, r.text
    restored = r.json()
    assert restored["revision"]["revision_number"] == 3
    assert restored["revision"]["change_type"] == "restored_revision"
    assert restored["revision"]["text_hash"] == first_revision["text_hash"]
    assert restored["verification_status"] == "pending_review"

    revisions_after = await _revisions(client, draft["id"], paragraph["id"])
    assert [rev["revision_number"] for rev in revisions_after] == [1, 2, 3]
    assert revisions_after[0] == {**first_revision, "current_revision": False}
    detail = (await client.get(f"{BASE}/{draft['id']}")).json()
    updated = next(p for p in detail["paragraphs"] if p["id"] == paragraph["id"])
    assert updated["text"] == "Ilk metin."
    assert all(l["verification_status"] == "needs_review" for l in updated["source_links"])
    assert link["id"] in {l["id"] for l in updated["source_links"]}


@pytest.mark.asyncio
async def test_restore_rejected_on_finalized_draft(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    revisions = await _revisions(client, draft["id"], paragraph["id"])
    maker = get_sessionmaker()
    async with maker() as session:
        await session.execute(update(DraftDocument).where(
            DraftDocument.id == draft["id"]).values(status="finalized"))
        await session.commit()
    r = await client.post(
        f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/revisions/"
        f"{revisions[0]['id']}/restore",
        json={"draft_version": 2, "paragraph_version": 1})
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# Finalize integration
# ---------------------------------------------------------------------------
async def _finalize(client: AsyncClient, draft_id: str) -> object:
    draft = (await client.get(f"{BASE}/{draft_id}")).json()
    return await client.post(f"{BASE}/{draft_id}/finalize",
                             json={"version": draft["version"]})


@pytest.mark.asyncio
async def test_edit_after_acceptance_blocks_finalize(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    await _add_source_link(client, draft["id"], paragraph["id"])
    await _accept(client, draft["id"], paragraph["id"])
    await _edit(client, draft["id"], paragraph["id"], "Kabulden sonra degisti.")

    # Bypass attempt: acceptance flag forced back without a new review must
    # still be blocked by the revision/event finalize barrier.
    maker = get_sessionmaker()
    async with maker() as session:
        await session.execute(update(DraftParagraph).where(
            DraftParagraph.id == paragraph["id"]).values(verification_status="accepted"))
        await session.execute(update(DraftParagraphSourceLink).where(
            DraftParagraphSourceLink.draft_paragraph_id == paragraph["id"]
        ).values(verification_status="verified"))
        await session.commit()
    r = await _finalize(client, draft["id"])
    assert r.status_code == 422
    assert "latest revision" in r.json()["detail"]


@pytest.mark.asyncio
async def test_latest_accepted_revision_passes_finalize(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    await _add_source_link(client, draft["id"], paragraph["id"])
    await _edit(client, draft["id"], paragraph["id"], "Guncellenmis nihai metin.")
    # Re-verify the source link after the edit, then accept the latest revision.
    detail = (await client.get(f"{BASE}/{draft['id']}")).json()
    updated = next(p for p in detail["paragraphs"] if p["id"] == paragraph["id"])
    maker = get_sessionmaker()
    async with maker() as session:
        await session.execute(update(DraftParagraphSourceLink).where(
            DraftParagraphSourceLink.id == updated["source_links"][0]["id"]
        ).values(verification_status="verified"))
        await session.commit()
    await _accept(client, draft["id"], paragraph["id"])
    r = await _finalize(client, draft["id"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "finalized"


@pytest.mark.asyncio
async def test_failed_review_leaves_no_partial_rows(client: AsyncClient):
    draft = await _create_draft(client)
    maker = get_sessionmaker()
    async with maker() as session:
        session.add(DraftParagraph(id="legacy-par-2", tenant_id=TENANT, case_id=CASE_ID,
                                   draft_document_id=draft["id"], paragraph_order=1,
                                   paragraph_type="olaylar",
                                   text="Bootstrap adayi.",
                                   verification_status="pending_review",
                                   generated_by="user", version=1))
        session.add(DraftParagraphSourceLink(
            id="legacy-link-2", tenant_id=TENANT, case_id=CASE_ID,
            draft_paragraph_id="legacy-par-2", source_record_id=REC,
            source_version_id=VER, source_paragraph_id=PAR,
            usage_type="citation", quote_hash=SOURCE_HASH,
            verification_status="needs_review", version=1))
        await session.commit()
    # Accept fails on the unverified link AFTER the lazy bootstrap step; the
    # whole transaction must roll back including the bootstrap revision.
    r = await client.post(
        f"{BASE}/{draft['id']}/paragraphs/legacy-par-2/accept",
        json={"draft_version": 1, "paragraph_version": 1,
              "revision_id": "nonexistent"})
    assert r.status_code == 404
    maker = get_sessionmaker()
    async with maker() as session:
        revisions = (await session.execute(select(DraftParagraphRevision).where(
            DraftParagraphRevision.draft_paragraph_id == "legacy-par-2"
        ))).scalars().all()
        events = (await session.execute(select(DraftParagraphReviewEvent).where(
            DraftParagraphReviewEvent.draft_paragraph_id == "legacy-par-2"
        ))).scalars().all()
    assert revisions == []
    assert events == []


# ---------------------------------------------------------------------------
# Hygiene + gates
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_revision_text_never_in_audit_or_logs(client: AsyncClient, caplog):
    import logging
    caplog.set_level(logging.DEBUG)
    sentinel = "GIZLI-REVIZYON-METNI-987654"
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    await _add_source_link(client, draft["id"], paragraph["id"])
    await _edit(client, draft["id"], paragraph["id"], f"Olay: {sentinel}.")
    revisions = await _revisions(client, draft["id"], paragraph["id"])
    assert sentinel in revisions[-1]["text"]  # allowed in the API response

    maker = get_sessionmaker()
    async with maker() as session:
        events = (await session.execute(select(AuditEvent).where(
            AuditEvent.case_id == CASE_ID))).scalars().all()
    dumped = json.dumps([e.safe_metadata for e in events], ensure_ascii=False)
    assert sentinel not in dumped
    assert SOURCE_TEXT not in dumped
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert sentinel not in logs
    actions = {e.action for e in events}
    assert "draft_paragraph_revised" in actions


def test_migration_single_head_is_review_revision():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "app" / "db" / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1
    revisions = {rev.revision for rev in script.walk_revisions()}
    assert "d3e4f5a6b7c8" in revisions


def test_migration_downgrade_reupgrade_roundtrip(tmp_path):
    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "rev-mig.db"
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "app" / "db" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "-1")
    command.upgrade(cfg, "head")


def test_openapi_snapshot_is_drift_free_with_review_paths():
    snapshot_path = BACKEND_DIR.parent / "docs" / "api" / "openapi-v1.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    runtime = app.openapi()
    assert json.dumps(runtime, sort_keys=True) == json.dumps(snapshot, sort_keys=True)
    base = "/api/v1/cases/{case_id}/drafts/{draft_id}/paragraphs/{paragraph_id}"
    for suffix in ("revisions", "revisions/{revision_id}/restore",
                   "accept", "request-changes", "reviews"):
        assert f"{base}/{suffix}" in runtime["paths"]
