"""P2.9A — Grounded draft persistence backbone tests.

Proves against the real DB pipeline:
- case-scoped member authorization (foreign tenant/case 404, non-member 404),
- deterministic paragraph ordering + duplicate-order rejection,
- optimistic version conflicts,
- exact SourceRecord/SourceVersion/SourceParagraph provenance validation,
- trust-eligibility fail-closed (needs_review / quarantined / conflicting),
- quote hash exactness,
- finalize acceptance + atomic used_in_final_draft transaction,
- immutability of finalized drafts and terminal deleted state,
- no draft text in audit metadata.
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
    CaseMember,
    DraftDocument,
    DraftParagraph,
    DraftParagraphIssueLink,
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
from app.services.source_paragraphs import text_hash

BACKEND_DIR = Path(__file__).resolve().parents[1]

TENANT = "local"
OTHER_TENANT = "tenant-draft-other"
OTHER_USER = "user-draft-other"
CASE_ID = "case-draft-main"
FOREIGN_CASE_ID = "case-draft-foreign"
ISSUE_ID = "issue-draft-main"
FOREIGN_ISSUE_ID = "issue-draft-foreign"

SOURCE_PARAGRAPH_TEXT = "Kira sozlesmesinin feshi icin yazili ihtar sarttir."
QUOTE_HASH = text_hash(SOURCE_PARAGRAPH_TEXT)


def _ids() -> dict[str, str]:
    suffix = uuid.uuid4().hex[:8]
    return {
        "record": f"src-rec-{suffix}",
        "version": f"src-ver-{suffix}",
        "paragraph": f"src-par-{suffix}",
        "record2": f"src-rec2-{suffix}",
        "version2": f"src-ver2-{suffix}",
        "paragraph2": f"src-par2-{suffix}",
    }


IDS = _ids()


async def _cleanup(session) -> None:
    tenants = [TENANT, OTHER_TENANT]
    # Break the draft superseding self-reference first (RESTRICT-safe on
    # PostgreSQL where bulk deletes check FKs per row).
    await session.execute(update(DraftDocument).where(
        DraftDocument.tenant_id.in_(tenants)).values(supersedes_draft_id=None))
    for model in (DraftParagraphSourceLink, DraftParagraphIssueLink, DraftParagraph,
                  DraftDocument, SourceUsage, LegalIssue):
        await session.execute(delete(model).where(model.tenant_id.in_(tenants)))
    await session.execute(delete(SourceParagraph).where(
        SourceParagraph.source_version_id.in_([IDS["version"], IDS["version2"]])))
    await session.execute(delete(SourceVersion).where(
        SourceVersion.source_record_id.in_([IDS["record"], IDS["record2"]])))
    await session.execute(delete(SourceRecord).where(
        SourceRecord.id.in_([IDS["record"], IDS["record2"]])))
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
        session.add(Tenant(id=TENANT, name="Local", slug="local-draft", status="active"))
        session.add(Tenant(id=OTHER_TENANT, name="Other", slug="other-draft", status="active"))
        await session.flush()
        session.add(User(id="local-user", tenant_id=TENANT, email_normalized="draft@local",
                         display_name="L", status="active", role="lawyer"))
        session.add(User(id=OTHER_USER, tenant_id=OTHER_TENANT, email_normalized="draft@other",
                         display_name="O", status="active", role="lawyer"))
        await session.flush()
        session.add(Case(id=CASE_ID, tenant_id=TENANT, owner_user_id="local-user",
                         title="Draft case", legal_topic="kira", status="active", version=1))
        session.add(Case(id=FOREIGN_CASE_ID, tenant_id=OTHER_TENANT, owner_user_id=OTHER_USER,
                         title="Foreign", legal_topic="kira", status="active", version=1))
        await session.flush()
        session.add(LegalIssue(id=ISSUE_ID, tenant_id=TENANT, case_id=CASE_ID,
                               title="Fesih ihtari", description="", status="proposed"))
        session.add(LegalIssue(id=FOREIGN_ISSUE_ID, tenant_id=OTHER_TENANT,
                               case_id=FOREIGN_CASE_ID, title="Foreign issue",
                               description="", status="proposed"))
        await session.flush()
        session.add(SourceRecord(id=IDS["record"], source_type="yargitay_karar",
                                 canonical_key=f"draft-smoke-{IDS['record']}",
                                 title="Trusted source",
                                 verification_status="editor_verified",
                                 current_version_id=IDS["version"]))
        session.add(SourceRecord(id=IDS["record2"], source_type="yargitay_karar",
                                 canonical_key=f"draft-smoke-{IDS['record2']}",
                                 title="Untrusted source",
                                 verification_status="needs_review",
                                 current_version_id=IDS["version2"]))
        await session.flush()
        session.add(SourceVersion(id=IDS["version"], source_record_id=IDS["record"],
                                  version_label="v1", content_hash=text_hash("full text"),
                                  normalized_text="full text", status="active"))
        session.add(SourceVersion(id=IDS["version2"], source_record_id=IDS["record2"],
                                  version_label="v1", content_hash=text_hash("other text"),
                                  normalized_text="other text", status="active"))
        await session.flush()
        session.add(SourceParagraph(id=IDS["paragraph"], source_version_id=IDS["version"],
                                    paragraph_index=1, text=SOURCE_PARAGRAPH_TEXT,
                                    text_hash=QUOTE_HASH))
        session.add(SourceParagraph(id=IDS["paragraph2"], source_version_id=IDS["version2"],
                                    paragraph_index=1, text=SOURCE_PARAGRAPH_TEXT,
                                    text_hash=QUOTE_HASH))
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


BASE = f"/api/v1/cases/{CASE_ID}/drafts"


async def _create_draft(client: AsyncClient, **overrides) -> dict:
    payload = {"title": "Dava dilekçesi taslağı", "draft_type": "dava_dilekcesi"}
    payload.update(overrides)
    r = await client.post(BASE, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


async def _add_paragraph(client: AsyncClient, draft_id: str, order: int = 1,
                         text_value: str = "Taraflar arasindaki kira iliskisi.",
                         paragraph_type: str = "olaylar") -> dict:
    r = await client.post(f"{BASE}/{draft_id}/paragraphs", json={
        "paragraph_order": order, "paragraph_type": paragraph_type, "text": text_value,
    })
    assert r.status_code == 201, r.text
    return r.json()


async def _accept_paragraph(client: AsyncClient, draft_id: str, paragraph: dict) -> dict:
    r = await client.patch(f"{BASE}/{draft_id}/paragraphs/{paragraph['id']}", json={
        "version": paragraph["version"], "verification_status": "accepted",
    })
    assert r.status_code == 200, r.text
    return r.json()


def _source_link_body(**overrides) -> dict:
    body = {
        "source_record_id": IDS["record"],
        "source_version_id": IDS["version"],
        "source_paragraph_id": IDS["paragraph"],
        "usage_type": "citation",
        "quote_hash": QUOTE_HASH,
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# CRUD + authorization
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_draft_create_list_get(client: AsyncClient):
    draft = await _create_draft(client)
    assert draft["status"] == "draft"
    assert draft["version"] == 1
    assert draft["finalized_at"] is None

    listed = (await client.get(BASE)).json()
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == draft["id"]

    detail = (await client.get(f"{BASE}/{draft['id']}")).json()
    assert detail["id"] == draft["id"]
    assert detail["paragraphs"] == []


@pytest.mark.asyncio
async def test_invalid_draft_type_rejected(client: AsyncClient):
    r = await client.post(BASE, json={"title": "X", "draft_type": "serbest_kategori"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_foreign_tenant_case_404(client: AsyncClient):
    r = await client.post(f"/api/v1/cases/{FOREIGN_CASE_ID}/drafts",
                          json={"title": "X", "draft_type": "dava_dilekcesi"})
    assert r.status_code == 404
    assert (await client.get(f"/api/v1/cases/{FOREIGN_CASE_ID}/drafts")).status_code == 404


@pytest.mark.asyncio
async def test_non_member_cannot_access(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    draft = await _create_draft(client)
    # Force the member-based authorization path (local mode bypass disabled).
    monkeypatch.setattr(draft_routes, "get_auth_mode", lambda: "jwt")
    r = await client.get(f"{BASE}/{draft['id']}")
    assert r.status_code == 404

    maker = get_sessionmaker()
    async with maker() as session:
        session.add(CaseMember(case_id=CASE_ID, tenant_id=TENANT, user_id="local-user",
                               membership_role="editor"))
        await session.commit()
    r = await client.get(f"{BASE}/{draft['id']}")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_viewer_member_cannot_write(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    draft = await _create_draft(client)
    maker = get_sessionmaker()
    async with maker() as session:
        session.add(CaseMember(case_id=CASE_ID, tenant_id=TENANT, user_id="local-user",
                               membership_role="viewer"))
        await session.commit()
    monkeypatch.setattr(draft_routes, "get_auth_mode", lambda: "jwt")
    assert (await client.get(f"{BASE}/{draft['id']}")).status_code == 200
    r = await client.patch(f"{BASE}/{draft['id']}", json={"version": 1, "title": "Yeni"})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Paragraph ordering + optimistic versions
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_paragraph_order_is_deterministic(client: AsyncClient):
    draft = await _create_draft(client)
    await _add_paragraph(client, draft["id"], order=2, text_value="Ikinci paragraf.")
    await _add_paragraph(client, draft["id"], order=1, text_value="Birinci paragraf.")
    await _add_paragraph(client, draft["id"], order=3, text_value="Ucuncu paragraf.")
    detail = (await client.get(f"{BASE}/{draft['id']}")).json()
    assert [p["paragraph_order"] for p in detail["paragraphs"]] == [1, 2, 3]


@pytest.mark.asyncio
async def test_duplicate_paragraph_order_blocked(client: AsyncClient):
    draft = await _create_draft(client)
    await _add_paragraph(client, draft["id"], order=1)
    r = await client.post(f"{BASE}/{draft['id']}/paragraphs", json={
        "paragraph_order": 1, "paragraph_type": "olaylar", "text": "Cakisan sira.",
    })
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_optimistic_version_conflict(client: AsyncClient):
    draft = await _create_draft(client)
    r = await client.patch(f"{BASE}/{draft['id']}", json={"version": 99, "title": "Yeni"})
    assert r.status_code == 409

    paragraph = await _add_paragraph(client, draft["id"])
    r = await client.patch(f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}",
                           json={"version": 99, "text": "Guncel."})
    assert r.status_code == 409

    r = await client.post(f"{BASE}/{draft['id']}/finalize", json={"version": 99})
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# Issue links
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_issue_link_requires_same_case_issue(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    r = await client.post(
        f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/issues",
        json={"legal_issue_id": FOREIGN_ISSUE_ID})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_issue_drafted_in_paragraph_relation_persisted(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    r = await client.post(
        f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/issues",
        json={"legal_issue_id": ISSUE_ID})
    assert r.status_code == 201, r.text
    assert r.json()["relation_type"] == "issue_drafted_in_paragraph"

    maker = get_sessionmaker()
    async with maker() as session:
        row = (await session.execute(select(DraftParagraphIssueLink).where(
            DraftParagraphIssueLink.draft_paragraph_id == paragraph["id"],
        ))).scalar_one()
        assert row.relation_type == "issue_drafted_in_paragraph"
        assert row.legal_issue_id == ISSUE_ID
        assert row.case_id == CASE_ID


@pytest.mark.asyncio
async def test_duplicate_issue_and_source_links_blocked(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    url = f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/issues"
    assert (await client.post(url, json={"legal_issue_id": ISSUE_ID})).status_code == 201
    assert (await client.post(url, json={"legal_issue_id": ISSUE_ID})).status_code == 409

    source_url = f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/sources"
    assert (await client.post(source_url, json=_source_link_body())).status_code == 201
    assert (await client.post(source_url, json=_source_link_body())).status_code == 409


# ---------------------------------------------------------------------------
# Source links — exact provenance + trust + quote hash
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_exact_source_provenance_required(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    url = f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/sources"

    r = await client.post(url, json=_source_link_body(source_record_id="nonexistent-record"))
    assert r.status_code == 404
    r = await client.post(url, json=_source_link_body(source_version_id="nonexistent-version"))
    assert r.status_code == 404
    r = await client.post(url, json=_source_link_body(source_paragraph_id="nonexistent-par"))
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_paragraph_from_other_version_rejected(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    url = f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/sources"
    # Paragraph belongs to record2/version2, not to record/version.
    r = await client.post(url, json=_source_link_body(
        source_paragraph_id=IDS["paragraph2"]))
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_trust_ineligible_source_rejected(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    url = f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/sources"
    # record2 is needs_review -> index-eligible for search but NOT trusted for drafting.
    r = await client.post(url, json=_source_link_body(
        source_record_id=IDS["record2"], source_version_id=IDS["version2"],
        source_paragraph_id=IDS["paragraph2"]))
    assert r.status_code == 422
    assert "trust" in r.json()["detail"]


@pytest.mark.asyncio
async def test_quarantined_and_conflicting_sources_rejected(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    url = f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/sources"
    maker = get_sessionmaker()
    for blocked_status in ("quarantined", "conflicting"):
        async with maker() as session:
            record = (await session.execute(select(SourceRecord).where(
                SourceRecord.id == IDS["record"]))).scalar_one()
            record.verification_status = blocked_status
            await session.commit()
        r = await client.post(url, json=_source_link_body())
        assert r.status_code == 409, blocked_status
    async with maker() as session:
        record = (await session.execute(select(SourceRecord).where(
            SourceRecord.id == IDS["record"]))).scalar_one()
        record.verification_status = "editor_verified"
        await session.commit()


# ---------------------------------------------------------------------------
# Immutability + terminal states
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_finalized_draft_cannot_be_edited_directly(client: AsyncClient):
    draft, paragraph = await _finalizable_draft(client)
    current = (await client.get(f"{BASE}/{draft['id']}")).json()
    r = await client.post(f"{BASE}/{draft['id']}/finalize", json={"version": current["version"]})
    assert r.status_code == 200
    finalized_version = r.json()["version"]

    r = await client.patch(f"{BASE}/{draft['id']}",
                           json={"version": finalized_version, "title": "Degisiklik"})
    assert r.status_code == 409
    r = await client.post(f"{BASE}/{draft['id']}/paragraphs", json={
        "paragraph_order": 2, "paragraph_type": "olaylar", "text": "Ek paragraf."})
    assert r.status_code == 409
    r = await client.patch(f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}",
                           json={"version": paragraph["version"], "text": "Degisti."})
    assert r.status_code == 409
    assert (await client.delete(f"{BASE}/{draft['id']}")).status_code == 409

    # Editing after finalize requires a superseding draft.
    superseding = await _create_draft(client, title="Yeni surum",
                                      supersedes_draft_id=draft["id"])
    assert superseding["supersedes_draft_id"] == draft["id"]
    old = (await client.get(f"{BASE}/{draft['id']}")).json()
    assert old["status"] == "superseded"


@pytest.mark.asyncio
async def test_deleted_draft_cannot_be_finalized(client: AsyncClient):
    draft, _ = await _finalizable_draft(client)
    current = (await client.get(f"{BASE}/{draft['id']}")).json()
    assert (await client.delete(f"{BASE}/{draft['id']}")).status_code == 204
    r = await client.post(f"{BASE}/{draft['id']}/finalize",
                          json={"version": current["version"] + 1})
    assert r.status_code == 404
    assert (await client.get(f"{BASE}/{draft['id']}")).status_code == 404


@pytest.mark.asyncio
async def test_superseding_requires_finalized_draft(client: AsyncClient):
    draft = await _create_draft(client)
    r = await client.post(BASE, json={"title": "X", "draft_type": "dava_dilekcesi",
                                      "supersedes_draft_id": draft["id"]})
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# Audit hygiene
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_audit_metadata_contains_no_paragraph_text(client: AsyncClient):
    sentinel = "GIZLI-MUVEKKIL-BEYANI-123456"
    draft = await _create_draft(client, title="Audit taslak")
    paragraph = await _add_paragraph(client, draft["id"], text_value=f"Olay: {sentinel}.")
    r = await client.post(
        f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/sources",
        json=_source_link_body())
    assert r.status_code == 201
    paragraph = await _accept_paragraph(client, draft["id"], paragraph)
    current = (await client.get(f"{BASE}/{draft['id']}")).json()
    assert (await client.post(f"{BASE}/{draft['id']}/finalize",
                              json={"version": current["version"]})).status_code == 200

    maker = get_sessionmaker()
    async with maker() as session:
        events = (await session.execute(select(AuditEvent).where(
            AuditEvent.case_id == CASE_ID))).scalars().all()
    assert events, "audit events expected"
    dumped = json.dumps([e.safe_metadata for e in events], ensure_ascii=False)
    assert sentinel not in dumped
    assert SOURCE_PARAGRAPH_TEXT not in dumped
    assert QUOTE_HASH not in dumped
    actions = {e.action for e in events}
    assert {"draft_created", "draft_paragraph_added",
            "draft_paragraph_source_linked", "draft_finalized"} <= actions


# ---------------------------------------------------------------------------
# Migration + OpenAPI gates
# ---------------------------------------------------------------------------
def test_migration_single_head_is_draft_revision():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "app" / "db" / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert len(heads) == 1
    revisions = {rev.revision for rev in script.walk_revisions()}
    assert "b1c2d3e4f5a6" in revisions


def test_migration_downgrade_reupgrade_roundtrip(tmp_path):
    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "draft-mig.db"
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "app" / "db" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "-1")
    command.upgrade(cfg, "head")


def test_openapi_snapshot_is_drift_free_and_additive():
    snapshot_path = BACKEND_DIR.parent / "docs" / "api" / "openapi-v1.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    runtime = app.openapi()
    assert json.dumps(runtime, sort_keys=True) == json.dumps(snapshot, sort_keys=True)
    base = "/api/v1/cases/{case_id}/drafts"
    expected_p29a_paths = [
        base,
        f"{base}/{{draft_id}}",
        f"{base}/{{draft_id}}/finalize",
        f"{base}/{{draft_id}}/paragraphs",
        f"{base}/{{draft_id}}/paragraphs/{{paragraph_id}}",
        f"{base}/{{draft_id}}/paragraphs/{{paragraph_id}}/issues",
        f"{base}/{{draft_id}}/paragraphs/{{paragraph_id}}/issues/{{link_id}}",
        f"{base}/{{draft_id}}/paragraphs/{{paragraph_id}}/sources",
        f"{base}/{{draft_id}}/paragraphs/{{paragraph_id}}/sources/{{link_id}}",
    ]
    for path in expected_p29a_paths:
        assert path in runtime["paths"]


@pytest.mark.asyncio
async def test_quote_hash_mismatch_rejected(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    url = f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/sources"
    r = await client.post(url, json=_source_link_body(quote_hash=text_hash("fabricated quote")))
    assert r.status_code == 422
    assert "hash" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# used_in_final_draft transaction
# ---------------------------------------------------------------------------
async def _add_usage(record_id: str, version_id: str, paragraph_id: str | None = None,
                     case_id: str = CASE_ID) -> str:
    maker = get_sessionmaker()
    async with maker() as session:
        usage = SourceUsage(tenant_id=TENANT, case_id=case_id,
                            source_record_id=record_id, source_version_id=version_id,
                            source_paragraph_id=paragraph_id, usage_type="reference",
                            target_type="case", target_id=case_id,
                            selected_by="local-user", used_in_final_draft=False)
        session.add(usage)
        await session.commit()
        return usage.id


async def _usage_flag(usage_id: str) -> bool:
    maker = get_sessionmaker()
    async with maker() as session:
        usage = (await session.execute(select(SourceUsage).where(
            SourceUsage.id == usage_id))).scalar_one()
        return usage.used_in_final_draft


async def _finalizable_draft(client: AsyncClient) -> tuple[dict, dict]:
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"])
    r = await client.post(
        f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/sources",
        json=_source_link_body())
    assert r.status_code == 201, r.text
    paragraph = await _accept_paragraph(client, draft["id"], paragraph)
    return draft, paragraph


@pytest.mark.asyncio
async def test_draft_creation_does_not_touch_used_in_final_draft(client: AsyncClient):
    usage_id = await _add_usage(IDS["record"], IDS["version"])
    await _finalizable_draft(client)
    assert await _usage_flag(usage_id) is False


@pytest.mark.asyncio
async def test_finalize_marks_only_really_used_source_usages(client: AsyncClient):
    used_usage = await _add_usage(IDS["record"], IDS["version"])
    unused_usage = await _add_usage(IDS["record2"], IDS["version2"])
    draft, _ = await _finalizable_draft(client)

    current = (await client.get(f"{BASE}/{draft['id']}")).json()
    r = await client.post(f"{BASE}/{draft['id']}/finalize", json={"version": current["version"]})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "finalized"
    assert data["finalized_at"]
    assert data["paragraph_count"] == 1
    assert data["source_link_count"] == 1
    assert data["marked_source_usage_count"] == 1

    assert await _usage_flag(used_usage) is True
    assert await _usage_flag(unused_usage) is False


@pytest.mark.asyncio
async def test_finalize_requires_accepted_paragraphs_and_contiguous_order(client: AsyncClient):
    draft = await _create_draft(client)
    paragraph = await _add_paragraph(client, draft["id"], order=2)
    await _accept_paragraph(client, draft["id"], paragraph)
    current = (await client.get(f"{BASE}/{draft['id']}")).json()
    r = await client.post(f"{BASE}/{draft['id']}/finalize", json={"version": current["version"]})
    assert r.status_code == 422
    assert "contiguous" in r.json()["detail"]

    draft2 = await _create_draft(client, title="Ikinci taslak")
    await _add_paragraph(client, draft2["id"], order=1)
    current2 = (await client.get(f"{BASE}/{draft2['id']}")).json()
    r = await client.post(f"{BASE}/{draft2['id']}/finalize", json={"version": current2["version"]})
    assert r.status_code == 422
    assert "accepted" in r.json()["detail"]

    draft3 = await _create_draft(client, title="Bos taslak")
    r = await client.post(f"{BASE}/{draft3['id']}/finalize", json={"version": draft3["version"]})
    assert r.status_code == 422
    assert "no paragraphs" in r.json()["detail"]


@pytest.mark.asyncio
async def test_finalize_atomic_rollback_when_source_becomes_blocked(client: AsyncClient):
    usage_id = await _add_usage(IDS["record"], IDS["version"])
    draft, _ = await _finalizable_draft(client)

    maker = get_sessionmaker()
    async with maker() as session:
        record = (await session.execute(select(SourceRecord).where(
            SourceRecord.id == IDS["record"]))).scalar_one()
        record.verification_status = "quarantined"
        await session.commit()

    current = (await client.get(f"{BASE}/{draft['id']}")).json()
    r = await client.post(f"{BASE}/{draft['id']}/finalize", json={"version": current["version"]})
    assert r.status_code == 409

    # Nothing was persisted: draft still editable, no usage flag, no finalized_at.
    after = (await client.get(f"{BASE}/{draft['id']}")).json()
    assert after["status"] == "draft"
    assert after["version"] == current["version"]
    assert after["finalized_at"] is None
    assert await _usage_flag(usage_id) is False
    maker = get_sessionmaker()
    async with maker() as session:
        events = (await session.execute(select(AuditEvent).where(
            AuditEvent.case_id == CASE_ID,
            AuditEvent.action == "draft_finalized"))).scalars().all()
        assert events == []
    async with maker() as session:
        record = (await session.execute(select(SourceRecord).where(
            SourceRecord.id == IDS["record"]))).scalar_one()
        record.verification_status = "editor_verified"
        await session.commit()
