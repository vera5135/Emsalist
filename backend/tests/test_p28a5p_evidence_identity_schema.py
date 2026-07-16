"""P2.8A5P - Evidence composite referential identity PostgreSQL acceptance tests."""
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

from app.db.models import Case, Evidence, Tenant, User


POSTGRES_HOST = os.environ.get("PGHOST", "127.0.0.1")
POSTGRES_PORT = os.environ.get("PGPORT", "5432")
POSTGRES_USER = os.environ.get("PGUSER", "emsalist")
POSTGRES_PASSWORD = os.environ.get("PGPASSWORD", "emsalist_test_pwd")
POSTGRES_DB = "emsalist_p28a5p_evidence_identity_acceptance"

TEST_DB_URL = (
    f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

_ALEMBIC_INI = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
_IN_CI = os.environ.get("CI", "").lower() == "true"

PREVIOUS_HEAD = "b8c9d0e1f2a3"

_PRE_EVIDENCE_COLUMNS = (
    "id", "tenant_id", "case_id", "evidence_type", "title", "description",
    "document_id", "supports_claim_id", "supports_event_id",
    "reliability_status", "admissibility_status", "source_type", "source_id",
    "verification_status", "created_by", "version",
)

_PRE_EVIDENCE_SELECT = (
    f"SELECT {', '.join(_PRE_EVIDENCE_COLUMNS)} FROM evidence WHERE id = 'ev1-pre'"
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
    """Seed deterministic pre-migration data at previous head; return exact row values."""
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    try:
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as s:
            t = Tenant(id="t1-pre", name="T1", slug="t1-pre", status="active")
            s.add(t)
            await s.flush()
            u = User(
                id="u1-pre",
                tenant_id="t1-pre",
                email_normalized="u1@pre.com",
                display_name="U1",
                status="active",
                role="editor",
            )
            s.add(u)
            await s.flush()
            c = Case(
                id="c1-pre",
                tenant_id="t1-pre",
                owner_user_id="u1-pre",
                title="Case 1",
                status="active",
            )
            s.add(c)
            await s.flush()
            ev = Evidence(
                id="ev1-pre",
                tenant_id="t1-pre",
                case_id="c1-pre",
                evidence_type="document",
                title="Employment contract",
                description="Signed employment contract.",
                document_id="doc-001",
                supports_claim_id="cl-001",
                supports_event_id="evt-001",
                reliability_status="reliable",
                admissibility_status="admissible",
                source_type="user_message",
                source_id="msg-001",
                verification_status="suggested",
                created_by="u1-pre",
                version=2,
            )
            s.add(ev)
            await s.commit()

        async with maker() as s:
            row = (await s.execute(text(_PRE_EVIDENCE_SELECT))).mappings().one()
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
    "WHERE t.relname = 'evidence' AND ic.relname = :index_name "
    "ORDER BY array_position(i.indkey, a.attnum)"
)

_CONSTRAINT_COLUMNS_SQL = (
    "SELECT a.attname FROM pg_constraint c "
    "JOIN pg_class t ON t.oid = c.conrelid "
    "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey) "
    "WHERE c.conname = :constraint_name "
    "ORDER BY array_position(c.conkey, a.attnum)"
)


class TestEvidenceModel:
    def test_table_name_is_evidence(self):
        assert Evidence.__tablename__ == "evidence"


class TestEvidenceCatalog:
    pytestmark = pytest.mark.asyncio

    async def test_exact_ordered_columns_unchanged(self, session):
        result = await session.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='evidence' ORDER BY ordinal_position"
        ))
        cols = [r[0] for r in result.fetchall()]
        expected = [
            "id", "tenant_id", "case_id", "evidence_type", "title",
            "description", "document_id", "supports_claim_id", "supports_event_id",
            "reliability_status", "admissibility_status", "source_type",
            "source_id", "verification_status", "created_by", "created_at",
            "updated_at", "deleted_at", "version",
        ]
        assert cols == expected, f"Expected {expected}, got {cols}"

    async def test_primary_key_remains_id_only(self, session):
        result = await session.execute(text(
            "SELECT a.attname FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey) "
            "WHERE t.relname = 'evidence' AND c.contype = 'p' "
            "ORDER BY array_position(c.conkey, a.attnum)"
        ))
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["id"], f"Got {cols}"

    async def test_composite_unique_exists_contype_u(self, session):
        result = await session.execute(text(
            "SELECT contype FROM pg_constraint "
            "WHERE conname = 'uq_evidence_tenant_case_id'"
        ))
        raw = result.scalar()
        assert raw is not None, "uq_evidence_tenant_case_id not found"
        assert _normalize_pg_char(raw) == "u", f"Expected UNIQUE (u), got {raw!r}"

    async def test_composite_unique_exact_ordered_columns(self, session):
        result = await session.execute(
            text(_CONSTRAINT_COLUMNS_SQL),
            {"constraint_name": "uq_evidence_tenant_case_id"},
        )
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["tenant_id", "case_id", "id"], f"Got {cols}"

    async def test_composite_unique_belongs_to_evidence(self, session):
        result = await session.execute(text(
            "SELECT t.relname FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "WHERE c.conname = 'uq_evidence_tenant_case_id'"
        ))
        assert result.scalar() == "evidence"

    async def test_ix_tenant_case_unchanged(self, session):
        result = await session.execute(
            text(_INDEX_COLUMNS_SQL), {"index_name": "ix_evidence_tenant_case"}
        )
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["tenant_id", "case_id"], f"Got {cols}"

    async def test_single_alembic_head(self, session):
        from alembic.script import ScriptDirectory

        cfg = Config(_ALEMBIC_INI)
        cfg.set_main_option("sqlalchemy.url", TEST_DB_URL.replace("+asyncpg", ""))
        heads = ScriptDirectory.from_config(cfg).get_heads()
        assert len(heads) == 1


class TestEvidencePreservation:
    pytestmark = pytest.mark.asyncio

    async def test_premigration_values_recorded(self, test_db):
        _, pre_record = test_db
        assert pre_record["id"] == "ev1-pre"
        assert pre_record["tenant_id"] == "t1-pre"
        assert pre_record["case_id"] == "c1-pre"

    async def test_row_survives_migration_exact_values(self, test_db):
        maker, pre_record = test_db
        async with maker() as fresh:
            result = await fresh.execute(text(_PRE_EVIDENCE_SELECT))
            row = result.mappings().one_or_none()
            assert row is not None, "Pre-migration Evidence row must survive migration"
            post = dict(row)
        for col in _PRE_EVIDENCE_COLUMNS:
            assert post[col] == pre_record[col], (
                f"Column {col!r} rewritten by migration: "
                f"pre={pre_record[col]!r} post={post[col]!r}"
            )


class TestCompositeFkTargetProbe:
    pytestmark = pytest.mark.asyncio

    async def test_probe_composite_fk_enforces_exact_tuple(self, test_db):
        maker, _ = test_db
        async with maker() as s:
            await s.execute(text(
                "CREATE TABLE p28a5p_evidence_fk_probe ("
                "  id VARCHAR(32) PRIMARY KEY,"
                "  tenant_id VARCHAR(32) NOT NULL REFERENCES tenants (id),"
                "  case_id VARCHAR(32) NOT NULL REFERENCES cases (id),"
                "  evidence_id VARCHAR(32) NOT NULL,"
                "  CONSTRAINT fk_p28a5p_probe_evidence_identity"
                "    FOREIGN KEY (tenant_id, case_id, evidence_id)"
                "    REFERENCES evidence (tenant_id, case_id, id)"
                ")"
            ))
            await s.commit()

        try:
            async with maker() as s:
                await s.execute(text(
                    "INSERT INTO p28a5p_evidence_fk_probe "
                    "(id, tenant_id, case_id, evidence_id) "
                    "VALUES ('probe-ok', 't1-pre', 'c1-pre', 'ev1-pre')"
                ))
                await s.commit()
                count = (await s.execute(text(
                    "SELECT COUNT(*) FROM p28a5p_evidence_fk_probe WHERE id = 'probe-ok'"
                ))).scalar()
                assert count == 1

            async with maker() as s:
                s.add(Case(
                    id="c2-pre",
                    tenant_id="t1-pre",
                    owner_user_id="u1-pre",
                    title="Case 2",
                    status="active",
                ))
                await s.commit()
            async with maker() as s:
                with pytest.raises(IntegrityError) as exc_info:
                    await s.execute(text(
                        "INSERT INTO p28a5p_evidence_fk_probe "
                        "(id, tenant_id, case_id, evidence_id) "
                        "VALUES ('probe-cc', 't1-pre', 'c2-pre', 'ev1-pre')"
                    ))
                assert _violated_constraint(exc_info) == "fk_p28a5p_probe_evidence_identity", (
                    f"Expected probe composite FK violation, got: {exc_info.value.orig}"
                )
                await s.rollback()

            async with maker() as s:
                s.add(Tenant(id="t2-pre", name="T2", slug="t2-pre", status="active"))
                await s.commit()
            async with maker() as s:
                with pytest.raises(IntegrityError) as exc_info:
                    await s.execute(text(
                        "INSERT INTO p28a5p_evidence_fk_probe "
                        "(id, tenant_id, case_id, evidence_id) "
                        "VALUES ('probe-ct', 't2-pre', 'c1-pre', 'ev1-pre')"
                    ))
                assert _violated_constraint(exc_info) == "fk_p28a5p_probe_evidence_identity", (
                    f"Expected probe composite FK violation, got: {exc_info.value.orig}"
                )
                await s.rollback()
        finally:
            async with maker() as s:
                await s.execute(text("DROP TABLE IF EXISTS p28a5p_evidence_fk_probe"))
                await s.commit()

    async def test_probe_table_absent_after_cleanup(self, session):
        result = await session.execute(text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name='p28a5p_evidence_fk_probe'"
        ))
        assert result.scalar() is None
