"""P2.8A1 — LegalIssue schema and hierarchy PostgreSQL acceptance tests."""
from __future__ import annotations

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
    import sys as _s
    old = _s.argv
    try:
        command.upgrade(cfg, "head")
    finally:
        _s.argv = old


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
        await sys_conn.execute(f'CREATE DATABASE "{POSTGRES_DB}"')
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

    sys_conn = await _pg_maintenance_connect()
    await _pg_drop_db(sys_conn, POSTGRES_DB)
    await sys_conn.close()


@pytest_asyncio.fixture
async def session(test_db):
    async with test_db() as s:
        yield s


async def _seed(session: AsyncSession):
    t = Tenant(id="t1", name="T1", slug="t1", status="active")
    session.add(t)
    await session.flush()
    u = User(id="u1", tenant_id="t1", email_normalized="u@t.com", display_name="U", status="active", role="editor")
    session.add(u)
    await session.flush()
    c = Case(id="c1", tenant_id="t1", owner_user_id="u1", title="Case 1", status="active")
    session.add(c)
    c2 = Case(id="c2", tenant_id="t1", owner_user_id="u1", title="Case 2", status="active")
    session.add(c2)
    await session.flush()


async def _violated_constraint_is(exc_context, expected_name: str) -> bool:
    err = exc_context.value
    if hasattr(err, "orig") and hasattr(err.orig, "constraint_name"):
        return err.orig.constraint_name == expected_name
    return False


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


# ── PostgreSQL catalog proofs ─────────────────────────────────────────────────

class TestLegalIssueCatalog:
    pytestmark = pytest.mark.asyncio

    async def test_exact_ordered_columns(self, session):
        result = await session.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='legal_issues' ORDER BY ordinal_position"
        ))
        cols = [r[0] for r in result.fetchall()]
        expected = [
            "id", "tenant_id", "case_id", "parent_issue_id",
            "issue_code", "title", "description", "status",
            "confidence", "created_at", "updated_at", "deleted_at", "version",
        ]
        assert cols == expected, f"Expected {expected}, got {cols}"

    async def test_ix_tenant_case_ordered(self, session):
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

    async def test_ix_case_parent_ordered(self, session):
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

    async def test_fk_backed_by_unique_constraint(self, session):
        result = await session.execute(text(
            "SELECT rc.unique_constraint_name "
            "FROM information_schema.referential_constraints rc "
            "JOIN information_schema.table_constraints tc "
            "  ON rc.constraint_name = tc.constraint_name "
            "  AND rc.constraint_schema = tc.constraint_schema "
            "WHERE tc.table_name = 'legal_issues' "
            "  AND tc.constraint_name = 'fk_legal_issues_parent_hierarchy'"
        ))
        row = result.fetchone()
        assert row is not None, "FK not found in information_schema"
        assert row[0] == "uq_legal_issues_tenant_case_id", f"Got {row[0]}"

    async def test_fk_delete_action_restrict(self, session):
        result = await session.execute(text(
            "SELECT confdeltype FROM pg_constraint "
            "WHERE conname = 'fk_legal_issues_parent_hierarchy'"
        ))
        raw = result.scalar_one()
        deltype = raw.decode() if isinstance(raw, bytes) else raw
        assert deltype == "r", f"Expected RESTRICT (r), got {raw!r}"


# ── PostgreSQL constraint enforcement tests ───────────────────────────────────

class TestLegalIssuePersistence:
    pytestmark = pytest.mark.asyncio

    async def test_all_seven_statuses_persist(self, session):
        await _seed(session)
        for s in sorted(LEGAL_ISSUE_STATUSES):
            session.add(LegalIssue(id=f"li-{s}", tenant_id="t1", case_id="c1", title=f"{s}", status=s))
        await session.flush()
        result = await session.execute(select(LegalIssue))
        assert len(result.scalars().all()) == 7

    async def test_null_parent_root_allowed(self, session):
        await _seed(session)
        session.add(LegalIssue(id="root", tenant_id="t1", case_id="c1", title="R", status="proposed"))
        await session.flush()
        assert (await session.get(LegalIssue, "root")).parent_issue_id is None

    async def test_same_case_parent_allowed(self, session):
        await _seed(session)
        p = LegalIssue(id="p1", tenant_id="t1", case_id="c1", title="P", status="proposed")
        session.add(p)
        await session.flush()
        c = LegalIssue(id="ch1", tenant_id="t1", case_id="c1", title="C",
                       status="proposed", parent_issue_id="p1")
        session.add(c)
        await session.flush()
        assert c.parent_issue_id == "p1"

    async def test_confidence_bounds_accepted(self, session):
        await _seed(session)
        for val in (0.0, 0.5, 1.0):
            session.add(LegalIssue(id=f"cb-{val}", tenant_id="t1", case_id="c1",
                                   title=f"C{val}", status="proposed", confidence=val))
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
        session.add(LegalIssue(id="bs", tenant_id="t1", case_id="c1", title="X", status="confirmed"))
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    async def test_cross_case_parent_rejected(self, session):
        await _seed(session)
        p = LegalIssue(id="p-cc", tenant_id="t1", case_id="c1", title="P", status="proposed")
        session.add(p)
        await session.flush()
        c = LegalIssue(id="ch-cc", tenant_id="t1", case_id="c2", title="C",
                       status="proposed", parent_issue_id="p-cc")
        session.add(c)
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint_is(exc_info, "fk_legal_issues_parent_hierarchy"), (
            f"Expected hierarchy FK violation, got: {exc_info.value.orig}"
        )
        await session.rollback()

    async def test_cross_tenant_parent_rejected(self, session):
        """Tenant dimension isolated: same case_id (c1), different tenant (t2)."""
        await _seed(session)
        t2 = Tenant(id="t2", name="T2", slug="t2", status="active")
        session.add(t2)
        await session.flush()
        p = LegalIssue(id="p-ct", tenant_id="t1", case_id="c1", title="P", status="proposed")
        session.add(p)
        await session.flush()
        c = LegalIssue(id="ch-ct", tenant_id="t2", case_id="c1", title="C",
                       status="proposed", parent_issue_id="p-ct")
        session.add(c)
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint_is(exc_info, "fk_legal_issues_parent_hierarchy"), (
            f"Expected hierarchy FK violation, got: {exc_info.value.orig}"
        )
        await session.rollback()

    async def test_parent_delete_rejected_children_survive(self, session):
        """RESTRICT: durable insert, separate-session delete rejected, fresh session proves survival."""
        t = Tenant(id="t-del", name="TD", slug="t-del", status="active")
        session.add(t)
        await session.flush()
        u = User(id="u-del", tenant_id="t-del", email_normalized="ud@t.com", display_name="UD", status="active", role="editor")
        session.add(u)
        await session.flush()
        c = Case(id="case-del", tenant_id="t-del", owner_user_id="u-del", title="CD", status="active")
        session.add(c)
        await session.flush()
        p = LegalIssue(id="p-del", tenant_id="t-del", case_id="case-del", title="P", status="proposed")
        session.add(p)
        await session.flush()
        ch = LegalIssue(id="c-del", tenant_id="t-del", case_id="case-del", title="C",
                        status="proposed", parent_issue_id="p-del")
        session.add(ch)
        await session.commit()

        maker = async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)
        async with maker() as s2:
            from sqlalchemy.exc import IntegrityError
            with pytest.raises(IntegrityError) as exc_info:
                await s2.execute(text("DELETE FROM legal_issues WHERE id = 'p-del'"))
            assert _violated_constraint_is(exc_info, "fk_legal_issues_parent_hierarchy"), (
                f"Expected hierarchy FK violation, got: {exc_info.value.orig}"
            )
            await s2.rollback()

        async with maker() as fresh:
            child = await fresh.get(LegalIssue, "c-del")
            assert child is not None, "Child must survive rejected parent delete"
            parent = await fresh.get(LegalIssue, "p-del")
            assert parent is not None, "Parent must survive rejected delete"

        async with maker() as cleanup:
            await cleanup.execute(text("DELETE FROM legal_issues WHERE id = 'c-del'"))
            await cleanup.execute(text("DELETE FROM legal_issues WHERE id = 'p-del'"))
            await cleanup.execute(text("DELETE FROM cases WHERE id = 'case-del'"))
            await cleanup.execute(text("DELETE FROM users WHERE id = 'u-del'"))
            await cleanup.execute(text("DELETE FROM tenants WHERE id = 't-del'"))
            await cleanup.commit()

    async def test_soft_delete_preserves_row(self, session):
        await _seed(session)
        from datetime import datetime, timezone
        issue = LegalIssue(id="sd", tenant_id="t1", case_id="c1", title="SD", status="proposed")
        session.add(issue)
        await session.flush()
        issue.deleted_at = datetime.now(timezone.utc)
        await session.flush()
        loaded = await session.get(LegalIssue, "sd")
        assert loaded is not None and loaded.deleted_at is not None

    async def test_single_alembic_head(self, session):
        from alembic.script import ScriptDirectory
        cfg = Config(_ALEMBIC_INI)
        cfg.set_main_option("sqlalchemy.url", TEST_DB_URL.replace("+asyncpg", ""))
        heads = ScriptDirectory.from_config(cfg).get_heads()
        assert len(heads) == 1
