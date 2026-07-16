"""P2.4 — Structured case memory route integration tests.

Runs against the real DB layer in local auth mode (ctx = local-user / local).
Cross-tenant / cross-user isolation is exercised by seeding rows owned by a
different user or tenant and asserting the API returns 404 (no disclosure).
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from app.db.models import (
    AuditEvent,
    Case,
    CaseFact,
    CaseMember,
    Contradiction,
    Deadline,
    Defense,
    Evidence,
    MissingInformation,
    Risk,
    TimelineEvent,
    Tenant,
    User,
)
from app.db.session import get_sessionmaker
from app.main import app

OTHER_TENANT = "tenant-mem-other"
OTHER_USER = "user-mem-other"


@pytest_asyncio.fixture(autouse=True)
async def db_setup():
    maker = get_sessionmaker()
    tenants = ["local", OTHER_TENANT]
    async with maker() as session:
        for model in (CaseFact, TimelineEvent, MissingInformation, Contradiction, Risk, Evidence, Deadline, Defense):
            await session.execute(delete(model).where(model.tenant_id.in_(tenants)))
        await session.execute(delete(CaseMember).where(CaseMember.tenant_id.in_(tenants)))
        await session.execute(delete(Case).where(Case.tenant_id.in_(tenants)))
        await session.execute(delete(AuditEvent).where(AuditEvent.tenant_id.in_(tenants)))
        await session.execute(delete(User).where(User.id.in_(["local-user", OTHER_USER])))
        await session.execute(delete(Tenant).where(Tenant.id.in_(tenants)))
        await session.flush()
        session.add(Tenant(id="local", name="Local", slug="local-mem", status="active"))
        session.add(Tenant(id=OTHER_TENANT, name="Other", slug="other-mem", status="active"))
        session.add(User(id="local-user", tenant_id="local", email_normalized="mem@local", display_name="L", status="active", role="lawyer"))
        session.add(User(id=OTHER_USER, tenant_id=OTHER_TENANT, email_normalized="mem@other", display_name="O", status="active", role="lawyer"))
        await session.commit()
    yield
    async with maker() as session:
        for model in (CaseFact, TimelineEvent, MissingInformation, Contradiction, Risk, Evidence, Deadline, Defense):
            await session.execute(delete(model).where(model.tenant_id.in_(tenants)))
        await session.execute(delete(CaseMember).where(CaseMember.tenant_id.in_(tenants)))
        await session.execute(delete(Case).where(Case.tenant_id.in_(tenants)))
        await session.execute(delete(AuditEvent).where(AuditEvent.tenant_id.in_(tenants)))
        await session.execute(delete(User).where(User.id.in_(["local-user", OTHER_USER])))
        await session.execute(delete(Tenant).where(Tenant.id.in_(tenants)))
        await session.commit()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _make_case(client: AsyncClient, title: str = "Mem Case") -> str:
    r = await client.post("/api/v1/cases", json={"title": title})
    assert r.status_code == 201
    return r.json()["id"]


async def _seed_foreign_case(case_id: str = "foreign-mem-case") -> str:
    maker = get_sessionmaker()
    async with maker() as session:
        session.add(Case(
            id=case_id, tenant_id=OTHER_TENANT, owner_user_id=OTHER_USER,
            title="Foreign", legal_topic="x", status="active", version=1,
        ))
        await session.commit()
    return case_id


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_and_list_facts(client: AsyncClient):
    case_id = await _make_case(client)
    r = await client.post(f"/api/v1/cases/{case_id}/memory/facts",
                          json={"fact_type": "sale_amount", "value": "150000", "importance": "critical"})
    assert r.status_code == 201
    data = r.json()
    assert data["fact_type"] == "sale_amount"
    assert data["verification_status"] == "suggested"
    assert data["version"] == 1

    mem = await client.get(f"/api/v1/cases/{case_id}/memory")
    assert mem.status_code == 200
    assert mem.json()["counts"]["facts"] == 1


@pytest.mark.asyncio
async def test_suggested_fact_is_not_trusted(client: AsyncClient):
    case_id = await _make_case(client)
    r = await client.post(f"/api/v1/cases/{case_id}/memory/facts",
                          json={"fact_type": "purchase_date", "value": "2023-01-01"})
    # Suggested, not user_confirmed — never auto-trusted.
    assert r.json()["verification_status"] == "suggested"


@pytest.mark.asyncio
async def test_confirm_and_reject_fact(client: AsyncClient):
    case_id = await _make_case(client)
    fid = (await client.post(f"/api/v1/cases/{case_id}/memory/facts",
                             json={"fact_type": "notice_date", "value": "2023-02-02"})).json()["id"]
    c = await client.post(f"/api/v1/cases/{case_id}/memory/facts/{fid}/confirm")
    assert c.status_code == 200
    assert c.json()["verification_status"] == "user_confirmed"

    rj = await client.post(f"/api/v1/cases/{case_id}/memory/facts/{fid}/reject")
    assert rj.json()["verification_status"] == "rejected"


@pytest.mark.asyncio
async def test_update_fact_version_conflict(client: AsyncClient):
    case_id = await _make_case(client)
    fact = (await client.post(f"/api/v1/cases/{case_id}/memory/facts",
                              json={"fact_type": "report_number", "value": "A1"})).json()
    fid = fact["id"]
    # Correct version succeeds and bumps to 2.
    ok = await client.patch(f"/api/v1/cases/{case_id}/memory/facts/{fid}",
                            json={"version": 1, "value": "A2"})
    assert ok.status_code == 200
    assert ok.json()["version"] == 2
    # Stale version rejected with 409.
    stale = await client.patch(f"/api/v1/cases/{case_id}/memory/facts/{fid}",
                               json={"version": 1, "value": "A3"})
    assert stale.status_code == 409


# ---------------------------------------------------------------------------
# Contradictions
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_conflicting_values_create_contradiction(client: AsyncClient):
    case_id = await _make_case(client)
    await client.post(f"/api/v1/cases/{case_id}/memory/facts",
                      json={"fact_type": "vehicle_plate", "value": "34ABC01"})
    await client.post(f"/api/v1/cases/{case_id}/memory/facts",
                      json={"fact_type": "vehicle_plate", "value": "34XYZ99"})

    contradictions = await client.get(f"/api/v1/cases/{case_id}/memory/contradictions")
    assert contradictions.status_code == 200
    items = contradictions.json()
    assert len(items) == 1
    assert items[0]["status"] == "open"
    assert items[0]["contradiction_type"] == "value_mismatch"

    # Conflicting facts must not appear trusted.
    mem = await client.get(f"/api/v1/cases/{case_id}/memory")
    statuses = {f["verification_status"] for f in mem.json()["facts"]}
    assert "conflicting" in statuses
    assert "user_confirmed" not in statuses


@pytest.mark.asyncio
async def test_resolve_contradiction_preserves_rejected(client: AsyncClient):
    case_id = await _make_case(client)
    f1 = (await client.post(f"/api/v1/cases/{case_id}/memory/facts",
                            json={"fact_type": "sale_amount", "value": "100"})).json()
    f2 = (await client.post(f"/api/v1/cases/{case_id}/memory/facts",
                            json={"fact_type": "sale_amount", "value": "200"})).json()
    contradiction = (await client.get(f"/api/v1/cases/{case_id}/memory/contradictions")).json()[0]

    resolve = await client.post(
        f"/api/v1/cases/{case_id}/memory/contradictions/{contradiction['id']}/resolve",
        json={"resolution_fact_id": f1["id"], "note": "receipt confirms"},
    )
    assert resolve.status_code == 200
    assert resolve.json()["status"] == "resolved"

    mem = await client.get(f"/api/v1/cases/{case_id}/memory")
    by_id = {f["id"]: f for f in mem.json()["facts"]}
    # Chosen fact confirmed; other preserved as rejected (NOT deleted).
    assert by_id[f1["id"]]["verification_status"] == "user_confirmed"
    assert by_id[f2["id"]]["verification_status"] == "rejected"
    assert len(mem.json()["facts"]) == 2


@pytest.mark.asyncio
async def test_resolve_contradiction_rejects_foreign_fact(client: AsyncClient):
    case_id = await _make_case(client)
    await client.post(f"/api/v1/cases/{case_id}/memory/facts", json={"fact_type": "x", "value": "1"})
    await client.post(f"/api/v1/cases/{case_id}/memory/facts", json={"fact_type": "x", "value": "2"})
    contradiction = (await client.get(f"/api/v1/cases/{case_id}/memory/contradictions")).json()[0]
    r = await client.post(
        f"/api/v1/cases/{case_id}/memory/contradictions/{contradiction['id']}/resolve",
        json={"resolution_fact_id": "not-a-conflicting-fact"},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Missing information
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_missing_info_not_resolved_without_verified_value(client: AsyncClient):
    case_id = await _make_case(client)
    item = (await client.post(f"/api/v1/cases/{case_id}/memory/missing-information",
                              json={"field_key": "sale_amount", "label": "Satış bedeli",
                                    "importance": "critical",
                                    "completion_condition": {"fact_type": "sale_amount", "value_required": True}})).json()
    # A merely suggested fact of the category does NOT complete it.
    await client.post(f"/api/v1/cases/{case_id}/memory/facts",
                      json={"fact_type": "sale_amount", "value": "150000"})
    r = await client.post(f"/api/v1/cases/{case_id}/memory/missing-information/{item['id']}/resolve")
    assert r.status_code == 409  # not satisfied — value not verified

    items = (await client.get(f"/api/v1/cases/{case_id}/memory/missing-information")).json()
    assert items[0]["status"] == "open"


@pytest.mark.asyncio
async def test_missing_info_resolved_after_confirm(client: AsyncClient):
    case_id = await _make_case(client)
    await client.post(f"/api/v1/cases/{case_id}/memory/missing-information",
                      json={"field_key": "purchase_date", "label": "Alım tarihi",
                            "importance": "critical",
                            "completion_condition": {"fact_type": "purchase_date", "value_required": True}})
    fact = (await client.post(f"/api/v1/cases/{case_id}/memory/facts",
                              json={"fact_type": "purchase_date", "value": "2023-01-01"})).json()
    # Confirming the fact auto-resolves the matching missing-information.
    await client.post(f"/api/v1/cases/{case_id}/memory/facts/{fact['id']}/confirm")
    items = (await client.get(f"/api/v1/cases/{case_id}/memory/missing-information")).json()
    assert items[0]["status"] == "supplied"
    assert items[0]["resolved_by_fact_id"] == fact["id"]


# ---------------------------------------------------------------------------
# Risk rules
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_overall_risk_not_low_with_critical_missing(client: AsyncClient):
    case_id = await _make_case(client)
    await client.post(f"/api/v1/cases/{case_id}/memory/missing-information",
                      json={"field_key": "defect_notice_date", "label": "İhbar tarihi",
                            "importance": "critical"})
    mem = await client.get(f"/api/v1/cases/{case_id}/memory")
    assert mem.json()["overall_risk_level"] != "low"


@pytest.mark.asyncio
async def test_overall_risk_not_low_with_open_critical_contradiction(client: AsyncClient):
    case_id = await _make_case(client)
    await client.post(f"/api/v1/cases/{case_id}/memory/facts", json={"fact_type": "vin", "value": "AAA"})
    await client.post(f"/api/v1/cases/{case_id}/memory/facts", json={"fact_type": "vin", "value": "BBB"})
    mem = await client.get(f"/api/v1/cases/{case_id}/memory")
    assert mem.json()["overall_risk_level"] != "low"


@pytest.mark.asyncio
async def test_risk_create_and_severity(client: AsyncClient):
    case_id = await _make_case(client)
    r = await client.post(f"/api/v1/cases/{case_id}/memory/risks",
                          json={"risk_type": "deadline", "severity": "high", "title": "Hak düşürücü süre"})
    assert r.status_code == 201
    assert r.json()["severity"] == "high"
    mem = await client.get(f"/api/v1/cases/{case_id}/memory")
    assert mem.json()["overall_risk_level"] in ("high", "critical")


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_timeline_ordering_dated_before_undated(client: AsyncClient):
    case_id = await _make_case(client)
    await client.post(f"/api/v1/cases/{case_id}/memory/timeline",
                      json={"description": "no date"})
    await client.post(f"/api/v1/cases/{case_id}/memory/timeline",
                      json={"description": "later", "event_date": "2023-05-01"})
    await client.post(f"/api/v1/cases/{case_id}/memory/timeline",
                      json={"description": "earlier", "event_date": "2023-01-01"})
    events = (await client.get(f"/api/v1/cases/{case_id}/memory/timeline")).json()
    descriptions = [e["description"] for e in events]
    assert descriptions.index("earlier") < descriptions.index("later")
    assert descriptions[-1] == "no date"  # undated sorts last


# ---------------------------------------------------------------------------
# Isolation / IDOR / validation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_foreign_case_memory_returns_404(client: AsyncClient):
    foreign = await _seed_foreign_case()
    assert (await client.get(f"/api/v1/cases/{foreign}/memory")).status_code == 404
    assert (await client.post(f"/api/v1/cases/{foreign}/memory/facts",
                              json={"fact_type": "x", "value": "1"})).status_code == 404
    assert (await client.get(f"/api/v1/cases/{foreign}/memory/risks")).status_code == 404


@pytest.mark.asyncio
async def test_missing_case_returns_404(client: AsyncClient):
    assert (await client.get("/api/v1/cases/does-not-exist/memory")).status_code == 404


@pytest.mark.asyncio
async def test_soft_deleted_case_memory_inaccessible(client: AsyncClient):
    case_id = await _make_case(client)
    await client.post(f"/api/v1/cases/{case_id}/memory/facts", json={"fact_type": "x", "value": "1"})
    await client.delete(f"/api/v1/cases/{case_id}")
    assert (await client.get(f"/api/v1/cases/{case_id}/memory")).status_code == 404


@pytest.mark.asyncio
async def test_empty_fact_type_rejected(client: AsyncClient):
    case_id = await _make_case(client)
    r = await client.post(f"/api/v1/cases/{case_id}/memory/facts", json={"fact_type": "", "value": "x"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_audit_metadata_excludes_content(client: AsyncClient):
    case_id = await _make_case(client)
    secret = "GİZLİ-DEĞER-12345"
    await client.post(f"/api/v1/cases/{case_id}/memory/facts",
                      json={"fact_type": "sale_amount", "value": secret})
    maker = get_sessionmaker()
    async with maker() as session:
        rows = (await session.execute(
            select(AuditEvent).where(AuditEvent.tenant_id == "local", AuditEvent.case_id == case_id)
        )).scalars().all()
    assert rows, "expected audit events"
    for row in rows:
        assert secret not in str(row.safe_metadata)
