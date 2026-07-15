"""P2.8B12 — current-source rebuild and transaction rollback executable proof."""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from sqlalchemy import delete, select

from app.db.models import (
    BurdenOfProof, Case, CaseFact, Counterargument,
    LegalIssue, LegalIssueFactLink, LegalIssueSourceLink,
    LegalReasoningRun, MemoryRevision, SourceParagraph,
    SourceRecord, SourceVersion,
)
from app.db.session import get_sessionmaker
from app.main import app
from app.services.legal_reasoning_service import (
    LegalReasoningService, legal_reasoning_service,
)

_created_cases: list[str] = []
_created_source_ids: list[dict[str, list[str]]] = []


# ── controlled test doubles ──────────────────────────────────────────────────


class _ControlledSourceAcquirer:
    def __init__(self):
        self.results: list[dict[str, str]] = []

    def set(self, sources: list[dict[str, str]]):
        self.results = list(sources)

    async def acquire(self, db, *, case_id, security_context):
        return list(self.results)


class _LifecycleProvider:
    provider_name = "lifecycle_provider"
    model_version = "1"

    async def analyze(self, payload):
        return {
            "issues": [{
                "issue_code": "contract_dispute",
                "title": "Sozlesme uyusmazligi",
                "description": "Test lifecycle issue.",
                "status": "proposed",
                "parent_code": None,
            }],
            "counterarguments": [{
                "issue_code": "contract_dispute",
                "category": "alternative_fact_interpretation",
                "title": "Karsi taraf savunmasi",
                "rationale": "Test rationale",
                "basis": "Test basis",
            }],
            "safe_summary": {"kind": "lifecycle_test"},
        }


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


@pytest_asyncio.fixture(autouse=True)
async def lifecycle_deps():
    old_provider = legal_reasoning_service.provider
    old_acquirer = legal_reasoning_service.source_acquirer
    acquirer = _ControlledSourceAcquirer()
    legal_reasoning_service.provider = _LifecycleProvider()
    legal_reasoning_service.source_acquirer = acquirer
    yield acquirer
    legal_reasoning_service.provider = old_provider
    legal_reasoning_service.source_acquirer = old_acquirer
    maker = get_sessionmaker()
    async with maker() as session:
        for case_id in _created_cases:
            for model in (BurdenOfProof, Counterargument, LegalReasoningRun,
                          MemoryRevision, LegalIssueSourceLink,
                          LegalIssueFactLink, LegalIssue, CaseFact):
                await session.execute(
                    delete(model).where(model.case_id == case_id)
                )
            await session.execute(
                delete(Case).where(Case.id == case_id)
            )
        await session.flush()
        for entry in _created_source_ids:
            for para_id in entry.get("paragraph_ids", []):
                await session.execute(
                    delete(SourceParagraph).where(
                        SourceParagraph.id == para_id
                    )
                )
            for ver_id in entry.get("version_ids", []):
                await session.execute(
                    delete(SourceVersion).where(
                        SourceVersion.id == ver_id
                    )
                )
            for rec_id in entry.get("record_ids", []):
                await session.execute(
                    delete(SourceRecord).where(
                        SourceRecord.id == rec_id
                    )
                )
        await session.commit()
    _created_cases.clear()
    _created_source_ids.clear()


async def _case(client: AsyncClient) -> str:
    response = await client.post(
        "/api/v1/cases",
        json={"title": f"P2.8B12 {uuid.uuid4().hex[:8]}"},
    )
    assert response.status_code == 201
    case_id = response.json()["id"]
    _created_cases.append(case_id)
    return case_id


def _maker():
    return get_sessionmaker()


async def _seed_source_v1() -> tuple[str, str, str]:
    rec_id = f"src-b12-{uuid.uuid4().hex[:8]}"
    ver_id = f"svr-b12-{uuid.uuid4().hex[:8]}"
    para_id = f"sp-b12-{uuid.uuid4().hex[:8]}"

    async with _maker()() as session:
        rec = SourceRecord(
            id=rec_id, source_type="legislation",
            canonical_key=f"b12-key-{uuid.uuid4().hex[:12]}",
            title="Test Statute V1", verification_status="document_verified",
            current_version_id=ver_id,
        )
        ver = SourceVersion(
            id=ver_id, source_record_id=rec_id, version_label="v1",
            content_hash=f"hash-{uuid.uuid4().hex[:8]}",
            normalized_text="V1 article 1 text",
        )
        session.add_all([rec, ver])
        await session.flush()
        para = SourceParagraph(
            id=para_id, source_version_id=ver_id, paragraph_index=1,
            text="V1 article 1 text",
            text_hash=f"th-{uuid.uuid4().hex[:8]}",
        )
        session.add(para)
        await session.commit()

    _created_source_ids.append({
        "record_ids": [rec_id], "version_ids": [ver_id],
        "paragraph_ids": [para_id],
    })
    return rec_id, ver_id, para_id


async def _seed_source_v2(rec_id: str) -> tuple[str, str]:
    ver2_id = f"sv2-b12-{uuid.uuid4().hex[:8]}"
    para2_id = f"sp2-b12-{uuid.uuid4().hex[:8]}"

    async with _maker()() as session:
        ver2 = SourceVersion(
            id=ver2_id, source_record_id=rec_id, version_label="v2",
            content_hash=f"hash2-{uuid.uuid4().hex[:8]}",
            normalized_text="V2 article 1 text",
        )
        session.add(ver2)
        rec = await session.get(SourceRecord, rec_id)
        rec.current_version_id = ver2_id
        await session.flush()
        para2 = SourceParagraph(
            id=para2_id, source_version_id=ver2_id, paragraph_index=1,
            text="V2 article 1 text",
            text_hash=f"th2-{uuid.uuid4().hex[:8]}",
        )
        session.add(para2)
        await session.commit()

    _created_source_ids.append({
        "record_ids": [], "version_ids": [ver2_id],
        "paragraph_ids": [para2_id],
    })
    return ver2_id, para2_id


# ── PROOF A: V1 → V2 current-source rebuild ──────────────────────────────────


@pytest.mark.asyncio
async def test_v1_to_v2_current_source_rebuild_lifecycle(client, lifecycle_deps):
    """Proof A: complete v1->v2 rebuild lifecycle with current-version sources."""
    acquirer = lifecycle_deps
    rec_id, v1_id, p1_id = await _seed_source_v1()

    acquirer.set([{
        "source_record_id": rec_id,
        "source_version_id": v1_id,
        "source_paragraph_id": p1_id,
        "effective_trust": "needs_review",
    }])

    case_id = await _case(client)

    # -- v1 rebuild --
    rebuilt = await client.post(
        f"/api/v1/cases/{case_id}/legal-issues/rebuild", json={},
    )
    assert rebuilt.status_code == 200
    assert rebuilt.json()["status"] == "succeeded"

    async with _maker()() as session:
        source_links = (await session.execute(
            select(LegalIssueSourceLink).where(
                LegalIssueSourceLink.case_id == case_id,
                LegalIssueSourceLink.deleted_at.is_(None),
            )
        )).scalars().all()
        assert len(source_links) >= 1
        assert any(
            sl.source_record_id == rec_id
            and sl.source_version_id == v1_id
            and sl.source_paragraph_id == p1_id
            for sl in source_links
        ), "v1 source link not found"

        runs = (await session.execute(
            select(LegalReasoningRun).where(
                LegalReasoningRun.case_id == case_id,
                LegalReasoningRun.status == "succeeded",
            )
        )).scalars().all()
        assert len(runs) == 1
        v1_run = runs[0]
        assert v1_run.source_fingerprint, "v1 run must have source fingerprint"

        v1_source_fingerprint = v1_run.source_fingerprint

    # -- advance to v2 --
    v2_id, p2_id = await _seed_source_v2(rec_id)

    # Verify source fingerprint changed after version update
    async with _maker()() as session:
        from app.services.legal_reasoning_reproducibility import (
            compute_case_source_fingerprint,
        )
        current_fp = await compute_case_source_fingerprint(
            session, tenant_id="local", case_id=case_id,
        )
        assert current_fp != v1_source_fingerprint, (
            "source fingerprint must differ after v2 becomes current"
        )

    # -- v2 rebuild --
    acquirer.set([{
        "source_record_id": rec_id,
        "source_version_id": v2_id,
        "source_paragraph_id": p2_id,
        "effective_trust": "needs_review",
    }])

    rebuilt2 = await client.post(
        f"/api/v1/cases/{case_id}/legal-issues/rebuild", json={},
    )
    assert rebuilt2.status_code == 200
    assert rebuilt2.json()["status"] == "succeeded"

    async with _maker()() as session:
        active_links = (await session.execute(
            select(LegalIssueSourceLink).where(
                LegalIssueSourceLink.case_id == case_id,
                LegalIssueSourceLink.deleted_at.is_(None),
            )
        )).scalars().all()
        assert any(
            sl.source_record_id == rec_id
            and sl.source_version_id == v2_id
            and sl.source_paragraph_id == p2_id
            for sl in active_links
        ), "v2 source link not found in active links"

        v1_active = any(
            sl.source_record_id == rec_id
            and sl.source_version_id == v1_id
            for sl in active_links
        )
        assert not v1_active, "v1 link must not be active after v2 rebuild"

        runs = (await session.execute(
            select(LegalReasoningRun).where(
                LegalReasoningRun.case_id == case_id,
                LegalReasoningRun.status == "succeeded",
            ).order_by(LegalReasoningRun.completed_at)
        )).scalars().all()
        assert len(runs) == 2
        assert runs[1].source_fingerprint != v1_source_fingerprint, (
            "v2 fingerprint must differ from v1"
        )

        v2_source_fingerprint = runs[1].source_fingerprint
        assert v2_source_fingerprint, "v2 run must have source fingerprint"


# ── PROOF B: late-graph-mutation rollback ────────────────────────────────────


@pytest.mark.asyncio
async def test_late_graph_mutation_rollback(client, lifecycle_deps):
    """Proof B: late failure after graph mutation rolls back completely."""
    acquirer = lifecycle_deps
    rec_id, v1_id, p1_id = await _seed_source_v1()

    acquirer.set([{
        "source_record_id": rec_id,
        "source_version_id": v1_id,
        "source_paragraph_id": p1_id,
        "effective_trust": "needs_review",
    }])

    case_id = await _case(client)

    # -- baseline successful rebuild --
    rebuilt = await client.post(
        f"/api/v1/cases/{case_id}/legal-issues/rebuild", json={},
    )
    assert rebuilt.status_code == 200

    async with _maker()() as session:
        baseline_runs = (await session.execute(
            select(LegalReasoningRun).where(
                LegalReasoningRun.case_id == case_id,
            )
        )).scalars().all()
        assert len(baseline_runs) == 1
        baseline_run_count = len(baseline_runs)

        baseline_issues = (await session.execute(
            select(LegalIssue).where(
                LegalIssue.case_id == case_id,
                LegalIssue.deleted_at.is_(None),
            )
        )).scalars().all()
        baseline_issue_versions = {
            issue.issue_code: issue.version for issue in baseline_issues
        }

        baseline_source_links = (await session.execute(
            select(LegalIssueSourceLink).where(
                LegalIssueSourceLink.case_id == case_id,
            )
        )).scalars().all()

        baseline_counterargs = (await session.execute(
            select(Counterargument).where(
                Counterargument.case_id == case_id,
            )
        )).scalars().all()

        baseline_burdens = (await session.execute(
            select(BurdenOfProof).where(
                BurdenOfProof.case_id == case_id,
            )
        )).scalars().all()

    # -- inject late-failing service --
    original_replace = legal_reasoning_service._replace_source_links

    async def _failing_replace(db, tenant_id, case_id, issue_id, sources):
        raise RuntimeError("injected_late_graph_failure")

    legal_reasoning_service._replace_source_links = _failing_replace

    error_occurred = False
    try:
        await client.post(
            f"/api/v1/cases/{case_id}/legal-issues/rebuild", json={},
        )
    except RuntimeError as exc:
        assert "injected_late_graph_failure" in str(exc)
        error_occurred = True
    finally:
        legal_reasoning_service._replace_source_links = original_replace

    assert error_occurred, "late graph failure was not raised"

    # -- fresh-session rollback assertions --
    async with _maker()() as session:
        current_runs = (await session.execute(
            select(LegalReasoningRun).where(
                LegalReasoningRun.case_id == case_id,
            )
        )).scalars().all()
        assert len(current_runs) == baseline_run_count, (
            "no new run persisted after failure"
        )
        assert current_runs[0].status == "succeeded", (
            "previous successful run still exists"
        )

        current_issues = (await session.execute(
            select(LegalIssue).where(
                LegalIssue.case_id == case_id,
                LegalIssue.deleted_at.is_(None),
            )
        )).scalars().all()
        for issue in current_issues:
            assert (
                issue.version == baseline_issue_versions[issue.issue_code]
            ), f"{issue.issue_code} version rolled back"

        current_source_links = (await session.execute(
            select(LegalIssueSourceLink).where(
                LegalIssueSourceLink.case_id == case_id,
            )
        )).scalars().all()
        assert len(current_source_links) == len(baseline_source_links), (
            "source links unchanged after rollback"
        )

        current_counterargs = (await session.execute(
            select(Counterargument).where(
                Counterargument.case_id == case_id,
            )
        )).scalars().all()
        assert len(current_counterargs) == len(baseline_counterargs), (
            "counterarguments unchanged after rollback"
        )

        current_burdens = (await session.execute(
            select(BurdenOfProof).where(
                BurdenOfProof.case_id == case_id,
            )
        )).scalars().all()
        assert len(current_burdens) == len(baseline_burdens), (
            "burdens unchanged after rollback"
        )
