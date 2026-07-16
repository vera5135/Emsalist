"""P2.8A3 — Typed fact-to-issue link (legal_issue_fact_links) PostgreSQL acceptance tests."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from alembic.config import Config
from alembic import command

from app.db.models import (
    Case,
    CaseFact,
    LegalIssue,
    LegalIssueDependency,
    LegalIssueEdge,
    LegalIssueFactLink,
    LEGAL_ISSUE_FACT_RELATIONS,
    Tenant,
    User,
)

# ── PostgreSQL configuration ──────────────────────────────────────────────────

POSTGRES_HOST = os.environ.get("PGHOST", "127.0.0.1")
POSTGRES_PORT = os.environ.get("PGPORT", "5432")
POSTGRES_USER = os.environ.get("PGUSER", "emsalist")
POSTGRES_PASSWORD = os.environ.get("PGPASSWORD", "emsalist_test_pwd")
POSTGRES_DB = "emsalist_p28a3_fact_issue_acceptance"

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
    command.upgrade(cfg, "head")


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
    try:
        sys_conn = await _pg_maintenance_connect()
    except Exception as e:
        if _IN_CI:
            raise RuntimeError(f"PostgreSQL not reachable in CI: {e}") from e
        pytest.skip(f"PostgreSQL not reachable — {e}")

    # Acceptance DB lifecycle has started: from here on, failures are visible.
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

    # Fail-closed final cleanup: any failure here must surface.
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


# ── Helpers ───────────────────────────────────────────────────────────────────

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


async def _seed_core(session: AsyncSession, suffix: str):
    """Seed tenant/user/cases/fact/issue with per-test dedicated IDs (FK-safe order)."""
    t = Tenant(id=f"t1{suffix}", name="T1", slug=f"t1{suffix}", status="active")
    session.add(t)
    await session.flush()
    u = User(id=f"u1{suffix}", tenant_id=f"t1{suffix}", email_normalized=f"u{suffix}@t.com",
             display_name="U", status="active", role="editor")
    session.add(u)
    await session.flush()
    c1 = Case(id=f"c1{suffix}", tenant_id=f"t1{suffix}", owner_user_id=f"u1{suffix}",
              title="Case 1", status="active")
    session.add(c1)
    await session.flush()
    c2 = Case(id=f"c2{suffix}", tenant_id=f"t1{suffix}", owner_user_id=f"u1{suffix}",
              title="Case 2", status="active")
    session.add(c2)
    await session.flush()
    fa = CaseFact(id=f"fa{suffix}", tenant_id=f"t1{suffix}", case_id=f"c1{suffix}",
                  fact_type="employment_start", value="2020-01-15")
    session.add(fa)
    await session.flush()
    ia = LegalIssue(id=f"ia{suffix}", tenant_id=f"t1{suffix}", case_id=f"c1{suffix}",
                    title="Issue A", status="proposed")
    session.add(ia)
    await session.flush()


# ── Model / table identity ────────────────────────────────────────────────────

class TestFactLinkModel:
    def test_fact_link_table_name(self):
        assert LegalIssueFactLink.__tablename__ == "legal_issue_fact_links"

    def test_legal_issue_table_name(self):
        assert LegalIssue.__tablename__ == "legal_issues"

    def test_case_fact_table_name(self):
        assert CaseFact.__tablename__ == "case_facts"

    def test_dependency_table_name(self):
        assert LegalIssueDependency.__tablename__ == "legal_issue_dependencies"

    def test_legacy_edge_table_name(self):
        assert LegalIssueEdge.__tablename__ == "legal_issue_edges"

    def test_fact_link_distinct_from_all(self):
        others = {
            LegalIssue.__tablename__,
            CaseFact.__tablename__,
            LegalIssueDependency.__tablename__,
            LegalIssueEdge.__tablename__,
        }
        assert LegalIssueFactLink.__tablename__ not in others

    def test_exact_relation_vocabulary(self):
        assert LEGAL_ISSUE_FACT_RELATIONS == frozenset({
            "fact_supports_issue", "fact_contradicts_issue",
        })

    def test_no_generic_polymorphic_columns(self):
        cols = {c.name for c in LegalIssueFactLink.__table__.columns}
        for forbidden in ("from_type", "from_id", "to_type", "to_id",
                          "confidence", "rationale", "source_type", "source_id",
                          "metadata_json", "status"):
            assert forbidden not in cols


# ── Migrated PostgreSQL catalog proofs ────────────────────────────────────────

_INDEX_COLUMNS_SQL = (
    "SELECT a.attname FROM pg_index i "
    "JOIN pg_class t ON t.oid = i.indrelid "
    "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(i.indkey) "
    "JOIN pg_class ic ON ic.oid = i.indexrelid "
    "WHERE t.relname = 'legal_issue_fact_links' AND ic.relname = :index_name "
    "ORDER BY array_position(i.indkey, a.attnum)"
)

_FK_LOCAL_COLUMNS_SQL = (
    "SELECT a.attname FROM pg_constraint c "
    "JOIN pg_class t ON t.oid = c.conrelid "
    "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey) "
    "WHERE t.relname = 'legal_issue_fact_links' AND c.conname = :fk_name "
    "ORDER BY array_position(c.conkey, a.attnum)"
)

_FK_REFERENCED_COLUMNS_SQL = (
    "SELECT a.attname FROM pg_constraint c "
    "JOIN pg_class t ON t.oid = c.confrelid "
    "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.confkey) "
    "WHERE c.conname = :fk_name "
    "ORDER BY array_position(c.confkey, a.attnum)"
)

_FK_UNIQUE_BACKING_SQL = (
    "SELECT rc.unique_constraint_name "
    "FROM information_schema.referential_constraints rc "
    "JOIN information_schema.table_constraints tc "
    "  ON rc.constraint_name = tc.constraint_name "
    "  AND rc.constraint_schema = tc.constraint_schema "
    "WHERE tc.table_name = 'legal_issue_fact_links' "
    "  AND tc.constraint_name = :fk_name"
)


class TestFactLinkCatalog:
    pytestmark = pytest.mark.asyncio

    async def test_table_exists(self, session):
        result = await session.execute(text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name='legal_issue_fact_links'"
        ))
        assert result.scalar() == 1

    async def test_exact_ordered_columns(self, session):
        result = await session.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='legal_issue_fact_links' ORDER BY ordinal_position"
        ))
        cols = [r[0] for r in result.fetchall()]
        expected = [
            "id", "tenant_id", "case_id", "issue_id", "fact_id",
            "relation_type", "created_at", "updated_at", "deleted_at", "version",
        ]
        assert cols == expected, f"Expected {expected}, got {cols}"

    async def test_primary_key_remains_id_only(self, session):
        result = await session.execute(text(
            "SELECT a.attname FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey) "
            "WHERE t.relname = 'legal_issue_fact_links' AND c.contype = 'p' "
            "ORDER BY array_position(c.conkey, a.attnum)"
        ))
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["id"], f"Got {cols}"

    async def test_issue_fk_exists_contype_f(self, session):
        result = await session.execute(text(
            "SELECT contype FROM pg_constraint "
            "WHERE conname = 'fk_legal_issue_fact_links_issue'"
        ))
        raw = result.scalar()
        assert raw is not None, "fk_legal_issue_fact_links_issue not found"
        assert _normalize_pg_char(raw) == "f", f"Expected FOREIGN KEY (f), got {raw!r}"

    async def test_issue_fk_local_ordered_columns(self, session):
        result = await session.execute(
            text(_FK_LOCAL_COLUMNS_SQL), {"fk_name": "fk_legal_issue_fact_links_issue"}
        )
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["tenant_id", "case_id", "issue_id"], f"Got {cols}"

    async def test_issue_fk_referenced_ordered_columns(self, session):
        result = await session.execute(
            text(_FK_REFERENCED_COLUMNS_SQL), {"fk_name": "fk_legal_issue_fact_links_issue"}
        )
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["tenant_id", "case_id", "id"], f"Got {cols}"

    async def test_issue_fk_references_legal_issues(self, session):
        result = await session.execute(text(
            "SELECT rt.relname FROM pg_constraint c "
            "JOIN pg_class rt ON rt.oid = c.confrelid "
            "WHERE c.conname = 'fk_legal_issue_fact_links_issue'"
        ))
        assert result.scalar() == "legal_issues"

    async def test_issue_fk_backed_by_issue_unique_constraint(self, session):
        result = await session.execute(
            text(_FK_UNIQUE_BACKING_SQL), {"fk_name": "fk_legal_issue_fact_links_issue"}
        )
        row = result.fetchone()
        assert row is not None, "Issue FK not found in information_schema"
        assert row[0] == "uq_legal_issues_tenant_case_id", f"Got {row[0]}"

    async def test_issue_fk_delete_restrict(self, session):
        result = await session.execute(text(
            "SELECT confdeltype FROM pg_constraint "
            "WHERE conname = 'fk_legal_issue_fact_links_issue'"
        ))
        raw = result.scalar_one()
        assert _normalize_pg_char(raw) == "r", f"Expected RESTRICT (r), got {raw!r}"

    async def test_fact_fk_exists_contype_f(self, session):
        result = await session.execute(text(
            "SELECT contype FROM pg_constraint "
            "WHERE conname = 'fk_legal_issue_fact_links_fact'"
        ))
        raw = result.scalar()
        assert raw is not None, "fk_legal_issue_fact_links_fact not found"
        assert _normalize_pg_char(raw) == "f", f"Expected FOREIGN KEY (f), got {raw!r}"

    async def test_fact_fk_local_ordered_columns(self, session):
        result = await session.execute(
            text(_FK_LOCAL_COLUMNS_SQL), {"fk_name": "fk_legal_issue_fact_links_fact"}
        )
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["tenant_id", "case_id", "fact_id"], f"Got {cols}"

    async def test_fact_fk_referenced_ordered_columns(self, session):
        result = await session.execute(
            text(_FK_REFERENCED_COLUMNS_SQL), {"fk_name": "fk_legal_issue_fact_links_fact"}
        )
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["tenant_id", "case_id", "id"], f"Got {cols}"

    async def test_fact_fk_references_case_facts(self, session):
        result = await session.execute(text(
            "SELECT rt.relname FROM pg_constraint c "
            "JOIN pg_class rt ON rt.oid = c.confrelid "
            "WHERE c.conname = 'fk_legal_issue_fact_links_fact'"
        ))
        assert result.scalar() == "case_facts"

    async def test_fact_fk_backed_by_fact_unique_constraint(self, session):
        result = await session.execute(
            text(_FK_UNIQUE_BACKING_SQL), {"fk_name": "fk_legal_issue_fact_links_fact"}
        )
        row = result.fetchone()
        assert row is not None, "Fact FK not found in information_schema"
        assert row[0] == "uq_case_facts_tenant_case_id", f"Got {row[0]}"

    async def test_fact_fk_delete_restrict(self, session):
        result = await session.execute(text(
            "SELECT confdeltype FROM pg_constraint "
            "WHERE conname = 'fk_legal_issue_fact_links_fact'"
        ))
        raw = result.scalar_one()
        assert _normalize_pg_char(raw) == "r", f"Expected RESTRICT (r), got {raw!r}"

    async def test_relation_check_exists_contype_c(self, session):
        result = await session.execute(text(
            "SELECT contype, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'ck_legal_issue_fact_links_relation_type'"
        ))
        row = result.fetchone()
        assert row is not None, "ck_legal_issue_fact_links_relation_type not found"
        assert _normalize_pg_char(row[0]) == "c", f"Expected CHECK (c), got {row[0]!r}"
        assert "fact_supports_issue" in row[1]
        assert "fact_contradicts_issue" in row[1]

    async def test_ix_tenant_case_ordered(self, session):
        result = await session.execute(
            text(_INDEX_COLUMNS_SQL),
            {"index_name": "ix_legal_issue_fact_links_tenant_case"},
        )
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["tenant_id", "case_id"], f"Got {cols}"

    async def test_ix_issue_ordered(self, session):
        result = await session.execute(
            text(_INDEX_COLUMNS_SQL),
            {"index_name": "ix_legal_issue_fact_links_issue"},
        )
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["case_id", "issue_id"], f"Got {cols}"

    async def test_ix_fact_ordered(self, session):
        result = await session.execute(
            text(_INDEX_COLUMNS_SQL),
            {"index_name": "ix_legal_issue_fact_links_fact"},
        )
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["case_id", "fact_id"], f"Got {cols}"

    async def test_active_relation_unique_index_exists(self, session):
        result = await session.execute(text(
            "SELECT i.indisunique FROM pg_index i "
            "JOIN pg_class ic ON ic.oid = i.indexrelid "
            "WHERE ic.relname = 'uq_legal_issue_fact_links_active_relation'"
        ))
        assert result.scalar() is True

    async def test_active_relation_ordered_columns(self, session):
        result = await session.execute(
            text(_INDEX_COLUMNS_SQL),
            {"index_name": "uq_legal_issue_fact_links_active_relation"},
        )
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["tenant_id", "case_id", "issue_id", "fact_id", "relation_type"], f"Got {cols}"

    async def test_active_relation_partial_predicate(self, session):
        result = await session.execute(text(
            "SELECT pg_get_expr(i.indpred, i.indrelid) FROM pg_index i "
            "JOIN pg_class ic ON ic.oid = i.indexrelid "
            "WHERE ic.relname = 'uq_legal_issue_fact_links_active_relation'"
        ))
        predicate = result.scalar()
        assert predicate is not None, "Index is not partial (no predicate)"
        normalized = predicate.strip().strip("()").strip().lower()
        assert normalized == "deleted_at is null", f"Got predicate {predicate!r}"

    async def test_single_alembic_head(self, session):
        from alembic.script import ScriptDirectory
        cfg = Config(_ALEMBIC_INI)
        cfg.set_main_option("sqlalchemy.url", TEST_DB_URL.replace("+asyncpg", ""))
        heads = ScriptDirectory.from_config(cfg).get_heads()
        assert len(heads) == 1


# ── PostgreSQL behavior proofs ────────────────────────────────────────────────

class TestFactLinkBehavior:
    pytestmark = pytest.mark.asyncio

    async def test_support_relation_persists(self, session):
        await _seed_core(session, "-sp")
        session.add(LegalIssueFactLink(
            id="lk-sp", tenant_id="t1-sp", case_id="c1-sp",
            issue_id="ia-sp", fact_id="fa-sp",
            relation_type="fact_supports_issue",
        ))
        await session.flush()
        loaded = await session.get(LegalIssueFactLink, "lk-sp")
        assert loaded is not None
        assert loaded.relation_type == "fact_supports_issue"
        assert loaded.version == 1
        assert loaded.deleted_at is None

    async def test_contradiction_relation_persists(self, session):
        await _seed_core(session, "-cn")
        session.add(LegalIssueFactLink(
            id="lk-cn", tenant_id="t1-cn", case_id="c1-cn",
            issue_id="ia-cn", fact_id="fa-cn",
            relation_type="fact_contradicts_issue",
        ))
        await session.flush()
        loaded = await session.get(LegalIssueFactLink, "lk-cn")
        assert loaded is not None
        assert loaded.relation_type == "fact_contradicts_issue"

    async def test_invalid_relation_rejected_by_check(self, session):
        await _seed_core(session, "-iv")
        session.add(LegalIssueFactLink(
            id="lk-iv", tenant_id="t1-iv", case_id="c1-iv",
            issue_id="ia-iv", fact_id="fa-iv",
            relation_type="related_to",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "ck_legal_issue_fact_links_relation_type", (
            f"Expected relation-type CHECK violation, got: {exc_info.value.orig}"
        )
        await session.rollback()

    async def test_missing_issue_endpoint_rejected(self, session):
        await _seed_core(session, "-mi")
        session.add(LegalIssueFactLink(
            id="lk-mi", tenant_id="t1-mi", case_id="c1-mi",
            issue_id="ghost-missing", fact_id="fa-mi",
            relation_type="fact_supports_issue",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "fk_legal_issue_fact_links_issue", (
            f"Expected issue FK violation, got: {exc_info.value.orig}"
        )
        await session.rollback()

    async def test_missing_fact_endpoint_rejected(self, session):
        await _seed_core(session, "-mf")
        session.add(LegalIssueFactLink(
            id="lk-mf", tenant_id="t1-mf", case_id="c1-mf",
            issue_id="ia-mf", fact_id="ghost-missing",
            relation_type="fact_supports_issue",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "fk_legal_issue_fact_links_fact", (
            f"Expected fact FK violation, got: {exc_info.value.orig}"
        )
        await session.rollback()

    async def test_cross_case_issue_endpoint_rejected(self, session):
        await _seed_core(session, "-cci")
        other_issue = LegalIssue(id="ix-cci", tenant_id="t1-cci", case_id="c2-cci",
                                 title="Other case issue", status="proposed")
        session.add(other_issue)
        await session.flush()
        session.add(LegalIssueFactLink(
            id="lk-cci", tenant_id="t1-cci", case_id="c1-cci",
            issue_id="ix-cci", fact_id="fa-cci",
            relation_type="fact_supports_issue",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "fk_legal_issue_fact_links_issue", (
            f"Expected issue FK violation, got: {exc_info.value.orig}"
        )
        await session.rollback()

    async def test_cross_case_fact_endpoint_rejected(self, session):
        await _seed_core(session, "-ccf")
        other_fact = CaseFact(id="fx-ccf", tenant_id="t1-ccf", case_id="c2-ccf",
                              fact_type="salary", value="1000")
        session.add(other_fact)
        await session.flush()
        session.add(LegalIssueFactLink(
            id="lk-ccf", tenant_id="t1-ccf", case_id="c1-ccf",
            issue_id="ia-ccf", fact_id="fx-ccf",
            relation_type="fact_supports_issue",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "fk_legal_issue_fact_links_fact", (
            f"Expected fact FK violation, got: {exc_info.value.orig}"
        )
        await session.rollback()

    async def test_cross_tenant_issue_endpoint_rejected(self, session):
        """Tenant dimension isolated: link under (t1, c1); issue exists only under (t2, c1)."""
        await _seed_core(session, "-cti")
        t2 = Tenant(id="t2-cti", name="T2", slug="t2-cti", status="active")
        session.add(t2)
        await session.flush()
        foreign_issue = LegalIssue(id="ix-cti", tenant_id="t2-cti", case_id="c1-cti",
                                   title="Issue under t2", status="proposed")
        session.add(foreign_issue)
        await session.flush()
        session.add(LegalIssueFactLink(
            id="lk-cti", tenant_id="t1-cti", case_id="c1-cti",
            issue_id="ix-cti", fact_id="fa-cti",
            relation_type="fact_supports_issue",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "fk_legal_issue_fact_links_issue", (
            f"Expected issue FK violation, got: {exc_info.value.orig}"
        )
        await session.rollback()

    async def test_cross_tenant_fact_endpoint_rejected(self, session):
        """Tenant dimension isolated: link under (t1, c1); fact exists only under (t2, c1)."""
        await _seed_core(session, "-ctf")
        t2 = Tenant(id="t2-ctf", name="T2", slug="t2-ctf", status="active")
        session.add(t2)
        await session.flush()
        foreign_fact = CaseFact(id="fx-ctf", tenant_id="t2-ctf", case_id="c1-ctf",
                                fact_type="salary", value="1000")
        session.add(foreign_fact)
        await session.flush()
        session.add(LegalIssueFactLink(
            id="lk-ctf", tenant_id="t1-ctf", case_id="c1-ctf",
            issue_id="ia-ctf", fact_id="fx-ctf",
            relation_type="fact_supports_issue",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "fk_legal_issue_fact_links_fact", (
            f"Expected fact FK violation, got: {exc_info.value.orig}"
        )
        await session.rollback()

    async def test_duplicate_active_support_rejected(self, session):
        await _seed_core(session, "-ds")
        session.add(LegalIssueFactLink(
            id="lk-ds1", tenant_id="t1-ds", case_id="c1-ds",
            issue_id="ia-ds", fact_id="fa-ds",
            relation_type="fact_supports_issue",
        ))
        await session.flush()
        session.add(LegalIssueFactLink(
            id="lk-ds2", tenant_id="t1-ds", case_id="c1-ds",
            issue_id="ia-ds", fact_id="fa-ds",
            relation_type="fact_supports_issue",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "uq_legal_issue_fact_links_active_relation", (
            f"Expected active-relation unique violation, got: {exc_info.value.orig}"
        )
        await session.rollback()

    async def test_duplicate_active_contradiction_rejected(self, session):
        await _seed_core(session, "-dc")
        session.add(LegalIssueFactLink(
            id="lk-dc1", tenant_id="t1-dc", case_id="c1-dc",
            issue_id="ia-dc", fact_id="fa-dc",
            relation_type="fact_contradicts_issue",
        ))
        await session.flush()
        session.add(LegalIssueFactLink(
            id="lk-dc2", tenant_id="t1-dc", case_id="c1-dc",
            issue_id="ia-dc", fact_id="fa-dc",
            relation_type="fact_contradicts_issue",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "uq_legal_issue_fact_links_active_relation", (
            f"Expected active-relation unique violation, got: {exc_info.value.orig}"
        )
        await session.rollback()

    async def test_support_and_contradiction_coexist(self, session):
        await _seed_core(session, "-cx")
        session.add(LegalIssueFactLink(
            id="lk-cx1", tenant_id="t1-cx", case_id="c1-cx",
            issue_id="ia-cx", fact_id="fa-cx",
            relation_type="fact_supports_issue",
        ))
        session.add(LegalIssueFactLink(
            id="lk-cx2", tenant_id="t1-cx", case_id="c1-cx",
            issue_id="ia-cx", fact_id="fa-cx",
            relation_type="fact_contradicts_issue",
        ))
        await session.flush()
        result = await session.execute(
            select(LegalIssueFactLink).where(LegalIssueFactLink.case_id == "c1-cx")
        )
        rows = result.scalars().all()
        assert len(rows) == 2
        relations = {r.relation_type for r in rows}
        assert relations == {"fact_supports_issue", "fact_contradicts_issue"}

    async def test_soft_delete_then_recreate_active_relation(self, session):
        await _seed_core(session, "-sd")
        first = LegalIssueFactLink(
            id="lk-sd1", tenant_id="t1-sd", case_id="c1-sd",
            issue_id="ia-sd", fact_id="fa-sd",
            relation_type="fact_supports_issue",
        )
        session.add(first)
        await session.flush()
        first.deleted_at = datetime.now(timezone.utc)
        await session.flush()
        second = LegalIssueFactLink(
            id="lk-sd2", tenant_id="t1-sd", case_id="c1-sd",
            issue_id="ia-sd", fact_id="fa-sd",
            relation_type="fact_supports_issue",
        )
        session.add(second)
        await session.flush()
        loaded = await session.get(LegalIssueFactLink, "lk-sd2")
        assert loaded is not None
        assert loaded.deleted_at is None
        soft_deleted = await session.get(LegalIssueFactLink, "lk-sd1")
        assert soft_deleted is not None
        assert soft_deleted.deleted_at is not None

    async def test_issue_physical_delete_rejected_rows_survive(self, session):
        """RESTRICT on issue endpoint: durable rows, rejected delete, fresh-session survival."""
        await _seed_core(session, "-pdi")
        session.add(LegalIssueFactLink(
            id="lk-pdi", tenant_id="t1-pdi", case_id="c1-pdi",
            issue_id="ia-pdi", fact_id="fa-pdi",
            relation_type="fact_supports_issue",
        ))
        await session.commit()

        maker = async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)
        try:
            async with maker() as s2:
                with pytest.raises(IntegrityError) as exc_info:
                    await s2.execute(text("DELETE FROM legal_issues WHERE id = 'ia-pdi'"))
                assert _violated_constraint(exc_info) == "fk_legal_issue_fact_links_issue", (
                    f"Expected issue FK violation, got: {exc_info.value.orig}"
                )
                await s2.rollback()

            async with maker() as fresh:
                link = await fresh.get(LegalIssueFactLink, "lk-pdi")
                assert link is not None, "Fact link must survive rejected endpoint delete"
                issue = await fresh.get(LegalIssue, "ia-pdi")
                assert issue is not None, "LegalIssue must survive rejected delete"
                fact = await fresh.get(CaseFact, "fa-pdi")
                assert fact is not None, "CaseFact must survive rejected delete"
        finally:
            async with maker() as cleanup:
                await cleanup.execute(text("DELETE FROM legal_issue_fact_links WHERE tenant_id = 't1-pdi'"))
                await cleanup.execute(text("DELETE FROM legal_issues WHERE tenant_id = 't1-pdi'"))
                await cleanup.execute(text("DELETE FROM case_facts WHERE tenant_id = 't1-pdi'"))
                await cleanup.execute(text("DELETE FROM cases WHERE tenant_id = 't1-pdi'"))
                await cleanup.execute(text("DELETE FROM users WHERE tenant_id = 't1-pdi'"))
                await cleanup.execute(text("DELETE FROM tenants WHERE id = 't1-pdi'"))
                await cleanup.commit()

    async def test_fact_physical_delete_rejected_rows_survive(self, session):
        """RESTRICT on fact endpoint: durable rows, rejected delete, fresh-session survival."""
        await _seed_core(session, "-pdf")
        session.add(LegalIssueFactLink(
            id="lk-pdf", tenant_id="t1-pdf", case_id="c1-pdf",
            issue_id="ia-pdf", fact_id="fa-pdf",
            relation_type="fact_contradicts_issue",
        ))
        await session.commit()

        maker = async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)
        try:
            async with maker() as s2:
                with pytest.raises(IntegrityError) as exc_info:
                    await s2.execute(text("DELETE FROM case_facts WHERE id = 'fa-pdf'"))
                assert _violated_constraint(exc_info) == "fk_legal_issue_fact_links_fact", (
                    f"Expected fact FK violation, got: {exc_info.value.orig}"
                )
                await s2.rollback()

            async with maker() as fresh:
                link = await fresh.get(LegalIssueFactLink, "lk-pdf")
                assert link is not None, "Fact link must survive rejected endpoint delete"
                issue = await fresh.get(LegalIssue, "ia-pdf")
                assert issue is not None, "LegalIssue must survive rejected delete"
                fact = await fresh.get(CaseFact, "fa-pdf")
                assert fact is not None, "CaseFact must survive rejected delete"
        finally:
            async with maker() as cleanup:
                await cleanup.execute(text("DELETE FROM legal_issue_fact_links WHERE tenant_id = 't1-pdf'"))
                await cleanup.execute(text("DELETE FROM legal_issues WHERE tenant_id = 't1-pdf'"))
                await cleanup.execute(text("DELETE FROM case_facts WHERE tenant_id = 't1-pdf'"))
                await cleanup.execute(text("DELETE FROM cases WHERE tenant_id = 't1-pdf'"))
                await cleanup.execute(text("DELETE FROM users WHERE tenant_id = 't1-pdf'"))
                await cleanup.execute(text("DELETE FROM tenants WHERE id = 't1-pdf'"))
                await cleanup.commit()
