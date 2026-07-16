"""P2.3 — Case & conversation/message route integration tests.

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
    CaseMember,
    Conversation,
    Message,
    Tenant,
    User,
)
from app.db.auth_repository import CaseMemberRepository
from app.db.session import get_sessionmaker
from app.main import app

OTHER_TENANT = "tenant-other"
OTHER_USER = "user-other"


@pytest_asyncio.fixture(autouse=True)
async def db_setup():
    maker = get_sessionmaker()
    async with maker() as session:
        # Clean any residue then seed local tenant/user + a foreign tenant/user.
        await session.execute(delete(Message).where(Message.tenant_id.in_(["local", OTHER_TENANT])))
        await session.execute(delete(Conversation).where(Conversation.tenant_id.in_(["local", OTHER_TENANT])))
        await session.execute(delete(CaseMember).where(CaseMember.tenant_id.in_(["local", OTHER_TENANT])))
        await session.execute(delete(Case).where(Case.tenant_id.in_(["local", OTHER_TENANT])))
        await session.execute(delete(AuditEvent).where(AuditEvent.tenant_id.in_(["local", OTHER_TENANT])))
        await session.execute(delete(User).where(User.id.in_(["local-user", OTHER_USER])))
        await session.execute(delete(Tenant).where(Tenant.id.in_(["local", OTHER_TENANT])))
        await session.flush()
        session.add(Tenant(id="local", name="Local", slug="local-cc", status="active"))
        session.add(Tenant(id=OTHER_TENANT, name="Other", slug="other-cc", status="active"))
        session.add(User(id="local-user", tenant_id="local", email_normalized="cc@local", display_name="L", status="active", role="lawyer"))
        session.add(User(id=OTHER_USER, tenant_id=OTHER_TENANT, email_normalized="cc@other", display_name="O", status="active", role="lawyer"))
        await session.commit()
    yield
    async with maker() as session:
        await session.execute(delete(Message).where(Message.tenant_id.in_(["local", OTHER_TENANT])))
        await session.execute(delete(Conversation).where(Conversation.tenant_id.in_(["local", OTHER_TENANT])))
        await session.execute(delete(CaseMember).where(CaseMember.tenant_id.in_(["local", OTHER_TENANT])))
        await session.execute(delete(Case).where(Case.tenant_id.in_(["local", OTHER_TENANT])))
        await session.execute(delete(AuditEvent).where(AuditEvent.tenant_id.in_(["local", OTHER_TENANT])))
        await session.execute(delete(User).where(User.id.in_(["local-user", OTHER_USER])))
        await session.execute(delete(Tenant).where(Tenant.id.in_(["local", OTHER_TENANT])))
        await session.commit()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _seed_foreign_case(case_id: str = "foreign-case") -> str:
    maker = get_sessionmaker()
    async with maker() as session:
        session.add(Case(
            id=case_id, tenant_id=OTHER_TENANT, owner_user_id=OTHER_USER,
            title="Foreign", legal_topic="x", status="active", version=1,
        ))
        await session.commit()
    return case_id


# ---------------------------------------------------------------------------
# Case CRUD
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_and_get_case(client: AsyncClient):
    r = await client.post("/api/v1/cases", json={"title": "Araç Ayıbı", "legal_topic": "Tüketici"})
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Araç Ayıbı"
    assert data["status"] == "active"
    assert data["version"] == 1
    case_id = data["id"]

    g = await client.get(f"/api/v1/cases/{case_id}")
    assert g.status_code == 200
    assert g.json()["id"] == case_id


@pytest.mark.asyncio
async def test_create_case_creates_owner_membership(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    r = await client.post(
        "/api/v1/cases",
        json={"title": "Membership", "legal_topic": "Tüketici"},
    )
    assert r.status_code == 201
    case_id = r.json()["id"]

    maker = get_sessionmaker()
    async with maker() as session:
        rows = (
            await session.execute(
                select(CaseMember).where(
                    CaseMember.tenant_id == "local",
                    CaseMember.user_id == "local-user",
                    CaseMember.case_id == case_id,
                )
            )
        ).scalars().all()

    assert len(rows) == 1
    member = rows[0]
    assert member.membership_role == "owner"
    assert member.revoked_at is None

    async def fail_membership(*args, **kwargs):
        raise RuntimeError("membership failed")

    monkeypatch.setattr(CaseMemberRepository, "ensure_member", fail_membership)
    with pytest.raises(RuntimeError, match="membership failed"):
        await client.post(
            "/api/v1/cases",
            json={"title": "Membership Rollback", "legal_topic": "Tüketici"},
        )

    async with maker() as session:
        rolled_back = (
            await session.execute(
                select(Case).where(
                    Case.tenant_id == "local",
                    Case.owner_user_id == "local-user",
                    Case.title == "Membership Rollback",
                )
            )
        ).scalar_one_or_none()
    assert rolled_back is None


@pytest.mark.asyncio
async def test_list_cases_excludes_archived_by_default(client: AsyncClient):
    a = (await client.post("/api/v1/cases", json={"title": "A"})).json()
    (await client.post("/api/v1/cases", json={"title": "B"})).json()
    await client.post(f"/api/v1/cases/{a['id']}/archive")

    active = await client.get("/api/v1/cases")
    assert active.status_code == 200
    titles = [c["title"] for c in active.json()["items"]]
    assert "B" in titles
    assert "A" not in titles

    archived = await client.get("/api/v1/cases", params={"archived": True})
    arch_titles = [c["title"] for c in archived.json()["items"]]
    assert arch_titles == ["A"]


@pytest.mark.asyncio
async def test_update_case_increments_version(client: AsyncClient):
    case = (await client.post("/api/v1/cases", json={"title": "Old"})).json()
    r = await client.patch(f"/api/v1/cases/{case['id']}", json={"title": "New"})
    assert r.status_code == 200
    assert r.json()["title"] == "New"
    assert r.json()["version"] == 2


@pytest.mark.asyncio
async def test_archive_and_restore(client: AsyncClient):
    case = (await client.post("/api/v1/cases", json={"title": "C"})).json()
    arch = await client.post(f"/api/v1/cases/{case['id']}/archive")
    assert arch.status_code == 200
    assert arch.json()["status"] == "archived"
    assert arch.json()["archived_at"] is not None

    rest = await client.post(f"/api/v1/cases/{case['id']}/restore")
    assert rest.status_code == 200
    assert rest.json()["status"] == "active"
    assert rest.json()["archived_at"] is None


@pytest.mark.asyncio
async def test_soft_delete_hides_case(client: AsyncClient):
    case = (await client.post("/api/v1/cases", json={"title": "D"})).json()
    d = await client.delete(f"/api/v1/cases/{case['id']}")
    assert d.status_code == 204

    g = await client.get(f"/api/v1/cases/{case['id']}")
    assert g.status_code == 404
    lst = await client.get("/api/v1/cases")
    assert case["id"] not in [c["id"] for c in lst.json()["items"]]


@pytest.mark.asyncio
async def test_get_missing_case_returns_404(client: AsyncClient):
    r = await client.get("/api/v1/cases/does-not-exist")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Tenant / IDOR isolation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cannot_access_foreign_case(client: AsyncClient):
    foreign_id = await _seed_foreign_case()
    # Local user must not see or mutate another tenant's case.
    assert (await client.get(f"/api/v1/cases/{foreign_id}")).status_code == 404
    assert (await client.patch(f"/api/v1/cases/{foreign_id}", json={"title": "hijack"})).status_code == 404
    assert (await client.post(f"/api/v1/cases/{foreign_id}/archive")).status_code == 404
    assert (await client.delete(f"/api/v1/cases/{foreign_id}")).status_code == 404


@pytest.mark.asyncio
async def test_foreign_case_absent_from_list(client: AsyncClient):
    await _seed_foreign_case()
    await client.post("/api/v1/cases", json={"title": "Mine"})
    lst = await client.get("/api/v1/cases")
    tenants_titles = [c["title"] for c in lst.json()["items"]]
    assert "Foreign" not in tenants_titles
    assert "Mine" in tenants_titles


# ---------------------------------------------------------------------------
# Conversations & messages
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_conversation_get_or_create_is_stable(client: AsyncClient):
    case = (await client.post("/api/v1/cases", json={"title": "Chat"})).json()
    c1 = await client.post(f"/api/v1/cases/{case['id']}/conversations")
    assert c1.status_code == 201
    c2 = await client.post(f"/api/v1/cases/{case['id']}/conversations")
    assert c2.status_code == 201
    # Same conversation returned, not a duplicate.
    assert c1.json()["id"] == c2.json()["id"]

    lst = await client.get(f"/api/v1/cases/{case['id']}/conversations")
    assert len(lst.json()["items"]) == 1


@pytest.mark.asyncio
async def test_send_and_list_messages_ordered(client: AsyncClient):
    case = (await client.post("/api/v1/cases", json={"title": "Chat"})).json()
    conv = (await client.post(f"/api/v1/cases/{case['id']}/conversations")).json()
    cid = conv["id"]

    for text in ["first", "second", "third"]:
        r = await client.post(f"/api/v1/conversations/{cid}/messages", json={"content": text})
        assert r.status_code == 201
        assert r.json()["role"] == "user"
        assert r.json()["status"] == "completed"

    lst = await client.get(f"/api/v1/conversations/{cid}/messages")
    assert lst.status_code == 200
    contents = [m["content"] for m in lst.json()["items"]]
    assert contents == ["first", "second", "third"]
    assert lst.json()["total"] == 3


@pytest.mark.asyncio
async def test_message_pagination(client: AsyncClient):
    case = (await client.post("/api/v1/cases", json={"title": "Chat"})).json()
    conv = (await client.post(f"/api/v1/cases/{case['id']}/conversations")).json()
    cid = conv["id"]
    for i in range(5):
        await client.post(f"/api/v1/conversations/{cid}/messages", json={"content": f"m{i}"})

    page1 = await client.get(f"/api/v1/conversations/{cid}/messages", params={"limit": 2, "offset": 0})
    assert len(page1.json()["items"]) == 2
    assert page1.json()["has_more"] is True

    page3 = await client.get(f"/api/v1/conversations/{cid}/messages", params={"limit": 2, "offset": 4})
    assert len(page3.json()["items"]) == 1
    assert page3.json()["has_more"] is False


@pytest.mark.asyncio
async def test_duplicate_message_prevented_by_client_request_id(client: AsyncClient):
    case = (await client.post("/api/v1/cases", json={"title": "Chat"})).json()
    conv = (await client.post(f"/api/v1/cases/{case['id']}/conversations")).json()
    cid = conv["id"]

    body = {"content": "hello", "client_request_id": "req-123"}
    r1 = await client.post(f"/api/v1/conversations/{cid}/messages", json=body)
    r2 = await client.post(f"/api/v1/conversations/{cid}/messages", json=body)
    assert r1.status_code == 201
    assert r2.status_code == 201
    # Idempotent: same message id, no duplicate row.
    assert r1.json()["id"] == r2.json()["id"]

    lst = await client.get(f"/api/v1/conversations/{cid}/messages")
    assert lst.json()["total"] == 1


@pytest.mark.asyncio
async def test_cannot_access_foreign_conversation(client: AsyncClient):
    foreign_case = await _seed_foreign_case("foreign-conv-case")
    maker = get_sessionmaker()
    async with maker() as session:
        session.add(Conversation(
            id="foreign-conv", tenant_id=OTHER_TENANT, case_id=foreign_case,
            title="", status="active", created_by=OTHER_USER,
        ))
        await session.commit()

    # Different tenant → 404, and no messages leak.
    assert (await client.get("/api/v1/conversations/foreign-conv/messages")).status_code == 404
    assert (await client.post("/api/v1/conversations/foreign-conv/messages", json={"content": "x"})).status_code == 404


@pytest.mark.asyncio
async def test_empty_message_rejected(client: AsyncClient):
    case = (await client.post("/api/v1/cases", json={"title": "Chat"})).json()
    conv = (await client.post(f"/api/v1/cases/{case['id']}/conversations")).json()
    r = await client.post(f"/api/v1/conversations/{conv['id']}/messages", json={"content": ""})
    assert r.status_code == 422
