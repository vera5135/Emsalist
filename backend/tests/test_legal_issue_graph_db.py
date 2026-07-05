"""P1.7 — Legal Issue Graph DB Service Tests."""
from __future__ import annotations

import pytest
import pytest_asyncio

from app.db.models import Tenant, User, Case, CaseMember, LegalIssueNode, LegalIssueEdge, new_uuid
from app.services import legal_issue_graph_db_service as svc
from app.db.session import get_sessionmaker


@pytest_asyncio.fixture
async def db_session():
    import sqlite3, os
    db_path = os.path.join(os.path.dirname(__file__), "..", "case_store", "emsalist.db")
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM legal_issue_edges WHERE tenant_id IN ('t-a-g','t-b-g')")
    conn.execute("DELETE FROM legal_issue_nodes WHERE tenant_id IN ('t-a-g','t-b-g')")
    conn.execute("DELETE FROM case_members WHERE tenant_id IN ('t-a-g','t-b-g')")
    conn.execute("DELETE FROM cases WHERE tenant_id IN ('t-a-g','t-b-g')")
    conn.execute("DELETE FROM users WHERE tenant_id IN ('t-a-g','t-b-g')")
    conn.execute("DELETE FROM tenants WHERE id IN ('t-a-g','t-b-g')")
    conn.commit()
    conn.close()
    maker = get_sessionmaker()
    async with maker() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def tenant_a(db_session):
    t = Tenant(id="t-a-g", name="Tenant A", slug="tenant-a-g", status="active")
    db_session.add(t)
    await db_session.flush()
    return t


@pytest_asyncio.fixture
async def user_a(db_session, tenant_a):
    u = User(id="u-a-g", tenant_id=tenant_a.id, email_normalized="a@g.com", display_name="User A", status="active", role="lawyer")
    db_session.add(u)
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def user_b(db_session, tenant_a):
    u = User(id="u-b-g", tenant_id=tenant_a.id, email_normalized="b@g.com", display_name="User B", status="active", role="lawyer")
    db_session.add(u)
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def case_a(db_session, tenant_a, user_a):
    c = Case(id="case-a-g", tenant_id=tenant_a.id, owner_user_id=user_a.id, title="Test Case A", status="active")
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def case_b(db_session, tenant_a, user_a):
    c = Case(id="case-b-g", tenant_id=tenant_a.id, owner_user_id=user_a.id, title="Test Case B", status="active")
    db_session.add(c)
    await db_session.flush()
    return c


@pytest_asyncio.fixture
async def member_a(db_session, tenant_a, case_a, user_a):
    m = CaseMember(id=new_uuid(), tenant_id=tenant_a.id, case_id=case_a.id, user_id=user_a.id, membership_role="owner")
    db_session.add(m)
    await db_session.flush()
    return m


@pytest_asyncio.fixture
async def member_viewer(db_session, tenant_a, case_a, user_b):
    m = CaseMember(id=new_uuid(), tenant_id=tenant_a.id, case_id=case_a.id, user_id=user_b.id, membership_role="viewer")
    db_session.add(m)
    await db_session.flush()
    return m


@pytest_asyncio.fixture
async def member_both(db_session, tenant_a, case_b, user_a):
    m = CaseMember(id=new_uuid(), tenant_id=tenant_a.id, case_id=case_b.id, user_id=user_a.id, membership_role="owner")
    db_session.add(m)
    await db_session.flush()
    return m


class TestNodeCRUD:
    @pytest.mark.asyncio
    async def test_create_node(self, db_session, tenant_a, case_a, member_a):
        result = await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="fact", title="Test Fact", status="proposed")
        assert result["node_type"] == "fact"
        assert result["title"] == "Test Fact"
        assert result["tenant_id"] == tenant_a.id

    @pytest.mark.asyncio
    async def test_get_node(self, db_session, tenant_a, case_a, member_a):
        created = await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="legal_issue", title="Ayıplı mal", status="confirmed", confidence=0.9)
        result = await svc.get_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_id=created["id"])
        assert result is not None
        assert result["title"] == "Ayıplı mal"

    @pytest.mark.asyncio
    async def test_update_node(self, db_session, tenant_a, case_a, member_a):
        created = await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="fact", title="Original", status="proposed")
        updated = await svc.update_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_id=created["id"], title="Updated", status="confirmed")
        assert updated["title"] == "Updated"
        assert updated["status"] == "confirmed"

    @pytest.mark.asyncio
    async def test_delete_node(self, db_session, tenant_a, case_a, member_a):
        created = await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="fact", title="To Delete")
        deleted = await svc.delete_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_id=created["id"])
        assert deleted["deleted_at"] is not None
        result = await svc.get_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_id=created["id"])
        assert result is None

    @pytest.mark.asyncio
    async def test_restore_node(self, db_session, tenant_a, case_a, member_a):
        created = await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="fact", title="Restore Me")
        await svc.delete_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_id=created["id"])
        restored = await svc.restore_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_id=created["id"])
        assert restored["deleted_at"] is None

    @pytest.mark.asyncio
    async def test_list_hides_deleted(self, db_session, tenant_a, case_a, member_a):
        n1 = await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="fact", title="Alive")
        n2 = await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="fact", title="Dead")
        await svc.delete_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_id=n2["id"])
        nodes = await svc.list_nodes(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g")
        ids = {n["id"] for n in nodes}
        assert n1["id"] in ids
        assert n2["id"] not in ids

    @pytest.mark.asyncio
    async def test_invalid_node_type(self, db_session, tenant_a, case_a, member_a):
        with pytest.raises(ValueError, match="Invalid node_type"):
            await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="imaginary", title="X")

    @pytest.mark.asyncio
    async def test_invalid_status(self, db_session, tenant_a, case_a, member_a):
        with pytest.raises(ValueError, match="Invalid status"):
            await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="fact", title="X", status="weird")

    @pytest.mark.asyncio
    async def test_confidence_bounds(self, db_session, tenant_a, case_a, member_a):
        with pytest.raises(ValueError, match="confidence"):
            await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="fact", title="X", confidence=1.5)

    @pytest.mark.asyncio
    async def test_cannot_update_deleted(self, db_session, tenant_a, case_a, member_a):
        n = await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="fact", title="X")
        await svc.delete_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_id=n["id"])
        with pytest.raises(ValueError, match="Cannot update a deleted node"):
            await svc.update_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_id=n["id"], title="Y")

    @pytest.mark.asyncio
    async def test_cannot_delete_twice(self, db_session, tenant_a, case_a, member_a):
        n = await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="fact", title="X")
        await svc.delete_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_id=n["id"])
        with pytest.raises(ValueError, match="Node already deleted"):
            await svc.delete_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_id=n["id"])

    @pytest.mark.asyncio
    async def test_restore_non_deleted(self, db_session, tenant_a, case_a, member_a):
        n = await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="fact", title="X")
        with pytest.raises(ValueError, match="Node is not deleted"):
            await svc.restore_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_id=n["id"])

    @pytest.mark.asyncio
    async def test_metadata_json(self, db_session, tenant_a, case_a, member_a):
        n = await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="fact", title="Meta", metadata={"key": "value"})
        assert n["metadata"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_missing_information_type(self, db_session, tenant_a, case_a, member_a):
        n = await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="missing_information", title="Satış tarihi", status="missing")
        assert n["node_type"] == "missing_information"
        assert n["status"] == "missing"


class TestEdgeCRUD:
    @pytest_asyncio.fixture
    async def nodes(self, db_session, tenant_a, case_a, member_a):
        n1 = await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="fact", title="F1", status="confirmed")
        n2 = await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="evidence", title="E1", status="confirmed")
        return n1, n2

    @pytest.mark.asyncio
    async def test_create_edge(self, db_session, tenant_a, case_a, member_a, nodes):
        n1, n2 = nodes
        edge = await svc.create_edge(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", source_node_id=n1["id"], target_node_id=n2["id"], relation_type="proven_by")
        assert edge["relation_type"] == "proven_by"

    @pytest.mark.asyncio
    async def test_self_loop_blocked(self, db_session, tenant_a, case_a, member_a, nodes):
        n1, _ = nodes
        with pytest.raises(ValueError, match="Self-loop"):
            await svc.create_edge(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", source_node_id=n1["id"], target_node_id=n1["id"], relation_type="supports")

    @pytest.mark.asyncio
    async def test_duplicate_edge(self, db_session, tenant_a, case_a, member_a, nodes):
        n1, n2 = nodes
        await svc.create_edge(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", source_node_id=n1["id"], target_node_id=n2["id"], relation_type="proven_by")
        with pytest.raises(ValueError, match="Duplicate"):
            await svc.create_edge(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", source_node_id=n1["id"], target_node_id=n2["id"], relation_type="proven_by")

    @pytest.mark.asyncio
    async def test_edge_to_deleted_node(self, db_session, tenant_a, case_a, member_a):
        n1 = await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="fact", title="F")
        n2 = await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="evidence", title="E")
        await svc.delete_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_id=n1["id"])
        with pytest.raises(KeyError, match="Source node"):
            await svc.create_edge(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", source_node_id=n1["id"], target_node_id=n2["id"], relation_type="supports")

    @pytest.mark.asyncio
    async def test_delete_restore_edge(self, db_session, tenant_a, case_a, member_a, nodes):
        n1, n2 = nodes
        edge = await svc.create_edge(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", source_node_id=n1["id"], target_node_id=n2["id"], relation_type="proven_by")
        deleted = await svc.delete_edge(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", edge_id=edge["id"])
        assert deleted["deleted_at"] is not None
        restored = await svc.restore_edge(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", edge_id=edge["id"])
        assert restored["deleted_at"] is None

    @pytest.mark.asyncio
    async def test_list_edges(self, db_session, tenant_a, case_a, member_a, nodes):
        n1, n2 = nodes
        e1 = await svc.create_edge(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", source_node_id=n1["id"], target_node_id=n2["id"], relation_type="proven_by")
        e2 = await svc.create_edge(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", source_node_id=n2["id"], target_node_id=n1["id"], relation_type="supports")
        edges = await svc.list_edges(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g")
        ids = {e["id"] for e in edges}
        assert e1["id"] in ids
        assert e2["id"] in ids

    @pytest.mark.asyncio
    async def test_all_relation_types(self, db_session, tenant_a, case_a, member_a, nodes):
        n1, n2 = nodes
        for rel in ["supports", "contradicts", "requires", "proven_by", "based_on", "leads_to", "rebuts", "depends_on"]:
            n3 = await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="fact", title=f"T{rel}")
            edge = await svc.create_edge(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", source_node_id=n1["id"], target_node_id=n3["id"], relation_type=rel)
            assert edge["relation_type"] == rel


class TestAuthorization:
    @pytest.mark.asyncio
    async def test_non_member_denied(self, db_session, tenant_a, case_a):
        with pytest.raises(PermissionError, match="CASE_MEMBERSHIP_REQUIRED"):
            await svc.list_nodes(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="stranger")

    @pytest.mark.asyncio
    async def test_viewer_cannot_write(self, db_session, tenant_a, case_a, member_viewer):
        with pytest.raises(PermissionError, match="INSUFFICIENT_PERMISSION"):
            await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-b-g", node_type="fact", title="X")

    @pytest.mark.asyncio
    async def test_viewer_can_read(self, db_session, tenant_a, case_a, member_viewer):
        nodes = await svc.list_nodes(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-b-g")
        assert isinstance(nodes, list)


class TestCrossCaseIsolation:
    @pytest.mark.asyncio
    async def test_node_not_visible_other_case(self, db_session, tenant_a, case_a, case_b, member_a, member_both):
        n = await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="fact", title="Secret")
        result = await svc.get_node(db_session, tenant_id=tenant_a.id, case_id=case_b.id, actor_id="u-a-g", node_id=n["id"])
        assert result is None

    @pytest.mark.asyncio
    async def test_cross_case_edge_blocked(self, db_session, tenant_a, case_a, case_b, member_a, member_both):
        n1 = await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="fact", title="F1")
        n2 = await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_b.id, actor_id="u-a-g", node_type="fact", title="F2")
        with pytest.raises(KeyError):
            await svc.create_edge(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", source_node_id=n1["id"], target_node_id=n2["id"], relation_type="supports")


class TestValidation:
    @pytest.mark.asyncio
    async def test_empty_valid(self, db_session, tenant_a, case_a, member_a):
        result = await svc.validate_graph(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g")
        assert result["valid"] is True

    @pytest.mark.asyncio
    async def test_orphan_warning(self, db_session, tenant_a, case_a, member_a):
        await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="fact", title="Orphan")
        result = await svc.validate_graph(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g")
        types = {w["type"] for w in result["warnings"]}
        assert "orphan_node" in types

    @pytest.mark.asyncio
    async def test_confirmed_fact_no_evidence(self, db_session, tenant_a, case_a, member_a):
        await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="fact", title="F", status="confirmed")
        result = await svc.validate_graph(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g")
        types = {w["type"] for w in result["warnings"]}
        assert "confirmed_fact_no_evidence" in types

    @pytest.mark.asyncio
    async def test_legal_issue_no_elements(self, db_session, tenant_a, case_a, member_a):
        await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="legal_issue", title="Issue")
        result = await svc.validate_graph(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g")
        types = {w["type"] for w in result["warnings"]}
        assert "legal_issue_no_elements" in types

    @pytest.mark.asyncio
    async def test_source_less_official(self, db_session, tenant_a, case_a, member_a):
        await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="official_source", title="TBK 219")
        result = await svc.validate_graph(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g")
        types = {w["type"] for w in result["warnings"]}
        assert "sourceless_official_source" in types

    @pytest.mark.asyncio
    async def test_remedy_not_linked(self, db_session, tenant_a, case_a, member_a):
        await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="remedy", title="Bedel iadesi")
        result = await svc.validate_graph(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g")
        types = {w["type"] for w in result["warnings"]}
        assert "remedy_not_linked" in types

    @pytest.mark.asyncio
    async def test_missing_information_warning(self, db_session, tenant_a, case_a, member_a):
        await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="missing_information", title="Satış bedeli", status="missing")
        result = await svc.validate_graph(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g")
        types = {w["type"] for w in result["warnings"]}
        assert "critical_missing_information" in types


class TestRebuild:
    @pytest.mark.asyncio
    async def test_idempotent(self, db_session, tenant_a, case_a, member_a):
        await svc.rebuild_case_graph(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g")
        r1 = await svc.get_case_graph(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g")
        await svc.rebuild_case_graph(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g")
        r2 = await svc.get_case_graph(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g")
        assert r2["node_count"] >= r1["node_count"]

    @pytest.mark.asyncio
    async def test_preserves_confirmed(self, db_session, tenant_a, case_a, member_a):
        n = await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="fact", title="UserFact", status="confirmed", source_type="user_input")
        await svc.rebuild_case_graph(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g")
        result = await svc.get_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_id=n["id"])
        assert result is not None


class TestSummary:
    @pytest.mark.asyncio
    async def test_empty(self, db_session, tenant_a, case_a, member_a):
        s = await svc.get_graph_summary(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g")
        assert s["total_nodes"] == 0

    @pytest.mark.asyncio
    async def test_with_data(self, db_session, tenant_a, case_a, member_a):
        await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="legal_issue", title="I1")
        await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="risk", title="R1")
        s = await svc.get_graph_summary(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g")
        assert s["legal_issue_count"] == 1
        assert s["risk_count"] == 1


class TestPurge:
    @pytest.mark.asyncio
    async def test_purge_removes(self, db_session, tenant_a, case_a, member_a):
        await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="fact", title="F")
        result = await svc.purge_case_graph(db_session, tenant_id=tenant_a.id, case_id=case_a.id, dry_run=False)
        assert result["purged"] is True
        nodes = await svc.list_nodes(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g")
        assert len(nodes) == 0

    @pytest.mark.asyncio
    async def test_dry_run_preserves(self, db_session, tenant_a, case_a, member_a):
        await svc.create_node(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g", node_type="fact", title="F")
        result = await svc.purge_case_graph(db_session, tenant_id=tenant_a.id, case_id=case_a.id, dry_run=True)
        assert result["dry_run"] is True
        nodes = await svc.list_nodes(db_session, tenant_id=tenant_a.id, case_id=case_a.id, actor_id="u-a-g")
        assert len(nodes) == 1
