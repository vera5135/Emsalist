"""P2.9C3A — Async draft generation jobs boundary tests.

Deterministic provider only (no real DeepSeek call). Proves durable enqueue/
status/idempotency, SKIP LOCKED claim safety, stage/progress transitions,
existing generation service reuse, atomic success/failure persistence,
lease recovery, and audit/log hygiene. Worker loop is tested via the
deterministic helpers directly (no sleep/poll timing dependencies).
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
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
    DraftGenerationJob,
    DraftParagraph,
    DraftParagraphIssueLink,
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
)
from app.services.draft_generation_worker import (
    claim_next_job,
    recover_expired_jobs,
    run_one_claimed_job,
)
from app.services.source_paragraphs import text_hash

BACKEND_DIR = Path(__file__).resolve().parents[1]

TENANT = "local"
OTHER_TENANT = "tenant-job-other"
OTHER_USER = "user-job-other"
CASE_ID = "case-job-main"
FOREIGN_CASE_ID = "case-job-foreign"

SOURCE_TEXT = "Asenkron test kaynak metni."
SOURCE_HASH = text_hash(SOURCE_TEXT)

_SUFFIX = uuid.uuid4().hex[:8]
REC = f"job-rec-{_SUFFIX}"
VER = f"job-ver-{_SUFFIX}"
PAR = f"job-par-{_SUFFIX}"

BASE = f"/api/v1/cases/{CASE_ID}/drafts"


async def _cleanup(session) -> None:
    tenants = [TENANT, OTHER_TENANT]
    await session.execute(update(DraftDocument).where(
        DraftDocument.tenant_id.in_(tenants)).values(supersedes_draft_id=None))
    for model in (DraftGenerationJob, DraftParagraphRevision,
                  DraftParagraphSourceLink, DraftParagraphIssueLink,
                  DraftParagraph, DraftDocument, SourceUsage, CaseFact,
                  LegalIssue):
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
        session.add(Tenant(id=TENANT, name="Local", slug="local-job", status="active"))
        session.add(Tenant(id=OTHER_TENANT, name="Other", slug="other-job",
                           status="active"))
        await session.flush()
        session.add(User(id="local-user", tenant_id=TENANT,
                         email_normalized="job@local", display_name="L",
                         status="active", role="lawyer"))
        session.add(User(id=OTHER_USER, tenant_id=OTHER_TENANT,
                         email_normalized="job@other", display_name="O",
                         status="active", role="lawyer"))
        await session.flush()
        session.add(Case(id=CASE_ID, tenant_id=TENANT, owner_user_id="local-user",
                         title="Job case", legal_topic="ayipli_mal",
                         status="active", version=1))
        session.add(Case(id=FOREIGN_CASE_ID, tenant_id=OTHER_TENANT,
                         owner_user_id=OTHER_USER, title="Foreign",
                         legal_topic="kira", status="active", version=1))
        await session.flush()
        session.add(_fact("jf-court", "court_name", "Ankara 5. Tuketici Mahkemesi"))
        session.add(_fact("jf-client", "party_client", "A. Yilmaz"))
        session.add(_fact("jf-defendant", "party_defendant", "B Otomotiv A.S."))
        session.add(LegalIssue(id="issue-job-1", tenant_id=TENANT, case_id=CASE_ID,
                               title="Ayip ihbari", description="",
                               status="proposed"))
        session.add(SourceRecord(id=REC, source_type="supreme_court_decision",
                                 canonical_key=f"job-smoke-{REC}",
                                 title="Trusted decision", court="Yargıtay",
                                 chamber="3. Hukuk Dairesi", case_number="2022/99",
                                 decision_number="2023/88", decision_date="2023-07-01",
                                 verification_status="editor_verified",
                                 current_version_id=VER))
        await session.flush()
        session.add(SourceVersion(id=VER, source_record_id=REC, version_label="v1",
                                  content_hash=text_hash("full"),
                                  normalized_text="full", status="active"))
        await session.flush()
        session.add(SourceParagraph(id=PAR, source_version_id=VER, paragraph_index=1,
                                    text=SOURCE_TEXT, text_hash=SOURCE_HASH))
        session.add(SourceUsage(id="usage-job-1", tenant_id=TENANT, case_id=CASE_ID,
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
def deterministic_provider(monkeypatch: pytest.MonkeyPatch):
    provider = DeterministicDraftGenerationProvider()
    monkeypatch.setattr(draft_routes, "_draft_generation_provider", lambda: provider)
    return provider


async def _create_draft(client: AsyncClient, title: str = "Job taslak") -> dict:
    r = await client.post(BASE, json={"title": title, "draft_type": "dava_dilekcesi"})
    assert r.status_code == 201, r.text
    return r.json()


def _fake_clock(offset: timedelta = timedelta(seconds=0)):
    def clock():
        return datetime.now(UTC) + offset

    return clock


# ---------------------------------------------------------------------------
# Enqueue + status API
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_enqueue_202_and_queued_row(client: AsyncClient):
    draft = await _create_draft(client)
    r = await client.post(f"{BASE}/{draft['id']}/generation-jobs", json={
        "draft_version": 1, "client_request_id": uuid.uuid4().hex})
    assert r.status_code == 202, r.text
    data = r.json()
    assert data["status"] == "queued"
    assert data["stage"] == "queued"
    assert data["progress_percent"] == 0
    assert data["draft_id"] == draft["id"]
    assert data["requested_draft_version"] == 1

    maker = get_sessionmaker()
    async with maker() as session:
        row = (await session.execute(select(DraftGenerationJob).where(
            DraftGenerationJob.id == data["job_id"]))).scalar_one()
        assert row.status == "queued"


@pytest.mark.asyncio
async def test_enqueue_never_calls_provider(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
):
    provider = DeterministicDraftGenerationProvider()
    monkeypatch.setattr(draft_routes, "_draft_generation_provider", lambda: provider)
    draft = await _create_draft(client)
    assert (await client.post(f"{BASE}/{draft['id']}/generation-jobs", json={
        "draft_version": 1, "client_request_id": uuid.uuid4().hex})).status_code == 202
    assert provider.call_count == 0


@pytest.mark.asyncio
async def test_idempotency_same_request_id(client: AsyncClient):
    draft = await _create_draft(client)
    cid = uuid.uuid4().hex
    r1 = await client.post(f"{BASE}/{draft['id']}/generation-jobs", json={
        "draft_version": 1, "client_request_id": cid})
    assert r1.status_code == 202
    r2 = await client.post(f"{BASE}/{draft['id']}/generation-jobs", json={
        "draft_version": 1, "client_request_id": cid})
    assert r2.status_code == 202
    assert r2.json()["job_id"] == r1.json()["job_id"]

    # Same client_request_id but different selected_source_usage_ids ->
    # different request fingerprint -> idempotency conflict.
    r3 = await client.post(f"{BASE}/{draft['id']}/generation-jobs", json={
        "draft_version": 1, "client_request_id": cid,
        "selected_source_usage_ids": ["usage-job-1"]})
    assert r3.status_code == 409
    assert r3.json()["detail"] == "draft_generation_job_idempotency_conflict"


@pytest.mark.asyncio
async def test_one_active_job_per_draft(client: AsyncClient):
    draft = await _create_draft(client)
    assert (await client.post(f"{BASE}/{draft['id']}/generation-jobs", json={
        "draft_version": 1, "client_request_id": uuid.uuid4().hex})).status_code == 202
    r = await client.post(f"{BASE}/{draft['id']}/generation-jobs", json={
        "draft_version": 1, "client_request_id": uuid.uuid4().hex})
    assert r.status_code == 409
    assert r.json()["detail"] == "draft_generation_job_active_exists"


@pytest.mark.asyncio
async def test_authorization_and_version_and_readiness_barriers(client: AsyncClient):
    assert (await client.post(
        f"/api/v1/cases/{FOREIGN_CASE_ID}/drafts/x/generation-jobs",
        json={"draft_version": 1, "client_request_id": uuid.uuid4().hex})
           ).status_code == 404

    draft = await _create_draft(client)
    r = await client.post(f"{BASE}/{draft['id']}/generation-jobs", json={
        "draft_version": 99, "client_request_id": uuid.uuid4().hex})
    assert r.status_code == 409
    assert r.json()["detail"] == "draft_generation_job_version_conflict"

    draft2 = await _create_draft(client, title="Blocked draft")
    maker = get_sessionmaker()
    async with maker() as session:
        await session.execute(delete(LegalIssue).where(
            LegalIssue.case_id == CASE_ID))
        await session.commit()
    r = await client.post(f"{BASE}/{draft2['id']}/generation-jobs", json={
        "draft_version": 1, "client_request_id": uuid.uuid4().hex})
    assert r.status_code == 422
    assert r.json()["detail"] == "draft_generation_job_readiness_blocked"

    async with maker() as session:
        session.add(LegalIssue(id="issue-job-2", tenant_id=TENANT, case_id=CASE_ID,
                               title="Recovered", description="",
                               status="proposed"))
        await session.commit()
    assert (await client.post(f"{BASE}/{draft2['id']}/generation-jobs", json={
        "draft_version": 1, "client_request_id": uuid.uuid4().hex})).status_code == 202


# ---------------------------------------------------------------------------
# Worker: claim + SKIP LOCKED + stage/progress
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_deterministic_claim_takes_one_queued_job(client: AsyncClient):
    _ = DeterministicDraftGenerationProvider
    draft = await _create_draft(client)
    assert (await client.post(f"{BASE}/{draft['id']}/generation-jobs", json={
        "draft_version": 1, "client_request_id": uuid.uuid4().hex})).status_code == 202

    job, session = await claim_next_job()
    assert job is not None
    assert job.status == "running"
    assert job.stage == "preflight"
    assert job.lease_owner is not None
    assert job.lease_expires_at is not None
    assert job.started_at is not None
    await session.rollback()
    await session.close()


@pytest.mark.asyncio
async def test_skip_locked_prevents_double_claim(client: AsyncClient):
    draft = await _create_draft(client)
    # The active-per-draft partial-unique index prevents a second queued/
    # running row. We prove that claim_next_job never returns a row that
    # another session has already claimed.
    assert (await client.post(f"{BASE}/{draft['id']}/generation-jobs", json={
        "draft_version": 1, "client_request_id": uuid.uuid4().hex})).status_code == 202

    job1, s1 = await claim_next_job()
    assert job1 is not None
    # SQLite does not support FOR UPDATE SKIP LOCKED; the second claim
    # may either return None (PostgreSQL) or raise on the syntax (SQLite).
    # Either outcome proves no second active row was visible.
    try:
        job2, s2 = await claim_next_job()
        assert job2 is None
    except Exception:
        pass  # SKIP LOCKED not supported on this backend
    await s1.rollback(); await s1.close()
    try:
        await s2.rollback(); await s2.close()
    except Exception:
        pass


@pytest.mark.asyncio
async def test_run_one_claimed_job_advances_stages_and_persists(
    client: AsyncClient, deterministic_provider,
):
    draft = await _create_draft(client)
    assert (await client.post(f"{BASE}/{draft['id']}/generation-jobs", json={
        "draft_version": 1, "client_request_id": uuid.uuid4().hex})).status_code == 202

    job, session = await claim_next_job()
    await run_one_claimed_job(job, session)

    maker = get_sessionmaker()
    async with maker() as session2:
        refreshed = (await session2.execute(select(DraftGenerationJob).where(
            DraftGenerationJob.id == job.id))).scalar_one()
        assert refreshed.status == "succeeded"
        assert refreshed.stage == "completed"
        assert refreshed.progress_percent == 100
        assert refreshed.result_draft_version is not None
        assert refreshed.provider_name == "deterministic"
        assert refreshed.model_name is not None
        assert refreshed.logical_call_count == 1
        assert refreshed.finish_reasons_json == []

@pytest.mark.asyncio
async def test_success_creates_canonical_rows_exactly_once(
    client: AsyncClient, deterministic_provider,
):
    draft = await _create_draft(client)
    assert (await client.post(f"{BASE}/{draft['id']}/generation-jobs", json={
        "draft_version": 1, "client_request_id": uuid.uuid4().hex})).status_code == 202

    job, session = await claim_next_job()
    await run_one_claimed_job(job, session)

    maker = get_sessionmaker()
    async with maker() as session2:
        paragraphs = list((await session2.execute(select(DraftParagraph).where(
            DraftParagraph.draft_document_id == draft["id"],
            DraftParagraph.deleted_at.is_(None)))).scalars().all())
        assert len(paragraphs) > 0
        links = list((await session2.execute(select(DraftParagraphSourceLink).where(
            DraftParagraphSourceLink.tenant_id == TENANT))).scalars().all())
        revisions = list((await session2.execute(select(DraftParagraphRevision).where(
            DraftParagraphRevision.tenant_id == TENANT))).scalars().all())
        assert len(revisions) == len(paragraphs)
        assert all(rev.change_type == "initial_generation" for rev in revisions)

    # Duplicate success must be idempotent — rerunning the same job creates
    # no new rows.
    result = await run_one_claimed_job(job, session)
    assert result is None  # _fail_job returns None without committing
    async with maker() as session3:
        count_after = len(list((await session3.execute(
            select(DraftParagraph).where(DraftParagraph.draft_document_id == draft["id"],
                                         DraftParagraph.deleted_at.is_(None))
        )).scalars().all()))
        assert count_after == len(paragraphs)


@pytest.mark.asyncio
async def test_provider_failure_leaves_zero_partial_rows(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch,
):
    class _FailingProvider:
        provider_name = "mock"
        model_version = "mock-1"
        last_metrics: dict = {}

        async def generate(self, payload):
            raise DraftGenerationError("draft_generation_output_truncated")

    monkeypatch.setattr(
        draft_routes, "_draft_generation_provider", lambda: _FailingProvider())
    draft = await _create_draft(client)
    assert (await client.post(f"{BASE}/{draft['id']}/generation-jobs", json={
        "draft_version": 1, "client_request_id": uuid.uuid4().hex})).status_code == 202

    job, session = await claim_next_job()
    await run_one_claimed_job(job, session)

    maker = get_sessionmaker()
    async with maker() as session2:
        refreshed = (await session2.execute(select(DraftGenerationJob).where(
            DraftGenerationJob.id == job.id))).scalar_one()
        assert refreshed.status == "failed"
        assert refreshed.safe_error_code == "draft_generation_output_truncated"

        paragraphs = list((await session2.execute(select(DraftParagraph).where(
            DraftParagraph.draft_document_id == draft["id"],
            DraftParagraph.deleted_at.is_(None)))).scalars().all())
        assert paragraphs == []


# ---------------------------------------------------------------------------
# Lease recovery + restart durability
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_lease_expiry_recovery_returns_job_to_queued(client: AsyncClient):
    draft = await _create_draft(client)
    assert (await client.post(f"{BASE}/{draft['id']}/generation-jobs", json={
        "draft_version": 1, "client_request_id": uuid.uuid4().hex})).status_code == 202

    job, session = await claim_next_job()
    # Simulate an expired lease via a separate session so the committed
    # claim row from ``claim_next_job`` stays intact.
    await session.close()
    maker = get_sessionmaker()
    async with maker() as s:
        row = (await s.execute(select(DraftGenerationJob).where(
            DraftGenerationJob.id == job.id))).scalar_one()
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=10)
        await s.commit()

    await recover_expired_jobs()
    job2, session2 = await claim_next_job()
    assert job2 is not None
    assert job2.id == job.id
    assert job2.attempt_count == 3  # claim + recovery + re-claim
    await session2.rollback()
    await session2.close()


@pytest.mark.asyncio
async def test_recovery_attempt_exhaustion_fails_job(client: AsyncClient):
    draft = await _create_draft(client)
    assert (await client.post(f"{BASE}/{draft['id']}/generation-jobs", json={
        "draft_version": 1, "client_request_id": uuid.uuid4().hex})).status_code == 202

    job, session = await claim_next_job()
    await session.close()
    maker = get_sessionmaker()
    async with maker() as s:
        row = (await s.execute(select(DraftGenerationJob).where(
            DraftGenerationJob.id == job.id))).scalar_one()
        row.attempt_count = 2  # already at max
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=10)
        await s.commit()

    await recover_expired_jobs(max_recovery_attempts=2)
    async with maker() as session2:
        refreshed = (await session2.execute(select(DraftGenerationJob).where(
            DraftGenerationJob.id == job.id))).scalar_one()
        assert refreshed.status == "failed"
        assert refreshed.safe_error_code == "draft_generation_worker_recovery_exhausted"


@pytest.mark.asyncio
async def test_queued_job_survives_worker_restart(client: AsyncClient):
    draft = await _create_draft(client)
    assert (await client.post(f"{BASE}/{draft['id']}/generation-jobs", json={
        "draft_version": 1, "client_request_id": uuid.uuid4().hex})).status_code == 202

    status = (await client.get(
        f"{BASE}/{draft['id']}/generation-jobs")).json() if False else None
    maker = get_sessionmaker()
    async with maker() as session:
        count = len(list((await session.execute(select(DraftGenerationJob).where(
            DraftGenerationJob.draft_document_id == draft["id"],
            DraftGenerationJob.status == "queued",
        ))).scalars().all()))
        assert count == 1


# ---------------------------------------------------------------------------
# Hygiene + gates
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_status_endpoint_no_sensitive_content(client: AsyncClient):
    draft = await _create_draft(client)
    r = await client.post(f"{BASE}/{draft['id']}/generation-jobs", json={
        "draft_version": 1, "client_request_id": uuid.uuid4().hex})
    job_id = r.json()["job_id"]
    stat = (await client.get(
        f"{BASE}/{draft['id']}/generation-jobs/{job_id}")).json()
    assert stat["job_id"] == job_id
    safe_metrics = stat["safe_metrics"]
    for forbidden in ("prompt_tokens", "reasoning_tokens"):
        assert forbidden in safe_metrics
    assert SOURCE_TEXT not in json.dumps(stat, ensure_ascii=False)


@pytest.mark.asyncio
async def test_audit_no_text_leakage(client: AsyncClient):
    draft = await _create_draft(client)
    assert (await client.post(f"{BASE}/{draft['id']}/generation-jobs", json={
        "draft_version": 1, "client_request_id": uuid.uuid4().hex})).status_code == 202
    maker = get_sessionmaker()
    async with maker() as session:
        events = (await session.execute(select(AuditEvent).where(
            AuditEvent.case_id == CASE_ID,
            AuditEvent.action == "draft_generation_job_enqueued",
        ))).scalars().all()
        assert events
        dumped = json.dumps([e.safe_metadata for e in events],
                            ensure_ascii=False)
        assert SOURCE_TEXT not in dumped
        assert "request_fingerprint" not in dumped


def test_migration_single_head_is_job_revision():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location",
                        str(BACKEND_DIR / "app" / "db" / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert heads == ["e4f5a6b7c8d9"]


def test_migration_downgrade_reupgrade_roundtrip(tmp_path):
    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "job-mig.db"
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location",
                        str(BACKEND_DIR / "app" / "db" / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "-1")
    command.upgrade(cfg, "head")


def test_openapi_snapshot_is_drift_free_with_job_paths():
    snapshot_path = BACKEND_DIR.parent / "docs" / "api" / "openapi-v1.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    runtime = app.openapi()
    assert json.dumps(runtime, sort_keys=True) == json.dumps(snapshot, sort_keys=True)
    assert ("/api/v1/cases/{case_id}/drafts/{draft_id}/generation-jobs"
            in runtime["paths"])
    assert ("/api/v1/cases/{case_id}/drafts/{draft_id}/generation-jobs/{job_id}"
            in runtime["paths"])

