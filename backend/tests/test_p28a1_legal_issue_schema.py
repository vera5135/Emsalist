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
    import sys as _sys
    old = _sys.argv
    try:
        command.upgrade(cfg, "head")
    finally:
        _sys.argv = old


# ── Database fixture ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="module")
async def test_db():
    """Create isolated P2.8A1 PostgreSQL DB, apply Alembic, return sessionmaker."""
    import asyncpg as _pg

    try:
        sys_conn = await _pg.connect(
            host=POSTGRES_HOST, port=int(POSTGRES_PORT),
            user=POSTGRES_USER, password=POSTGRES_PASSWORD,
            database="postgres",
        )
    except (ConnectionRefusedError, OSError, Exception) as e:
        if _IN_CI:
            raise RuntimeError(f"PostgreSQL not reachable in CI: {e}") from e
        pytest.skip(f"PostgreSQL not reachable — {e}")
        yield None
        return

    try:
        existing = await sys_conn.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", POSTGRES_DB)
        if existing:
            await sys_conn.execute(
                f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname='{POSTGRES_DB}' AND pid <> pg_backend_pid()"
            )
            await sys_conn.execute(f'DROP DATABASE "{POSTGRES_DB}"')
        await sys_conn.execute(f'CREATE DATABASE "{POSTGRES_DB}"')
    finally:
        await sys_conn.close()

    _run_alembic_upgrade(TEST_DB_URL)

    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield maker
    await engine.dispose()

    try:
        sys_conn = await _pg.connect(
            host=POSTGRES_HOST, port=int(POSTGRES_PORT),
            user=POSTGRES_USER, password=POSTGRES_PASSWORD,
            database="postgres",
        )
        await sys_conn.execute(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname='{POSTGRES_DB}' AND pid <> pg_backend_pid()"
        )
        await sys_conn.execute(f'DROP DATABASE "{POSTGRES_DB}"')
        await sys_conn.close()
    except Exception:
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
    """Canonical LegalIssue model and status vocabulary."""

    def test_table_name_is_legal_issues(self):
        assert LegalIssue.__tablename__ == "legal_issues"

    def test_legacy_node_table_remains_distinct(self):
        assert LegalIssueNode.__tablename__ == "legal_issue_nodes"
        assert LegalIssueNode.__tablename__ != LegalIssue.__tablename__

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


# ── PostgreSQL persistence tests ──────────────────────────────────────────────

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
        parent = LegalIssue(id="p1", tenant_id="t1", case_id="c1", title="Parent", status="proposed")
        session.add(parent)
        await session.flush()
        child = LegalIssue(id="c1", tenant_id="t1", case_id="c1", title="Child",
                           status="proposed", parent_issue_id="p1")
        session.add(child)
        await session.flush()
        loaded = await session.get(LegalIssue, "c1")
        assert loaded.parent_issue_id == "p1"

    async def test_confidence_bounds_accepted(self, session):
        await _seed(session)
        for val in (0.0, 0.5, 1.0):
            session.add(LegalIssue(id=f"conf-{val}", tenant_id="t1", case_id="c1",
                                   title=f"Conf {val}", status="proposed", confidence=val))
        await session.flush()

    async def test_confidence_below_zero_rejected(self, session):
        await _seed(session)
        session.add(LegalIssue(id="c-bad", tenant_id="t1", case_id="c1",
                               title="Bad", status="proposed", confidence=-0.1))
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    async def test_confidence_above_one_rejected(self, session):
        await _seed(session)
        session.add(LegalIssue(id="c-bad2", tenant_id="t1", case_id="c1",
                               title="Bad", status="proposed", confidence=1.1))
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    async def test_confirmed_status_rejected_by_check(self, session):
        await _seed(session)
        session.add(LegalIssue(id="bad-status", tenant_id="t1", case_id="c1",
                               title="Bad", status="confirmed"))
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    async def test_cross_case_parent_rejected(self, session):
        await _seed(session)
        parent = LegalIssue(id="p-cc", tenant_id="t1", case_id="c1", title="P-C1", status="proposed")
        session.add(parent)
        await session.flush()
        child = LegalIssue(id="ch-cc", tenant_id="t1", case_id="c2", title="C-C2",
                           status="proposed", parent_issue_id="p-cc")
        session.add(child)
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    async def test_cross_tenant_parent_rejected(self, session):
        t2 = Tenant(id="t2", name="T2", slug="t2", status="active")
        session.add(t2)
        u2 = User(id="u2", tenant_id="t2", email_normalized="u2@t.com", display_name="U2", status="active", role="editor")
        session.add(u2)
        c_t1a = Case(id="c-t1a", tenant_id="t1", owner_user_id="u1", title="CT1", status="active")
        session.add(c_t1a)
        await session.flush()
        parent = LegalIssue(id="p-ct", tenant_id="t1", case_id="c-t1a", title="P-T1", status="proposed")
        session.add(parent)
        await session.flush()
        c_t2 = Case(id="c-t2", tenant_id="t2", owner_user_id="u2", title="CT2", status="active")
        session.add(c_t2)
        await session.flush()
        child = LegalIssue(id="ch-ct", tenant_id="t2", case_id="c-t2", title="C-T2",
                           status="proposed", parent_issue_id="p-ct")
        session.add(child)
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    async def test_parent_physical_delete_with_child_rejected(self, session):
        await _seed(session)
        parent = LegalIssue(id="p-del", tenant_id="t1", case_id="c1", title="P", status="proposed")
        session.add(parent)
        await session.flush()
        child = LegalIssue(id="c-del", tenant_id="t1", case_id="c1", title="C",
                           status="proposed", parent_issue_id="p-del")
        session.add(child)
        await session.flush()
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            await session.execute(text("DELETE FROM legal_issues WHERE id = 'p-del'"))
        await session.rollback()
        child_exists = await session.get(LegalIssue, "c-del")
        assert child_exists is not None

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

    async def test_indexes_exist(self, session):
        await _seed(session)
        await session.execute(select(LegalIssue).where(
            LegalIssue.tenant_id == "t1", LegalIssue.case_id == "c1",
        ))

    async def test_unique_constraint_is_present(self, session):
        result = await session.execute(text(
            "SELECT constraint_name FROM information_schema.table_constraints "
            "WHERE table_name='legal_issues' AND constraint_name='uq_legal_issues_tenant_case_id'"
        ))
        rows = result.fetchall()
        assert len(rows) == 1

    async def test_unique_constraint_columns(self, session):
        result = await session.execute(text(
            "SELECT column_name FROM information_schema.constraint_column_usage "
            "WHERE table_name='legal_issues' AND constraint_name='uq_legal_issues_tenant_case_id' "
            "ORDER BY column_name"
        ))
        cols = [r[0] for r in result.fetchall()]
        assert "case_id" in cols
        assert "id" in cols
        assert "tenant_id" in cols

    async def test_fk_columns_correct(self, session):
        result = await session.execute(text(
            "SELECT column_name FROM information_schema.constraint_column_usage "
            "WHERE table_name='legal_issues' AND constraint_name='fk_legal_issues_parent_hierarchy' "
            "ORDER BY ordinal_position"
        ))
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["tenant_id", "case_id", "parent_issue_id"]

    async def test_fk_references_correct(self, session):
        result = await session.execute(text(
            "SELECT unique_constraint_name FROM information_schema.referential_constraints "
            "WHERE constraint_name='fk_legal_issues_parent_hierarchy'"
        ))
        rows = result.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "uq_legal_issues_tenant_case_id"

    async def test_single_alembic_head(self, session):
        from alembic.script import ScriptDirectory
        cfg = Config(_ALEMBIC_INI)
        cfg.set_main_option("sqlalchemy.url", TEST_DB_URL.replace("+asyncpg", ""))
        script = ScriptDirectory.from_config(cfg)
        heads = script.get_heads()
        assert len(heads) == 1
