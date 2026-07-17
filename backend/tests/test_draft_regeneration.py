"""P2.9C1B — Selective grounded paragraph regeneration boundary tests.

Deterministic provider only (no real DeepSeek call). Proves single-paragraph
regeneration flows through the immutable revision history, replaces grounding
atomically, respects version/authorization/readiness guards and leaves zero
partial state on provider failure.
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
    User,
)
from app.db.session import get_sessionmaker
from app.main import app
from app.routes import draft_routes
from app.services.draft_generation_provider import (
    DeterministicDraftGenerationProvider,
    DraftGenerationError,
    UnavailableDraftGenerationProvider,
)
from app.services.source_paragraphs import text_hash

BACKEND_DIR = Path(__file__).resolve().parents[1]

TENANT = "local"
OTHER_TENANT = "tenant-regen-other"
OTHER_USER = "user-regen-other"
CASE_ID = "case-regen-main"
FOREIGN_CASE_ID = "case-regen-foreign"
ISSUE_1 = "issue-regen-1"

SOURCE_TEXT = "Secimlik hak kullanildiginda satici talebi yerine getirmelidir."
SOURCE_HASH = text_hash(SOURCE_TEXT)

_SUFFIX = uuid.uuid4().hex[:8]
REC = f"regen-rec-{_SUFFIX}"
VER = f"regen-ver-{_SUFFIX}"
PAR = f"regen-par-{_SUFFIX}"

BASE = f"/api/v1/cases/{CASE_ID}/drafts"


async def _cleanup(session) -> None:
    tenants = [TENANT, OTHER_TENANT]
    await session.execute(update(DraftDocument).where(
        DraftDocument.tenant_id.in_(tenants)).values(supersedes_draft_id=None))
    for model in (DraftParagraphReviewEvent, DraftParagraphRevision,
                  DraftParagraphSourceLink, DraftParagraphIssueLink, DraftParagraph,
                  DraftDocument, SourceUsage, CaseFact, LegalIssue):
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
        session.add(Tenant(id=TENANT, name="Local", slug="local-regen", status="active"))
        session.add(Tenant(id=OTHER_TENANT, name="Other", slug="other-regen",
                           status="active"))
        await session.flush()
        session.add(User(id="local-user", tenant_id=TENANT,
                         email_normalized="regen@local", display_name="L",
                         status="active", role="lawyer"))
        session.add(User(id=OTHER_USER, tenant_id=OTHER_TENANT,
                         email_normalized="regen@other", display_name="O",
                         status="active", role="lawyer"))
        await session.flush()
        session.add(Case(id=CASE_ID, tenant_id=TENANT, owner_user_id="local-user",
                         title="Regen case", legal_topic="ayipli_mal",
                         status="active", version=1))
        session.add(Case(id=FOREIGN_CASE_ID, tenant_id=OTHER_TENANT,
                         owner_user_id=OTHER_USER, title="Foreign",
                         legal_topic="kira", status="active", version=1))
        await session.flush()
        session.add(LegalIssue(id=ISSUE_1, tenant_id=TENANT, case_id=CASE_ID,
                               title="Secimlik hak", description="",
                               status="proposed"))
        session.add(_fact("gf-court", "court_name", "Ankara 5. Tuketici Mahkemesi"))
        session.add(_fact("gf-client", "party_client", "A. Yilmaz"))
        session.add(_fact("gf-defendant", "party_defendant", "B Otomotiv A.S."))
        session.add(SourceRecord(id=REC, source_type="supreme_court_decision",
                                 canonical_key=f"regen-smoke-{REC}",
                                 title="Trusted decision", court="Yargıtay",
                                 chamber="3. Hukuk Dairesi", case_number="2022/9",
                                 decision_number="2023/10", decision_date="2023-05-02",
                                 verification_status="editor_verified",
                                 current_version_id=VER))
        await session.flush()
        session.add(SourceVersion(id=VER, source_record_id=REC, version_label="v1",
                                  content_hash=text_hash("full"),
                                  normalized_text="full", status="active"))
        await session.flush()
        session.add(SourceParagraph(id=PAR, source_version_id=VER, paragraph_index=1,
                                    text=SOURCE_TEXT, text_hash=SOURCE_HASH))
        session.add(SourceUsage(id="usage-regen-1", tenant_id=TENANT, case_id=CASE_ID,
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


@pytest.fixture
def deterministic_provider(monkeypatch: pytest.MonkeyPatch) -> DeterministicDraftGenerationProvider:
    provider = DeterministicDraftGenerationProvider()
    monkeypatch.setattr(draft_routes, "_draft_generation_provider", lambda: provider)
    return provider


async def _seed_paragraph(client: AsyncClient) -> tuple[dict, dict]:
    r = await client.post(BASE, json={"title": "Regen taslak",
                                      "draft_type": "dava_dilekcesi"})
    assert r.status_code == 201, r.text
    draft = r.json()
    r = await client.post(f"{BASE}/{draft['id']}/paragraphs", json={
        "paragraph_order": 1, "paragraph_type": "hukuki_degerlendirme",
        "text": "Kullanicinin ilk metni."})
    assert r.status_code == 201, r.text
    return draft, r.json()


async def _state(client: AsyncClient, draft_id: str, paragraph_id: str) -> tuple[dict, dict]:
    detail = (await client.get(f"{BASE}/{draft_id}")).json()
    return detail, next(p for p in detail["paragraphs"] if p["id"] == paragraph_id)


async def _regenerate(client: AsyncClient, draft_id: str, paragraph_id: str) -> dict:
    detail, paragraph = await _state(client, draft_id, paragraph_id)
    r = await client.post(
        f"{BASE}/{draft_id}/paragraphs/{paragraph_id}/regenerate",
        json={"draft_version": detail["version"],
              "paragraph_version": paragraph["version"]})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_regenerate_appends_ai_regeneration_revision(
    client: AsyncClient, deterministic_provider,
):
    draft, paragraph = await _seed_paragraph(client)
    result = await _regenerate(client, draft["id"], paragraph["id"])
    assert result["provider"] == "deterministic"
    assert result["generation_run_id"]
    assert result["revision"]["change_type"] == "ai_regeneration"
    assert result["revision"]["revision_number"] == 2
    assert result["verification_status"] == "pending_review"

    detail, updated = await _state(client, draft["id"], paragraph["id"])
    assert updated["text"] != "Kullanicinin ilk metni."
    assert updated["generated_by"] == "ai"
    assert updated["model_name"] == deterministic_provider.model_version
    revisions = (await client.get(
        f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/revisions")).json()
    assert [r["revision_number"] for r in revisions] == [1, 2]
    assert revisions[0]["change_type"] == "manual_creation"
    assert revisions[0]["text"] == "Kullanicinin ilk metni."  # history intact
    assert revisions[1]["current_revision"] is True

    maker = get_sessionmaker()
    async with maker() as session:
        row = (await session.execute(select(DraftParagraph).where(
            DraftParagraph.id == paragraph["id"]))).scalar_one()
        assert row.generation_run_id == result["generation_run_id"]
        assert len(row.generation_input_fingerprint) == 64


@pytest.mark.asyncio
async def test_regenerate_replaces_links_with_verified_grounding(
    client: AsyncClient, deterministic_provider,
):
    draft, paragraph = await _seed_paragraph(client)
    r = await client.post(f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/sources",
                          json={"source_record_id": REC, "source_version_id": VER,
                                "source_paragraph_id": PAR, "usage_type": "citation",
                                "quote_hash": SOURCE_HASH})
    assert r.status_code == 201
    old_link_id = r.json()["id"]

    result = await _regenerate(client, draft["id"], paragraph["id"])
    assert result["replaced_source_link_count"] == 1
    assert result["source_link_count"] == 1
    assert result["issue_link_count"] == 1  # hukuki_degerlendirme targets issues

    _, updated = await _state(client, draft["id"], paragraph["id"])
    active_ids = {link["id"] for link in updated["source_links"]}
    assert old_link_id not in active_ids
    assert all(link["verification_status"] == "verified"
               for link in updated["source_links"])
    maker = get_sessionmaker()
    async with maker() as session:
        old_link = (await session.execute(select(DraftParagraphSourceLink).where(
            DraftParagraphSourceLink.id == old_link_id))).scalar_one()
        assert old_link.deleted_at is not None  # soft-deleted, history preserved


@pytest.mark.asyncio
async def test_regenerate_bumps_versions_and_supports_accept_finalize(
    client: AsyncClient, deterministic_provider,
):
    draft, paragraph = await _seed_paragraph(client)
    result = await _regenerate(client, draft["id"], paragraph["id"])
    assert result["paragraph_version"] == paragraph["version"] + 1
    assert result["draft_version"] > draft["version"]

    detail, updated = await _state(client, draft["id"], paragraph["id"])
    revisions = (await client.get(
        f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/revisions")).json()
    r = await client.post(f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/accept",
                          json={"draft_version": detail["version"],
                                "paragraph_version": updated["version"],
                                "revision_id": revisions[-1]["id"]})
    assert r.status_code == 200, r.text
    detail, _ = await _state(client, draft["id"], paragraph["id"])
    r = await client.post(f"{BASE}/{draft['id']}/finalize",
                          json={"version": detail["version"]})
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_regenerate_version_conflicts(client: AsyncClient, deterministic_provider):
    draft, paragraph = await _seed_paragraph(client)
    url = f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/regenerate"
    r = await client.post(url, json={"draft_version": 99, "paragraph_version": 1})
    assert r.status_code == 409
    detail, _ = await _state(client, draft["id"], paragraph["id"])
    r = await client.post(url, json={"draft_version": detail["version"],
                                     "paragraph_version": 99})
    assert r.status_code == 409
    assert deterministic_provider.call_count == 0


@pytest.mark.asyncio
async def test_regenerate_rejected_for_terminal_or_blocked_states(
    client: AsyncClient, deterministic_provider,
):
    draft, paragraph = await _seed_paragraph(client)
    url = f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/regenerate"
    maker = get_sessionmaker()
    async with maker() as session:
        await session.execute(update(DraftDocument).where(
            DraftDocument.id == draft["id"]).values(status="finalized"))
        await session.commit()
    r = await client.post(url, json={"draft_version": 2, "paragraph_version": 1})
    assert r.status_code == 409
    assert r.json()["detail"] == "draft_not_editable"

    async with maker() as session:
        await session.execute(update(DraftDocument).where(
            DraftDocument.id == draft["id"]).values(status="draft"))
        await session.execute(delete(LegalIssue).where(LegalIssue.tenant_id == TENANT))
        await session.commit()
    r = await client.post(url, json={"draft_version": 2, "paragraph_version": 1})
    assert r.status_code == 422
    assert r.json()["detail"] == "readiness_blocked"
    assert deterministic_provider.call_count == 0


@pytest.mark.asyncio
async def test_regenerate_unknown_selection_rejected(
    client: AsyncClient, deterministic_provider,
):
    draft, paragraph = await _seed_paragraph(client)
    detail, current = await _state(client, draft["id"], paragraph["id"])
    r = await client.post(
        f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/regenerate",
        json={"draft_version": detail["version"],
              "paragraph_version": current["version"],
              "selected_source_usage_ids": ["usage-unknown"]})
    assert r.status_code == 422
    assert r.json()["detail"] == "draft_generation_unknown_source"
    assert deterministic_provider.call_count == 0


@pytest.mark.asyncio
async def test_regenerate_authorization_boundaries(
    client: AsyncClient, deterministic_provider, monkeypatch: pytest.MonkeyPatch,
):
    r = await client.post(
        f"/api/v1/cases/{FOREIGN_CASE_ID}/drafts/x/paragraphs/y/regenerate",
        json={"draft_version": 1, "paragraph_version": 1})
    assert r.status_code == 404

    draft, paragraph = await _seed_paragraph(client)
    monkeypatch.setattr(draft_routes, "get_auth_mode", lambda: "jwt")
    url = f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/regenerate"
    r = await client.post(url, json={"draft_version": 2, "paragraph_version": 1})
    assert r.status_code == 404  # non-member

    maker = get_sessionmaker()
    async with maker() as session:
        session.add(CaseMember(case_id=CASE_ID, tenant_id=TENANT, user_id="local-user",
                               membership_role="viewer"))
        await session.commit()
    r = await client.post(url, json={"draft_version": 2, "paragraph_version": 1})
    assert r.status_code == 404  # viewer cannot write
    assert deterministic_provider.call_count == 0


@pytest.mark.asyncio
async def test_failed_regeneration_leaves_paragraph_untouched(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
):
    class _FailingProvider:
        provider_name = "deepseek"
        model_version = "deepseek-v4-pro"
        last_metrics: dict = {}

        async def generate(self, payload):
            raise DraftGenerationError("draft_generation_output_truncated")

    monkeypatch.setattr(draft_routes, "_draft_generation_provider",
                        lambda: _FailingProvider())
    draft, paragraph = await _seed_paragraph(client)
    detail, current = await _state(client, draft["id"], paragraph["id"])
    r = await client.post(
        f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/regenerate",
        json={"draft_version": detail["version"],
              "paragraph_version": current["version"]})
    assert r.status_code == 502
    assert r.json()["detail"] == "draft_generation_output_truncated"

    after_detail, after = await _state(client, draft["id"], paragraph["id"])
    assert after["text"] == "Kullanicinin ilk metni."
    assert after["version"] == current["version"]
    assert after["generated_by"] == "user"
    assert after_detail["version"] == detail["version"]
    revisions = (await client.get(
        f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/revisions")).json()
    assert [rev["change_type"] for rev in revisions] == ["manual_creation"]

    monkeypatch.setattr(draft_routes, "_draft_generation_provider",
                        lambda: UnavailableDraftGenerationProvider())
    r = await client.post(
        f"{BASE}/{draft['id']}/paragraphs/{paragraph['id']}/regenerate",
        json={"draft_version": detail["version"],
              "paragraph_version": current["version"]})
    assert r.status_code == 503
    assert r.json()["detail"] == "draft_generation_unavailable"


@pytest.mark.asyncio
async def test_regeneration_audit_contains_no_text(
    client: AsyncClient, deterministic_provider,
):
    draft, paragraph = await _seed_paragraph(client)
    await _regenerate(client, draft["id"], paragraph["id"])
    maker = get_sessionmaker()
    async with maker() as session:
        events = (await session.execute(select(AuditEvent).where(
            AuditEvent.case_id == CASE_ID,
            AuditEvent.action == "draft_paragraph_regenerated"))).scalars().all()
    assert len(events) == 1
    dumped = json.dumps(events[0].safe_metadata, ensure_ascii=False)
    assert "Kullanicinin ilk metni" not in dumped
    assert SOURCE_TEXT not in dumped
    assert "deterministik taslak metni" not in dumped


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------
def test_migration_single_head_is_regeneration_revision():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "app" / "db" / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert heads == ["e4f5a6b7c8d9"]


def test_openapi_snapshot_is_drift_free_with_regenerate_path():
    snapshot_path = BACKEND_DIR.parent / "docs" / "api" / "openapi-v1.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    runtime = app.openapi()
    assert json.dumps(runtime, sort_keys=True) == json.dumps(snapshot, sort_keys=True)
    assert ("/api/v1/cases/{case_id}/drafts/{draft_id}/paragraphs/"
            "{paragraph_id}/regenerate") in runtime["paths"]
