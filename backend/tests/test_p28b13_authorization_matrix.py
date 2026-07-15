"""P2.8B13C — complete seven-endpoint JWT authorization matrix for P2.8 legal reasoning."""
from __future__ import annotations

import uuid
from contextlib import contextmanager

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch

from sqlalchemy import delete, select

from app.db.models import (
    AuthSession, BurdenOfProof, Case, CaseFact, CaseMember, Claim,
    Counterargument, Evidence, EvidenceClaimLink,
    EvidenceSufficiencyAssessment, LegalIssue, LegalIssueFactLink,
    LegalIssueSourceLink, LegalReasoningRun, MemoryRevision,
    SourceParagraph, SourceRecord, SourceVersion, Tenant, User,
)
from app.db.session import get_sessionmaker
from app.main import app
from app.services.auth_service import create_access_token
from app.services.legal_reasoning_service import legal_reasoning_service


# ── identity constants ───────────────────────────────────────────────────────

TENANT_A = "tenant-a-p28b13c"
TENANT_B = "tenant-b-p28b13c"

TENANT_ADMIN_A = "user-ta-a-p28b13c"
WRITER_A = "user-w-a-p28b13c"
VIEWER_A = "user-v-a-p28b13c"
NONMEMBER_A = "user-nm-a-p28b13c"
REVOKED_MEMBER_A = "user-rm-a-p28b13c"
FOREIGN_USER_B = "user-f-b-p28b13c"
TENANT_ADMIN_B = "user-ta-b-p28b13c"

SEED_USER_IDS = [
    TENANT_ADMIN_A, WRITER_A, VIEWER_A, NONMEMBER_A,
    REVOKED_MEMBER_A, FOREIGN_USER_B, TENANT_ADMIN_B,
]

_case_id: str = ""
_issue_id: str = ""
_claim_id: str = ""
_evidence_id: str = ""
_source_rec_id: str = ""
_source_ver_id: str = ""
_source_para_id: str = ""
_session_ids: dict[str, str] = {}
_user_token_versions: dict[str, int] = {}


# ── controlled test doubles ──────────────────────────────────────────────────

class _B13Provider:
    provider_name = "b13c_auth_provider"
    model_version = "1"
    async def analyze(self, payload):
        return {"issues": [{"issue_code": "contract_dispute", "title": "Sözleşme uyuşmazlığı",
                "description": "Auth matrix test.", "status": "proposed", "parent_code": None}],
                "counterarguments": [], "safe_summary": {"kind": "b13c_auth_test"}}


class _B13SourceAcquirer:
    async def acquire(self, db, *, case_id, security_context): return []


# ── JWT helpers ──────────────────────────────────────────────────────────────

def _jwt(user_id: str, role: str, tenant_id: str = TENANT_A) -> str:
    sid = _session_ids.get(user_id, f"s-{user_id}")
    tv = _user_token_versions.get(user_id, 0)
    return create_access_token(user_id, tenant_id, role, sid, tv)

def _h(user_id: str, role: str, tenant_id: str = TENANT_A) -> dict:
    return {"Authorization": f"Bearer {_jwt(user_id, role, tenant_id)}"}

_PATCH_MODULES = [
    "app.services.auth_service.get_auth_mode",
    "app.services.auth_manager.get_auth_mode",
    "app.routes.legal_reasoning_routes.get_auth_mode",
]

@contextmanager
def _jwt_mode():
    patches = [patch(p, return_value="jwt") for p in _PATCH_MODULES]
    for p in patches: p.start()
    try: yield
    finally:
        for p in patches: p.stop()


# ── HTTP helpers ─────────────────────────────────────────────────────────────

async def _req(method, path, json=None, headers=None, expect=None):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        kwargs = {"headers": headers or {}}
        if json is not None:
            kwargs["json"] = json
        r = await ac.request(method, path, **kwargs)
        if expect is not None:
            assert r.status_code == expect, f"{method} {path}: expected {expect} got {r.status_code}"
        return r

async def _get(path, headers=None, expect=None):
    return await _req("GET", path, headers=headers, expect=expect)

async def _post(path, json=None, headers=None, expect=None):
    return await _req("POST", path, json=json if json is not None else {}, headers=headers, expect=expect)

async def _patch(path, json, headers=None, expect=None):
    return await _req("PATCH", path, json=json, headers=headers, expect=expect)


# ── snapshot helper ──────────────────────────────────────────────────────────

async def _snapshot():
    async with get_sessionmaker()() as session:
        async def _rows(model):
            result = await session.execute(select(model).where(
                model.tenant_id == TENANT_A, model.case_id == _case_id
            ))
            return list(result.scalars().all())

        return {
            "runs": [(r.id, r.status, r.source_fingerprint) for r in await _rows(LegalReasoningRun)],
            "issues": [(i.id, i.issue_code, i.title, i.description, i.status, i.version,
                         i.parent_issue_id, bool(i.deleted_at)) for i in await _rows(LegalIssue)],
            "ecl": [(e.id, e.claim_id, e.evidence_id, e.relation_type, e.status,
                      bool(e.deleted_at)) for e in await _rows(EvidenceClaimLink)],
            "esa": [(a.id, a.issue_id, a.claim_id, a.evidence_id, a.status, a.version,
                      bool(a.deleted_at)) for a in await _rows(EvidenceSufficiencyAssessment)],
            "sl": [(s.id, s.issue_id, s.source_record_id, s.source_version_id,
                     s.source_paragraph_id, s.relation_type, bool(s.deleted_at))
                    for s in await _rows(LegalIssueSourceLink)],
            "ca": [(c.id, c.issue_id, c.category, c.title, c.rationale, c.basis,
                     c.status, c.version, bool(c.deleted_at)) for c in await _rows(Counterargument)],
            "bop": [(b.id, b.issue_id, b.burden_party_id, b.burden_type, b.required_standard,
                      str(b.legal_source_refs), b.evidence_status, b.status, b.notes,
                      b.version, bool(b.deleted_at)) for b in await _rows(BurdenOfProof)],
        }


def _assert_snapshot_equal(a, b, label):
    for key in sorted(set(a) | set(b)):
        assert a.get(key) == b.get(key), f"snapshot changed: {key} in {label}"


# ── fixture ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(autouse=True)
async def b13c_setup():
    global _case_id, _issue_id, _claim_id, _evidence_id
    global _source_rec_id, _source_ver_id, _source_para_id
    global _session_ids, _user_token_versions

    old_provider = legal_reasoning_service.provider
    old_acquirer = legal_reasoning_service.source_acquirer
    legal_reasoning_service.provider = _B13Provider()
    legal_reasoning_service.source_acquirer = _B13SourceAcquirer()

    maker = get_sessionmaker()
    async with maker() as session:
        for uid in SEED_USER_IDS:
            await session.execute(delete(AuthSession).where(AuthSession.user_id == uid))
            await session.execute(delete(CaseMember).where(CaseMember.user_id == uid))
        for model in (LegalReasoningRun, MemoryRevision, LegalIssueSourceLink,
                      LegalIssueFactLink, Counterargument, BurdenOfProof,
                      EvidenceSufficiencyAssessment, LegalIssue, EvidenceClaimLink,
                      Evidence, Claim, CaseFact, Case):
            await session.execute(delete(model).where(
                model.tenant_id.in_([TENANT_A, TENANT_B])
            ))
        for uid in SEED_USER_IDS:
            await session.execute(delete(User).where(User.id == uid))
        for tid in [TENANT_A, TENANT_B]:
            await session.execute(delete(Tenant).where(Tenant.id == tid))
        await session.commit()

    async with maker() as session:
        session.add(Tenant(id=TENANT_A, name="Tenant A", slug=TENANT_A, status="active"))
        session.add(Tenant(id=TENANT_B, name="Tenant B", slug=TENANT_B, status="active"))
        await session.flush()
        _au = lambda uid, tid, role: session.add(User(id=uid, tenant_id=tid,
            email_normalized=f"{uid}@test", display_name=uid, status="active", role=role))
        _au(TENANT_ADMIN_A, TENANT_A, "tenant_admin")
        _au(WRITER_A, TENANT_A, "lawyer")
        _au(VIEWER_A, TENANT_A, "lawyer")
        _au(NONMEMBER_A, TENANT_A, "lawyer")
        _au(REVOKED_MEMBER_A, TENANT_A, "lawyer")
        _au(FOREIGN_USER_B, TENANT_B, "lawyer")
        _au(TENANT_ADMIN_B, TENANT_B, "tenant_admin")
        await session.flush()

        # Create real AuthSessions for all actors
        from hashlib import sha256
        from datetime import UTC, datetime, timedelta
        _session_ids.clear()
        _user_token_versions.clear()
        for uid, tid in [
            (TENANT_ADMIN_A, TENANT_A), (WRITER_A, TENANT_A),
            (VIEWER_A, TENANT_A), (NONMEMBER_A, TENANT_A),
            (REVOKED_MEMBER_A, TENANT_A), (FOREIGN_USER_B, TENANT_B),
            (TENANT_ADMIN_B, TENANT_B),
        ]:
            now = datetime.now(UTC)
            s = AuthSession(
                tenant_id=tid, user_id=uid,
                refresh_token_hash=sha256(f"rt-{uid}".encode()).hexdigest(),
                token_family_id=f"tf-{uid}", created_at=now, last_used_at=now,
                expires_at=now + timedelta(days=7),
            )
            session.add(s)
            await session.flush()
            _session_ids[uid] = s.id
            _user_token_versions[uid] = 0

        await session.commit()

        case = Case(tenant_id=TENANT_A, owner_user_id=TENANT_ADMIN_A,
                     title="Auth Matrix Case A", status="active", version=1)
        session.add(case)
        await session.flush()
        _case_id = case.id

        claim = Claim(tenant_id=TENANT_A, case_id=_case_id, claim_type="contract",
                       title="Borcun ihlali", description="Ifa edilmedi")
        evidence = Evidence(tenant_id=TENANT_A, case_id=_case_id,
                            evidence_type="document", title="Sözleşme", description="İmzalı sözleşme metni")
        session.add_all([claim, evidence])
        await session.flush()
        _claim_id = claim.id
        _evidence_id = evidence.id

        session.add(CaseMember(tenant_id=TENANT_A, case_id=_case_id,
                               user_id=WRITER_A, membership_role="owner"))
        session.add(CaseMember(tenant_id=TENANT_A, case_id=_case_id,
                               user_id=VIEWER_A, membership_role="viewer"))
        revoked = CaseMember(tenant_id=TENANT_A, case_id=_case_id,
                             user_id=REVOKED_MEMBER_A, membership_role="owner")
        session.add(revoked)
        await session.flush()
        from datetime import datetime, UTC
        revoked.revoked_at = datetime(2025, 1, 1, tzinfo=UTC)
        await session.commit()

    # Eligible source triple for source-link tests
    _source_rec_id = f"src-b13c-{uuid.uuid4().hex[:8]}"
    _source_ver_id = f"svr-b13c-{uuid.uuid4().hex[:8]}"
    _source_para_id = f"sp-b13c-{uuid.uuid4().hex[:8]}"
    async with maker() as session:
        rec = SourceRecord(id=_source_rec_id, source_type="legislation",
            canonical_key=f"b13c-key-{uuid.uuid4().hex[:12]}",
            title="Test Statute", verification_status="needs_review",
            current_version_id=_source_ver_id)
        ver = SourceVersion(id=_source_ver_id, source_record_id=_source_rec_id,
            version_label="v1", content_hash=f"h-{uuid.uuid4().hex[:8]}",
            normalized_text="Article text")
        session.add_all([rec, ver])
        await session.flush()
        para = SourceParagraph(id=_source_para_id, source_version_id=_source_ver_id,
            paragraph_index=1, text="Article text", text_hash=f"th-{uuid.uuid4().hex[:8]}")
        session.add(para)
        await session.commit()

    # Baseline rebuild
    async with maker() as session:
        from app.services.legal_reasoning_service import LegalReasoningService
        svc = LegalReasoningService(provider=_B13Provider(), source_acquirer=_B13SourceAcquirer())
        await svc.rebuild(session, tenant_id=TENANT_A, case_id=_case_id, actor_id=TENANT_ADMIN_A)
        await session.commit()

    async with maker() as session:
        issues = (await session.execute(select(LegalIssue).where(
            LegalIssue.case_id == _case_id, LegalIssue.deleted_at.is_(None)))).scalars().all()
        assert len(issues) >= 1
        _issue_id = issues[0].id

    yield

    legal_reasoning_service.provider = old_provider
    legal_reasoning_service.source_acquirer = old_acquirer

    async with maker() as session:
        for uid in SEED_USER_IDS:
            await session.execute(delete(AuthSession).where(AuthSession.user_id == uid))
            await session.execute(delete(CaseMember).where(CaseMember.user_id == uid))
        for model in (LegalReasoningRun, MemoryRevision, LegalIssueSourceLink,
                      LegalIssueFactLink, Counterargument, BurdenOfProof,
                      EvidenceSufficiencyAssessment, LegalIssue, EvidenceClaimLink,
                      Evidence, Claim, CaseFact, Case):
            await session.execute(delete(model).where(
                model.tenant_id.in_([TENANT_A, TENANT_B])))
        await session.flush()
        await session.execute(delete(SourceParagraph).where(
            SourceParagraph.id == _source_para_id))
        await session.flush()
        await session.execute(delete(SourceVersion).where(
            SourceVersion.id == _source_ver_id))
        await session.flush()
        await session.execute(delete(SourceRecord).where(
            SourceRecord.id == _source_rec_id))
        await session.flush()
        for uid in SEED_USER_IDS:
            await session.execute(delete(User).where(User.id == uid))
        for tid in [TENANT_A, TENANT_B]:
            await session.execute(delete(Tenant).where(Tenant.id == tid))
        await session.commit()


def _R(path, h, expect=200):
    """Read endpoint."""
    return _get(path, headers=h, expect=expect)

def _W(method, path, h, json=None, expect=200):
    """Write endpoint."""
    if method == "POST":
        return _post(path, json=json, headers=h, expect=expect)
    elif method == "PATCH":
        return _patch(path, json=json, headers=h, expect=expect)


# ── path helpers ─────────────────────────────────────────────────────────────

def _rebuild():   return f"/api/v1/cases/{_case_id}/legal-issues/rebuild"
def _issues():    return f"/api/v1/cases/{_case_id}/legal-issues"
def _runs():      return f"/api/v1/cases/{_case_id}/reasoning-runs"
def _graph():     return f"/api/v1/legal-issues/{_issue_id}/graph"
def _patch_path(): return f"/api/v1/legal-issues/{_issue_id}"
def _evidence():  return f"/api/v1/legal-issues/{_issue_id}/evidence-links"
def _source():    return f"/api/v1/legal-issues/{_issue_id}/source-links"


# ═══════════════════════════════════════════════════════════════════════════════
# UNAUTHENTICATED — all 7 endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_unauthenticated_all_seven():
    with _jwt_mode():
        # reads
        await _get(_issues(), expect=401)
        await _get(_graph(), expect=401)
        await _get(_runs(), expect=401)
        # writes
        await _post(_rebuild(), expect=401)
        await _patch(_patch_path(), json={"version": 1}, expect=401)
        await _post(_evidence(), json={"claim_id": "x", "evidence_id": "y",
            "relation_type": "evidence_supports_claim"}, expect=401)
        await _post(_source(), json={"source_record_id": "x", "source_version_id": "y",
            "source_paragraph_id": "z", "relation_type": "source_governs_issue"}, expect=401)


@pytest.mark.asyncio
async def test_invalid_token_all_seven():
    h = {"Authorization": "Bearer invalid.token"}
    with _jwt_mode():
        await _get(_issues(), headers=h, expect=401)
        await _get(_graph(), headers=h, expect=401)
        await _get(_runs(), headers=h, expect=401)
        await _post(_rebuild(), headers=h, expect=401)
        await _patch(_patch_path(), json={"version": 1}, headers=h, expect=401)
        await _post(_evidence(), json={"claim_id": "x", "evidence_id": "y",
            "relation_type": "evidence_supports_claim"}, headers=h, expect=401)
        await _post(_source(), json={"source_record_id": "x", "source_version_id": "y",
            "source_paragraph_id": "z", "relation_type": "source_governs_issue"}, headers=h, expect=401)


# ═══════════════════════════════════════════════════════════════════════════════
# VIEWER_A — reads 200, writes 404
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_viewer_matrix():
    h = _h(VIEWER_A, "lawyer")
    with _jwt_mode():
        await _R(_issues(), h, 200)
        await _R(_graph(), h, 200)
        await _R(_runs(), h, 200)
        await _post(_rebuild(), headers=h, expect=404)
        await _patch(_patch_path(), json={"version": 1}, headers=h, expect=404)
        await _post(_evidence(), json={"claim_id": _claim_id, "evidence_id": _evidence_id,
            "relation_type": "evidence_supports_claim"}, headers=h, expect=404)
        await _post(_source(), json={"source_record_id": _source_rec_id,
            "source_version_id": _source_ver_id, "source_paragraph_id": _source_para_id,
            "relation_type": "source_governs_issue"}, headers=h, expect=404)


# ═══════════════════════════════════════════════════════════════════════════════
# WRITER_A — all read/write success
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_writer_matrix():
    h = _h(WRITER_A, "lawyer")
    with _jwt_mode():
        # reads
        await _R(_issues(), h, 200)
        await _R(_graph(), h, 200)
        await _R(_runs(), h, 200)
        # writes
        await _post(_rebuild(), headers=h, expect=200)
        # fetch current issue for version-dependent operations
        r = await _get(_issues(), headers=h)
        issue = r.json()[0]
        await _patch(_patch_path(), json={"version": issue["version"], "status": "accepted"}, headers=h, expect=200)
        await _post(_evidence(), json={"claim_id": _claim_id, "evidence_id": _evidence_id,
            "relation_type": "evidence_supports_claim"}, headers=h, expect=200)
        # source-link success
        r = await _post(_source(), json={"source_record_id": _source_rec_id,
            "source_version_id": _source_ver_id, "source_paragraph_id": _source_para_id,
            "relation_type": "source_governs_issue"}, headers=h, expect=200)
        body = r.json()
        assert body["source_record_id"] == _source_rec_id
        assert body["source_version_id"] == _source_ver_id
        assert body["source_paragraph_id"] == _source_para_id


# ═══════════════════════════════════════════════════════════════════════════════
# NONMEMBER_A — all 404
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_nonmember_matrix():
    h = _h(NONMEMBER_A, "lawyer")
    with _jwt_mode():
        await _R(_issues(), h, 404)
        await _R(_graph(), h, 404)
        await _R(_runs(), h, 404)
        await _post(_rebuild(), headers=h, expect=404)
        await _patch(_patch_path(), json={"version": 1}, headers=h, expect=404)
        await _post(_evidence(), json={"claim_id": _claim_id, "evidence_id": _evidence_id,
            "relation_type": "evidence_supports_claim"}, headers=h, expect=404)
        await _post(_source(), json={"source_record_id": _source_rec_id,
            "source_version_id": _source_ver_id, "source_paragraph_id": _source_para_id,
            "relation_type": "source_governs_issue"}, headers=h, expect=404)


# ═══════════════════════════════════════════════════════════════════════════════
# REVOKED_MEMBER_A — all 404
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_revoked_member_matrix():
    h = _h(REVOKED_MEMBER_A, "lawyer")
    with _jwt_mode():
        await _R(_issues(), h, 404)
        await _R(_graph(), h, 404)
        await _R(_runs(), h, 404)
        await _post(_rebuild(), headers=h, expect=404)
        await _patch(_patch_path(), json={"version": 1}, headers=h, expect=404)
        await _post(_evidence(), json={"claim_id": _claim_id, "evidence_id": _evidence_id,
            "relation_type": "evidence_supports_claim"}, headers=h, expect=404)
        await _post(_source(), json={"source_record_id": _source_rec_id,
            "source_version_id": _source_ver_id, "source_paragraph_id": _source_para_id,
            "relation_type": "source_governs_issue"}, headers=h, expect=404)


# ═══════════════════════════════════════════════════════════════════════════════
# FOREIGN_USER_B — all Tenant A paths 404
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_foreign_user_matrix():
    h = _h(FOREIGN_USER_B, "lawyer", TENANT_B)
    with _jwt_mode():
        await _R(_issues(), h, 404)
        await _R(_graph(), h, 404)
        await _R(_runs(), h, 404)
        await _post(_rebuild(), headers=h, expect=404)
        await _patch(_patch_path(), json={"version": 1}, headers=h, expect=404)
        await _post(_evidence(), json={"claim_id": _claim_id, "evidence_id": _evidence_id,
            "relation_type": "evidence_supports_claim"}, headers=h, expect=404)
        await _post(_source(), json={"source_record_id": _source_rec_id,
            "source_version_id": _source_ver_id, "source_paragraph_id": _source_para_id,
            "relation_type": "source_governs_issue"}, headers=h, expect=404)


# ═══════════════════════════════════════════════════════════════════════════════
# TENANT_ADMIN_B — all Tenant A paths 404 (no cross-tenant)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_tenant_admin_b_matrix():
    h = _h(TENANT_ADMIN_B, "tenant_admin", TENANT_B)
    with _jwt_mode():
        await _R(_issues(), h, 404)
        await _R(_graph(), h, 404)
        await _R(_runs(), h, 404)
        await _post(_rebuild(), headers=h, expect=404)
        await _patch(_patch_path(), json={"version": 1}, headers=h, expect=404)
        await _post(_evidence(), json={"claim_id": _claim_id, "evidence_id": _evidence_id,
            "relation_type": "evidence_supports_claim"}, headers=h, expect=404)
        await _post(_source(), json={"source_record_id": _source_rec_id,
            "source_version_id": _source_ver_id, "source_paragraph_id": _source_para_id,
            "relation_type": "source_governs_issue"}, headers=h, expect=404)


# ═══════════════════════════════════════════════════════════════════════════════
# TENANT_ADMIN_A — all reads + writes, NO CaseMember
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_tenant_admin_a_matrix():
    h = _h(TENANT_ADMIN_A, "tenant_admin")
    with _jwt_mode():
        await _R(_issues(), h, 200)
        await _R(_graph(), h, 200)
        await _R(_runs(), h, 200)
        await _post(_rebuild(), headers=h, expect=200)
        r = await _get(_issues(), headers=h)
        issue = r.json()[0]
        await _patch(_patch_path(), json={"version": issue["version"], "status": "accepted"}, headers=h, expect=200)
        await _post(_evidence(), json={"claim_id": _claim_id, "evidence_id": _evidence_id,
            "relation_type": "evidence_supports_claim"}, headers=h, expect=200)
        r = await _post(_source(), json={"source_record_id": _source_rec_id,
            "source_version_id": _source_ver_id, "source_paragraph_id": _source_para_id,
            "relation_type": "source_governs_issue"}, headers=h, expect=200)
        body = r.json()
        assert body["source_record_id"] == _source_rec_id
        assert body["source_version_id"] == _source_ver_id
        assert body["source_paragraph_id"] == _source_para_id


# ═══════════════════════════════════════════════════════════════════════════════
# ISSUE-SCOPED NO-DISCLOSURE — real Tenant A issue ID, four endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_issue_no_disclosure_nonmember():
    h = _h(NONMEMBER_A, "lawyer")
    with _jwt_mode():
        await _R(_graph(), h, 404)
        await _patch(_patch_path(), json={"version": 1}, headers=h, expect=404)
        await _post(_evidence(), json={"claim_id": _claim_id, "evidence_id": _evidence_id,
            "relation_type": "evidence_supports_claim"}, headers=h, expect=404)
        await _post(_source(), json={"source_record_id": _source_rec_id,
            "source_version_id": _source_ver_id, "source_paragraph_id": _source_para_id,
            "relation_type": "source_governs_issue"}, headers=h, expect=404)


@pytest.mark.asyncio
async def test_issue_no_disclosure_foreign_user():
    h = _h(FOREIGN_USER_B, "lawyer", TENANT_B)
    with _jwt_mode():
        await _R(_graph(), h, 404)
        await _patch(_patch_path(), json={"version": 1}, headers=h, expect=404)
        await _post(_evidence(), json={"claim_id": _claim_id, "evidence_id": _evidence_id,
            "relation_type": "evidence_supports_claim"}, headers=h, expect=404)
        await _post(_source(), json={"source_record_id": _source_rec_id,
            "source_version_id": _source_ver_id, "source_paragraph_id": _source_para_id,
            "relation_type": "source_governs_issue"}, headers=h, expect=404)


@pytest.mark.asyncio
async def test_issue_no_disclosure_foreign_admin():
    h = _h(TENANT_ADMIN_B, "tenant_admin", TENANT_B)
    with _jwt_mode():
        await _R(_graph(), h, 404)
        await _patch(_patch_path(), json={"version": 1}, headers=h, expect=404)
        await _post(_evidence(), json={"claim_id": _claim_id, "evidence_id": _evidence_id,
            "relation_type": "evidence_supports_claim"}, headers=h, expect=404)
        await _post(_source(), json={"source_record_id": _source_rec_id,
            "source_version_id": _source_ver_id, "source_paragraph_id": _source_para_id,
            "relation_type": "source_governs_issue"}, headers=h, expect=404)


# ═══════════════════════════════════════════════════════════════════════════════
# DENIED-WRITE NO-MUTATION — viewer, nonmember, foreign user
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_viewer_denied_writes_no_mutation():
    h = _h(VIEWER_A, "lawyer")
    before = await _snapshot()
    with _jwt_mode():
        await _post(_rebuild(), headers=h, expect=404)
        await _patch(_patch_path(), json={"version": 1}, headers=h, expect=404)
        await _post(_evidence(), json={"claim_id": _claim_id, "evidence_id": _evidence_id,
            "relation_type": "evidence_supports_claim"}, headers=h, expect=404)
        await _post(_source(), json={"source_record_id": _source_rec_id,
            "source_version_id": _source_ver_id, "source_paragraph_id": _source_para_id,
            "relation_type": "source_governs_issue"}, headers=h, expect=404)
    after = await _snapshot()
    _assert_snapshot_equal(before, after, "viewer")


@pytest.mark.asyncio
async def test_nonmember_denied_writes_no_mutation():
    h = _h(NONMEMBER_A, "lawyer")
    before = await _snapshot()
    with _jwt_mode():
        await _post(_rebuild(), headers=h, expect=404)
        await _patch(_patch_path(), json={"version": 1}, headers=h, expect=404)
        await _post(_evidence(), json={"claim_id": _claim_id, "evidence_id": _evidence_id,
            "relation_type": "evidence_supports_claim"}, headers=h, expect=404)
        await _post(_source(), json={"source_record_id": _source_rec_id,
            "source_version_id": _source_ver_id, "source_paragraph_id": _source_para_id,
            "relation_type": "source_governs_issue"}, headers=h, expect=404)
    after = await _snapshot()
    _assert_snapshot_equal(before, after, "nonmember")


@pytest.mark.asyncio
async def test_foreign_user_denied_writes_no_mutation():
    h = _h(FOREIGN_USER_B, "lawyer", TENANT_B)
    before = await _snapshot()
    with _jwt_mode():
        await _post(_rebuild(), headers=h, expect=404)
        await _patch(_patch_path(), json={"version": 1}, headers=h, expect=404)
        await _post(_evidence(), json={"claim_id": _claim_id, "evidence_id": _evidence_id,
            "relation_type": "evidence_supports_claim"}, headers=h, expect=404)
        await _post(_source(), json={"source_record_id": _source_rec_id,
            "source_version_id": _source_ver_id, "source_paragraph_id": _source_para_id,
            "relation_type": "source_governs_issue"}, headers=h, expect=404)
    after = await _snapshot()
    _assert_snapshot_equal(before, after, "foreign_user")
