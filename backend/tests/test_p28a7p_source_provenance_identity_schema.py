"""P2.8A7P - Source provenance composite identity PostgreSQL acceptance tests."""
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

from app.db.models import SourceParagraph, SourceRecord, SourceVersion


POSTGRES_HOST = os.environ.get("PGHOST", "127.0.0.1")
POSTGRES_PORT = os.environ.get("PGPORT", "5432")
POSTGRES_USER = os.environ.get("PGUSER", "emsalist")
POSTGRES_PASSWORD = os.environ.get("PGPASSWORD", "emsalist_test_pwd")
POSTGRES_DB = "emsalist_p28a7p_source_provenance_identity_acceptance"

TEST_DB_URL = (
    f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

_ALEMBIC_INI = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
_IN_CI = os.environ.get("CI", "").lower() == "true"

PREVIOUS_HEAD = "f2a3b4c5d6e7"

_PRE_VERSION_COLUMNS = (
    "id", "source_record_id", "version_label", "content_hash",
    "raw_document_hash", "valid_from", "valid_to", "supersedes_version_id",
    "retrieval_method", "parser_version", "normalized_text", "metadata_json",
    "status",
)
_PRE_PARAGRAPH_COLUMNS = (
    "id", "source_version_id", "paragraph_index", "heading_path", "text",
    "text_hash", "page", "article_number", "locator_json", "embedding_status",
    "embedding_model", "embedding_version", "embedding_dimension",
    "embedding_vector_json",
)

_PRE_VERSION_SELECT = (
    f"SELECT {', '.join(_PRE_VERSION_COLUMNS)} FROM source_versions WHERE id = 'sv1-pre'"
)
_PRE_PARAGRAPH_SELECT = (
    f"SELECT {', '.join(_PRE_PARAGRAPH_COLUMNS)} FROM source_paragraphs WHERE id = 'sp1-pre'"
)


def _run_alembic_upgrade(db_url_async: str, revision: str) -> None:
    cfg = Config(_ALEMBIC_INI)
    cfg.set_main_option("sqlalchemy.url", db_url_async.replace("+asyncpg", ""))
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


async def _seed_premigration_and_record() -> dict[str, dict]:
    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    try:
        maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with maker() as s:
            s.add(SourceRecord(
                id="sr1-pre",
                source_type="case_law",
                canonical_key="YARGITAY:PRE:1",
                title="Pre source",
                verification_status="verified_official",
                current_version_id="sv1-pre",
            ))
            await s.flush()
            s.add(SourceVersion(
                id="sv1-pre",
                source_record_id="sr1-pre",
                version_label="v1",
                content_hash="hash-pre-1",
                raw_document_hash="raw-pre-1",
                valid_from="2020-01-01",
                valid_to="",
                supersedes_version_id=None,
                retrieval_method="official",
                parser_version="p2.6",
                normalized_text="Article text.",
                metadata_json={"court": "Yargitay"},
                status="active",
            ))
            await s.flush()
            s.add(SourceParagraph(
                id="sp1-pre",
                source_version_id="sv1-pre",
                paragraph_index=1,
                heading_path="Gerekce",
                text="Governing paragraph.",
                text_hash="para-hash-pre-1",
                page=2,
                article_number="12",
                locator_json={"line": 7},
                embedding_status="pending",
                embedding_model=None,
                embedding_version=None,
                embedding_dimension=None,
                embedding_vector_json=None,
            ))
            await s.commit()

        async with maker() as s:
            version = (await s.execute(text(_PRE_VERSION_SELECT))).mappings().one()
            paragraph = (await s.execute(text(_PRE_PARAGRAPH_SELECT))).mappings().one()
            return {"version": dict(version), "paragraph": dict(paragraph)}
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
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("ascii")
    return str(value)


def _violated_constraint(exc_context) -> str | None:
    err = getattr(exc_context.value, "orig", None)
    seen: set[int] = set()
    while err is not None and id(err) not in seen:
        seen.add(id(err))
        name = getattr(err, "constraint_name", None)
        if name:
            return name
        err = getattr(err, "__cause__", None)
    return None


_CONSTRAINT_COLUMNS_SQL = (
    "SELECT a.attname FROM pg_constraint c "
    "JOIN pg_class t ON t.oid = c.conrelid "
    "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey) "
    "WHERE c.conname = :constraint_name "
    "ORDER BY array_position(c.conkey, a.attnum)"
)


class TestSourceProvenanceModel:
    def test_table_names(self):
        assert SourceVersion.__tablename__ == "source_versions"
        assert SourceParagraph.__tablename__ == "source_paragraphs"


class TestSourceProvenanceCatalog:
    pytestmark = pytest.mark.asyncio

    async def test_composite_uniques_exist_contype_u(self, session):
        for name in ("uq_source_versions_record_id", "uq_source_paragraphs_version_id"):
            raw = (await session.execute(text(
                "SELECT contype FROM pg_constraint WHERE conname = :name"
            ), {"name": name})).scalar()
            assert raw is not None
            assert _normalize_pg_char(raw) == "u"

    async def test_composite_unique_exact_ordered_columns(self, session):
        result = await session.execute(
            text(_CONSTRAINT_COLUMNS_SQL),
            {"constraint_name": "uq_source_versions_record_id"},
        )
        assert [r[0] for r in result.fetchall()] == ["source_record_id", "id"]

        result = await session.execute(
            text(_CONSTRAINT_COLUMNS_SQL),
            {"constraint_name": "uq_source_paragraphs_version_id"},
        )
        assert [r[0] for r in result.fetchall()] == ["source_version_id", "id"]

    async def test_single_alembic_head(self, session):
        from alembic.script import ScriptDirectory

        cfg = Config(_ALEMBIC_INI)
        cfg.set_main_option("sqlalchemy.url", TEST_DB_URL.replace("+asyncpg", ""))
        assert len(ScriptDirectory.from_config(cfg).get_heads()) == 1


class TestSourceProvenancePreservation:
    pytestmark = pytest.mark.asyncio

    async def test_row_survives_migration_exact_values(self, test_db):
        maker, pre_record = test_db
        async with maker() as fresh:
            version = dict((await fresh.execute(text(_PRE_VERSION_SELECT))).mappings().one())
            paragraph = dict((await fresh.execute(text(_PRE_PARAGRAPH_SELECT))).mappings().one())

        for col in _PRE_VERSION_COLUMNS:
            assert version[col] == pre_record["version"][col]
        for col in _PRE_PARAGRAPH_COLUMNS:
            assert paragraph[col] == pre_record["paragraph"][col]


class TestCompositeFkTargetProbe:
    pytestmark = pytest.mark.asyncio

    async def test_probe_composite_fks_enforce_exact_source_chain(self, test_db):
        maker, _ = test_db
        async with maker() as s:
            s.add(SourceRecord(
                id="sr2-probe",
                source_type="case_law",
                canonical_key="YARGITAY:PROBE:2",
                title="Second source",
                current_version_id="sv2-probe",
            ))
            await s.flush()
            s.add(SourceVersion(
                id="sv2-probe",
                source_record_id="sr2-probe",
                version_label="v2",
                content_hash="hash-probe-2",
                normalized_text="Other article.",
            ))
            await s.flush()
            s.add(SourceParagraph(
                id="sp2-probe",
                source_version_id="sv2-probe",
                paragraph_index=1,
                text="Other paragraph.",
            ))
            await s.execute(text(
                "CREATE TABLE p28a7p_source_fk_probe ("
                "  id VARCHAR(32) PRIMARY KEY,"
                "  source_record_id VARCHAR(32) NOT NULL,"
                "  source_version_id VARCHAR(32) NOT NULL,"
                "  source_paragraph_id VARCHAR(32) NOT NULL,"
                "  CONSTRAINT fk_p28a7p_probe_version_identity"
                "    FOREIGN KEY (source_record_id, source_version_id)"
                "    REFERENCES source_versions (source_record_id, id),"
                "  CONSTRAINT fk_p28a7p_probe_paragraph_identity"
                "    FOREIGN KEY (source_version_id, source_paragraph_id)"
                "    REFERENCES source_paragraphs (source_version_id, id)"
                ")"
            ))
            await s.commit()

        try:
            async with maker() as s:
                await s.execute(text(
                    "INSERT INTO p28a7p_source_fk_probe "
                    "(id, source_record_id, source_version_id, source_paragraph_id) "
                    "VALUES ('probe-ok', 'sr1-pre', 'sv1-pre', 'sp1-pre')"
                ))
                await s.commit()

            async with maker() as s:
                with pytest.raises(IntegrityError) as exc_info:
                    await s.execute(text(
                        "INSERT INTO p28a7p_source_fk_probe "
                        "(id, source_record_id, source_version_id, source_paragraph_id) "
                        "VALUES ('probe-version-mismatch', 'sr1-pre', 'sv2-probe', 'sp2-probe')"
                    ))
                assert _violated_constraint(exc_info) == "fk_p28a7p_probe_version_identity"
                await s.rollback()

            async with maker() as s:
                with pytest.raises(IntegrityError) as exc_info:
                    await s.execute(text(
                        "INSERT INTO p28a7p_source_fk_probe "
                        "(id, source_record_id, source_version_id, source_paragraph_id) "
                        "VALUES ('probe-paragraph-mismatch', 'sr1-pre', 'sv1-pre', 'sp2-probe')"
                    ))
                assert _violated_constraint(exc_info) == "fk_p28a7p_probe_paragraph_identity"
                await s.rollback()
        finally:
            async with maker() as s:
                await s.execute(text("DROP TABLE IF EXISTS p28a7p_source_fk_probe"))
                await s.execute(text("DELETE FROM source_paragraphs WHERE id = 'sp2-probe'"))
                await s.execute(text("DELETE FROM source_versions WHERE id = 'sv2-probe'"))
                await s.execute(text("DELETE FROM source_records WHERE id = 'sr2-probe'"))
                await s.commit()

    async def test_probe_table_absent_after_cleanup(self, session):
        result = await session.execute(text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name='p28a7p_source_fk_probe'"
        ))
        assert result.scalar() is None
