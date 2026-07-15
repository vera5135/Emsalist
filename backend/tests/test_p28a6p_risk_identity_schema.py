"""P2.8A6P - Risk composite referential identity PostgreSQL acceptance tests."""
from __future__ import annotations

import os

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models import Case, Risk, Tenant, User


POSTGRES_HOST = os.environ.get("PGHOST", "127.0.0.1")
POSTGRES_PORT = os.environ.get("PGPORT", "5432")
POSTGRES_USER = os.environ.get("PGUSER", "emsalist")
POSTGRES_PASSWORD = os.environ.get("PGPASSWORD", "emsalist_test_pwd")
POSTGRES_DB = "emsalist_p28a6p_risk_identity_acceptance"

TEST_DB_URL = (
    f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

_ALEMBIC_INI = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
_IN_CI = os.environ.get("CI", "").lower() == "true"

PREVIOUS_HEAD = "d0e1f2a3b4c5"

_PRE_RISK_COLUMNS = (
    "id", "tenant_id", "case_id", "risk_type", "severity", "title",
    "rationale", "affected_claim", "supporting_reference", "mitigation",
    "related_missing_information", "status", "source_type", "source_id",
    "created_by", "version",
)

_PRE_RISK_SELECT = (
    f"SELECT {', '.join(_PRE_RISK_COLUMNS)} FROM risks WHERE id = 'rk1-pre'"
)


def _run_alembic_upgrade(db_url_async: str, revision: str) -> None:
    sync_url = db_url_async.replace("+asyncpg", "")
    cfg = Config(_ALEMBIC_INI)
    cfg.set_main_option("sqlalchemy.url", sync_url)
    command.upgrade(cfg, revision)


async def _pg_maintenance_connect():
    import asyncpg as _pg

    return await _pg.connect(
        host=POSTGRES_HOST,
        port=int(POSTGRES_PORT),
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        database="postgres",
    )


async def _pg_drop_db(conn, db_name: str):
    await conn.execute(
        f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname='{db_name}' AND pid <> pg_backend_pid()"
    )
    await conn.execute(f'DROP DATABASE "{db_name}"')


async def _seed_premigration_and_record() -> dict:
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    try:
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as s:
            s.add(Tenant(id="t1-pre", name="T1", slug="t1-pre", status="active"))
            await s.flush()
            s.add(User(
                id="u1-pre", tenant_id="t1-pre", email_normalized="u1@pre.com",
                display_name="U1", status="active", role="editor",
            ))
            await s.flush()
            s.add(Case(
                id="c1-pre", tenant_id="t1-pre", owner_user_id="u1-pre",
                title="Case 1", status="active",
            ))
            await s.flush()
            s.add(Risk(
                id="rk1-pre", tenant_id="t1-pre", case_id="c1-pre",
                risk_type="procedure", severity="high", title="Limitation risk",
                rationale="Deadline may be disputed.",
                affected_claim="severance", supporting_reference="ref-001",
                mitigation="Preserve notice evidence.",
                related_missing_information="mi-001", status="open",
                source_type="system_inference", source_id="sys-001",
                created_by="u1-pre", version=2,
            ))
            await s.commit()

        async with maker() as s:
            row = (await s.execute(text(_PRE_RISK_SELECT))).mappings().one()
            return dict(row)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="module")
async def test_db():
    try:
        sys_conn = await _pg_maintenance_connect()
    except Exception as e:
        if _IN_CI:
            raise RuntimeError(f"PostgreSQL not reachable in CI: {e}") from e
        pytest.skip(f"PostgreSQL not reachable - {e}")

    try:
        existing = await sys_conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname=$1", POSTGRES_DB
        )
        if existing:
            await _pg_drop_db(sys_conn, POSTGRES_DB)
        await sys_conn.execute(f'CREATE DATABASE "{POSTGRES_DB}"')
    finally:
        await sys_conn.close()

    try:
        _run_alembic_upgrade(TEST_DB_URL, PREVIOUS_HEAD)
        pre_record = await _seed_premigration_and_record()
        _run_alembic_upgrade(TEST_DB_URL, "head")
    except Exception:
        sys_conn = await _pg_maintenance_connect()
        try:
            await _pg_drop_db(sys_conn, POSTGRES_DB)
        finally:
            await sys_conn.close()
        raise

    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield maker, pre_record
    await engine.dispose()

    sys_conn = await _pg_maintenance_connect()
    try:
        await _pg_drop_db(sys_conn, POSTGRES_DB)
    finally:
        await sys_conn.close()


@pytest_asyncio.fixture
async def session(test_db):
    maker, _ = test_db
    async with maker() as s:
        yield s
        await s.rollback()


def _normalize_pg_char(value) -> str:
    """Normalize a PostgreSQL internal ``"char"`` transport value to str."""
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("ascii")
    return str(value)


def _violated_constraint(exc_context) -> str | None:
    """Extract the exact violated constraint name from asyncpg diagnostics."""
    err = getattr(exc_context.value, "orig", None)
    seen: set[int] = set()
    while err is not None and id(err) not in seen:
        seen.add(id(err))
        name = getattr(err, "constraint_name", None)
        if name:
            return name
        err = getattr(err, "__cause__", None)
    return None


_INDEX_COLUMNS_SQL = (
    "SELECT a.attname FROM pg_index i "
    "JOIN pg_class t ON t.oid = i.indrelid "
    "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(i.indkey) "
    "JOIN pg_class ic ON ic.oid = i.indexrelid "
    "WHERE t.relname = 'risks' AND ic.relname = :index_name "
    "ORDER BY array_position(i.indkey, a.attnum)"
)

_CONSTRAINT_COLUMNS_SQL = (
    "SELECT a.attname FROM pg_constraint c "
    "JOIN pg_class t ON t.oid = c.conrelid "
    "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey) "
    "WHERE c.conname = :constraint_name "
    "ORDER BY array_position(c.conkey, a.attnum)"
)


class TestRiskModel:
    def test_table_name_is_risks(self):
        assert Risk.__tablename__ == "risks"


class TestRiskCatalog:
    pytestmark = pytest.mark.asyncio

    async def test_exact_ordered_columns_unchanged(self, session):
        result = await session.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='risks' ORDER BY ordinal_position"
        ))
        cols = [r[0] for r in result.fetchall()]
        expected = [
            "id", "tenant_id", "case_id", "risk_type", "severity", "title",
            "rationale", "affected_claim", "supporting_reference", "mitigation",
            "related_missing_information", "status", "source_type", "source_id",
            "created_by", "created_at", "updated_at", "deleted_at", "version",
        ]
        assert cols == expected, f"Expected {expected}, got {cols}"

    async def test_primary_key_remains_id_only(self, session):
        result = await session.execute(text(
            "SELECT a.attname FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey) "
            "WHERE t.relname = 'risks' AND c.contype = 'p' "
            "ORDER BY array_position(c.conkey, a.attnum)"
        ))
        assert [r[0] for r in result.fetchall()] == ["id"]

    async def test_composite_unique_exists_contype_u(self, session):
        result = await session.execute(text(
            "SELECT contype FROM pg_constraint "
            "WHERE conname = 'uq_risks_tenant_case_id'"
        ))
        raw = result.scalar()
        assert raw is not None
        assert _normalize_pg_char(raw) == "u"

    async def test_composite_unique_exact_ordered_columns(self, session):
        result = await session.execute(
            text(_CONSTRAINT_COLUMNS_SQL),
            {"constraint_name": "uq_risks_tenant_case_id"},
        )
        assert [r[0] for r in result.fetchall()] == ["tenant_id", "case_id", "id"]

    async def test_ix_tenant_case_unchanged(self, session):
        result = await session.execute(
            text(_INDEX_COLUMNS_SQL), {"index_name": "ix_risks_tenant_case"}
        )
        assert [r[0] for r in result.fetchall()] == ["tenant_id", "case_id"]

    async def test_single_alembic_head(self, session):
        from alembic.script import ScriptDirectory

        cfg = Config(_ALEMBIC_INI)
        cfg.set_main_option("sqlalchemy.url", TEST_DB_URL.replace("+asyncpg", ""))
        assert len(ScriptDirectory.from_config(cfg).get_heads()) == 1


class TestRiskPreservation:
    pytestmark = pytest.mark.asyncio

    async def test_premigration_values_recorded(self, test_db):
        _, pre_record = test_db
        assert pre_record["id"] == "rk1-pre"
        assert pre_record["tenant_id"] == "t1-pre"
        assert pre_record["case_id"] == "c1-pre"

    async def test_row_survives_migration_exact_values(self, test_db):
        maker, pre_record = test_db
        async with maker() as fresh:
            result = await fresh.execute(text(_PRE_RISK_SELECT))
            post = dict(result.mappings().one())
        for col in _PRE_RISK_COLUMNS:
            assert post[col] == pre_record[col]


class TestCompositeFkTargetProbe:
    pytestmark = pytest.mark.asyncio

    async def test_probe_composite_fk_enforces_exact_tuple(self, test_db):
        maker, _ = test_db
        async with maker() as s:
            await s.execute(text(
                "CREATE TABLE p28a6p_risk_fk_probe ("
                "  id VARCHAR(32) PRIMARY KEY,"
                "  tenant_id VARCHAR(32) NOT NULL REFERENCES tenants (id),"
                "  case_id VARCHAR(32) NOT NULL REFERENCES cases (id),"
                "  risk_id VARCHAR(32) NOT NULL,"
                "  CONSTRAINT fk_p28a6p_probe_risk_identity"
                "    FOREIGN KEY (tenant_id, case_id, risk_id)"
                "    REFERENCES risks (tenant_id, case_id, id)"
                ")"
            ))
            await s.commit()

        try:
            async with maker() as s:
                await s.execute(text(
                    "INSERT INTO p28a6p_risk_fk_probe (id, tenant_id, case_id, risk_id) "
                    "VALUES ('probe-ok', 't1-pre', 'c1-pre', 'rk1-pre')"
                ))
                await s.commit()

            async with maker() as s:
                s.add(Case(id="c2-pre", tenant_id="t1-pre", owner_user_id="u1-pre",
                           title="Case 2", status="active"))
                await s.commit()
            async with maker() as s:
                with pytest.raises(IntegrityError) as exc_info:
                    await s.execute(text(
                        "INSERT INTO p28a6p_risk_fk_probe (id, tenant_id, case_id, risk_id) "
                        "VALUES ('probe-cc', 't1-pre', 'c2-pre', 'rk1-pre')"
                    ))
                assert _violated_constraint(exc_info) == "fk_p28a6p_probe_risk_identity"
                await s.rollback()

            async with maker() as s:
                s.add(Tenant(id="t2-pre", name="T2", slug="t2-pre", status="active"))
                await s.commit()
            async with maker() as s:
                with pytest.raises(IntegrityError) as exc_info:
                    await s.execute(text(
                        "INSERT INTO p28a6p_risk_fk_probe (id, tenant_id, case_id, risk_id) "
                        "VALUES ('probe-ct', 't2-pre', 'c1-pre', 'rk1-pre')"
                    ))
                assert _violated_constraint(exc_info) == "fk_p28a6p_probe_risk_identity"
                await s.rollback()
        finally:
            async with maker() as s:
                await s.execute(text("DROP TABLE IF EXISTS p28a6p_risk_fk_probe"))
                await s.commit()

    async def test_probe_table_absent_after_cleanup(self, session):
        result = await session.execute(text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name='p28a6p_risk_fk_probe'"
        ))
        assert result.scalar() is None
