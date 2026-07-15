"""P2.8B13 — real JWT authorization matrix for P2.8 legal reasoning endpoints."""
from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch

from sqlalchemy import delete, select

from app.db.models import (
    BurdenOfProof, Case, CaseFact, CaseMember, Claim, Counterargument,
    Evidence, EvidenceClaimLink, LegalIssue, LegalIssueFactLink,
    LegalIssueSourceLink, LegalReasoningRun, MemoryRevision,
    SourceParagraph, SourceRecord, SourceVersion, Tenant, User,
)
from app.db.auth_repository import CaseMemberRepository
from app.db.case_chat_repository import CaseRepository
from app.db.session import get_sessionmaker
from app.main import app
from app.services.auth_service import create_access_token, set_security_context, \
    SecurityContext
from app.services.legal_reasoning_service import legal_reasoning_service


# ── identity constants ───────────────────────────────────────────────────────

TENANT_A = "tenant-a-p28b13"
TENANT_B = "tenant-b-p28b13"

TENANT_ADMIN_A = "user-ta-a-p28b13"
WRITER_A = "user-w-a-p28b13"
VIEWER_A = "user-v-a-p28b13"
NONMEMBER_A = "user-nm-a-p28b13"
REVOKED_MEMBER_A = "user-rm-a-p28b13"
FOREIGN_USER_B = "user-f-b-p28b13"
TENANT_ADMIN_B = "user-ta-b-p28b13"

SEED_USER_IDS = [
    TENANT_ADMIN_A, WRITER_A, VIEWER_A, NONMEMBER_A,
    REVOKED_MEMBER_A, FOREIGN_USER_B, TENANT_ADMIN_B,
]

_case_id: str = ""
_issue_id: str = ""
_claim_id: str = ""
_evidence_id: str = ""

_maker = get_sessionmaker


# ── controlled test doubles ──────────────────────────────────────────────────


class _B13Provider:
    provider_name = "b13_auth_provider"
    model_version = "1"

    async def analyze(self, payload):
        return {
            "issues": [{
                "issue_code": "contract_dispute",
                "title": "Sozlesme uyusmazligi",
                "description": "Auth matrix test.",
                "status": "proposed",
                "parent_code": None,
            }],
            "counterarguments": [],
            "safe_summary": {"kind": "b13_auth_test"},
        }


class _B13SourceAcquirer:
    async def acquire(self, db, *, case_id, security_context):
        return []


# ── JWT helpers ──────────────────────────────────────────────────────────────


def _jwt(user_id: str, role: str, tenant_id: str = TENANT_A) -> str:
    return create_access_token(user_id, tenant_id, role, f"session-{user_id}")


def _headers(user_id: str, role: str, tenant_id: str = TENANT_A) -> dict:
    return {"Authorization": f"Bearer {_jwt(user_id, role, tenant_id)}"}


_PATCH_MODULES = [
    "app.services.auth_service.get_auth_mode",
    "app.services.auth_manager.get_auth_mode",
    "app.routes.legal_reasoning_routes.get_auth_mode",
]


@contextmanager
def _jwt_mode():
    patches = [patch(p, return_value="jwt") for p in _PATCH_MODULES]
    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in patches:
            p.stop()


# ── fixture ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(autouse=True)
async def b13_setup():
    global _case_id, _issue_id, _claim_id, _evidence_id

    old_provider = legal_reasoning_service.provider
    old_acquirer = legal_reasoning_service.source_acquirer
    legal_reasoning_service.provider = _B13Provider()
    legal_reasoning_service.source_acquirer = _B13SourceAcquirer()

    async with _maker()() as session:
        # Clean up from previous runs
        for uid in SEED_USER_IDS:
            await session.execute(delete(CaseMember).where(
                CaseMember.user_id == uid,
            ))
        for model in (LegalReasoningRun, MemoryRevision, LegalIssueSourceLink,
                      LegalIssueFactLink, Counterargument, BurdenOfProof,
                      LegalIssue, EvidenceClaimLink, Evidence, Claim, CaseFact, Case):
            await session.execute(delete(model).where(
                model.tenant_id.in_([TENANT_A, TENANT_B])
            ))
        for uid in SEED_USER_IDS:
            await session.execute(delete(User).where(User.id == uid))
        for tid in [TENANT_A, TENANT_B]:
            await session.execute(delete(Tenant).where(Tenant.id == tid))
        await session.commit()

    # Seed tenants
    session.add(Tenant(id=TENANT_A, name="Tenant A", slug=TENANT_A, status="active"))
    session.add(Tenant(id=TENANT_B, name="Tenant B", slug=TENANT_B, status="active"))
    await session.flush()

    # Seed users
    _add_user = lambda uid, tid, role: session.add(User(
        id=uid, tenant_id=tid,
        email_normalized=f"{uid}@test",
        display_name=uid, status="active", role=role,
    ))
    _add_user(TENANT_ADMIN_A, TENANT_A, "tenant_admin")
    _add_user(WRITER_A, TENANT_A, "lawyer")
    _add_user(VIEWER_A, TENANT_A, "lawyer")
    _add_user(NONMEMBER_A, TENANT_A, "lawyer")
    _add_user(REVOKED_MEMBER_A, TENANT_A, "lawyer")
    _add_user(FOREIGN_USER_B, TENANT_B, "lawyer")
    _add_user(TENANT_ADMIN_B, TENANT_B, "tenant_admin")
    await session.flush()

    # Create Case A in Tenant A
    case = Case(
        tenant_id=TENANT_A, owner_user_id=TENANT_ADMIN_A,
        title="Auth Matrix Case A", status="active", version=1,
    )
    session.add(case)
    await session.flush()
    _case_id = case.id

    # Create Claim + Evidence in Case A
    claim = Claim(
        tenant_id=TENANT_A, case_id=_case_id, claim_type="contract",
        title="Borcun ihlali", description="Ifa edilmedi",
    )
    evidence = Evidence(
        tenant_id=TENANT_A, case_id=_case_id,
        evidence_type="document", title="Sozlesme",
        description="Imzali sozlesme metni",
    )
    session.add_all([claim, evidence])
    await session.flush()
    _claim_id = claim.id
    _evidence_id = evidence.id

    # CaseMember rows
    session.add(CaseMember(
        tenant_id=TENANT_A, case_id=_case_id, user_id=WRITER_A,
        membership_role="owner",
    ))
    session.add(CaseMember(
        tenant_id=TENANT_A, case_id=_case_id, user_id=VIEWER_A,
        membership_role="viewer",
    ))
    revoked = CaseMember(
        tenant_id=TENANT_A, case_id=_case_id, user_id=REVOKED_MEMBER_A,
        membership_role="owner", revoked_at=None,
    )
    session.add(revoked)
    await session.flush()
    # Revoke the revoked member's membership
    revoked.revoked_at = revoked.created_at.__class__(2025, 1, 1)
    await session.commit()

    # Run baseline rebuild via local mode to seed the graph
    async with _maker()() as session:
        from app.services.legal_reasoning_service import (
            LegalReasoningService,
        )
        svc = LegalReasoningService(provider=_B13Provider(),
                                     source_acquirer=_B13SourceAcquirer())
        await svc.rebuild(
            session, tenant_id=TENANT_A, case_id=_case_id,
            actor_id=TENANT_ADMIN_A,
        )
        await session.commit()

    async with _maker()() as session:
        issues = (await session.execute(
            select(LegalIssue).where(
                LegalIssue.case_id == _case_id,
                LegalIssue.deleted_at.is_(None),
            )
        )).scalars().all()
        assert len(issues) >= 1
        _issue_id = issues[0].id

    yield

    legal_reasoning_service.provider = old_provider
    legal_reasoning_service.source_acquirer = old_acquirer

    async with _maker()() as session:
        for uid in SEED_USER_IDS:
            await session.execute(delete(CaseMember).where(
                CaseMember.user_id == uid,
            ))
        for model in (LegalReasoningRun, MemoryRevision, LegalIssueSourceLink,
                      LegalIssueFactLink, Counterargument, BurdenOfProof,
                      LegalIssue, EvidenceClaimLink, Evidence, Claim, CaseFact, Case):
            await session.execute(delete(model).where(
                model.tenant_id.in_([TENANT_A, TENANT_B])
            ))
        for uid in SEED_USER_IDS:
            await session.execute(delete(User).where(User.id == uid))
        for tid in [TENANT_A, TENANT_B]:
            await session.execute(delete(Tenant).where(Tenant.id == tid))
        await session.commit()


def _post(path, json=None, headers=None):
    async def _do():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            return await ac.post(path, json=json or {}, headers=headers or {})
    return _do


def _get(path, headers=None):
    async def _do():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            return await ac.get(path, headers=headers or {})
    return _do


def _patch(path, json, headers=None):
    async def _do():
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            return await ac.patch(path, json=json, headers=headers or {})
    return _do


# ── snapshot helper ──────────────────────────────────────────────────────────


async def _snapshot():
    async with _maker()() as session:
        runs = (await session.execute(
            select(LegalReasoningRun).where(LegalReasoningRun.case_id == _case_id)
        )).scalars().all()
        issues = (await session.execute(
            select(LegalIssue).where(LegalIssue.case_id == _case_id)
        )).scalars().all()
        ecl = (await session.execute(
            select(EvidenceClaimLink).where(EvidenceClaimLink.case_id == _case_id)
        )).scalars().all()
        sl = (await session.execute(
            select(LegalIssueSourceLink).where(LegalIssueSourceLink.case_id == _case_id)
        )).scalars().all()
        ca = (await session.execute(
            select(Counterargument).where(Counterargument.case_id == _case_id)
        )).scalars().all()
        bop = (await session.execute(
            select(BurdenOfProof).where(BurdenOfProof.case_id == _case_id)
        )).scalars().all()
        return {
            "run_ids": {r.id for r in runs},
            "run_count": len(runs),
            "issue_versions": {i.id: i.version for i in issues},
            "ecl_count": len(ecl),
            "sl_count": len(sl),
            "ca_count": len(ca),
            "bop_count": len(bop),
        }


def _rebuild_path(): return f"/api/v1/cases/{_case_id}/legal-issues/rebuild"
def _issues_path():  return f"/api/v1/cases/{_case_id}/legal-issues"
def _runs_path():    return f"/api/v1/cases/{_case_id}/reasoning-runs"
def _graph_path():   return f"/api/v1/legal-issues/{_issue_id}/graph"
def _patch_path():   return f"/api/v1/legal-issues/{_issue_id}"
def _evidence_path(): return f"/api/v1/legal-issues/{_issue_id}/evidence-links"
def _source_path():  return f"/api/v1/legal-issues/{_issue_id}/source-links"


# ═══════════════════════════════════════════════════════════════════════════════
# UNAUTHENTICATED
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_unauthenticated_all_rejected():
    with _jwt_mode():
        for fn in [
            _get(_issues_path()), _get(_runs_path()), _get(_graph_path()),
            _post(_rebuild_path()), _post(_evidence_path()), _post(_source_path()),
        ]:
            r = await fn()
            assert r.status_code == 401, f"{r.status_code} for unauth"


@pytest.mark.asyncio
async def test_invalid_token_rejected():
    with _jwt_mode():
        h = {"Authorization": "Bearer invalid.token.here"}
        for fn in [
            _get(_issues_path(), h), _post(_rebuild_path(), headers=h),
        ]:
            r = await fn()
            assert r.status_code == 401, f"{r.status_code} for invalid token"


# ═══════════════════════════════════════════════════════════════════════════════
# VIEWER_A — reads allowed, writes denied
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_viewer_reads_allowed():
    h = _headers(VIEWER_A, "lawyer")
    with _jwt_mode():
        r = await _get(_issues_path(), h)()
        assert r.status_code == 200
        r = await _get(_graph_path(), h)()
        assert r.status_code == 200
        r = await _get(_runs_path(), h)()
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_viewer_writes_denied_no_mutation():
    h = _headers(VIEWER_A, "lawyer")
    snap = await _snapshot()
    with _jwt_mode():
        r = await _post(_rebuild_path(), headers=h)()
        assert r.status_code == 404
        r = await _patch(_patch_path(), {"version": 1}, h)()
        assert r.status_code == 404
        r = await _post(_evidence_path(), json={
            "claim_id": _claim_id, "evidence_id": _evidence_id,
            "relation_type": "evidence_supports_claim",
        }, headers=h)()
        assert r.status_code == 404
        r = await _post(_source_path(), json={
            "source_record_id": "nonexistent",
            "source_version_id": "nonexistent",
            "source_paragraph_id": "nonexistent",
            "relation_type": "source_governs_issue",
        }, headers=h)()
        assert r.status_code == 404
    snap2 = await _snapshot()
    assert snap2["run_ids"] == snap["run_ids"], "no new run"
    assert snap2["ecl_count"] == snap["ecl_count"], "no new evidence link"
    assert snap2["sl_count"] == snap["sl_count"], "no new source link"


# ═══════════════════════════════════════════════════════════════════════════════
# WRITER_A — all reads + writes allowed
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_writer_reads_allowed():
    h = _headers(WRITER_A, "lawyer")
    with _jwt_mode():
        for fn in [_get(_issues_path(), h), _get(_graph_path(), h),
                   _get(_runs_path(), h)]:
            r = await fn()
            assert r.status_code == 200


@pytest.mark.asyncio
async def test_writer_writes_allowed():
    h = _headers(WRITER_A, "lawyer")
    with _jwt_mode():
        r = await _post(_rebuild_path(), headers=h)()
        assert r.status_code == 200
        r = await _get(_issues_path(), h)()
        issues = r.json()
        issue = issues[0]
        r = await _patch(_patch_path(),
                         {"version": issue["version"], "status": "accepted"}, h)()
        assert r.status_code == 200
        r = await _post(_evidence_path(), json={
            "claim_id": _claim_id, "evidence_id": _evidence_id,
            "relation_type": "evidence_supports_claim",
        }, headers=h)()
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# NONMEMBER_A — all denied
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_nonmember_all_denied():
    h = _headers(NONMEMBER_A, "lawyer")
    with _jwt_mode():
        for fn in [
            _get(_issues_path(), h), _get(_graph_path(), h), _get(_runs_path(), h),
            _post(_rebuild_path(), headers=h),
            _post(_evidence_path(), json={
                "claim_id": "nonex", "evidence_id": "nonex",
                "relation_type": "evidence_supports_claim",
            }, headers=h),
            _post(_source_path(), json={
                "source_record_id": "nonex",
                "source_version_id": "nonex",
                "source_paragraph_id": "nonex",
                "relation_type": "source_governs_issue",
            }, headers=h),
        ]:
            r = await fn()
            assert r.status_code == 404, f"nonmember got {r.status_code}"


# ═══════════════════════════════════════════════════════════════════════════════
# REVOKED_MEMBER_A — all denied
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_revoked_member_all_denied():
    h = _headers(REVOKED_MEMBER_A, "lawyer")
    with _jwt_mode():
        r = await _get(_issues_path(), h)()
        assert r.status_code == 404
        r = await _post(_rebuild_path(), headers=h)()
        assert r.status_code == 404
        r = await _get(_graph_path(), h)()
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# FOREIGN_USER_B (tenant B, non-admin) — all Tenant A paths denied
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_foreign_user_all_tenant_a_denied():
    h = _headers(FOREIGN_USER_B, "lawyer", TENANT_B)
    with _jwt_mode():
        r = await _get(_issues_path(), h)()
        assert r.status_code == 404
        r = await _post(_rebuild_path(), headers=h)()
        assert r.status_code == 404
        r = await _get(_graph_path(), h)()
        assert r.status_code == 404
        r = await _patch(_patch_path(), {"version": 1}, h)()
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# TENANT_ADMIN_B — Tenant A paths denied (no cross-tenant)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_tenant_admin_b_denied_tenant_a():
    h = _headers(TENANT_ADMIN_B, "tenant_admin", TENANT_B)
    with _jwt_mode():
        r = await _get(_issues_path(), h)()
        assert r.status_code == 404
        r = await _post(_rebuild_path(), headers=h)()
        assert r.status_code == 404
        r = await _get(_graph_path(), h)()
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# TENANT_ADMIN_A — reads + writes allowed, WITH NO CaseMember membership
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_tenant_admin_a_reads_allowed_no_membership():
    h = _headers(TENANT_ADMIN_A, "tenant_admin")
    with _jwt_mode():
        for fn in [_get(_issues_path(), h), _get(_graph_path(), h),
                   _get(_runs_path(), h)]:
            r = await fn()
            assert r.status_code == 200, f"admin read: {r.status_code}"


@pytest.mark.asyncio
async def test_tenant_admin_a_rebuild_without_membership():
    """Regression: require_case_write must allow tenant_admin without CaseMember."""
    h = _headers(TENANT_ADMIN_A, "tenant_admin")
    with _jwt_mode():
        r = await _post(_rebuild_path(), headers=h)()
        assert r.status_code == 200, (
            f"tenant_admin rebuild without membership got {r.status_code}, "
            "expected 200 — require_case_write must allow tenant_admin bypass"
        )


@pytest.mark.asyncio
async def test_tenant_admin_a_issue_writes_allowed():
    h = _headers(TENANT_ADMIN_A, "tenant_admin")
    with _jwt_mode():
        r = await _get(_issues_path(), h)()
        issues = r.json()
        issue = issues[0]
        r = await _patch(_patch_path(),
                         {"version": issue["version"], "status": "accepted"}, h)()
        assert r.status_code == 200, f"admin patch: {r.status_code}"
        r = await _post(_evidence_path(), json={
            "claim_id": _claim_id, "evidence_id": _evidence_id,
            "relation_type": "evidence_supports_claim",
        }, headers=h)()
        assert r.status_code == 200, f"admin evidence-link: {r.status_code}"


# ═══════════════════════════════════════════════════════════════════════════════
# FOREIGN ISSUE ID NO-DISCLOSURE (uses real Tenant A issue ID)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_foreign_issue_id_no_disclosure_nonmember():
    h = _headers(NONMEMBER_A, "lawyer")
    with _jwt_mode():
        r = await _get(_graph_path(), h)()
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_foreign_issue_id_no_disclosure_foreign_user():
    h = _headers(FOREIGN_USER_B, "lawyer", TENANT_B)
    with _jwt_mode():
        r = await _get(_graph_path(), h)()
        assert r.status_code == 404
        r = await _patch(_patch_path(), {"version": 1}, h)()
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_foreign_issue_id_no_disclosure_foreign_admin():
    h = _headers(TENANT_ADMIN_B, "tenant_admin", TENANT_B)
    with _jwt_mode():
        r = await _get(_graph_path(), h)()
        assert r.status_code == 404
