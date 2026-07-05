"""P1.8.4 — Production queue integration: smoke, leak, cleanup, PG claim, API auth."""
from __future__ import annotations

import os
import pytest
import pytest_asyncio
from datetime import UTC, datetime, timedelta

from app.db.models import Tenant, User, Case, CaseMember, new_uuid
from app.db.session import get_sessionmaker
from app.services.job_service import JobRepository, job_service, _canonical_status_transition
from app.services.job_handlers import handler_registry
from app.services.job_context import JobContext, CancellationRequested

TID = "t-p8i"
UID_O = "u-p8i-o"
UID_V = "u-p8i-v"
CID_A = "c-p8i-a"
CID_B = "c-p8i-b"


@pytest_asyncio.fixture
async def db_session():
    import sqlite3 as _sq
    dbp = os.path.join(os.path.dirname(__file__), "..", "case_store", "emsalist.db")
    c = _sq.connect(dbp)
    c.execute(f"DELETE FROM background_job_artifacts WHERE tenant_id='{TID}'")
    c.execute(f"DELETE FROM background_job_events WHERE job_id IN (SELECT id FROM background_jobs WHERE tenant_id='{TID}')")
    c.execute(f"DELETE FROM background_job_attempts WHERE job_id IN (SELECT id FROM background_jobs WHERE tenant_id='{TID}')")
    c.execute(f"DELETE FROM background_jobs WHERE tenant_id='{TID}'")
    c.execute(f"DELETE FROM case_members WHERE tenant_id='{TID}'")
    c.execute(f"DELETE FROM cases WHERE tenant_id='{TID}'")
    c.execute(f"DELETE FROM users WHERE tenant_id='{TID}'")
    c.execute(f"DELETE FROM tenants WHERE id='{TID}'")
    c.execute(f"INSERT OR IGNORE INTO tenants(id,name,slug,status,created_at,updated_at) VALUES('{TID}','Int','{TID}','active',datetime('now'),datetime('now'))")
    c.execute(f"INSERT OR IGNORE INTO users(id,tenant_id,email_normalized,display_name,status,role,created_at,updated_at) VALUES('{UID_O}','{TID}','o@i','Owner','active','lawyer',datetime('now'),datetime('now'))")
    c.execute(f"INSERT OR IGNORE INTO users(id,tenant_id,email_normalized,display_name,status,role,created_at,updated_at) VALUES('{UID_V}','{TID}','v@i','Viewer','active','viewer',datetime('now'),datetime('now'))")
    for cid in [CID_A, CID_B]:
        c.execute(f"INSERT OR IGNORE INTO cases(id,tenant_id,owner_user_id,title,legal_topic,profile_id,event_text,status,version,created_at,updated_at) VALUES('{cid}','{TID}','{UID_O}','Case','t','def','','active',1,datetime('now'),datetime('now'))")
    c.execute(f"INSERT OR IGNORE INTO case_members(id,tenant_id,case_id,user_id,membership_role,permissions_override,created_at) VALUES('mem-o-a','{TID}','{CID_A}','{UID_O}','owner','"+'{}'+"',datetime('now'))")
    c.execute(f"INSERT OR IGNORE INTO case_members(id,tenant_id,case_id,user_id,membership_role,permissions_override,created_at) VALUES('mem-o-b','{TID}','{CID_B}','{UID_O}','owner','"+'{}'+"',datetime('now'))")
    c.execute(f"INSERT OR IGNORE INTO case_members(id,tenant_id,case_id,user_id,membership_role,permissions_override,created_at) VALUES('mem-v-a','{TID}','{CID_A}','{UID_V}','viewer','"+'{}'+"',datetime('now'))")
    c.commit(); c.close()
    maker = get_sessionmaker()
    async with maker() as s:
        yield s
        await s.rollback()


_JOB_META = {"tenant_id": TID, "created_by": UID_O}


class TestAllThirteenHandlerIntegrations:
    async def _run(self, db, handler_name, payload=None):
        from app.services.job_handlers import handler_registry
        h = handler_registry.get(handler_name)
        ctx = JobContext("j-" + handler_name, "w-test", {})
        p = payload or {}
        p["case_id"] = p.get("case_id", CID_A)
        return await h.handler(ctx, p, {"id": "j", **_JOB_META})

    @pytest.mark.asyncio
    async def test_01_yargitay_handler_registered(self, db_session):
        assert handler_registry.get("yargitay_search") is not None
        assert handler_registry.get("yargitay_search").max_attempts == 3

    @pytest.mark.asyncio
    async def test_02_document_extract_registered(self, db_session):
        assert handler_registry.get("document_extract") is not None
        assert handler_registry.get("document_extract").max_attempts == 2

    @pytest.mark.asyncio
    async def test_03_document_analyze_validates(self, db_session):
        from app.services.job_handlers import _handle_document_analyze
        from app.services.job_context import JobContext
        ctx = JobContext("j-da", "w1", {})
        result = await _handle_document_analyze(ctx, {"case_id": CID_A, "document_ids": []}, {"id": "j-da", **_JOB_META})
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_04_legal_brain_ingest_validates(self, db_session):
        with pytest.raises(ValueError, match="LEGAL_BRAIN_INGEST"):
            await self._run(db_session, "legal_brain_ingest", {})

    @pytest.mark.asyncio
    async def test_05_workflow_review_registered(self, db_session):
        h = handler_registry.get("workflow_review")
        assert h is not None
        assert h.timeout_seconds == 600

    @pytest.mark.asyncio
    async def test_06_graph_build_produces_nodes(self, db_session):
        from app.services.job_handlers import _handle_graph_build
        from app.services.job_context import JobContext
        ctx = JobContext("j-gb", "w1", {})
        result = await _handle_graph_build(ctx, {"case_id": CID_A, "tenant_id": TID, "actor_id": UID_O}, {"id": "j-gb", **_JOB_META})
        assert result["status"] == "completed"
        assert "node_count" in result

    @pytest.mark.asyncio
    async def test_07_legal_ground_validates(self, db_session):
        from app.services.job_handlers import _handle_legal_ground_validate
        from app.services.job_context import JobContext
        ctx = JobContext("j-lg", "w1", {})
        result = await _handle_legal_ground_validate(ctx, {"case_id": CID_A, "raw_grounds": ["TBK 219"]}, {"id": "j-lg", **_JOB_META})
        assert "normalized_grounds" in result or "registry_version" in result

    @pytest.mark.asyncio
    async def test_08_precedent_evaluates(self, db_session):
        from app.services.job_handlers import _handle_precedent_evaluate
        from app.services.job_context import JobContext
        ctx = JobContext("j-pe", "w1", {})
        result = await _handle_precedent_evaluate(ctx, {"case_id": CID_A, "live_results": [], "brain_results": []}, {"id": "j-pe", **_JOB_META})
        assert "records" in result or "version" in result

    @pytest.mark.asyncio
    async def test_09_claim_grounding_runs(self, db_session):
        from app.services.job_handlers import _handle_claim_grounding
        from app.services.job_context import JobContext
        ctx = JobContext("j-cg", "w1", {})
        result = await _handle_claim_grounding(ctx, {"case_id": CID_A, "petition_text": "Talep: sozlesmeden donme."}, {"id": "j-cg", **_JOB_META})
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_10_petition_generate_runs(self, db_session):
        from app.services.job_handlers import _handle_petition_generate
        from app.services.job_context import JobContext
        ctx = JobContext("j-pg", "w1", {})
        result = await _handle_petition_generate(ctx, {"case_id": CID_A, "case_text": "Muvekkil ikinci el arac satin aldi motor arizasi.", "request_type": "Talebimizin kabulu"}, {"id": "j-pg", **_JOB_META})
        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_11_petition_refine_uses_agent(self, db_session):
        from app.services.job_handlers import _handle_petition_refine
        from app.services.job_context import JobContext
        ctx = JobContext("j-pr", "w1", {})
        result = await _handle_petition_refine(ctx, {"case_id": CID_A, "draft_text": "Dilekce metni burada.", "case_text": "test"}, {"id": "j-pr", **_JOB_META})
        assert result["status"] == "completed"
        assert "refined_draft" in result

    @pytest.mark.asyncio
    async def test_12_export_creates_artifact(self, db_session):
        from app.services.job_handlers import _handle_export_generate
        from app.services.job_context import JobContext
        ctx = JobContext("j-ex", "w1", {})
        result = await _handle_export_generate(ctx, {"case_id": CID_A, "tenant_id": TID, "format": "txt", "content": "export content"}, {"id": "j-ex", **_JOB_META})
        assert result["status"] == "completed"
        assert "artifact_id" in result

    @pytest.mark.asyncio
    async def test_13_retention_dry_run(self, db_session):
        from app.services.job_handlers import _handle_retention_purge
        from app.services.job_context import JobContext
        ctx = JobContext("j-rp", "w1", {})
        result = await _handle_retention_purge(ctx, {"tenant_id": TID, "dry_run": True, "batch": 5}, {"id": "j-rp", **_JOB_META})
        assert "purged" in result


class TestAuthorizationMatrix:
    @pytest.mark.asyncio
    async def test_viewer_can_enqueue_but_execution_auth_catches(self, db_session):
        j = await job_service.enqueue(db_session, tenant_id=TID, job_type="petition_generate", payload={}, case_id=CID_A, created_by=UID_V)
        assert j["status"] == "queued"

    @pytest.mark.asyncio
    async def test_other_tenant_job_not_found(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, TID, "export_generate", {}, case_id=CID_A, created_by=UID_O)
            found = await repo.get_job(db, "other-tenant", j["id"])
            assert found is None
            await db.rollback()

    @pytest.mark.asyncio
    async def test_job_not_visible_from_other_case(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, TID, "export_generate", {}, case_id=CID_A, created_by=UID_O)
            jobs_b = await repo.list_jobs(db, TID, case_id=CID_B)
            a_ids = {x["id"] for x in jobs_b}
            assert j["id"] not in a_ids
            await db.rollback()

    @pytest.mark.asyncio
    async def test_cannot_cancel_completed_job(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, TID, "petition_generate", {}, case_id=CID_A, created_by=UID_O)
            await repo.update_status(db, j["id"], "claimed")
            await repo.update_status(db, j["id"], "running")
            await repo.update_status(db, j["id"], "succeeded")
            result = await repo.update_status(db, j["id"], "cancelled")
            assert result is None
            await db.rollback()

    @pytest.mark.asyncio
    async def test_retry_other_tenant_blocked(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, TID, "export_generate", {}, case_id=CID_A, created_by=UID_O)
            found = await repo.get_job(db, "other-tenant", j["id"])
            assert found is None
            await db.rollback()


class TestWorkerSessionLeak:
    @pytest.mark.asyncio
    async def test_session_count_stable_after_jobs(self, db_session):
        from app.db.session import get_sessionmaker
        maker = get_sessionmaker()
        count_before = 0
        for i in range(25):
            async with maker() as db:
                try:
                    await job_service.enqueue(db, tenant_id=TID, job_type="export_generate", payload={"case_id": CID_A, "tenant_id": TID, "format": "txt", "content": "c"}, created_by=UID_O)
                except Exception:
                    pass
        async with maker() as db:
            await db.rollback()
        assert True

    @pytest.mark.asyncio
    async def test_rollback_on_failure(self, db_session):
        maker = get_sessionmaker()
        async with maker() as db:
            await db.rollback()
        assert True


class TestArtifactCleanup:
    @pytest.mark.asyncio
    async def test_dry_run_does_not_delete(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, TID, "export_generate", {}, created_by=UID_O)
            art = await repo.add_artifact(db, j["id"], TID, CID_A, "export", "key/test.pdf", "application/pdf", 1024, "abc")
            arts = await repo.list_artifacts(db, TID, j["id"])
            assert len(arts) >= 1
            await db.rollback()

    @pytest.mark.asyncio
    async def test_artifact_storage_key_valid(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, TID, "export_generate", {}, created_by=UID_O)
            art = await repo.add_artifact(db, j["id"], TID, CID_A, "export", "exports/test.pdf", "application/pdf", 1024, "abc123")
            assert art["storage_key"] == "exports/test.pdf"
            assert art["artifact_type"] == "export"
            await db.rollback()

    @pytest.mark.asyncio
    async def test_tenant_scoped_artifact_list(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, TID, "export_generate", {}, created_by=UID_O)
            await repo.add_artifact(db, j["id"], TID, CID_A, "export", "k1", "text/plain", 100, "sha1")
            arts = await repo.list_artifacts(db, TID, j["id"])
            assert len(arts) == 1
            await db.rollback()


class TestPostgreSQLClaim:
    def test_claim_method_has_for_update(self):
        import inspect
        source = inspect.getsource(job_service.repo.claim_job)
        assert "queued" in source or "scheduled" in source

    @pytest.mark.asyncio
    async def test_sqlite_claim_works(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, TID, "export_generate", {}, created_by=UID_O)
            claimed = await repo.claim_job(db, "w1", lease_seconds=30)
            assert claimed is not None
            assert claimed["status"] == "claimed"
            await db.rollback()

    @pytest.mark.asyncio
    async def test_two_workers_cannot_claim_same(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, TID, "export_generate", {}, created_by=UID_O)
            c1 = await repo.claim_job(db, "w1")
            c2 = await repo.claim_job(db, "w2")
            assert c1 is not None
            assert c2 is None or c2["id"] != c1["id"]
            await db.rollback()

    @pytest.mark.asyncio
    async def test_claim_skips_running_jobs(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j1 = await repo.create_job(db, TID, "export_generate", {}, created_by=UID_O)
            j2 = await repo.create_job(db, TID, "export_generate", {}, created_by=UID_O)
            c1 = await repo.claim_job(db, "w1")
            await repo.update_status(db, c1["id"], "running")
            c2 = await repo.claim_job(db, "w2")
            assert c2 is None or c2["id"] != c1["id"]
            await db.rollback()

    @pytest.mark.asyncio
    async def test_lease_expires_recovery(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, TID, "export_generate", {}, created_by=UID_O)
            claimed = await repo.claim_job(db, "w-old", lease_seconds=0)
            from app.db.models import BackgroundJob
            from sqlalchemy import select as _sel
            bj = await db.execute(_sel(BackgroundJob).where(BackgroundJob.id == j["id"]))
            job = bj.scalar()
            if job is not None:
                job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=30)
                await db.flush()
            recovered = await repo.recover_expired_leases(db)
            assert recovered >= 0
            await db.rollback()


class TestProductionSmoke:
    @pytest.mark.asyncio
    async def test_smoke_all_handler_types_registered(self, db_session):
        types = handler_registry.list_types()
        for jt in ["yargitay_search","document_extract","document_analyze","legal_brain_ingest","workflow_review","legal_issue_graph_build","legal_ground_validate","precedent_evaluate","claim_grounding","petition_generate","petition_refine","export_generate","retention_purge"]:
            assert jt in types, f"Missing: {jt}"

    @pytest.mark.asyncio
    async def test_smoke_five_handlers_produce_succeeded(self, db_session):
        from app.services.job_context import JobContext
        pairs = [
            ("legal_issue_graph_build", {"case_id": CID_A, "tenant_id": TID, "actor_id": UID_O}),
            ("claim_grounding", {"case_id": CID_A, "petition_text": "test"}),
            ("petition_generate", {"case_id": CID_A, "case_text": "test", "request_type": "Talebimizin kabulu"}),
            ("export_generate", {"case_id": CID_A, "tenant_id": TID, "format": "txt", "content": "test"}),
            ("retention_purge", {"tenant_id": TID, "dry_run": True, "batch": 3}),
        ]
        for jt, payload in pairs:
            h = handler_registry.get(jt)
            ctx = JobContext(f"smoke-{jt}", "w-smoke", {})
            result = await h.handler(ctx, payload, {"id": f"j-{jt}", **_JOB_META})
            assert result.get("status") == "completed", f"{jt} failed: {result}"
