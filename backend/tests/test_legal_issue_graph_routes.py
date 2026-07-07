"""P1.7 — Legal Issue Graph Route Integration Tests."""
from __future__ import annotations

import asyncio
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db.models import Tenant, User, Case, CaseMember
from app.db.session import get_sessionmaker
from app.main import app

CASE_A = "case-rt-a"
CASE_B = "case-rt-b"


@pytest_asyncio.fixture(autouse=True)
async def db_setup():
    maker = get_sessionmaker()
    async with maker() as session:
        from sqlalchemy import delete
        from app.db.models import LegalIssueNode, LegalIssueEdge, CaseMember, Case, User, Tenant
        from app.db.models import AuditEvent, BackgroundJob
        await session.execute(delete(BackgroundJob).where(BackgroundJob.tenant_id == 'local'))
        await session.execute(delete(LegalIssueEdge).where(
            (LegalIssueEdge.tenant_id == 'local') &
            LegalIssueEdge.case_id.in_([CASE_A, CASE_B])))
        await session.execute(delete(LegalIssueNode).where(
            (LegalIssueNode.tenant_id == 'local') &
            LegalIssueNode.case_id.in_([CASE_A, CASE_B])))
        await session.execute(delete(AuditEvent).where(AuditEvent.tenant_id == 'local'))
        await session.execute(delete(CaseMember).where(CaseMember.id.in_(['mem-rt-a', 'mem-rt-b'])))
        await session.execute(delete(Case).where(Case.id.in_([CASE_A, CASE_B])))
        await session.execute(delete(User).where(User.id == 'local-user'))
        await session.execute(delete(Tenant).where(Tenant.id == 'local'))
        await session.flush()
        tid = Tenant(id="local", name="LocalRoute", slug="local-rt", status="active")
        uid = User(id="local-user", tenant_id="local", email_normalized="rt@local", display_name="Test", status="active", role="lawyer")
        session.add(tid)
        session.add(uid)
        await session.flush()
        session.add(Case(id=CASE_A, tenant_id="local", owner_user_id="local-user", title="CaseA", legal_topic="test", profile_id="default", event_text="", status="active", version=1))
        session.add(Case(id=CASE_B, tenant_id="local", owner_user_id="local-user", title="CaseB", legal_topic="test", profile_id="default", event_text="", status="active", version=1))
        await session.flush()
        session.add(CaseMember(id="mem-rt-a", tenant_id="local", case_id=CASE_A, user_id="local-user", membership_role="owner", permissions_override={}))
        session.add(CaseMember(id="mem-rt-b", tenant_id="local", case_id=CASE_B, user_id="local-user", membership_role="owner", permissions_override={}))
        await session.flush()
        await session.commit()
    yield
    async with maker() as session:
        from sqlalchemy import delete
        from app.db.models import LegalIssueNode, LegalIssueEdge, CaseMember, Case
        from app.db.models import AuditEvent
        await session.execute(delete(LegalIssueEdge).where(
            (LegalIssueEdge.tenant_id == 'local') &
            LegalIssueEdge.case_id.in_([CASE_A, CASE_B])))
        await session.execute(delete(LegalIssueNode).where(
            (LegalIssueNode.tenant_id == 'local') &
            LegalIssueNode.case_id.in_([CASE_A, CASE_B])))
        await session.execute(delete(AuditEvent).where(AuditEvent.tenant_id == 'local'))
        await session.execute(delete(CaseMember).where(CaseMember.id.in_(['mem-rt-a', 'mem-rt-b'])))
        await session.execute(delete(Case).where(Case.id.in_([CASE_A, CASE_B])))
        await session.commit()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _g(path):
    return f"/api/cases/{CASE_A}/legal-graph{path}"

def _gb(path):
    return f"/api/cases/{CASE_B}/legal-graph{path}"


class TestGraphEndpoints:
    @pytest.mark.asyncio
    async def test_get_empty_graph(self, db_setup, client):
        r = await client.get(_g(""))
        assert r.status_code == 200
        assert r.json()["node_count"] == 0

    @pytest.mark.asyncio
    async def test_get_empty_summary(self, db_setup, client):
        r = await client.get(_g("/summary"))
        assert r.status_code == 200
        assert r.json()["total_nodes"] == 0

    @pytest.mark.asyncio
    async def test_validate_empty(self, db_setup, client):
        r = await client.get(_g("/validate"))
        assert r.status_code == 200
        assert r.json()["valid"] is True

    @pytest.mark.asyncio
    async def test_rebuild(self, db_setup, client):
        r = await client.post(_g("/rebuild"), json={})
        assert r.status_code == 200
        assert "nodes" in r.json()


class TestNodeEndpoints:
    @pytest.mark.asyncio
    async def test_create(self, db_setup, client):
        r = await client.post(_g("/nodes"), json={"node_type":"fact","title":"F1","source_type":"user_input"})
        assert r.status_code == 201
        assert r.json()["title"] == "F1"

    @pytest.mark.asyncio
    async def test_invalid_type_400(self, db_setup, client):
        r = await client.post(_g("/nodes"), json={"node_type":"bad","title":"X"})
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_status_400(self, db_setup, client):
        r = await client.post(_g("/nodes"), json={"node_type":"fact","title":"X","status":"bad"})
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_list(self, db_setup, client):
        r = await client.get(_g("/nodes"))
        count_before = len(r.json())
        await client.post(_g("/nodes"), json={"node_type":"fact","title":"ListTestA","source_type":"user_input"})
        await client.post(_g("/nodes"), json={"node_type":"legal_issue","title":"ListTestB","source_type":"user_input"})
        r = await client.get(_g("/nodes"))
        assert r.status_code == 200
        assert len(r.json()) == count_before + 2

    @pytest.mark.asyncio
    async def test_get_single(self, db_setup, client):
        cr = await client.post(_g("/nodes"), json={"node_type":"fact","title":"Single","source_type":"user_input"})
        nid = cr.json()["id"]
        r = await client.get(_g(f"/nodes/{nid}"))
        assert r.status_code == 200
        assert r.json()["title"] == "Single"

    @pytest.mark.asyncio
    async def test_not_found_404(self, db_setup, client):
        r = await client.get(_g("/nodes/nope"))
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_update(self, db_setup, client):
        cr = await client.post(_g("/nodes"), json={"node_type":"fact","title":"Old","source_type":"user_input"})
        nid = cr.json()["id"]
        r = await client.patch(_g(f"/nodes/{nid}"), json={"title":"New","status":"confirmed"})
        assert r.status_code == 200
        assert r.json()["title"] == "New"
        assert r.json()["status"] == "confirmed"

    @pytest.mark.asyncio
    async def test_delete_restore(self, db_setup, client):
        cr = await client.post(_g("/nodes"), json={"node_type":"fact","title":"DelMe","source_type":"user_input"})
        nid = cr.json()["id"]
        dr = await client.delete(_g(f"/nodes/{nid}"))
        assert dr.status_code == 200
        assert dr.json()["deleted_at"] is not None
        rr = await client.post(_g(f"/nodes/{nid}/restore"))
        assert rr.status_code == 200
        assert rr.json()["deleted_at"] is None

    @pytest.mark.asyncio
    async def test_delete_twice_409(self, db_setup, client):
        cr = await client.post(_g("/nodes"), json={"node_type":"fact","title":"2X","source_type":"user_input"})
        nid = cr.json()["id"]
        await client.delete(_g(f"/nodes/{nid}"))
        r = await client.delete(_g(f"/nodes/{nid}"))
        assert r.status_code == 409


class TestEdgeEndpoints:
    async def _nodes(self, client):
        r1 = await client.post(_g("/nodes"), json={"node_type":"fact","title":"Src","status":"confirmed","source_type":"user_input"})
        r2 = await client.post(_g("/nodes"), json={"node_type":"evidence","title":"Tgt","status":"confirmed","source_type":"user_input"})
        return r1.json()["id"], r2.json()["id"]

    @pytest.mark.asyncio
    async def test_create(self, db_setup, client):
        n1, n2 = await self._nodes(client)
        r = await client.post(_g("/edges"), json={"source_node_id":n1,"target_node_id":n2,"relation_type":"proven_by"})
        assert r.status_code == 201

    @pytest.mark.asyncio
    async def test_self_loop_400(self, db_setup, client):
        n1, _ = await self._nodes(client)
        r = await client.post(_g("/edges"), json={"source_node_id":n1,"target_node_id":n1,"relation_type":"supports"})
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_duplicate_409(self, db_setup, client):
        n1, n2 = await self._nodes(client)
        body = {"source_node_id":n1,"target_node_id":n2,"relation_type":"proven_by"}
        await client.post(_g("/edges"), json=body)
        r = await client.post(_g("/edges"), json=body)
        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_missing_source_404(self, db_setup, client):
        _, n2 = await self._nodes(client)
        r = await client.post(_g("/edges"), json={"source_node_id":"none","target_node_id":n2,"relation_type":"supports"})
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_list(self, db_setup, client):
        n1, n2 = await self._nodes(client)
        r_before = await client.get(_g("/edges"))
        count_before = len(r_before.json())
        await client.post(_g("/edges"), json={"source_node_id":n1,"target_node_id":n2,"relation_type":"proven_by"})
        r = await client.get(_g("/edges"))
        assert r.status_code == 200
        assert len(r.json()) == count_before + 1

    @pytest.mark.asyncio
    async def test_delete_restore(self, db_setup, client):
        n1, n2 = await self._nodes(client)
        cr = await client.post(_g("/edges"), json={"source_node_id":n1,"target_node_id":n2,"relation_type":"proven_by"})
        eid = cr.json()["id"]
        dr = await client.delete(_g(f"/edges/{eid}"))
        assert dr.status_code == 200
        assert dr.json()["deleted_at"] is not None
        rr = await client.post(_g(f"/edges/{eid}/restore"))
        assert rr.status_code == 200
        assert rr.json()["deleted_at"] is None


class TestCrossCase:
    @pytest.mark.asyncio
    async def test_node_not_visible(self, db_setup, client):
        r = await client.post(_g("/nodes"), json={"node_type":"fact","title":"Secret","source_type":"user_input"})
        nid = r.json()["id"]
        r2 = await client.get(_gb(f"/nodes/{nid}"))
        assert r2.status_code == 404

    @pytest.mark.asyncio
    async def test_cross_case_edge(self, db_setup, client):
        r1 = await client.post(_g("/nodes"), json={"node_type":"fact","title":"F1","source_type":"user_input"})
        r2 = await client.post(_gb("/nodes"), json={"node_type":"fact","title":"F2","source_type":"user_input"})
        n1, n2 = r1.json()["id"], r2.json()["id"]
        r = await client.post(_g("/edges"), json={"source_node_id":n1,"target_node_id":n2,"relation_type":"supports"})
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_nodes_separate_per_case(self, db_setup, client):
        c1 = await client.post(_g("/nodes"), json={"node_type":"fact","title":"XC1Node","source_type":"user_input"})
        c2 = await client.post(_gb("/nodes"), json={"node_type":"fact","title":"XC2Node","source_type":"user_input"})
        nid1, nid2 = c1.json()["id"], c2.json()["id"]

        r1 = await client.get(_g(f"/nodes/{nid1}"))
        assert r1.status_code == 200
        assert r1.json()["title"] == "XC1Node"

        r2 = await client.get(_gb(f"/nodes/{nid2}"))
        assert r2.status_code == 200
        assert r2.json()["title"] == "XC2Node"

        r_cross = await client.get(_gb(f"/nodes/{nid1}"))
        assert r_cross.status_code == 404


class TestWorkflowRegression:
    @pytest.mark.asyncio
    async def test_graph_isolated_per_case(self, db_setup, client):
        cr = await client.post(_g("/nodes"), json={"node_type":"legal_issue","title":"IsoIssue","source_type":"user_input"})
        nid = cr.json()["id"]

        r_cross = await client.get(_gb(f"/nodes/{nid}"))
        assert r_cross.status_code == 404

    @pytest.mark.asyncio
    async def test_rebuild_no_data_works(self, db_setup, client):
        r = await client.post(_g("/rebuild"), json={})
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_rebuild_idempotent(self, db_setup, client):
        await client.post(_g("/rebuild"), json={})
        r1 = await client.get(_g(""))
        await client.post(_g("/rebuild"), json={})
        r2 = await client.get(_g(""))
        assert r1.json()["node_count"] == r2.json()["node_count"]
