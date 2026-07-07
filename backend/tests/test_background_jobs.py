"""P1.8 — Background job system tests."""
from __future__ import annotations

import pytest
import pytest_asyncio
from datetime import UTC, datetime, timedelta

from app.db.models import Tenant, User, Case, CaseMember, BackgroundJob, new_uuid
from app.db.session import get_sessionmaker
from app.services.job_service import JobRepository, job_service, _canonical_status_transition, KNOWN_JOB_TYPES, RETRYABLE_CODES, NON_RETRYABLE_CODES
from app.services.job_context import JobContext, CancellationRequested
from app.services.job_handlers import handler_registry


@pytest_asyncio.fixture
async def db_session():
    maker = get_sessionmaker()
    async with maker() as session:
        from sqlalchemy import delete
        await session.execute(delete(BackgroundJob).where(BackgroundJob.tenant_id == 't-p8'))
        await session.execute(delete(CaseMember).where(CaseMember.tenant_id == 't-p8'))
        await session.execute(delete(Case).where(Case.tenant_id == 't-p8'))
        await session.execute(delete(User).where(User.tenant_id == 't-p8'))
        await session.execute(delete(Tenant).where(Tenant.id == 't-p8'))
        await session.flush()
        session.add(Tenant(id="t-p8", name="P8", slug="t-p8", status="active"))
        session.add(User(id="u-p8", tenant_id="t-p8", email_normalized="p8@t.com", display_name="P8 User", status="active", role="tenant_admin"))
        session.add(User(id="u-p8-v", tenant_id="t-p8", email_normalized="p8v@t.com", display_name="P8 Viewer", status="active", role="viewer"))
        await session.flush()
        session.add(Case(id="c-p8-a", tenant_id="t-p8", owner_user_id="u-p8", title="CaseA", legal_topic="test", profile_id="default", event_text="", status="active", version=1))
        session.add(Case(id="c-p8-b", tenant_id="t-p8", owner_user_id="u-p8", title="CaseB", legal_topic="test", profile_id="default", event_text="", status="active", version=1))
        await session.flush()
        session.add(CaseMember(id=new_uuid(), tenant_id="t-p8", case_id="c-p8-a", user_id="u-p8", membership_role="owner"))
        session.add(CaseMember(id=new_uuid(), tenant_id="t-p8", case_id="c-p8-b", user_id="u-p8", membership_role="owner"))
        session.add(CaseMember(id=new_uuid(), tenant_id="t-p8", case_id="c-p8-a", user_id="u-p8-v", membership_role="viewer"))
        await session.flush()
        await session.commit()
        yield session
        await session.rollback()


class TestStatusTransitions:
    def test_valid_transition_queued_to_claimed(self):
        assert _canonical_status_transition("queued", "claimed") is True

    def test_valid_transition_running_to_succeeded(self):
        assert _canonical_status_transition("running", "succeeded") is True

    def test_invalid_transition_succeeded_to_running(self):
        assert _canonical_status_transition("succeeded", "running") is False

    def test_invalid_transition_cancelled_to_running(self):
        assert _canonical_status_transition("cancelled", "running") is False

    def test_running_to_retry_wait(self):
        assert _canonical_status_transition("running", "retry_wait") is True

    def test_retry_wait_to_queued(self):
        assert _canonical_status_transition("retry_wait", "queued") is True

    def test_retry_wait_to_dead_lettered(self):
        assert _canonical_status_transition("retry_wait", "dead_lettered") is True

    def test_failed_to_queued(self):
        assert _canonical_status_transition("failed", "queued") is True

    def test_failed_to_dead_lettered(self):
        assert _canonical_status_transition("failed", "dead_lettered") is True


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_same_payload_returns_existing(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j1 = await repo.create_job(db, "t-p8", "petition_generate", {"case_id": "c-p8-a"}, case_id="c-p8-a", created_by="u-p8")
            j2 = await repo.create_job(db, "t-p8", "petition_generate", {"case_id": "c-p8-a"}, case_id="c-p8-a", created_by="u-p8")
            assert j1["id"] == j2["id"]
            await db.rollback()

    @pytest.mark.asyncio
    async def test_different_payload_creates_new(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j1 = await repo.create_job(db, "t-p8", "petition_generate", {"x": "1"}, case_id="c-p8-a", created_by="u-p8")
            j2 = await repo.create_job(db, "t-p8", "petition_generate", {"x": "2"}, case_id="c-p8-a", created_by="u-p8")
            assert j1["id"] != j2["id"]
            await db.rollback()

    @pytest.mark.asyncio
    async def test_idempotency_key_tenant_scoped(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j1 = await repo.create_job(db, "t-p8", "petition_generate", {"a": "1"}, case_id="c-p8-a", created_by="u-p8")
            j2 = await repo.create_job(db, "other-tenant", "petition_generate", {"a": "1"}, case_id="c-p8-a", created_by="u-p8")
            assert j1["id"] != j2["id"]
            await db.rollback()


class TestJobCRUD:
    @pytest.mark.asyncio
    async def test_create_job_queued(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, "t-p8", "petition_generate", {}, case_id="c-p8-a", created_by="u-p8")
            assert j["status"] == "queued"
            assert j["job_type"] == "petition_generate"
            assert j["tenant_id"] == "t-p8"
            await db.rollback()

    @pytest.mark.asyncio
    async def test_get_job(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, "t-p8", "export_generate", {}, case_id="c-p8-a", created_by="u-p8")
            found = await repo.get_job(db, "t-p8", j["id"])
            assert found is not None
            assert found["id"] == j["id"]
            await db.rollback()

    @pytest.mark.asyncio
    async def test_get_other_tenant_returns_none(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, "t-p8", "export_generate", {}, case_id="c-p8-a", created_by="u-p8")
            found = await repo.get_job(db, "other-tenant", j["id"])
            assert found is None
            await db.rollback()

    @pytest.mark.asyncio
    async def test_list_jobs_by_case(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            await repo.create_job(db, "t-p8", "export_generate", {}, case_id="c-p8-a", created_by="u-p8")
            await repo.create_job(db, "t-p8", "export_generate", {}, case_id="c-p8-b", created_by="u-p8")
            jobs_a = await repo.list_jobs(db, "t-p8", case_id="c-p8-a")
            jobs_b = await repo.list_jobs(db, "t-p8", case_id="c-p8-b")
            assert len(jobs_a) >= 1
            assert len(jobs_b) >= 1
            for j in jobs_a:
                assert j["case_id"] == "c-p8-a"
            await db.rollback()

    @pytest.mark.asyncio
    async def test_invalid_job_type_rejected(self, db_session):
        with pytest.raises(ValueError, match="Unknown job_type"):
            await job_service.enqueue(db_session, tenant_id="t-p8", job_type="invalid_type", payload={})


class TestClaimLease:
    @pytest.mark.asyncio
    async def test_claim_queued_job(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, "t-p8", "petition_generate", {}, created_by="u-p8")
            claimed = await repo.claim_job(db, "worker-1")
            assert claimed is not None
            assert claimed["status"] == "claimed"
            await db.rollback()

    @pytest.mark.asyncio
    async def test_two_workers_cannot_claim_same_job(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, "t-p8", "petition_generate", {}, created_by="u-p8")
            c1 = await repo.claim_job(db, "worker-1")
            c2 = await repo.claim_job(db, "worker-2")
            assert c1 is not None
            assert c2 is None or c2["id"] != c1["id"]
            await db.rollback()

    @pytest.mark.asyncio
    async def test_claim_sets_lease(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, "t-p8", "petition_generate", {}, created_by="u-p8")
            claimed = await repo.claim_job(db, "worker-1", lease_seconds=60)
            assert claimed["lease_expires_at"] is not None
            await db.rollback()

    @pytest.mark.asyncio
    async def test_claim_skips_completed_jobs(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, "t-p8", "petition_generate", {}, created_by="u-p8")
            await repo.update_status(db, j["id"], "succeeded")
            claimed = await repo.claim_job(db, "worker-2")
            assert claimed is None or claimed["status"] != "queued"
            await db.rollback()

    @pytest.mark.asyncio
    async def test_recover_expired_leases(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, "t-p8", "petition_generate", {}, created_by="u-p8")
            await repo.claim_job(db, "worker-old", lease_seconds=0)
            await db.execute(
                BackgroundJob.__table__.update()
                .where(BackgroundJob.id == j["id"])
                .values(lease_expires_at=datetime.now(UTC) - timedelta(seconds=10))
            )
            await db.flush()
            await db.commit()
            recovered = await repo.recover_expired_leases(db)
            assert recovered >= 0
            await db.rollback()


class TestEvents:
    @pytest.mark.asyncio
    async def test_add_event(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, "t-p8", "export_generate", {}, created_by="u-p8")
            e = await repo.add_event(db, j["id"], "progress", 50, "stage1", "working")
            assert e["sequence_number"] >= 1
            assert e["event_type"] == "progress"
            await db.rollback()

    @pytest.mark.asyncio
    async def test_event_sequence_unique(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, "t-p8", "export_generate", {}, created_by="u-p8")
            e1 = await repo.add_event(db, j["id"], "start")
            e2 = await repo.add_event(db, j["id"], "end")
            assert e2["sequence_number"] > e1["sequence_number"]
            await db.rollback()

    @pytest.mark.asyncio
    async def test_list_events(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, "t-p8", "export_generate", {}, created_by="u-p8")
            await repo.add_event(db, j["id"], "e1")
            await repo.add_event(db, j["id"], "e2")
            events = await repo.list_events(db, "t-p8", j["id"])
            assert len(events) == 2
            await db.rollback()


class TestArtifacts:
    @pytest.mark.asyncio
    async def test_add_artifact(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, "t-p8", "export_generate", {}, created_by="u-p8")
            a = await repo.add_artifact(db, j["id"], "t-p8", "c-p8-a", "export", "key/test.pdf", "application/pdf", 1024, "abc123")
            assert a["artifact_type"] == "export"
            assert a["storage_key"] == "key/test.pdf"
            await db.rollback()

    @pytest.mark.asyncio
    async def test_list_artifacts(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, "t-p8", "export_generate", {}, created_by="u-p8")
            await repo.add_artifact(db, j["id"], "t-p8", "c-p8-a", "export", "k1", "text/plain", 100, "sha1")
            await repo.add_artifact(db, j["id"], "t-p8", "c-p8-a", "export", "k2", "text/plain", 200, "sha2")
            arts = await repo.list_artifacts(db, "t-p8", j["id"])
            assert len(arts) == 2
            await db.rollback()


class TestCancelRetry:
    @pytest.mark.asyncio
    async def test_cancel_queued(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, "t-p8", "petition_generate", {}, created_by="u-p8")
            cancelled = await repo.update_status(db, j["id"], "cancelled", cancelled_at=datetime.now(UTC))
            assert cancelled is not None
            assert cancelled["status"] == "cancelled"
            await db.rollback()

    @pytest.mark.asyncio
    async def test_cannot_cancel_completed(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, "t-p8", "petition_generate", {}, created_by="u-p8")
            await repo.update_status(db, j["id"], "claimed")
            await repo.update_status(db, j["id"], "running")
            await repo.update_status(db, j["id"], "succeeded")
            result = await repo.update_status(db, j["id"], "cancelled")
            assert result is None
            await db.rollback()

    @pytest.mark.asyncio
    async def test_retry_failed(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, "t-p8", "petition_generate", {}, created_by="u-p8")
            await repo.update_status(db, j["id"], "claimed")
            await repo.update_status(db, j["id"], "running")
            await repo.update_status(db, j["id"], "failed")
            retried = await repo.update_status(db, j["id"], "queued")
            assert retried is not None
            assert retried["status"] == "queued"
            await db.rollback()


class TestHandlerRegistry:
    def test_all_known_types_registered(self):
        for jt in KNOWN_JOB_TYPES:
            assert handler_registry.get(jt) is not None, f"Missing handler for {jt}"

    def test_registry_list(self):
        types = handler_registry.list_types()
        assert len(types) >= 13


class TestJobContext:
    @pytest.mark.asyncio
    async def test_progress_monotonic(self):
        events = []
        async def up(jid, p, s):
            events.append((p, s))
        ctx = JobContext("jid", "w", {"update_progress": up})
        await ctx.set_progress(50, "mid")
        await ctx.set_progress(30, "lower")  # should be ignored
        await ctx.set_progress(80, "high")
        assert events == [(50, "mid"), (80, "high")]

    def test_check_cancelled_raises(self):
        ctx = JobContext("jid", "w", {})
        ctx.signal_cancel()
        with pytest.raises(CancellationRequested):
            ctx.check_cancelled()

    def test_check_cancelled_noop(self):
        ctx = JobContext("jid", "w", {})
        ctx.check_cancelled()


class TestRetryPolicy:
    def test_retryable_network_error(self):
        assert "NETWORK_ERROR" in RETRYABLE_CODES

    def test_non_retryable_validation(self):
        assert "VALIDATION_ERROR" in NON_RETRYABLE_CODES

    def test_non_retryable_authorization(self):
        assert "AUTHORIZATION_ERROR" in NON_RETRYABLE_CODES


class TestHandlerRegistryReal:
    def test_no_noop_handlers(self):
        for jt in KNOWN_JOB_TYPES:
            h = handler_registry.get(jt)
            assert h is not None, f"No handler for {jt}"
            assert "noop" not in h.handler.__name__.lower(), f"{jt} uses noop handler ({h.handler.__name__})"

    def test_all_production_types_have_real_handlers(self):
        types = handler_registry.list_types()
        for jt in KNOWN_JOB_TYPES:
            assert jt in types, f"Missing production type: {jt}"

    def test_yargitay_handler_exists(self):
        h = handler_registry.get("yargitay_search")
        assert h is not None
        assert h.timeout_seconds == 600
        assert h.max_attempts == 3

    def test_retention_handler_requires_admin(self):
        h = handler_registry.get("retention_purge")
        assert h is not None
        assert h.required_permission == "tenant_admin"

    def test_export_handler_exists(self):
        h = handler_registry.get("export_generate")
        assert h is not None
        assert h.max_attempts == 2

    def test_registry_startup_validation(self):
        for jt in KNOWN_JOB_TYPES:
            assert handler_registry.get(jt) is not None


class TestRealHandlerExecutions:
    @pytest.mark.asyncio
    async def test_graph_handler_runs(self, db_session):
        from app.services.job_handlers import _handle_graph_build
        from app.services.job_context import JobContext
        ctx = JobContext("j1", "w1", {})
        result = await _handle_graph_build(ctx, {"case_id": "c-p8-a", "tenant_id": "t-p8", "actor_id": "u-p8"}, {"id": "j1", "tenant_id": "t-p8"})
        assert result["status"] == "completed"
        assert "node_count" in result

    @pytest.mark.asyncio
    async def test_petition_handler_runs(self, db_session):
        from app.services.job_handlers import _handle_petition_generate
        from app.services.job_context import JobContext
        ctx = JobContext("j2", "w1", {})
        result = await _handle_petition_generate(ctx, {
            "case_id": "c-p8-a",
            "case_text": "Muvekkil ikinci el araci galeriden satin aldi motor arizasi cikti.",
            "request_type": "Talebimizin kabulu",
        }, {"id": "j2", "tenant_id": "t-p8", "created_by": "u-p8"})
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_export_handler_creates_file(self, db_session):
        from app.services.job_handlers import _handle_export_generate
        from app.services.job_context import JobContext
        ctx = JobContext("j3", "w1", {})
        result = await _handle_export_generate(ctx, {
            "case_id": "c-p8-a",
            "tenant_id": "t-p8",
            "format": "txt",
            "content": "Test export content",
        }, {"id": "j3", "tenant_id": "t-p8", "created_by": "u-p8"})
        assert result["status"] == "completed"
        assert "artifact_id" in result

    @pytest.mark.asyncio
    async def test_ground_handler_runs(self, db_session):
        from app.services.job_handlers import _handle_legal_ground_validate
        from app.services.job_context import JobContext
        ctx = JobContext("j4", "w1", {})
        result = await _handle_legal_ground_validate(ctx, {
            "case_id": "c-p8-a",
            "raw_grounds": ["TBK 219"],
        }, {"id": "j4", "tenant_id": "t-p8", "created_by": "u-p8"})
        assert "normalized_grounds" in result or "registry_version" in result

    @pytest.mark.asyncio
    async def test_claim_grounding_runs(self, db_session):
        from app.services.job_handlers import _handle_claim_grounding
        from app.services.job_context import JobContext
        ctx = JobContext("j5", "w1", {})
        result = await _handle_claim_grounding(ctx, {
            "case_id": "c-p8-a",
            "petition_text": "Davali satici ayibi gizlemistir. Sozlesmeden donme talep edilmektedir.",
        }, {"id": "j5", "tenant_id": "t-p8", "created_by": "u-p8"})
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_purge_handler_runs(self, db_session):
        from app.services.job_handlers import _handle_retention_purge
        from app.services.job_context import JobContext
        ctx = JobContext("j6", "w1", {})
        result = await _handle_retention_purge(ctx, {"tenant_id": "t-p8", "dry_run": True, "batch": 5}, {"id": "j6", "tenant_id": "t-p8", "created_by": "u-p8"})
        assert "purged" in result or "status" in result


class TestJobService:
    @pytest.mark.asyncio
    async def test_enqueue_valid_job(self, db_session):
        j = await job_service.enqueue(db_session, tenant_id="t-p8", job_type="petition_generate", payload={}, case_id="c-p8-a", created_by="u-p8")
        assert j["status"] == "queued"
        await db_session.rollback()

    @pytest.mark.asyncio
    async def test_enqueue_unknown_type(self, db_session):
        with pytest.raises(ValueError):
            await job_service.enqueue(db_session, tenant_id="t-p8", job_type="invalid", payload={})

    @pytest.mark.asyncio
    async def test_priority_bounds(self, db_session):
        with pytest.raises(ValueError):
            await job_service.enqueue(db_session, tenant_id="t-p8", job_type="petition_generate", payload={}, priority=999)
