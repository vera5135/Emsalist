"""P2.8A1 — LegalIssue schema and hierarchy PostgreSQL acceptance tests."""
from __future__ import annotations

import json
import os

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from alembic.config import Config
from alembic import command

from app.db.models import (
    Case,
    LegalIssue,
    LegalIssueEdge,
    LegalIssueNode,
    LEGAL_ISSUE_STATUSES,
    Tenant,
    User,
)

# ── PostgreSQL configuration ──────────────────────────────────────────────────

POSTGRES_HOST = os.environ.get("PGHOST", "127.0.0.1")
POSTGRES_PORT = os.environ.get("PGPORT", "5432")
POSTGRES_USER = os.environ.get("PGUSER", "emsalist")
POSTGRES_PASSWORD = os.environ.get("PGPASSWORD", "emsalist_test_pwd")
POSTGRES_DB = "emsalist_p28a1_acceptance"

TEST_DB_URL = (
    f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

_ALEMBIC_INI = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
_IN_CI = os.environ.get("CI", "").lower() == "true"


def _run_alembic_upgrade(db_url_async: str) -> None:
    sync_url = db_url_async.replace("+asyncpg", "")
    cfg = Config(_ALEMBIC_INI)
    cfg.set_main_option("sqlalchemy.url", sync_url)
    old = __import__("sys").argv
    try:
        command.upgrade(cfg, "head")
    finally:
        __import__("sys").argv = old


async def _pg_maintenance_connect():
    import asyncpg as _pg
    return await _pg.connect(
        host=POSTGRES_HOST, port=int(POSTGRES_PORT),
        user=POSTGRES_USER, password=POSTGRES_PASSWORD,
        database="postgres",
    )


async def _pg_drop_db(conn, db_name: str):
    await conn.execute(
        f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname='{db_name}' AND pid <> pg_backend_pid()"
    )
    await conn.execute(f'DROP DATABASE "{db_name}"')


async def _pg_create_db(conn, db_name: str):
    await conn.execute(f'CREATE DATABASE "{db_name}"')


# ── Database fixture ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="module")
async def test_db():
    import asyncpg as _pg

    try:
        sys_conn = await _pg_maintenance_connect()
    except (ConnectionRefusedError, OSError, Exception) as e:
        if _IN_CI:
            raise RuntimeError(f"PostgreSQL not reachable in CI: {e}") from e
        pytest.skip(f"PostgreSQL not reachable — {e}")
        yield None
        return

    try:
        existing = await sys_conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", POSTGRES_DB)
        if existing:
            await _pg_drop_db(sys_conn, POSTGRES_DB)
        await _pg_create_db(sys_conn, POSTGRES_DB)
    except Exception:
        await sys_conn.close()
        if _IN_CI:
            raise
        pytest.skip("PostgreSQL database create/drop failed")
        yield None
        return
    finally:
        await sys_conn.close()

    _run_alembic_upgrade(TEST_DB_URL)

    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield maker
    await engine.dispose()

    try:
        sys_conn = await _pg_maintenance_connect()
        await _pg_drop_db(sys_conn, POSTGRES_DB)
        await sys_conn.close()
    except Exception:
        if _IN_CI:
            raise
        else:
            pass


@pytest_asyncio.fixture
async def session(test_db):
    async with test_db() as s:
        yield s


async def _seed(session: AsyncSession):
    t = Tenant(id="t1", name="T1", slug="t1", status="active")
    session.add(t)
    u = User(id="u1", tenant_id="t1", email_normalized="u@t.com", display_name="U", status="active", role="editor")
    session.add(u)
    c = Case(id="c1", tenant_id="t1", owner_user_id="u1", title="Case 1", status="active")
    session.add(c)
    c2 = Case(id="c2", tenant_id="t1", owner_user_id="u1", title="Case 2", status="active")
    session.add(c2)
    await session.flush()


# ── Model tests ───────────────────────────────────────────────────────────────

class TestLegalIssueModel:
    def test_table_name_is_legal_issues(self):
        assert LegalIssue.__tablename__ == "legal_issues"

    def test_legacy_node_table_remains_distinct(self):
        assert LegalIssueNode.__tablename__ == "legal_issue_nodes"
        assert LegalIssueNode.__tablename__ != LegalIssue.__tablename__

    def test_legacy_edge_table_remains_distinct(self):
        assert LegalIssueEdge.__tablename__ == "legal_issue_edges"
        assert LegalIssueEdge.__tablename__ != LegalIssue.__tablename__

    def test_canonical_statuses(self):
        assert LEGAL_ISSUE_STATUSES == frozenset({
            "proposed", "accepted", "disputed", "unsupported",
            "satisfied", "failed", "needs_review",
        })

    def test_legacy_status_not_in_canonical(self):
        for legacy in ("confirmed", "missing", "rejected"):
            assert legacy not in LEGAL_ISSUE_STATUSES

    def test_all_canonical_count(self):
        assert len(LEGAL_ISSUE_STATUSES) == 7


# ── PostgreSQL constraint and catalog proofs ──────────────────────────────────

class TestLegalIssueCatalog:
    pytestmark = pytest.mark.asyncio

    async def test_table_has_required_columns(self, session):
        result = await session.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='legal_issues' ORDER BY ordinal_position"
        ))
        cols = [r[0] for r in result.fetchall()]
        required = [
            "id", "tenant_id", "case_id", "parent_issue_id",
            "issue_code", "title", "description", "status",
            "confidence", "created_at", "updated_at", "deleted_at", "version",
        ]
        for req in required:
            assert req in cols, f"Missing required column: {req}"
        assert len(cols) >= len(required)

    async def test_ix_tenant_case_exists_and_ordered(self, session):
        result = await session.execute(text(
            "SELECT column_name FROM information_schema.constraint_column_usage "
            "WHERE table_name='legal_issues' AND constraint_name='ix_legal_issues_tenant_case' "
            "ORDER BY ordinal_position"
        ))
        cols = [r[0] for r in result.fetchall()]
        # Index columns aren't in constraint_column_usage — use pg_index instead
        result = await session.execute(text(
            "SELECT a.attname FROM pg_index i "
            "JOIN pg_class t ON t.oid = i.indrelid "
            "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(i.indkey) "
            "JOIN pg_class ic ON ic.oid = i.indexrelid "
            "WHERE t.relname = 'legal_issues' AND ic.relname = 'ix_legal_issues_tenant_case' "
            "ORDER BY array_position(i.indkey, a.attnum)"
        ))
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["tenant_id", "case_id"], f"Got {cols}"

    async def test_ix_case_parent_exists_and_ordered(self, session):
        result = await session.execute(text(
            "SELECT a.attname FROM pg_index i "
            "JOIN pg_class t ON t.oid = i.indrelid "
            "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(i.indkey) "
            "JOIN pg_class ic ON ic.oid = i.indexrelid "
            "WHERE t.relname = 'legal_issues' AND ic.relname = 'ix_legal_issues_case_parent' "
            "ORDER BY array_position(i.indkey, a.attnum)"
        ))
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["case_id", "parent_issue_id"], f"Got {cols}"

    async def test_unique_constraint_ordered(self, session):
        result = await session.execute(text(
            "SELECT a.attname FROM pg_index i "
            "JOIN pg_class t ON t.oid = i.indrelid "
            "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(i.indkey) "
            "JOIN pg_constraint c ON c.conindid = i.indexrelid "
            "WHERE t.relname = 'legal_issues' AND c.conname = 'uq_legal_issues_tenant_case_id' "
            "ORDER BY array_position(i.indkey, a.attnum)"
        ))
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["tenant_id", "case_id", "id"], f"Got {cols}"

    async def test_fk_local_ordered_columns(self, session):
        result = await session.execute(text(
            "SELECT a.attname FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey) "
            "WHERE t.relname = 'legal_issues' AND c.conname = 'fk_legal_issues_parent_hierarchy' "
            "ORDER BY array_position(c.conkey, a.attnum)"
        ))
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["tenant_id", "case_id", "parent_issue_id"], f"Got {cols}"

    async def test_fk_referenced_ordered_columns(self, session):
        result = await session.execute(text(
            "SELECT a.attname FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.confrelid "
            "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.confkey) "
            "WHERE c.conname = 'fk_legal_issues_parent_hierarchy' "
            "ORDER BY array_position(c.confkey, a.attnum)"
        ))
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["tenant_id", "case_id", "id"], f"Got {cols}"

    async def test_fk_references_unique_constraint(self, session):
        result = await session.execute(text(
            "SELECT confrelid::regclass::text FROM pg_constraint "
            "WHERE conname = 'fk_legal_issues_parent_hierarchy'"
        ))
        assert result.scalar_one() == "legal_issues"

    async def test_fk_delete_action_restrict(self, session):
        result = await session.execute(text(
            "SELECT confdeltype FROM pg_constraint "
            "WHERE conname = 'fk_legal_issues_parent_hierarchy'"
        ))
        deltype = result.scalar_one()
        assert deltype == "r", f"Expected RESTRICT (r), got {deltype}"


# ── PostgreSQL persistence/constraint enforcement tests ────────────────────────

class TestLegalIssuePersistence:
    pytestmark = pytest.mark.asyncio

    async def test_all_seven_statuses_persist(self, session):
        await _seed(session)
        for s in sorted(LEGAL_ISSUE_STATUSES):
            session.add(LegalIssue(id=f"li-{s}", tenant_id="t1", case_id="c1", title=f"Issue {s}", status=s))
        await session.flush()
        result = await session.execute(select(LegalIssue))
        assert len(result.scalars().all()) == 7

    async def test_null_parent_root_allowed(self, session):
        await _seed(session)
        session.add(LegalIssue(id="root", tenant_id="t1", case_id="c1", title="Root", status="proposed"))
        await session.flush()
        loaded = await session.get(LegalIssue, "root")
        assert loaded is not None
        assert loaded.parent_issue_id is None

    async def test_same_case_parent_allowed(self, session):
        await _seed(session)
        p = LegalIssue(id="p1", tenant_id="t1", case_id="c1", title="Parent", status="proposed")
        session.add(p)
        await session.flush()
        c = LegalIssue(id="c1", tenant_id="t1", case_id="c1", title="Child",
                       status="proposed", parent_issue_id="p1")
        session.add(c)
        await session.flush()
        assert c.parent_issue_id == "p1"

    async def test_confidence_bounds_accepted(self, session):
        await _seed(session)
        for val in (0.0, 0.5, 1.0):
            session.add(LegalIssue(id=f"c-{val}", tenant_id="t1", case_id="c1",
                                   title=f"Conf {val}", status="proposed", confidence=val))
        await session.flush()

    async def test_confidence_below_zero_rejected(self, session):
        await _seed(session)
        session.add(LegalIssue(id="c-lo", tenant_id="t1", case_id="c1",
                               title="Lo", status="proposed", confidence=-0.1))
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    async def test_confidence_above_one_rejected(self, session):
        await _seed(session)
        session.add(LegalIssue(id="c-hi", tenant_id="t1", case_id="c1",
                               title="Hi", status="proposed", confidence=1.1))
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    async def test_confirmed_status_rejected_by_check(self, session):
        await _seed(session)
        session.add(LegalIssue(id="bs", tenant_id="t1", case_id="c1",
                               title="Bad", status="confirmed"))
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    async def test_cross_case_parent_rejected(self, session):
        await _seed(session)
        p = LegalIssue(id="p-cc", tenant_id="t1", case_id="c1", title="P-C1", status="proposed")
        session.add(p)
        await session.flush()
        c = LegalIssue(id="ch-cc", tenant_id="t1", case_id="c2", title="C-C2",
                       status="proposed", parent_issue_id="p-cc")
        session.add(c)
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    async def test_cross_tenant_same_case_parent_rejected(self, session):
        """Isolates the tenant component: same case_id, different tenant_id."""
        await _seed(session)
        t2 = Tenant(id="t2", name="T2", slug="t2", status="active")
        session.add(t2)
        u2 = User(id="u2", tenant_id="t2", email_normalized="u2@t.com", display_name="U2", status="active", role="editor")
        session.add(u2)
        c_t1_shared = Case(id="c-shared", tenant_id="t1", owner_user_id="u1", title="CS", status="active")
        session.add(c_t1_shared)
        c_t2_shared = Case(id="c-shared", tenant_id="t2", owner_user_id="u2", title="CS", status="active")
        session.add(c_t2_shared)
        await session.flush()
        # Parent: tenant t1, case c-shared
        p = LegalIssue(id="p-ct", tenant_id="t1", case_id="c-shared", title="P-T1", status="proposed")
        session.add(p)
        await session.flush()
        # Child: tenant t2, SAME case_id c-shared, parent from t1
        c = LegalIssue(id="ch-ct", tenant_id="t2", case_id="c-shared", title="C-T2",
                       status="proposed", parent_issue_id="p-ct")
        session.add(c)
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    async def test_parent_physical_delete_rejected_and_children_survive(self, session):
        """Parent delete RESTRICT proof: durable insert, delete fails, child survives in fresh session."""
        await _seed(session)
        p = LegalIssue(id="p-del", tenant_id="t1", case_id="c1", title="P", status="proposed")
        session.add(p)
        await session.flush()
        c = LegalIssue(id="c-del", tenant_id="t1", case_id="c1", title="C",
                       status="proposed", parent_issue_id="p-del")
        session.add(c)
        await session.commit()

        from sqlalchemy.exc import IntegrityError
        async with session.begin():
            with pytest.raises(IntegrityError):
                await session.execute(text("DELETE FROM legal_issues WHERE id = 'p-del'"))
        await session.rollback()

        maker = async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)
        async with maker() as fresh:
            child = await fresh.get(LegalIssue, "c-del")
            assert child is not None, "Child must survive rejected parent delete"
            parent = await fresh.get(LegalIssue, "p-del")
            assert parent is not None, "Parent must survive rejected delete"

    async def test_soft_delete_preserves_row(self, session):
        await _seed(session)
        from datetime import datetime, timezone
        issue = LegalIssue(id="sd", tenant_id="t1", case_id="c1", title="SD", status="proposed")
        session.add(issue)
        await session.flush()
        issue.deleted_at = datetime.now(timezone.utc)
        await session.flush()
        result = await session.execute(select(LegalIssue).where(LegalIssue.id == "sd"))
        loaded = result.scalar_one_or_none()
        assert loaded is not None
        assert loaded.deleted_at is not None

    async def test_single_alembic_head(self, session):
        from alembic.script import ScriptDirectory
        cfg = Config(_ALEMBIC_INI)
        cfg.set_main_option("sqlalchemy.url", TEST_DB_URL.replace("+asyncpg", ""))
        script = ScriptDirectory.from_config(cfg)
        heads = script.get_heads()
        assert len(heads) == 1
