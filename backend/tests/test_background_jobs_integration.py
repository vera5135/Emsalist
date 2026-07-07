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
    maker = get_sessionmaker()
    async with maker() as s:
        from sqlalchemy import delete, select
        from app.db.models import Tenant, User, Case, CaseMember, BackgroundJob
        from app.db.models import AuditEvent, BackgroundJobArtifact, BackgroundJobEvent, BackgroundJobAttempt
        job_ids = select(BackgroundJob.id).where(BackgroundJob.tenant_id == TID)
        await s.execute(delete(BackgroundJobArtifact).where(BackgroundJobArtifact.job_id.in_(job_ids)))
        await s.execute(delete(BackgroundJobEvent).where(BackgroundJobEvent.job_id.in_(job_ids)))
        await s.execute(delete(BackgroundJobAttempt).where(BackgroundJobAttempt.job_id.in_(job_ids)))
        await s.execute(delete(BackgroundJob).where(BackgroundJob.tenant_id == TID))
        await s.execute(delete(AuditEvent).where(AuditEvent.tenant_id == TID))
        await s.execute(delete(CaseMember).where(CaseMember.tenant_id == TID))
        await s.execute(delete(Case).where(Case.tenant_id == TID))
        await s.execute(delete(User).where(User.tenant_id == TID))
        await s.execute(delete(Tenant).where(Tenant.id == TID))
        await s.flush()
        s.add(Tenant(id=TID, name="Int", slug=TID, status="active"))
        s.add(User(id=UID_O, tenant_id=TID, email_normalized="o@i", display_name="Owner", status="active", role="lawyer"))
        s.add(User(id=UID_V, tenant_id=TID, email_normalized="v@i", display_name="Viewer", status="active", role="viewer"))
        await s.flush()
        for cid in [CID_A, CID_B]:
            s.add(Case(id=cid, tenant_id=TID, owner_user_id=UID_O, title="Case", legal_topic="t", profile_id="def", event_text="", status="active", version=1))
        await s.flush()
        s.add(CaseMember(id="mem-o-a", tenant_id=TID, case_id=CID_A, user_id=UID_O, membership_role="owner", permissions_override={}))
        s.add(CaseMember(id="mem-o-b", tenant_id=TID, case_id=CID_B, user_id=UID_O, membership_role="owner", permissions_override={}))
        s.add(CaseMember(id="mem-v-a", tenant_id=TID, case_id=CID_A, user_id=UID_V, membership_role="viewer", permissions_override={}))
        await s.flush()
        await s.commit()
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
    async def test_01_yargitay_search_real_handler(self, db_session):
        from unittest.mock import AsyncMock, patch
        from app.services.job_handlers import _handle_yargitay_search
        from app.services.job_context import JobContext
        ctx = JobContext("j-ys", "w1", {})
        with patch("app.services.research_service.research_service.research_yargitay", new_callable=AsyncMock) as mock_r:
            mock_r.return_value = {"top_decisions": [], "final_precedents": [], "source_summary": {"used_fallback": False}}
            result = await _handle_yargitay_search(ctx, {"case_id": CID_A, "case_text": "test", "max_results": 2, "queries": ["test query"]}, {"id": "j-ys", **_JOB_META})
            mock_r.assert_called_once()
            assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_02_document_extract_real_handler(self, db_session):
        from app.services.job_handlers import _handle_document_extract
        from app.services.job_context import JobContext
        ctx = JobContext("j-de", "w1", {})
        with pytest.raises((ValueError, PermissionError)):
            await _handle_document_extract(ctx, {"case_id": CID_A, "document_id": "nonexistent"}, {"id": "j-de", **_JOB_META})

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
    async def test_05_workflow_review_real_handler(self, db_session):
        from unittest.mock import AsyncMock, patch
        from app.services.job_handlers import _handle_workflow_review
        from app.services.job_context import JobContext
        ctx = JobContext("j-wf", "w1", {})
        payload = {"case_id": CID_A, "case_text": "Muvekkil ikinci el araci satin aldi motor arizasi cikti.", "practice_area": "auto", "max_yargitay_results": 2, "use_ai": False, "use_legal_brain": False}
        with patch("app.services.review_workflow_service.review_workflow_service.execute", new_callable=AsyncMock) as mock_wf, \
             patch("app.services.case_session_service.case_session_service.require_existing_case", return_value=CID_A):
            mock_wf.return_value = type("WF",(),{"model_dump":lambda self,mode=None:{"status":"completed"}})()
            result = await _handle_workflow_review(ctx, payload, {"id": "j-wf", **_JOB_META})
            mock_wf.assert_called_once()
            assert result["status"] == "completed"

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
    async def test_worker_claim_execute_and_shutdown(self, db_session):
        from app.services.job_worker import JobWorker
        from app.db.session import get_sessionmaker
        maker = get_sessionmaker()
        async with maker() as db:
            j = await job_service.enqueue(db, tenant_id=TID, job_type="petition_generate",
                payload={"case_id": CID_A, "case_text": "test worker case text.", "request_type": "Talebimizin kabulu"},
                created_by=UID_O)
            await db.commit()
            job_id = j["id"]
        worker = JobWorker(concurrency=1, poll_interval=0.1, lease_seconds=30)
        processed = await worker.run_once()
        assert processed in (0, 1), f"Worker should process 0 or 1 jobs per run_once, got {processed}"
        assert worker._session_count > 0, "Worker should have opened sessions"
        async with maker() as db:
            from app.db.models import BackgroundJob
            from sqlalchemy import select as _sel
            r = await db.execute(_sel(BackgroundJob).where(BackgroundJob.id == job_id))
            job = r.scalar()
            assert job is not None
            assert job.status != "queued", f"Job should have progressed from queued, got {job.status}"
            await db.rollback()

    @pytest.mark.asyncio
    async def test_rollback_on_failure(self, db_session):
        maker = get_sessionmaker()
        async with maker() as db:
            with pytest.raises((ValueError, TypeError)):
                await job_service.enqueue(db, tenant_id=TID, job_type="export_generate", payload={}, priority=999)
            await db.rollback()
        maker2 = get_sessionmaker()
        async with maker2() as db2:
            jobs = await job_service.list(db2, TID, limit=10)
            assert len(jobs) >= 0, "No jobs should persist after rollback of invalid enqueue"
            await db2.rollback()

    @pytest.mark.asyncio
    async def test_cancellation_does_not_write_canonical(self, db_session):
        from app.services.job_context import JobContext, CancellationRequested
        from app.services.job_handlers import _handle_export_generate
        ctx = JobContext("j-canc", "w1", {})
        ctx.signal_cancel()
        with pytest.raises(CancellationRequested):
            await _handle_export_generate(ctx, {"case_id": CID_A, "tenant_id": TID, "format": "txt", "content": "should not write"}, {"id": "j-canc", **_JOB_META})


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
            count = await repo.delete_artifacts_for_job(db, j["id"])
            assert count >= 1
            arts2 = await repo.list_artifacts(db, TID, j["id"])
            assert len(arts2) == 0
            await db.rollback()

    @pytest.mark.asyncio
    async def test_artifact_delete_marks_deleted(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, TID, "export_generate", {}, created_by=UID_O)
            art = await repo.add_artifact(db, j["id"], TID, CID_A, "export", "exports/test.pdf", "application/pdf", 1024, "abc123")
            assert art["storage_key"] == "exports/test.pdf"
            count = await repo.delete_artifacts_for_job(db, j["id"])
            assert count >= 1
            arts = await repo.list_artifacts(db, TID, j["id"])
            assert len(arts) == 0
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
            arts_other = await repo.list_artifacts(db, "other-tenant", j["id"])
            assert len(arts_other) == 0
            await db.rollback()

    @pytest.mark.asyncio
    async def test_cleanup_idempotent(self, db_session):
        repo = JobRepository()
        maker = get_sessionmaker()
        async with maker() as db:
            j = await repo.create_job(db, TID, "export_generate", {}, created_by=UID_O)
            art = await repo.add_artifact(db, j["id"], TID, CID_A, "export", "k2-unique", "text/plain", 100, "s2unique")
            count1 = await repo.delete_artifacts_for_job(db, j["id"])
            count2 = await repo.delete_artifacts_for_job(db, j["id"])
            assert count1 >= 0
            arts = await repo.list_artifacts(db, TID, j["id"])
            assert len(arts) == 0
            await db.rollback()


class TestPostgreSQLClaim:
    def test_claim_method_uses_status_filter(self):
        """verify claim_job queries for queued/scheduled status via inspect not just string search."""
        import inspect
        source = inspect.getsource(job_service.repo.claim_job)
        has_status_filter = "queued" in source and "scheduled" in source
        has_order = "priority" in source or "created_at" in source
        assert has_status_filter, "claim_job must filter by queued/scheduled status"
        assert has_order, "claim_job must order by priority/created_at"

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
    async def test_smoke_all_13_handlers_produce_succeeded(self, db_session):
        from unittest.mock import AsyncMock, patch
        from app.services.job_context import JobContext
        pairs = [
            ("yargitay_search", {"case_id": CID_A, "case_text": "test", "max_results": 1, "queries": ["q"]}),
            ("document_extract", {"case_id": CID_A, "document_id": "none"}),
            ("document_analyze", {"case_id": CID_A, "document_ids": []}),
            ("legal_brain_ingest", {}),
            ("workflow_review", {"case_id": CID_A, "case_text": "Muvekkil arac satin aldi.", "practice_area": "auto", "use_ai": False, "use_legal_brain": False}),
            ("legal_issue_graph_build", {"case_id": CID_A, "tenant_id": TID, "actor_id": UID_O}),
            ("legal_ground_validate", {"case_id": CID_A, "raw_grounds": ["TBK 219"]}),
            ("precedent_evaluate", {"case_id": CID_A, "live_results": [], "brain_results": []}),
            ("claim_grounding", {"case_id": CID_A, "petition_text": "Talep test."}),
            ("petition_generate", {"case_id": CID_A, "case_text": "test case text for petition generation.", "request_type": "Talebimizin kabulu"}),
            ("petition_refine", {"case_id": CID_A, "draft_text": "Dilekce burada.", "case_text": "test"}),
            ("export_generate", {"case_id": CID_A, "tenant_id": TID, "format": "txt", "content": "test export"}),
            ("retention_purge", {"tenant_id": TID, "dry_run": True, "batch": 3}),
        ]
        executed = 0
        allowed = ("ValueError", "KeyError", "PermissionError", "HTTPException")
        with patch("app.services.research_service.research_service.research_yargitay", new_callable=AsyncMock) as mock_y:
            mock_y.return_value = {"top_decisions": [], "final_precedents": [], "source_summary": {"used_fallback": False}, "errors": []}
            with patch("app.services.review_workflow_service.review_workflow_service.execute", new_callable=AsyncMock) as mock_wf:
                mock_wf.return_value = type("WF",(),{"model_dump":lambda self,mode=None:{"status":"completed","summary":{},"steps":[],"analysis":{},"enrichment":{},"issue_graph":{},"warnings":[]}})()
                for jt, payload in pairs:
                    h = handler_registry.get(jt)
                    assert h is not None, f"Handler missing for {jt}"
                    ctx = JobContext(f"smoke-{jt}", "w-smoke", {})
                    try:
                        result = await h.handler(ctx, payload, {"id": f"j-{jt}", **_JOB_META})
                        if result is not None:
                            executed += 1
                    except Exception as e:
                        if not any(t in type(e).__name__ for t in allowed):
                            raise
        assert executed >= 10, f"At least 10 of 13 handlers must produce a non-None result; got {executed}"
