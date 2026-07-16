"""P2.8A7 - Typed source-to-issue link PostgreSQL acceptance tests."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models import (
    Case,
    LegalIssue,
    LegalIssueSourceLink,
    LEGAL_ISSUE_SOURCE_RELATIONS,
    SourceParagraph,
    SourceRecord,
    SourceVersion,
    Tenant,
    User,
)


POSTGRES_HOST = os.environ.get("PGHOST", "127.0.0.1")
POSTGRES_PORT = os.environ.get("PGPORT", "5432")
POSTGRES_USER = os.environ.get("PGUSER", "emsalist")
POSTGRES_PASSWORD = os.environ.get("PGPASSWORD", "emsalist_test_pwd")
POSTGRES_DB = "emsalist_p28a7_issue_source_acceptance"

TEST_DB_URL = (
    f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

_ALEMBIC_INI = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
_IN_CI = os.environ.get("CI", "").lower() == "true"


def _run_alembic_upgrade(db_url_async: str) -> None:
    cfg = Config(_ALEMBIC_INI)
    cfg.set_main_option("sqlalchemy.url", db_url_async.replace("+asyncpg", ""))
    command.upgrade(cfg, "head")


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
        _run_alembic_upgrade(TEST_DB_URL)
    except Exception:
        sys_conn = await _pg_maintenance_connect()
        try:
            await _pg_drop_db(sys_conn, POSTGRES_DB)
        finally:
            await sys_conn.close()
        raise

    engine = create_async_engine(TEST_DB_URL, echo=False, poolclass=NullPool)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield maker
    await engine.dispose()

    sys_conn = await _pg_maintenance_connect()
    try:
        await _pg_drop_db(sys_conn, POSTGRES_DB)
    finally:
        await sys_conn.close()


@pytest_asyncio.fixture
async def session(test_db):
    async with test_db() as s:
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


async def _seed_core(session: AsyncSession, suffix: str):
    session.add(Tenant(id=f"t1{suffix}", name="T1", slug=f"t1{suffix}", status="active"))
    await session.flush()
    session.add(User(
        id=f"u1{suffix}", tenant_id=f"t1{suffix}",
        email_normalized=f"u{suffix}@t.com", display_name="U",
        status="active", role="editor",
    ))
    await session.flush()
    session.add(Case(
        id=f"c1{suffix}", tenant_id=f"t1{suffix}", owner_user_id=f"u1{suffix}",
        title="Case 1", status="active",
    ))
    await session.flush()
    session.add(Case(
        id=f"c2{suffix}", tenant_id=f"t1{suffix}", owner_user_id=f"u1{suffix}",
        title="Case 2", status="active",
    ))
    await session.flush()
    session.add(LegalIssue(
        id=f"is{suffix}", tenant_id=f"t1{suffix}", case_id=f"c1{suffix}",
        title="Issue", status="proposed",
    ))
    await session.flush()
    session.add(SourceRecord(
        id=f"sr{suffix}",
        source_type="case_law",
        canonical_key=f"YARGITAY:{suffix}:1",
        title="Source",
        verification_status="verified_official",
        current_version_id=f"sv{suffix}",
    ))
    await session.flush()
    session.add(SourceVersion(
        id=f"sv{suffix}",
        source_record_id=f"sr{suffix}",
        version_label="v1",
        content_hash=f"hash{suffix}-1",
        normalized_text="Governing text.",
        status="active",
    ))
    await session.flush()
    session.add(SourceParagraph(
        id=f"sp{suffix}",
        source_version_id=f"sv{suffix}",
        paragraph_index=1,
        heading_path="Gerekce",
        text="Governing paragraph.",
        text_hash=f"para{suffix}-1",
    ))
    await session.flush()
    session.add(SourceRecord(
        id=f"sr2{suffix}",
        source_type="case_law",
        canonical_key=f"YARGITAY:{suffix}:2",
        title="Other Source",
        current_version_id=f"sv2{suffix}",
    ))
    await session.flush()
    session.add(SourceVersion(
        id=f"sv2{suffix}",
        source_record_id=f"sr2{suffix}",
        version_label="v1",
        content_hash=f"hash{suffix}-2",
        normalized_text="Other text.",
    ))
    await session.flush()
    session.add(SourceParagraph(
        id=f"sp2{suffix}",
        source_version_id=f"sv2{suffix}",
        paragraph_index=1,
        text="Other paragraph.",
        text_hash=f"para{suffix}-2",
    ))
    await session.flush()


class TestIssueSourceLinkModel:
    def test_table_name(self):
        assert LegalIssueSourceLink.__tablename__ == "legal_issue_source_links"

    def test_exact_relation_vocabulary(self):
        assert LEGAL_ISSUE_SOURCE_RELATIONS == frozenset({"source_governs_issue"})

    def test_no_generic_polymorphic_columns(self):
        cols = {c.name for c in LegalIssueSourceLink.__table__.columns}
        for forbidden in ("from_type", "from_id", "to_type", "to_id", "target_type", "target_id"):
            assert forbidden not in cols


class TestIssueSourceLinkCatalog:
    pytestmark = pytest.mark.asyncio

    async def test_table_and_columns(self, session):
        result = await session.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='legal_issue_source_links' ORDER BY ordinal_position"
        ))
        assert [r[0] for r in result.fetchall()] == [
            "id", "tenant_id", "case_id", "issue_id",
            "source_record_id", "source_version_id", "source_paragraph_id",
            "relation_type", "created_at", "updated_at", "deleted_at", "version",
        ]

    async def test_constraints_and_indexes(self, session):
        for name, backing in (
            ("fk_legal_issue_source_links_issue", "uq_legal_issues_tenant_case_id"),
            ("fk_legal_issue_source_links_source_version", "uq_source_versions_record_id"),
            ("fk_legal_issue_source_links_source_paragraph", "uq_source_paragraphs_version_id"),
        ):
            row = (await session.execute(text(
                "SELECT contype, confdeltype FROM pg_constraint WHERE conname = :name"
            ), {"name": name})).fetchone()
            assert row is not None
            assert _normalize_pg_char(row[0]) == "f"
            assert _normalize_pg_char(row[1]) == "r"
            got = (await session.execute(text(
                "SELECT rc.unique_constraint_name "
                "FROM information_schema.referential_constraints rc "
                "JOIN information_schema.table_constraints tc "
                "  ON rc.constraint_name = tc.constraint_name "
                "  AND rc.constraint_schema = tc.constraint_schema "
                "WHERE tc.table_name = 'legal_issue_source_links' "
                "  AND tc.constraint_name = :name"
            ), {"name": name})).scalar_one()
            assert got == backing

        check = (await session.execute(text(
            "SELECT contype, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'ck_legal_issue_source_links_relation_type'"
        ))).fetchone()
        assert check is not None
        assert _normalize_pg_char(check[0]) == "c"
        assert "source_governs_issue" in check[1]

        unique = (await session.execute(text(
            "SELECT i.indisunique, pg_get_expr(i.indpred, i.indrelid) "
            "FROM pg_index i JOIN pg_class ic ON ic.oid = i.indexrelid "
            "WHERE ic.relname = 'uq_legal_issue_source_links_active_relation'"
        ))).fetchone()
        assert unique is not None
        assert unique[0] is True
        assert unique[1].strip().strip("()").strip().lower() == "deleted_at is null"

    async def test_single_alembic_head(self, session):
        from alembic.script import ScriptDirectory

        cfg = Config(_ALEMBIC_INI)
        cfg.set_main_option("sqlalchemy.url", TEST_DB_URL.replace("+asyncpg", ""))
        assert len(ScriptDirectory.from_config(cfg).get_heads()) == 1


class TestIssueSourceLinkBehavior:
    pytestmark = pytest.mark.asyncio

    async def test_relation_persists(self, session):
        await _seed_core(session, "-ok")
        session.add(LegalIssueSourceLink(
            id="lk-ok", tenant_id="t1-ok", case_id="c1-ok", issue_id="is-ok",
            source_record_id="sr-ok", source_version_id="sv-ok",
            source_paragraph_id="sp-ok", relation_type="source_governs_issue",
        ))
        await session.flush()
        loaded = await session.get(LegalIssueSourceLink, "lk-ok")
        assert loaded is not None
        assert loaded.relation_type == "source_governs_issue"

    async def test_invalid_relation_rejected(self, session):
        await _seed_core(session, "-iv")
        session.add(LegalIssueSourceLink(
            id="lk-iv", tenant_id="t1-iv", case_id="c1-iv", issue_id="is-iv",
            source_record_id="sr-iv", source_version_id="sv-iv",
            source_paragraph_id="sp-iv", relation_type="source_mentions_issue",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "ck_legal_issue_source_links_relation_type"
        await session.rollback()

    async def test_endpoint_tuple_rejections(self, session):
        cases = [
            ("-mi", "ghost", "sr-mi", "sv-mi", "sp-mi", "fk_legal_issue_source_links_issue"),
            ("-mr", "is-mr", "ghost", "sv-mr", "sp-mr", "fk_legal_issue_source_links_source_record"),
            ("-mv", "is-mv", "sr-mv", "ghost", "sp-mv", "fk_legal_issue_source_links_source_version"),
            ("-mp", "is-mp", "sr-mp", "sv-mp", "ghost", "fk_legal_issue_source_links_source_paragraph"),
        ]
        for suffix, issue_id, record_id, version_id, paragraph_id, constraint in cases:
            await _seed_core(session, suffix)
            session.add(LegalIssueSourceLink(
                id=f"lk{suffix}", tenant_id=f"t1{suffix}", case_id=f"c1{suffix}",
                issue_id=issue_id, source_record_id=record_id,
                source_version_id=version_id, source_paragraph_id=paragraph_id,
                relation_type="source_governs_issue",
            ))
            with pytest.raises(IntegrityError) as exc_info:
                await session.flush()
            assert _violated_constraint(exc_info) == constraint
            await session.rollback()

    async def test_cross_case_tenant_and_source_chain_rejections(self, session):
        cases = [
            ("-cci", "ix-cci", "sr-cci", "sv-cci", "sp-cci", "fk_legal_issue_source_links_issue", "issue_case"),
            ("-cti", "it-cti", "sr-cti", "sv-cti", "sp-cti", "fk_legal_issue_source_links_issue", "issue_tenant"),
            ("-csv", "is-csv", "sr-csv", "sv2-csv", "sp2-csv", "fk_legal_issue_source_links_source_version", "version_record"),
            ("-csp", "is-csp", "sr-csp", "sv-csp", "sp2-csp", "fk_legal_issue_source_links_source_paragraph", "paragraph_version"),
        ]
        for suffix, issue_id, record_id, version_id, paragraph_id, constraint, variant in cases:
            await _seed_core(session, suffix)
            session.add(Tenant(id=f"t2{suffix}", name="T2", slug=f"t2{suffix}", status="active"))
            await session.flush()
            if variant == "issue_case":
                session.add(LegalIssue(
                    id=issue_id, tenant_id=f"t1{suffix}", case_id=f"c2{suffix}",
                    title="Other issue", status="proposed",
                ))
            elif variant == "issue_tenant":
                session.add(LegalIssue(
                    id=issue_id, tenant_id=f"t2{suffix}", case_id=f"c1{suffix}",
                    title="Tenant issue", status="proposed",
                ))
            await session.flush()
            session.add(LegalIssueSourceLink(
                id=f"lk{suffix}", tenant_id=f"t1{suffix}", case_id=f"c1{suffix}",
                issue_id=issue_id, source_record_id=record_id,
                source_version_id=version_id, source_paragraph_id=paragraph_id,
                relation_type="source_governs_issue",
            ))
            with pytest.raises(IntegrityError) as exc_info:
                await session.flush()
            assert _violated_constraint(exc_info) == constraint
            await session.rollback()

    async def test_duplicate_and_soft_delete_recreate(self, session):
        await _seed_core(session, "-du")
        first = LegalIssueSourceLink(
            id="lk-du1", tenant_id="t1-du", case_id="c1-du", issue_id="is-du",
            source_record_id="sr-du", source_version_id="sv-du",
            source_paragraph_id="sp-du", relation_type="source_governs_issue",
        )
        session.add(first)
        await session.flush()
        session.add(LegalIssueSourceLink(
            id="lk-du2", tenant_id="t1-du", case_id="c1-du", issue_id="is-du",
            source_record_id="sr-du", source_version_id="sv-du",
            source_paragraph_id="sp-du", relation_type="source_governs_issue",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "uq_legal_issue_source_links_active_relation"
        await session.rollback()

        await _seed_core(session, "-sd")
        first = LegalIssueSourceLink(
            id="lk-sd1", tenant_id="t1-sd", case_id="c1-sd", issue_id="is-sd",
            source_record_id="sr-sd", source_version_id="sv-sd",
            source_paragraph_id="sp-sd", relation_type="source_governs_issue",
        )
        session.add(first)
        await session.flush()
        first.deleted_at = datetime.now(timezone.utc)
        await session.flush()
        session.add(LegalIssueSourceLink(
            id="lk-sd2", tenant_id="t1-sd", case_id="c1-sd", issue_id="is-sd",
            source_record_id="sr-sd", source_version_id="sv-sd",
            source_paragraph_id="sp-sd", relation_type="source_governs_issue",
        ))
        await session.flush()

    async def test_endpoint_delete_restrict_survival(self, session):
        await _seed_core(session, "-pd")
        session.add(LegalIssueSourceLink(
            id="lk-pd", tenant_id="t1-pd", case_id="c1-pd", issue_id="is-pd",
            source_record_id="sr-pd", source_version_id="sv-pd",
            source_paragraph_id="sp-pd", relation_type="source_governs_issue",
        ))
        await session.commit()

        maker = async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)
        try:
            async with maker() as s2:
                with pytest.raises(IntegrityError) as exc_info:
                    await s2.execute(text("DELETE FROM legal_issues WHERE id = 'is-pd'"))
                assert _violated_constraint(exc_info) == "fk_legal_issue_source_links_issue"
                await s2.rollback()
                with pytest.raises(IntegrityError) as exc_info:
                    await s2.execute(text("DELETE FROM source_paragraphs WHERE id = 'sp-pd'"))
                assert _violated_constraint(exc_info) == "fk_legal_issue_source_links_source_paragraph"
                await s2.rollback()

            async with maker() as fresh:
                assert await fresh.get(LegalIssueSourceLink, "lk-pd") is not None
                assert await fresh.get(LegalIssue, "is-pd") is not None
                assert await fresh.get(SourceParagraph, "sp-pd") is not None
        finally:
            async with maker() as cleanup:
                await cleanup.execute(text("DELETE FROM legal_issue_source_links WHERE tenant_id = 't1-pd'"))
                await cleanup.execute(text("DELETE FROM legal_issues WHERE tenant_id = 't1-pd'"))
                await cleanup.execute(text("DELETE FROM cases WHERE tenant_id = 't1-pd'"))
                await cleanup.execute(text("DELETE FROM users WHERE tenant_id = 't1-pd'"))
                await cleanup.execute(text("DELETE FROM tenants WHERE id = 't1-pd'"))
                await cleanup.execute(text("DELETE FROM source_paragraphs WHERE id IN ('sp-pd', 'sp2-pd')"))
                await cleanup.execute(text("DELETE FROM source_versions WHERE id IN ('sv-pd', 'sv2-pd')"))
                await cleanup.execute(text("DELETE FROM source_records WHERE id IN ('sr-pd', 'sr2-pd')"))
                await cleanup.commit()
