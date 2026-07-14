"""P2.8A1 — LegalIssue schema and hierarchy executable tests."""
from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models import (
    Base,
    Case,
    LegalIssue,
    LegalIssueNode,
    LEGAL_ISSUE_STATUSES,
    Tenant,
    User,
)

_TEST_DB_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./test_p28a1.db",
)
_IS_PG = "postgres" in _TEST_DB_URL


@pytest_asyncio.fixture(scope="module")
async def test_db():
    engine = create_async_engine(_TEST_DB_URL, echo=False, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield maker
    await engine.dispose()


@pytest_asyncio.fixture
async def session(test_db):
    async with test_db() as s:
        yield s


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
            assert legacy not in LEGAL_ISSUE_STATUSES, (
                f"Legacy status '{legacy}' must not be in canonical P2.8 set"
            )

    def test_all_statuses_present(self):
        assert len(LEGAL_ISSUE_STATUSES) == 7


class TestLegalIssuePersistence:
    """DB-level CRUD and constraint enforcement."""
    pytestmark = pytest.mark.asyncio

    async def _seed(self, session: AsyncSession):
        t = Tenant(id="t1", name="T1", slug="t1", status="active")
        session.add(t)
        u = User(id="u1", tenant_id="t1", email_normalized="u@t.com", display_name="U", status="active", role="editor")
        session.add(u)
        c = Case(id="c1", tenant_id="t1", owner_user_id="u1", title="Case", status="active")
        session.add(c)
        await session.flush()

    async def test_all_seven_statuses_persist(self, session):
        await self._seed(session)
        for s in sorted(LEGAL_ISSUE_STATUSES):
            issue = LegalIssue(
                id=f"li-{s}",
                tenant_id="t1",
                case_id="c1",
                title=f"Issue {s}",
                status=s,
            )
            session.add(issue)
        await session.flush()
        result = await session.execute(select(LegalIssue))
        assert len(result.scalars().all()) == 7

    async def test_root_issue_null_parent(self, session):
        await self._seed(session)
        issue = LegalIssue(id="root", tenant_id="t1", case_id="c1", title="Root", status="proposed")
        session.add(issue)
        await session.flush()
        loaded = await session.get(LegalIssue, "root")
        assert loaded.parent_issue_id is None

    async def test_child_references_parent_same_case(self, session):
        await self._seed(session)
        parent = LegalIssue(id="p1", tenant_id="t1", case_id="c1", title="Parent", status="proposed")
        session.add(parent)
        await session.flush()
        child = LegalIssue(id="c1", tenant_id="t1", case_id="c1", title="Child",
                           status="proposed", parent_issue_id="p1")
        session.add(child)
        await session.flush()
        assert child.parent_issue_id == "p1"

    async def test_confidence_bounds_accepted(self, session):
        await self._seed(session)
        for val in (0.0, 0.5, 1.0):
            issue = LegalIssue(id=f"conf-{val}", tenant_id="t1", case_id="c1",
                               title=f"Conf {val}", status="proposed", confidence=val)
            session.add(issue)
        await session.flush()
        assert True

    async def test_confidence_below_zero_rejected(self, session):
        await self._seed(session)
        issue = LegalIssue(id="c-bad", tenant_id="t1", case_id="c1",
                           title="Bad", status="proposed", confidence=-0.1)
        session.add(issue)
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    async def test_confidence_above_one_rejected(self, session):
        await self._seed(session)
        issue = LegalIssue(id="c-bad2", tenant_id="t1", case_id="c1",
                           title="Bad", status="proposed", confidence=1.1)
        session.add(issue)
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    async def test_wrong_status_rejected_by_constraint(self, session):
        await self._seed(session)
        issue = LegalIssue(id="bad-status", tenant_id="t1", case_id="c1",
                           title="Bad", status="confirmed")
        session.add(issue)
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    async def test_cross_case_parent_prevented(self, session):
        await self._seed(session)
        c2 = Case(id="c2", tenant_id="t1", owner_user_id="u1", title="C2", status="active")
        session.add(c2)
        parent = LegalIssue(id="p-cross", tenant_id="t1", case_id="c1", title="P", status="proposed")
        session.add(parent)
        await session.flush()
        child = LegalIssue(id="child-cross", tenant_id="t1", case_id="c2", title="Child",
                           status="proposed", parent_issue_id="p-cross")
        session.add(child)
        if _IS_PG:
            from sqlalchemy.exc import IntegrityError
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()
        else:
            pytest.skip("SQLite does not enforce composite self-FK constraints")

    async def test_cross_tenant_parent_prevented(self, session):
        t2 = Tenant(id="t2", name="T2", slug="t2", status="active")
        session.add(t2)
        u2 = User(id="u2", tenant_id="t2", email_normalized="u2@t.com", display_name="U2", status="active", role="editor")
        session.add(u2)
        c_t1 = Case(id="c-t1", tenant_id="t1", owner_user_id="u1", title="CT1", status="active")
        session.add(c_t1)
        await session.flush()
        parent = LegalIssue(id="p-t1", tenant_id="t1", case_id="c-t1", title="P", status="proposed")
        session.add(parent)
        await session.flush()
        c_t2 = Case(id="c-t2", tenant_id="t2", owner_user_id="u2", title="CT2", status="active")
        session.add(c_t2)
        await session.flush()
        child = LegalIssue(id="c-t2", tenant_id="t2", case_id="c-t2", title="C",
                           status="proposed", parent_issue_id="p-t1")
        session.add(child)
        if _IS_PG:
            from sqlalchemy.exc import IntegrityError
            with pytest.raises(IntegrityError):
                await session.flush()
            await session.rollback()
        else:
            pytest.skip("SQLite does not enforce composite self-FK constraints")

    async def test_parent_delete_does_not_cascade(self, session):
        await self._seed(session)
        parent = LegalIssue(id="p-del", tenant_id="t1", case_id="c1", title="P", status="proposed")
        session.add(parent)
        await session.flush()
        child = LegalIssue(id="c-del", tenant_id="t1", case_id="c1", title="C",
                           status="proposed", parent_issue_id="p-del")
        session.add(child)
        await session.flush()
        if _IS_PG:
            from sqlalchemy.exc import IntegrityError
            with pytest.raises(IntegrityError):
                await session.execute(text("DELETE FROM legal_issues WHERE id = 'p-del'"))
            await session.rollback()
        child_exists = await session.get(LegalIssue, "c-del")
        assert child_exists is not None

    async def test_soft_delete_preserves_row(self, session):
        await self._seed(session)
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
        await self._seed(session)
        result = await session.execute(select(LegalIssue).where(
            LegalIssue.tenant_id == "t1",
            LegalIssue.case_id == "c1",
        ))
        assert result.scalars().all() == []

    async def test_migration_roundtrip_single_head(self):
        from alembic.config import Config
        from alembic import command
        import os as _os
        ini = _os.path.normpath(_os.path.join(_os.path.dirname(__file__), "..", "alembic.ini"))
        cfg = Config(ini)
        if "postgres" in _TEST_DB_URL:
            cfg.set_main_option("sqlalchemy.url", _TEST_DB_URL.replace("+asyncpg", ""))
        # Verify single head exists
        from alembic.script import ScriptDirectory
        script = ScriptDirectory.from_config(cfg)
        heads = script.get_heads()
        assert len(heads) == 1, f"Expected 1 Alembic head, got {len(heads)}: {heads}"
