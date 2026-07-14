"""P2.8A2 — Typed issue-to-issue dependency (legal_issue_dependencies) PostgreSQL acceptance tests."""
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
    LegalIssue,
    LegalIssueDependency,
    LegalIssueEdge,
    Tenant,
    User,
)

# ── PostgreSQL configuration ──────────────────────────────────────────────────

POSTGRES_HOST = os.environ.get("PGHOST", "127.0.0.1")
POSTGRES_PORT = os.environ.get("PGPORT", "5432")
POSTGRES_USER = os.environ.get("PGUSER", "emsalist")
POSTGRES_PASSWORD = os.environ.get("PGPASSWORD", "emsalist_test_pwd")
POSTGRES_DB = "emsalist_p28a2_acceptance"

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
    """Normalize a PostgreSQL internal ``"char"`` transport value to str.

    asyncpg may return single-byte ``"char"`` columns (pg_constraint.contype,
    pg_constraint.confdeltype) as bytes/bytearray/memoryview depending on the
    execution path. Normalize deterministically to the ASCII character.
    """
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
    """Seed tenant/user/cases/issues with per-test dedicated IDs."""
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
    ia = LegalIssue(id=f"ia{suffix}", tenant_id=f"t1{suffix}", case_id=f"c1{suffix}",
                    title="Issue A", status="proposed")
    ib = LegalIssue(id=f"ib{suffix}", tenant_id=f"t1{suffix}", case_id=f"c1{suffix}",
                    title="Issue B", status="proposed")
    session.add(ia)
    session.add(ib)
    await session.flush()


# ── Model / table identity ────────────────────────────────────────────────────

class TestDependencyModel:
    def test_dependency_table_name(self):
        assert LegalIssueDependency.__tablename__ == "legal_issue_dependencies"

    def test_legacy_edge_table_name(self):
        assert LegalIssueEdge.__tablename__ == "legal_issue_edges"

    def test_legacy_edge_distinct_from_dependency(self):
        assert LegalIssueEdge.__tablename__ != LegalIssueDependency.__tablename__

    def test_canonical_legal_issue_table_name(self):
        assert LegalIssue.__tablename__ == "legal_issues"

    def test_no_generic_polymorphic_columns(self):
        cols = {c.name for c in LegalIssueDependency.__table__.columns}
        for forbidden in ("from_type", "from_id", "to_type", "to_id", "relation_type"):
            assert forbidden not in cols


# ── Migrated PostgreSQL catalog proofs ────────────────────────────────────────

_INDEX_COLUMNS_SQL = (
    "SELECT a.attname FROM pg_index i "
    "JOIN pg_class t ON t.oid = i.indrelid "
    "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(i.indkey) "
    "JOIN pg_class ic ON ic.oid = i.indexrelid "
    "WHERE t.relname = 'legal_issue_dependencies' AND ic.relname = :index_name "
    "ORDER BY array_position(i.indkey, a.attnum)"
)

_FK_LOCAL_COLUMNS_SQL = (
    "SELECT a.attname FROM pg_constraint c "
    "JOIN pg_class t ON t.oid = c.conrelid "
    "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey) "
    "WHERE t.relname = 'legal_issue_dependencies' AND c.conname = :fk_name "
    "ORDER BY array_position(c.conkey, a.attnum)"
)

_FK_REFERENCED_COLUMNS_SQL = (
    "SELECT a.attname FROM pg_constraint c "
    "JOIN pg_class t ON t.oid = c.confrelid "
    "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.confkey) "
    "WHERE c.conname = :fk_name "
    "ORDER BY array_position(c.confkey, a.attnum)"
)


class TestDependencyCatalog:
    pytestmark = pytest.mark.asyncio

    async def test_table_exists(self, session):
        result = await session.execute(text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name='legal_issue_dependencies'"
        ))
        assert result.scalar() == 1

    async def test_exact_ordered_columns(self, session):
        result = await session.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='legal_issue_dependencies' ORDER BY ordinal_position"
        ))
        cols = [r[0] for r in result.fetchall()]
        expected = [
            "id", "tenant_id", "case_id", "issue_id", "required_issue_id",
            "created_at", "updated_at", "deleted_at", "version",
        ]
        assert cols == expected, f"Expected {expected}, got {cols}"

    async def test_issue_fk_exists(self, session):
        result = await session.execute(text(
            "SELECT contype FROM pg_constraint "
            "WHERE conname = 'fk_legal_issue_dependencies_issue'"
        ))
        raw = result.scalar()
        assert raw is not None, "fk_legal_issue_dependencies_issue not found"
        assert _normalize_pg_char(raw) == "f", f"Expected FOREIGN KEY (f), got {raw!r}"

    async def test_issue_fk_local_ordered_columns(self, session):
        result = await session.execute(
            text(_FK_LOCAL_COLUMNS_SQL), {"fk_name": "fk_legal_issue_dependencies_issue"}
        )
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["tenant_id", "case_id", "issue_id"], f"Got {cols}"

    async def test_issue_fk_referenced_ordered_columns(self, session):
        result = await session.execute(
            text(_FK_REFERENCED_COLUMNS_SQL), {"fk_name": "fk_legal_issue_dependencies_issue"}
        )
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["tenant_id", "case_id", "id"], f"Got {cols}"

    async def test_issue_fk_references_legal_issues(self, session):
        result = await session.execute(text(
            "SELECT rt.relname FROM pg_constraint c "
            "JOIN pg_class rt ON rt.oid = c.confrelid "
            "WHERE c.conname = 'fk_legal_issue_dependencies_issue'"
        ))
        assert result.scalar() == "legal_issues"

    async def test_required_issue_fk_exists(self, session):
        result = await session.execute(text(
            "SELECT contype FROM pg_constraint "
            "WHERE conname = 'fk_legal_issue_dependencies_required_issue'"
        ))
        raw = result.scalar()
        assert raw is not None, "fk_legal_issue_dependencies_required_issue not found"
        assert _normalize_pg_char(raw) == "f", f"Expected FOREIGN KEY (f), got {raw!r}"

    async def test_required_issue_fk_local_ordered_columns(self, session):
        result = await session.execute(
            text(_FK_LOCAL_COLUMNS_SQL),
            {"fk_name": "fk_legal_issue_dependencies_required_issue"},
        )
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["tenant_id", "case_id", "required_issue_id"], f"Got {cols}"

    async def test_required_issue_fk_referenced_ordered_columns(self, session):
        result = await session.execute(
            text(_FK_REFERENCED_COLUMNS_SQL),
            {"fk_name": "fk_legal_issue_dependencies_required_issue"},
        )
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["tenant_id", "case_id", "id"], f"Got {cols}"

    async def test_required_issue_fk_references_legal_issues(self, session):
        result = await session.execute(text(
            "SELECT rt.relname FROM pg_constraint c "
            "JOIN pg_class rt ON rt.oid = c.confrelid "
            "WHERE c.conname = 'fk_legal_issue_dependencies_required_issue'"
        ))
        assert result.scalar() == "legal_issues"

    async def test_both_endpoint_fks_delete_restrict(self, session):
        for fk in ("fk_legal_issue_dependencies_issue",
                   "fk_legal_issue_dependencies_required_issue"):
            result = await session.execute(
                text("SELECT confdeltype FROM pg_constraint WHERE conname = :n"),
                {"n": fk},
            )
            raw = result.scalar_one()
            assert _normalize_pg_char(raw) == "r", f"{fk}: expected RESTRICT (r), got {raw!r}"

    async def test_no_self_check_exists(self, session):
        result = await session.execute(text(
            "SELECT contype, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'ck_legal_issue_dependencies_no_self'"
        ))
        row = result.fetchone()
        assert row is not None, "ck_legal_issue_dependencies_no_self not found"
        assert _normalize_pg_char(row[0]) == "c", f"Expected CHECK (c), got {row[0]!r}"
        assert "issue_id" in row[1] and "required_issue_id" in row[1]

    async def test_ix_tenant_case_ordered(self, session):
        result = await session.execute(
            text(_INDEX_COLUMNS_SQL),
            {"index_name": "ix_legal_issue_dependencies_tenant_case"},
        )
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["tenant_id", "case_id"], f"Got {cols}"

    async def test_ix_issue_ordered(self, session):
        result = await session.execute(
            text(_INDEX_COLUMNS_SQL),
            {"index_name": "ix_legal_issue_dependencies_issue"},
        )
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["case_id", "issue_id"], f"Got {cols}"

    async def test_ix_required_issue_ordered(self, session):
        result = await session.execute(
            text(_INDEX_COLUMNS_SQL),
            {"index_name": "ix_legal_issue_dependencies_required_issue"},
        )
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["case_id", "required_issue_id"], f"Got {cols}"

    async def test_active_pair_unique_index_exists(self, session):
        result = await session.execute(text(
            "SELECT i.indisunique FROM pg_index i "
            "JOIN pg_class ic ON ic.oid = i.indexrelid "
            "WHERE ic.relname = 'uq_legal_issue_dependencies_active_pair'"
        ))
        assert result.scalar() is True

    async def test_active_pair_ordered_columns(self, session):
        result = await session.execute(
            text(_INDEX_COLUMNS_SQL),
            {"index_name": "uq_legal_issue_dependencies_active_pair"},
        )
        cols = [r[0] for r in result.fetchall()]
        assert cols == ["tenant_id", "case_id", "issue_id", "required_issue_id"], f"Got {cols}"

    async def test_active_pair_partial_predicate(self, session):
        result = await session.execute(text(
            "SELECT pg_get_expr(i.indpred, i.indrelid) FROM pg_index i "
            "JOIN pg_class ic ON ic.oid = i.indexrelid "
            "WHERE ic.relname = 'uq_legal_issue_dependencies_active_pair'"
        ))
        predicate = result.scalar()
        assert predicate is not None, "Index is not partial (no predicate)"
        normalized = predicate.strip().strip("()").strip().lower()
        assert normalized == "deleted_at is null", f"Got predicate {predicate!r}"


# ── PostgreSQL behavior proofs ────────────────────────────────────────────────

class TestDependencyBehavior:
    pytestmark = pytest.mark.asyncio

    async def test_same_tenant_same_case_dependency_persists(self, session):
        await _seed_core(session, "-p")
        dep = LegalIssueDependency(
            id="dep-p", tenant_id="t1-p", case_id="c1-p",
            issue_id="ia-p", required_issue_id="ib-p",
        )
        session.add(dep)
        await session.flush()
        loaded = await session.get(LegalIssueDependency, "dep-p")
        assert loaded is not None
        assert loaded.issue_id == "ia-p"
        assert loaded.required_issue_id == "ib-p"
        assert loaded.version == 1
        assert loaded.deleted_at is None

    async def test_self_dependency_rejected_by_check(self, session):
        await _seed_core(session, "-s")
        session.add(LegalIssueDependency(
            id="dep-s", tenant_id="t1-s", case_id="c1-s",
            issue_id="ia-s", required_issue_id="ia-s",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "ck_legal_issue_dependencies_no_self", (
            f"Expected no-self CHECK violation, got: {exc_info.value.orig}"
        )
        await session.rollback()

    async def test_missing_issue_endpoint_rejected(self, session):
        await _seed_core(session, "-mi")
        session.add(LegalIssueDependency(
            id="dep-mi", tenant_id="t1-mi", case_id="c1-mi",
            issue_id="ghost-missing", required_issue_id="ib-mi",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "fk_legal_issue_dependencies_issue", (
            f"Expected issue FK violation, got: {exc_info.value.orig}"
        )
        await session.rollback()

    async def test_missing_required_issue_endpoint_rejected(self, session):
        await _seed_core(session, "-mr")
        session.add(LegalIssueDependency(
            id="dep-mr", tenant_id="t1-mr", case_id="c1-mr",
            issue_id="ia-mr", required_issue_id="ghost-missing",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "fk_legal_issue_dependencies_required_issue", (
            f"Expected required-issue FK violation, got: {exc_info.value.orig}"
        )
        await session.rollback()

    async def test_cross_case_issue_endpoint_rejected(self, session):
        await _seed_core(session, "-cci")
        other = LegalIssue(id="ix-cci", tenant_id="t1-cci", case_id="c2-cci",
                           title="Other case issue", status="proposed")
        session.add(other)
        await session.flush()
        session.add(LegalIssueDependency(
            id="dep-cci", tenant_id="t1-cci", case_id="c1-cci",
            issue_id="ix-cci", required_issue_id="ib-cci",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "fk_legal_issue_dependencies_issue", (
            f"Expected issue FK violation, got: {exc_info.value.orig}"
        )
        await session.rollback()

    async def test_cross_case_required_endpoint_rejected(self, session):
        await _seed_core(session, "-ccr")
        other = LegalIssue(id="rx-ccr", tenant_id="t1-ccr", case_id="c2-ccr",
                           title="Other case issue", status="proposed")
        session.add(other)
        await session.flush()
        session.add(LegalIssueDependency(
            id="dep-ccr", tenant_id="t1-ccr", case_id="c1-ccr",
            issue_id="ia-ccr", required_issue_id="rx-ccr",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "fk_legal_issue_dependencies_required_issue", (
            f"Expected required-issue FK violation, got: {exc_info.value.orig}"
        )
        await session.rollback()

    async def test_cross_tenant_issue_endpoint_rejected(self, session):
        """Tenant dimension isolated: same case_id, dependency under t2.

        Both tenants exist; the case row exists once (owned by t1); the
        required endpoint is valid under (t2, c1) so only the issue FK fails.
        """
        await _seed_core(session, "-cti")
        t2 = Tenant(id="t2-cti", name="T2", slug="t2-cti", status="active")
        session.add(t2)
        await session.flush()
        valid_required = LegalIssue(id="rr-cti", tenant_id="t2-cti", case_id="c1-cti",
                                    title="Required under t2", status="proposed")
        session.add(valid_required)
        await session.flush()
        session.add(LegalIssueDependency(
            id="dep-cti", tenant_id="t2-cti", case_id="c1-cti",
            issue_id="ia-cti", required_issue_id="rr-cti",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "fk_legal_issue_dependencies_issue", (
            f"Expected issue FK violation, got: {exc_info.value.orig}"
        )
        await session.rollback()

    async def test_cross_tenant_required_endpoint_rejected(self, session):
        """Tenant dimension isolated: same case_id, dependency under t2.

        Both tenants exist; the case row exists once (owned by t1); the
        issue endpoint is valid under (t2, c1) so only the required FK fails.
        """
        await _seed_core(session, "-ctr")
        t2 = Tenant(id="t2-ctr", name="T2", slug="t2-ctr", status="active")
        session.add(t2)
        await session.flush()
        valid_issue = LegalIssue(id="ii-ctr", tenant_id="t2-ctr", case_id="c1-ctr",
                                 title="Issue under t2", status="proposed")
        session.add(valid_issue)
        await session.flush()
        session.add(LegalIssueDependency(
            id="dep-ctr", tenant_id="t2-ctr", case_id="c1-ctr",
            issue_id="ii-ctr", required_issue_id="ib-ctr",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "fk_legal_issue_dependencies_required_issue", (
            f"Expected required-issue FK violation, got: {exc_info.value.orig}"
        )
        await session.rollback()

    async def test_duplicate_active_pair_rejected(self, session):
        await _seed_core(session, "-dup")
        session.add(LegalIssueDependency(
            id="dep-dup1", tenant_id="t1-dup", case_id="c1-dup",
            issue_id="ia-dup", required_issue_id="ib-dup",
        ))
        await session.flush()
        session.add(LegalIssueDependency(
            id="dep-dup2", tenant_id="t1-dup", case_id="c1-dup",
            issue_id="ia-dup", required_issue_id="ib-dup",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "uq_legal_issue_dependencies_active_pair", (
            f"Expected active-pair unique violation, got: {exc_info.value.orig}"
        )
        await session.rollback()

    async def test_directional_pairs_both_persist(self, session):
        await _seed_core(session, "-dir")
        session.add(LegalIssueDependency(
            id="dep-ab", tenant_id="t1-dir", case_id="c1-dir",
            issue_id="ia-dir", required_issue_id="ib-dir",
        ))
        session.add(LegalIssueDependency(
            id="dep-ba", tenant_id="t1-dir", case_id="c1-dir",
            issue_id="ib-dir", required_issue_id="ia-dir",
        ))
        await session.flush()
        result = await session.execute(
            select(LegalIssueDependency).where(LegalIssueDependency.case_id == "c1-dir")
        )
        rows = result.scalars().all()
        assert len(rows) == 2
        pairs = {(r.issue_id, r.required_issue_id) for r in rows}
        assert pairs == {("ia-dir", "ib-dir"), ("ib-dir", "ia-dir")}

    async def test_soft_delete_then_recreate_active_pair(self, session):
        await _seed_core(session, "-sd")
        first = LegalIssueDependency(
            id="dep-sd1", tenant_id="t1-sd", case_id="c1-sd",
            issue_id="ia-sd", required_issue_id="ib-sd",
        )
        session.add(first)
        await session.flush()
        first.deleted_at = datetime.now(timezone.utc)
        await session.flush()
        second = LegalIssueDependency(
            id="dep-sd2", tenant_id="t1-sd", case_id="c1-sd",
            issue_id="ia-sd", required_issue_id="ib-sd",
        )
        session.add(second)
        await session.flush()
        loaded = await session.get(LegalIssueDependency, "dep-sd2")
        assert loaded is not None
        assert loaded.deleted_at is None
        soft_deleted = await session.get(LegalIssueDependency, "dep-sd1")
        assert soft_deleted is not None
        assert soft_deleted.deleted_at is not None

    async def test_issue_endpoint_physical_delete_rejected_rows_survive(self, session):
        """RESTRICT on issue endpoint: durable rows, rejected delete, fresh-session survival."""
        await _seed_core(session, "-pdi")
        session.add(LegalIssueDependency(
            id="dep-pdi", tenant_id="t1-pdi", case_id="c1-pdi",
            issue_id="ia-pdi", required_issue_id="ib-pdi",
        ))
        await session.commit()

        maker = async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)
        try:
            async with maker() as s2:
                with pytest.raises(IntegrityError) as exc_info:
                    await s2.execute(text("DELETE FROM legal_issues WHERE id = 'ia-pdi'"))
                assert _violated_constraint(exc_info) == "fk_legal_issue_dependencies_issue", (
                    f"Expected issue FK violation, got: {exc_info.value.orig}"
                )
                await s2.rollback()

            async with maker() as fresh:
                dep = await fresh.get(LegalIssueDependency, "dep-pdi")
                assert dep is not None, "Dependency must survive rejected endpoint delete"
                issue = await fresh.get(LegalIssue, "ia-pdi")
                assert issue is not None, "Issue endpoint must survive rejected delete"
                required = await fresh.get(LegalIssue, "ib-pdi")
                assert required is not None, "Required endpoint must survive rejected delete"
        finally:
            async with maker() as cleanup:
                await cleanup.execute(text("DELETE FROM legal_issue_dependencies WHERE id = 'dep-pdi'"))
                await cleanup.execute(text("DELETE FROM legal_issues WHERE tenant_id = 't1-pdi'"))
                await cleanup.execute(text("DELETE FROM cases WHERE tenant_id = 't1-pdi'"))
                await cleanup.execute(text("DELETE FROM users WHERE tenant_id = 't1-pdi'"))
                await cleanup.execute(text("DELETE FROM tenants WHERE id = 't1-pdi'"))
                await cleanup.commit()

    async def test_required_endpoint_physical_delete_rejected_rows_survive(self, session):
        """RESTRICT on required endpoint: durable rows, rejected delete, fresh-session survival."""
        await _seed_core(session, "-pdr")
        session.add(LegalIssueDependency(
            id="dep-pdr", tenant_id="t1-pdr", case_id="c1-pdr",
            issue_id="ia-pdr", required_issue_id="ib-pdr",
        ))
        await session.commit()

        maker = async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)
        try:
            async with maker() as s2:
                with pytest.raises(IntegrityError) as exc_info:
                    await s2.execute(text("DELETE FROM legal_issues WHERE id = 'ib-pdr'"))
                assert _violated_constraint(exc_info) == "fk_legal_issue_dependencies_required_issue", (
                    f"Expected required-issue FK violation, got: {exc_info.value.orig}"
                )
                await s2.rollback()

            async with maker() as fresh:
                dep = await fresh.get(LegalIssueDependency, "dep-pdr")
                assert dep is not None, "Dependency must survive rejected endpoint delete"
                issue = await fresh.get(LegalIssue, "ia-pdr")
                assert issue is not None, "Issue endpoint must survive rejected delete"
                required = await fresh.get(LegalIssue, "ib-pdr")
                assert required is not None, "Required endpoint must survive rejected delete"
        finally:
            async with maker() as cleanup:
                await cleanup.execute(text("DELETE FROM legal_issue_dependencies WHERE id = 'dep-pdr'"))
                await cleanup.execute(text("DELETE FROM legal_issues WHERE tenant_id = 't1-pdr'"))
                await cleanup.execute(text("DELETE FROM cases WHERE tenant_id = 't1-pdr'"))
                await cleanup.execute(text("DELETE FROM users WHERE tenant_id = 't1-pdr'"))
                await cleanup.execute(text("DELETE FROM tenants WHERE id = 't1-pdr'"))
                await cleanup.commit()

    async def test_single_alembic_head(self, session):
        from alembic.script import ScriptDirectory
        cfg = Config(_ALEMBIC_INI)
        cfg.set_main_option("sqlalchemy.url", TEST_DB_URL.replace("+asyncpg", ""))
        heads = ScriptDirectory.from_config(cfg).get_heads()
        assert len(heads) == 1
