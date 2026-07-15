"""P2.8B12C -- complete rebuild lifecycle proof with current-state, provider-input and late-rollback."""
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

    def __init__(self):
        self.payloads: list[dict] = []

    async def analyze(self, payload):
        self.payloads.append(payload)
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


class _PhaseAwareProvider:
    """Returns different candidates depending on call phase."""

    provider_name = "phase_aware"
    model_version = "2"

    def __init__(self):
        self._phase = 1

    def advance(self):
        self._phase = 2

    async def analyze(self, payload):
        if self._phase == 1:
            return {
                "issues": [{
                    "issue_code": "contract_dispute",
                    "title": "Sozlesme uyusmazligi",
                    "description": "Phase 1 description.",
                    "status": "proposed",
                    "parent_code": None,
                }],
                "counterarguments": [{
                    "issue_code": "contract_dispute",
                    "category": "alternative_fact_interpretation",
                    "title": "Baseline counterargument",
                    "rationale": "Baseline rationale",
                    "basis": "Baseline basis",
                }],
                "safe_summary": {"kind": "phase_1"},
            }
        else:
            return {
                "issues": [
                    {
                        "issue_code": "defective_vehicle",
                        "title": "Ayıplı araç uyuşmazlığı",
                        "description": "Phase 2 defect root.",
                        "status": "proposed",
                        "parent_code": None,
                    },
                    {
                        "issue_code": "defect",
                        "title": "Ayıbın varlığı",
                        "description": "Phase 2 defect child.",
                        "status": "proposed",
                        "parent_code": "defective_vehicle",
                    },
                    {
                        "issue_code": "contract_dispute",
                        "title": "CHANGED title",
                        "description": "CHANGED description",
                        "status": "accepted",
                        "parent_code": None,
                    },
                ],
                "counterarguments": [
                    {
                        "issue_code": "defect",
                        "category": "alternative_fact_interpretation",
                        "title": "Phase 2 counterargument 1",
                        "rationale": "Phase 2 rationale 1",
                        "basis": "Phase 2 basis 1",
                    },
                    {
                        "issue_code": "defect",
                        "category": "missing_evidence",
                        "title": "Phase 2 counterargument 2",
                        "rationale": "Phase 2 rationale 2",
                        "basis": "Phase 2 basis 2",
                    },
                ],
                "safe_summary": {"kind": "phase_2"},
            }


# ── module-level references for test inspection ──────────────────────────────

_lifecycle_provider = _LifecycleProvider()


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as value:
        yield value


@pytest_asyncio.fixture(autouse=True)
async def lifecycle_deps():
    global _lifecycle_provider
    _lifecycle_provider = _LifecycleProvider()
    old_provider = legal_reasoning_service.provider
    old_acquirer = legal_reasoning_service.source_acquirer
    acquirer = _ControlledSourceAcquirer()
    legal_reasoning_service.provider = _lifecycle_provider
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
        await session.flush()
        for entry in _created_source_ids:
            for ver_id in entry.get("version_ids", []):
                await session.execute(
                    delete(SourceVersion).where(
                        SourceVersion.id == ver_id
                    )
                )
        await session.flush()
        for entry in _created_source_ids:
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
        json={"title": f"P2.8B12C {uuid.uuid4().hex[:8]}"},
    )
    assert response.status_code == 201
    case_id = response.json()["id"]
    _created_cases.append(case_id)
    return case_id


def _maker():
    return get_sessionmaker()


async def _seed_source_v1() -> tuple[str, str, str]:
    rec_id = f"src-b12c-{uuid.uuid4().hex[:8]}"
    ver_id = f"svr-b12c-{uuid.uuid4().hex[:8]}"
    para_id = f"sp-b12c-{uuid.uuid4().hex[:8]}"

    async with _maker()() as session:
        rec = SourceRecord(
            id=rec_id, source_type="legislation",
            canonical_key=f"b12c-key-{uuid.uuid4().hex[:12]}",
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
    ver2_id = f"sv2-b12c-{uuid.uuid4().hex[:8]}"
    para2_id = f"sp2-b12c-{uuid.uuid4().hex[:8]}"

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


def _provider_payload():
    return _lifecycle_provider.payloads


# ── PROOF A: V1 → V2 current-source rebuild with current_state + payload ─────


@pytest.mark.asyncio
async def test_v1_to_v2_current_source_rebuild_lifecycle(client, lifecycle_deps):
    """Proof A: v1->v2 rebuild with current_state lifecycle and provider-input proof."""
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
        # Proof: v1 source links created
        source_links = (await session.execute(
            select(LegalIssueSourceLink).where(
                LegalIssueSourceLink.case_id == case_id,
                LegalIssueSourceLink.deleted_at.is_(None),
            )
        )).scalars().all()
        assert any(
            sl.source_record_id == rec_id and sl.source_version_id == v1_id
            and sl.source_paragraph_id == p1_id
            for sl in source_links
        ), "v1 source link not found"

        runs = (await session.execute(
            select(LegalReasoningRun).where(
                LegalReasoningRun.case_id == case_id,
            )
        )).scalars().all()
        assert len(runs) >= 1, "run must be visible in fresh session"
        succeeded = [r for r in runs if r.status == "succeeded"]
        assert len(succeeded) >= 1, "succeeded run must be visible"
        latest_run = succeeded[-1]

        from app.services.legal_reasoning_reproducibility import (
            compute_memory_fingerprint,
        )
        revision = (await session.execute(
            select(MemoryRevision).where(
                MemoryRevision.id == latest_run.memory_revision_id,
                MemoryRevision.tenant_id == "local",
                MemoryRevision.case_id == case_id,
            )
        )).scalar_one_or_none()
        assert revision is not None
        memory_fp = await compute_memory_fingerprint(
            session, tenant_id="local", case_id=case_id,
        )
        assert revision.memory_fingerprint == memory_fp, (
            "revision memory fingerprint must match current state"
        )

        stale, _, _ = await legal_reasoning_service.current_state(
            session, tenant_id="local", case_id=case_id,
        )
        assert stale is False, "v1 state must not be stale after rebuild"

        v1_source_fingerprint = latest_run.source_fingerprint

    # Proof: provider input contains V1 source text
    payloads = _provider_payload()
    v1_sources = payloads[-1]["legal_sources"]["items"]
    assert len(v1_sources) >= 1
    assert any(
        s["source_record_id"] == rec_id and s["source_version_id"] == v1_id
        and s["source_paragraph_id"] == p1_id and s["text"] == "V1 article 1 text"
        for s in v1_sources
    ), "v1 provider input must contain V1 source text"
    assert payloads[-1]["legal_sources"]["content_boundary"] == "UNTRUSTED_LEGAL_CONTENT"

    # -- advance to v2 --
    v2_id, p2_id = await _seed_source_v2(rec_id)

    # Proof: v2 stale state (V2 is current, last run used V1)
    async with _maker()() as session:
        stale, _, _ = await legal_reasoning_service.current_state(
            session, tenant_id="local", case_id=case_id,
        )
        assert stale is True, "state must be stale after v2 becomes current"

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
        # Proof: v2 source link active, v1 not active
        active_links = (await session.execute(
            select(LegalIssueSourceLink).where(
                LegalIssueSourceLink.case_id == case_id,
                LegalIssueSourceLink.deleted_at.is_(None),
            )
        )).scalars().all()
        assert any(
            sl.source_record_id == rec_id and sl.source_version_id == v2_id
            and sl.source_paragraph_id == p2_id
            for sl in active_links
        ), "v2 source link not found in active links"
        assert not any(
            sl.source_record_id == rec_id and sl.source_version_id == v1_id
            for sl in active_links
        ), "v1 link must not be active after v2 rebuild"

        runs = (await session.execute(
            select(LegalReasoningRun).where(
                LegalReasoningRun.case_id == case_id,
                LegalReasoningRun.status == "succeeded",
            ).order_by(LegalReasoningRun.completed_at)
        )).scalars().all()
        assert len(runs) == 2
        assert runs[1].source_fingerprint != v1_source_fingerprint

        from app.services.legal_reasoning_reproducibility import (
            compute_memory_fingerprint,
        )
        latest = runs[-1]
        rev = (await session.execute(
            select(MemoryRevision).where(
                MemoryRevision.id == latest.memory_revision_id,
                MemoryRevision.tenant_id == "local",
                MemoryRevision.case_id == case_id,
            )
        )).scalar_one_or_none()
        assert rev is not None
        assert rev.memory_fingerprint == await compute_memory_fingerprint(
            session, tenant_id="local", case_id=case_id,
        ), "v2 revision fingerprint must match current state"

        stale2, _, _ = await legal_reasoning_service.current_state(
            session, tenant_id="local", case_id=case_id,
        )
        assert stale2 is False, "v2 state must be current after v2 rebuild"

    # Proof: V2 provider input contains V2 text, NOT V1 text
    v2_sources = _provider_payload()[-1]["legal_sources"]["items"]
    assert len(v2_sources) >= 1
    assert any(
        s["source_record_id"] == rec_id and s["source_version_id"] == v2_id
        and s["source_paragraph_id"] == p2_id and s["text"] == "V2 article 1 text"
        for s in v2_sources
    ), "v2 provider input must contain V2 source text"
    assert not any(
        s.get("source_version_id") == v1_id for s in v2_sources
    ), "v2 provider input must NOT contain V1 source"
    assert not any(
        "V1 article 1 text" in str(s.get("text", "")) for s in v2_sources
    ), "v2 provider input must NOT contain old V1 text"


# ── PROOF B: late-graph-mutation rollback after source-link flush ────────────


@pytest.mark.asyncio
async def test_late_graph_mutation_rollback_after_source_flush(client, lifecycle_deps):
    """Proof B: failure after source-link flush rolls back all graph mutations."""
    acquirer = lifecycle_deps
    provider = _PhaseAwareProvider()
    rec_id, v1_id, p1_id = await _seed_source_v1()

    acquirer.set([{
        "source_record_id": rec_id,
        "source_version_id": v1_id,
        "source_paragraph_id": p1_id,
        "effective_trust": "needs_review",
    }])

    case_id = await _case(client)

    # -- baseline rebuild (phase 1) --
    legal_reasoning_service.provider = provider
    rebuilt = await client.post(
        f"/api/v1/cases/{case_id}/legal-issues/rebuild", json={},
    )
    assert rebuilt.status_code == 200

    # -- record baseline snapshot --
    async with _maker()() as session:
        baseline_runs_raw = (await session.execute(
            select(LegalReasoningRun).where(
                LegalReasoningRun.case_id == case_id,
            )
        )).scalars().all()
        baseline_run_ids = {r.id for r in baseline_runs_raw}
        baseline_run_count = len(baseline_run_ids)

        baseline_issues = (await session.execute(
            select(LegalIssue).where(
                LegalIssue.case_id == case_id,
                LegalIssue.deleted_at.is_(None),
            )
        )).scalars().all()
        baseline_issue_snap = {
            i.issue_code: {
                "id": i.id, "title": i.title, "description": i.description,
                "status": i.status, "version": i.version,
                "parent_issue_id": i.parent_issue_id,
            }
            for i in baseline_issues
        }

        baseline_source_links = (await session.execute(
            select(LegalIssueSourceLink).where(
                LegalIssueSourceLink.case_id == case_id,
            )
        )).scalars().all()
        baseline_sl_snap = [
            {
                "source_record_id": sl.source_record_id,
                "source_version_id": sl.source_version_id,
                "source_paragraph_id": sl.source_paragraph_id,
                "deleted_at": sl.deleted_at,
            }
            for sl in baseline_source_links
        ]

        baseline_ca = (await session.execute(
            select(Counterargument).where(
                Counterargument.case_id == case_id,
            )
        )).scalars().all()
        baseline_ca_snap = [
            {
                "id": c.id, "issue_id": c.issue_id, "category": c.category,
                "title": c.title, "rationale": c.rationale, "basis": c.basis,
                "status": c.status, "version": c.version,
            }
            for c in baseline_ca
        ]

        baseline_burdens = (await session.execute(
            select(BurdenOfProof).where(
                BurdenOfProof.case_id == case_id,
            )
        )).scalars().all()
        baseline_burden_snap = [
            {
                "id": b.id, "issue_id": b.issue_id, "burden_party_id": b.burden_party_id,
                "burden_type": b.burden_type, "required_standard": b.required_standard,
                "legal_source_refs": b.legal_source_refs, "evidence_status": b.evidence_status,
                "status": b.status, "notes": b.notes, "version": b.version,
            }
            for b in baseline_burdens
        ]

    # -- advance to v2, set up phase 2 --
    v2_id, p2_id = await _seed_source_v2(rec_id)

    acquirer.set([{
        "source_record_id": rec_id,
        "source_version_id": v2_id,
        "source_paragraph_id": p2_id,
        "effective_trust": "needs_review",
    }])

    provider.advance()

    # Add a CaseFact so the defect rebuild would create BurdenOfProof + fact_links
    async with _maker()() as session:
        fact = CaseFact(
            tenant_id="local", case_id=case_id,
            fact_type="defect", value="motor arızası mevcut",
            verification_status="document_verified",
        )
        session.add(fact)
        await session.commit()

    # -- inject late failure after source-link flush --
    import app.services.legal_reasoning_service as _lrs
    _original_output_hash = _lrs.output_hash

    def _failing_output_hash(candidate):
        raise RuntimeError("injected_late_graph_failure")

    _lrs.output_hash = _failing_output_hash

    error_occurred = False
    try:
        await client.post(
            f"/api/v1/cases/{case_id}/legal-issues/rebuild", json={},
        )
    except RuntimeError as exc:
        assert "injected_late_graph_failure" in str(exc)
        error_occurred = True
    finally:
        _lrs.output_hash = _original_output_hash

    assert error_occurred, "late graph failure was not raised"

    # -- fresh-session rollback assertions --
    async with _maker()() as session:
        # 1. no new succeeded run
        current_runs = (await session.execute(
            select(LegalReasoningRun).where(
                LegalReasoningRun.case_id == case_id,
            )
        )).scalars().all()
        current_run_ids = {r.id for r in current_runs}
        assert len(current_runs) == baseline_run_count, "no new run persisted"
        # 2. baseline run IDs match
        assert current_run_ids == baseline_run_ids, "exact baseline run IDs"

        # 3-4. LegalIssue exact rollback
        current_issues = (await session.execute(
            select(LegalIssue).where(
                LegalIssue.case_id == case_id,
                LegalIssue.deleted_at.is_(None),
            )
        )).scalars().all()
        assert len(current_issues) == len(baseline_issue_snap), "issue count unchanged"
        for ci in current_issues:
            snap = baseline_issue_snap[ci.issue_code]
            assert ci.id == snap["id"], f"{ci.issue_code} id preserved"
            assert ci.title == snap["title"], f"{ci.issue_code} title rolled back"
            assert ci.description == snap["description"], f"{ci.issue_code} desc rolled back"
            assert ci.status == snap["status"], f"{ci.issue_code} status rolled back"
            assert ci.version == snap["version"], f"{ci.issue_code} version rolled back"
            assert ci.parent_issue_id == snap["parent_issue_id"], f"{ci.issue_code} parent rolled back"

        # 5-7. Source-link restoration
        current_sl = (await session.execute(
            select(LegalIssueSourceLink).where(
                LegalIssueSourceLink.case_id == case_id,
            )
        )).scalars().all()
        assert len(current_sl) == len(baseline_sl_snap), "source link count unchanged"
        current_sl_tuples = set()
        for sl in current_sl:
            current_sl_tuples.add((
                sl.source_record_id, sl.source_version_id,
                sl.source_paragraph_id, bool(sl.deleted_at),
            ))
        for snap in baseline_sl_snap:
            t = (
                snap["source_record_id"], snap["source_version_id"],
                snap["source_paragraph_id"], bool(snap["deleted_at"]),
            )
            assert t in current_sl_tuples, f"baseline source link {t} preserved"

        # 6. no V2 source link active
        assert not any(
            sl.source_version_id == v2_id and sl.deleted_at is None
            for sl in current_sl
        ), "no active V2 source link survived"

        # 8-9. Counterargument exact rollback
        current_ca = (await session.execute(
            select(Counterargument).where(
                Counterargument.case_id == case_id,
            )
        )).scalars().all()
        assert len(current_ca) == len(baseline_ca_snap), "counterargument count unchanged"
        current_ca_keys = {
            (c.category, c.title) for c in current_ca
        }
        for snap in baseline_ca_snap:
            assert (snap["category"], snap["title"]) in current_ca_keys, (
                f"baseline counterargument {snap['category']} preserved"
            )
        # 9. missing_evidence NOT present
        assert not any(
            c.category == "missing_evidence" for c in current_ca
        ), "new missing_evidence counterargument not persisted"

        # 10-11. BurdenOfProof exact rollback
        current_burden = (await session.execute(
            select(BurdenOfProof).where(
                BurdenOfProof.case_id == case_id,
            )
        )).scalars().all()
        assert len(current_burden) == len(baseline_burden_snap), "burden count unchanged"
        for cb in current_burden:
            matching = [
                s for s in baseline_burden_snap if s["id"] == cb.id
            ]
            assert len(matching) == 1, f"baseline burden {cb.id} found"
            snap = matching[0]
            assert cb.burden_type == snap["burden_type"], "burden_type preserved"
            assert cb.version == snap["version"], "burden version preserved"
            assert cb.status == snap["status"], "burden status preserved"

        # 14. post-failure stale is True (V2 is current, but rebuild rolled back)
        stale, _, _ = await legal_reasoning_service.current_state(
            session, tenant_id="local", case_id=case_id,
        )
        assert stale is True, (
            "state must be stale after failed rebuild — V2 is current "
            "but reasoning state reflects V1"
        )

# ---------------------------------------------------------------------------
# EvidenceSufficiencyAssessment rollback applicability:
# NOT APPLICABLE — CURRENT REBUILD PATH DOES NOT MUTATE
# EVIDENCE SUFFICIENCY ASSESSMENTS.
# The rebuild() method in LegalReasoningService does not create, update,
# or delete EvidenceSufficiencyAssessment rows in any code path.
# Baseline assessment rows, if any exist, are unchanged by the failed
# rebuild, but no assessment mutation is attempted by rebuild.
# ---------------------------------------------------------------------------


# ── PROOF C: LegalIssue output does NOT stale reasoning ──────────────────────


@pytest.mark.asyncio
async def test_legal_issue_output_does_not_stale_reasoning(client, lifecycle_deps):
    """Proof C: LegalIssue output must not invalidate the memory input revision."""
    acquirer = lifecycle_deps
    rec_id, v1_id, p1_id = await _seed_source_v1()
    acquirer.set([{
        "source_record_id": rec_id,
        "source_version_id": v1_id,
        "source_paragraph_id": p1_id,
        "effective_trust": "needs_review",
    }])

    case_id = await _case(client)

    # -- seed case-memory input --
    async with _maker()() as session:
        fact = CaseFact(
            tenant_id="local", case_id=case_id,
            fact_type="defect", value="motor arizasi mevcut",
            verification_status="document_verified",
        )
        session.add(fact)
        await session.commit()

    # -- record input memory fingerprint before rebuild --
    async with _maker()() as session:
        from app.services.legal_reasoning_reproducibility import (
            compute_memory_fingerprint,
        )
        input_memory_fp = await compute_memory_fingerprint(
            session, tenant_id="local", case_id=case_id,
        )

    # -- successful rebuild (creates LegalIssue as reasoning output) --
    rebuilt = await client.post(
        f"/api/v1/cases/{case_id}/legal-issues/rebuild", json={},
    )
    assert rebuilt.status_code == 200
    assert rebuilt.json()["status"] == "succeeded"

    # -- verify LegalIssue was created --
    async with _maker()() as session:
        issues = (await session.execute(
            select(LegalIssue).where(
                LegalIssue.case_id == case_id,
                LegalIssue.deleted_at.is_(None),
            )
        )).scalars().all()
        assert len(issues) >= 1, "LegalIssue must be created by rebuild"

    # -- recompute memory fingerprint; must equal input fingerprint --
    async with _maker()() as session:
        from app.services.legal_reasoning_reproducibility import (
            compute_memory_fingerprint,
        )
        post_rebuild_memory_fp = await compute_memory_fingerprint(
            session, tenant_id="local", case_id=case_id,
        )
        assert post_rebuild_memory_fp == input_memory_fp, (
            "memory fingerprint must be unchanged after LegalIssue creation"
        )

        stale, _, _ = await legal_reasoning_service.current_state(
            session, tenant_id="local", case_id=case_id,
        )
        assert stale is False, (
            "current_state must not be stale — LegalIssue output does not "
            "invalidate the memory input revision"
        )

    # -- mutate genuine Case Memory input --
    async with _maker()() as session:
        from app.services.legal_reasoning_reproducibility import (
            compute_memory_fingerprint,
        )
        facts = (await session.execute(
            select(CaseFact).where(
                CaseFact.case_id == case_id,
                CaseFact.deleted_at.is_(None),
            )
        )).scalars().all()
        assert len(facts) >= 1
        fact = facts[0]
        fact.value = "motor tamamen calismiyor"
        fact.version += 1
        await session.commit()

        changed_memory_fp = await compute_memory_fingerprint(
            session, tenant_id="local", case_id=case_id,
        )
        assert changed_memory_fp != input_memory_fp, (
            "memory fingerprint must change after genuine input mutation"
        )

        stale, _, _ = await legal_reasoning_service.current_state(
            session, tenant_id="local", case_id=case_id,
        )
        assert stale is True, (
            "current_state must be stale after genuine CaseFact input change"
        )
