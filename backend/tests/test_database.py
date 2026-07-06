"""P1.4 — Database layer tests."""
from __future__ import annotations

import os
import unittest
from datetime import UTC, datetime
from pathlib import Path

from app.db.models import (
    Base,
    Tenant,
    User,
    Case,
    Document,
    DocumentFact,
    Precedent,
    AIRun,
    WorkflowRun,
    LegalIssueGraph,
    AuditEvent,
    CaseSession,
)
from app.db.session import get_engine, get_sessionmaker, check_db_health


class DatabaseModelTests(unittest.IsolatedAsyncioTestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls._saved_db_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./case_store/emsalist_test.db"

        import app.config
        app.config.get_settings.cache_clear()

        import app.db.session
        app.db.session._engine = None
        app.db.session._sessionmaker = None

        import asyncio
        asyncio.run(cls._setup())

    @classmethod
    async def _setup(cls) -> None:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    @classmethod
    def tearDownClass(cls) -> None:
        import asyncio

        async def _dispose():
            engine = get_engine()
            await engine.dispose()

        asyncio.run(_dispose())

        import app.db.session
        app.db.session._engine = None
        app.db.session._sessionmaker = None

        import app.config
        app.config.get_settings.cache_clear()

        if cls._saved_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = cls._saved_db_url

    async def test_tenant_creation(self) -> None:
        sm = get_sessionmaker()
        async with sm() as s:
            t = Tenant(id="loc", name="Local", slug="local")
            s.add(t)
            await s.commit()
            result = await s.get(Tenant, "loc")
            self.assertIsNotNone(result)

    async def test_duplicate_tenant_slug_fails(self) -> None:
        sm = get_sessionmaker()
        async with sm() as s:
            t1 = Tenant(id="t1", name="Test", slug="test")
            t2 = Tenant(id="t2", name="Test2", slug="test")
            s.add(t1)
            await s.commit()
            s.add(t2)
            with self.assertRaises(Exception):
                await s.commit()
            await s.rollback()

    async def test_user_creation(self) -> None:
        sm = get_sessionmaker()
        async with sm() as s:
            t = Tenant(id="ut", name="U", slug="u")
            s.add(t)
            await s.commit()
            u = User(tenant_id="ut", email_normalized="a@b.com")
            s.add(u)
            await s.commit()
            result = await s.get(User, u.id)
            self.assertIsNotNone(result)

    async def test_case_creation(self) -> None:
        sm = get_sessionmaker()
        async with sm() as s:
            t = Tenant(id="ct", name="C", slug="c")
            u = User(id="cu", tenant_id="ct", email_normalized="c@d.com")
            s.add_all([t, u])
            await s.commit()
            c = Case(id="c1", tenant_id="ct", owner_user_id="cu", title="Test")
            s.add(c)
            await s.commit()
            result = await s.get(Case, "c1")
            self.assertIsNotNone(result)

    async def test_case_session(self) -> None:
        sm = get_sessionmaker()
        async with sm() as s:
            t = Tenant(id="st", name="S", slug="s")
            u = User(id="su", tenant_id="st", email_normalized="e@f.com")
            c = Case(id="sc", tenant_id="st", owner_user_id="su")
            s.add_all([t, u, c])
            await s.commit()
            cs = CaseSession(case_id="sc", state_json={"key": "val"})
            s.add(cs)
            await s.commit()

    async def test_precedent_unique_constraint(self) -> None:
        sm = get_sessionmaker()
        async with sm() as s:
            t = Tenant(id="pt", name="P", slug="p")
            u = User(id="pu", tenant_id="pt", email_normalized="g@h.com")
            c = Case(id="pc", tenant_id="pt", owner_user_id="pu")
            s.add_all([t, u, c])
            await s.commit()
            p1 = Precedent(id="p1", case_id="pc", canonical_key="YARGITAY:3HD:2023/1:2024/2:2024-01-01")
            p2 = Precedent(id="p2", case_id="pc", canonical_key="YARGITAY:3HD:2023/1:2024/2:2024-01-01")
            s.add_all([p1, p2])
            with self.assertRaises(Exception):
                await s.commit()
            await s.rollback()

    async def test_workflow_run_unique(self) -> None:
        sm = get_sessionmaker()
        async with sm() as s:
            t = Tenant(id="wt", name="W", slug="w")
            u = User(id="wu", tenant_id="wt", email_normalized="i@j.com")
            c = Case(id="wc", tenant_id="wt", owner_user_id="wu")
            s.add_all([t, u, c])
            await s.commit()
            w1 = WorkflowRun(id="w1", case_id="wc", request_id="req-1")
            w2 = WorkflowRun(id="w2", case_id="wc", request_id="req-1")
            s.add_all([w1, w2])
            with self.assertRaises(Exception):
                await s.commit()
            await s.rollback()

    async def test_cross_case_isolation(self) -> None:
        sm = get_sessionmaker()
        async with sm() as s:
            t = Tenant(id="xt", name="X", slug="x")
            u = User(id="xu", tenant_id="xt", email_normalized="k@l.com")
            c1 = Case(id="xc1", tenant_id="xt", owner_user_id="xu")
            c2 = Case(id="xc2", tenant_id="xt", owner_user_id="xu")
            s.add_all([t, u, c1, c2])
            await s.commit()
            p1 = Precedent(id="xp1", case_id="xc1", canonical_key="K1")
            p2 = Precedent(id="xp2", case_id="xc2", canonical_key="K2")
            s.add_all([p1, p2])
            await s.commit()

            r1 = await s.get(Precedent, "xp1")
            r2 = await s.get(Precedent, "xp2")
            self.assertNotEqual(r1.case_id, r2.case_id)

    async def test_ai_run_creation(self) -> None:
        sm = get_sessionmaker()
        async with sm() as s:
            t = Tenant(id="at", name="A", slug="a")
            u = User(id="au", tenant_id="at", email_normalized="m@n.com")
            c = Case(id="ac", tenant_id="at", owner_user_id="au")
            s.add_all([t, u, c])
            await s.commit()
            ar = AIRun(case_id="ac", operation="test", status="completed", input_tokens=100)
            s.add(ar)
            await s.commit()

    async def test_db_health(self) -> None:
        result = await check_db_health()
        self.assertIsNotNone(result)

    async def test_migration_roundtrip(self) -> None:
        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        self.assertTrue(True)


class AlembicUrlConversionTests(unittest.TestCase):
    """P1.14 — Test production migration_utils.to_sync_migration_url()."""

    def test_alembic_uses_psycopg_for_sync_migrations(self):
        from app.db.migration_utils import to_sync_migration_url
        pg_url = "postgresql+asyncpg://user:pass@localhost:5432/db"
        converted = to_sync_migration_url(pg_url)
        self.assertIn("+psycopg", converted)
        self.assertNotIn("+asyncpg", converted)
        self.assertEqual(converted, "postgresql+psycopg://user:pass@localhost:5432/db")

    def test_sqlite_strips_async_driver(self):
        from app.db.migration_utils import to_sync_migration_url
        sqlite_url = "sqlite+aiosqlite:///./case_store/emsalist.db"
        converted = to_sync_migration_url(sqlite_url)
        self.assertNotIn("+aiosqlite", converted)
        self.assertEqual(converted, "sqlite:///./case_store/emsalist.db")

    def test_non_async_url_passthrough(self):
        from app.db.migration_utils import to_sync_migration_url
        plain_url = "postgresql+psycopg://user:pass@localhost/db"
        converted = to_sync_migration_url(plain_url)
        self.assertEqual(converted, plain_url)

    def test_empty_url_passthrough(self):
        from app.db.migration_utils import to_sync_migration_url
        self.assertEqual(to_sync_migration_url(""), "")

    def test_percent_encoded_url_preserved(self):
        from app.db.migration_utils import to_sync_migration_url
        pg_url = "postgresql+asyncpg://user:p%40ss@localhost:5432/db%5Ftest"
        converted = to_sync_migration_url(pg_url)
        self.assertIn("p%40ss", converted)
        self.assertIn("db%5Ftest", converted)
        self.assertNotIn("+asyncpg", converted)


class AlembicConfigUrlTests(unittest.TestCase):
    """P1.14 — Alembic ConfigParser compatibility with percent-encoded URLs."""

    def test_config_set_main_option_percent_encoded_password(self):
        from app.db.migration_utils import to_alembic_config_url
        from alembic.config import Config

        url = "postgresql+asyncpg://user:p%40ss%21@localhost:5432/db"
        escaped = to_alembic_config_url(url)
        self.assertNotIn("%", escaped.replace("%%", ""),
                         "All bare % must be escaped to %%")
        self.assertIn("%%", escaped)

        cfg = Config()
        cfg.set_main_option("sqlalchemy.url", escaped)

        read_back = cfg.get_main_option("sqlalchemy.url")
        self.assertIn("+psycopg", read_back)
        self.assertNotIn("+asyncpg", read_back)
        self.assertIn("p%40ss%21", read_back,
                      "ConfigParser must decode %% back to literal %")

    def test_config_url_semantic_preservation(self):
        from app.db.migration_utils import to_alembic_config_url, to_sync_migration_url
        from alembic.config import Config

        url = "postgresql+asyncpg://user:secret@host:5432/db%5Fname"
        escaped = to_alembic_config_url(url)

        cfg = Config()
        cfg.set_main_option("sqlalchemy.url", escaped)
        read_back = cfg.get_main_option("sqlalchemy.url")

        self.assertEqual(read_back, to_sync_migration_url(url),
                         "Round-trip through ConfigParser must preserve URL semantics")

    def test_config_url_no_percent_chars_unchanged(self):
        from app.db.migration_utils import to_alembic_config_url, to_sync_migration_url
        from alembic.config import Config

        url = "postgresql+asyncpg://user:pass@localhost:5432/db"
        escaped = to_alembic_config_url(url)

        cfg = Config()
        cfg.set_main_option("sqlalchemy.url", escaped)
        read_back = cfg.get_main_option("sqlalchemy.url")

        self.assertEqual(read_back, to_sync_migration_url(url))


class FreshDatabaseMigrationTests(unittest.TestCase):
    """P1.14 — Full migration chain produces zero drift on a clean database."""

    def test_fresh_sqlite_migration_chain_zero_drift(self):
        from alembic.config import Config as AlcConfig
        from alembic import command
        from alembic.runtime.migration import MigrationContext
        from alembic.autogenerate import compare_metadata
        from sqlalchemy import create_engine
        import app.db.models  # noqa: ensure all models registered
        import app.config as app_config
        import app.db.session as db_session

        saved_url = os.environ.get("DATABASE_URL")
        db_url = "sqlite+aiosqlite:///./case_store/_p1.14_fresh_migration_test.db"
        os.environ["DATABASE_URL"] = db_url
        app_config.get_settings.cache_clear()
        db_session._engine = None
        db_session._sessionmaker = None

        cleanup_path = Path("case_store") / "_p1.14_fresh_migration_test.db"

        try:
            migrations_dir = str(Path(__file__).resolve().parents[1] / "app" / "db" / "migrations")
            alc_cfg = AlcConfig()
            alc_cfg.set_main_option("script_location", migrations_dir)
            command.upgrade(alc_cfg, "head")

            engine = create_engine("sqlite:///./case_store/_p1.14_fresh_migration_test.db", echo=False)
            with engine.connect() as conn:
                ctx = MigrationContext.configure(conn)
                diffs = compare_metadata(ctx, app.db.models.Base.metadata)
                self.assertEqual(
                    diffs, [],
                    f"Fresh database has unresolved migration operations: {diffs}"
                )
            engine.dispose()
        finally:
            if saved_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = saved_url
            app_config.get_settings.cache_clear()
            db_session._engine = None
            db_session._sessionmaker = None
            if cleanup_path.exists():
                cleanup_path.unlink()


if __name__ == "__main__":
    unittest.main()
