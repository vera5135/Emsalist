"""P2.8A5 - Typed evidence-to-claim link PostgreSQL acceptance tests."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models import (
    Case,
    Claim,
    Evidence,
    EvidenceClaimLink,
    EVIDENCE_CLAIM_RELATIONS,
    Tenant,
    User,
)


POSTGRES_HOST = os.environ.get("PGHOST", "127.0.0.1")
POSTGRES_PORT = os.environ.get("PGPORT", "5432")
POSTGRES_USER = os.environ.get("PGUSER", "emsalist")
POSTGRES_PASSWORD = os.environ.get("PGPASSWORD", "emsalist_test_pwd")
POSTGRES_DB = "emsalist_p28a5_evidence_claim_acceptance"

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
    t = Tenant(id=f"t1{suffix}", name="T1", slug=f"t1{suffix}", status="active")
    session.add(t)
    await session.flush()
    u = User(
        id=f"u1{suffix}",
        tenant_id=f"t1{suffix}",
        email_normalized=f"u{suffix}@t.com",
        display_name="U",
        status="active",
        role="editor",
    )
    session.add(u)
    await session.flush()
    c1 = Case(
        id=f"c1{suffix}",
        tenant_id=f"t1{suffix}",
        owner_user_id=f"u1{suffix}",
        title="Case 1",
        status="active",
    )
    session.add(c1)
    await session.flush()
    c2 = Case(
        id=f"c2{suffix}",
        tenant_id=f"t1{suffix}",
        owner_user_id=f"u1{suffix}",
        title="Case 2",
        status="active",
    )
    session.add(c2)
    await session.flush()
    cl = Claim(
        id=f"cl{suffix}",
        tenant_id=f"t1{suffix}",
        case_id=f"c1{suffix}",
        claim_type="severance",
        title="Claim",
    )
    session.add(cl)
    await session.flush()
    ev = Evidence(
        id=f"ev{suffix}",
        tenant_id=f"t1{suffix}",
        case_id=f"c1{suffix}",
        evidence_type="document",
        title="Evidence",
    )
    session.add(ev)
    await session.flush()


_INDEX_COLUMNS_SQL = (
    "SELECT a.attname FROM pg_index i "
    "JOIN pg_class t ON t.oid = i.indrelid "
    "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(i.indkey) "
    "JOIN pg_class ic ON ic.oid = i.indexrelid "
    "WHERE t.relname = 'evidence_claim_links' AND ic.relname = :index_name "
    "ORDER BY array_position(i.indkey, a.attnum)"
)

_FK_LOCAL_COLUMNS_SQL = (
    "SELECT a.attname FROM pg_constraint c "
    "JOIN pg_class t ON t.oid = c.conrelid "
    "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey) "
    "WHERE t.relname = 'evidence_claim_links' AND c.conname = :fk_name "
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
    "WHERE tc.table_name = 'evidence_claim_links' "
    "  AND tc.constraint_name = :fk_name"
)


class TestEvidenceClaimLinkModel:
    def test_table_name(self):
        assert EvidenceClaimLink.__tablename__ == "evidence_claim_links"

    def test_endpoint_table_names(self):
        assert Claim.__tablename__ == "claims"
        assert Evidence.__tablename__ == "evidence"

    def test_exact_relation_vocabulary(self):
        assert EVIDENCE_CLAIM_RELATIONS == frozenset({
            "evidence_supports_claim", "evidence_contradicts_claim",
        })

    def test_no_generic_polymorphic_columns(self):
        cols = {c.name for c in EvidenceClaimLink.__table__.columns}
        for forbidden in (
            "from_type", "from_id", "to_type", "to_id",
            "confidence", "rationale", "source_type", "source_id",
            "metadata_json", "status",
        ):
            assert forbidden not in cols


class TestEvidenceClaimLinkCatalog:
    pytestmark = pytest.mark.asyncio

    async def test_table_exists(self, session):
        result = await session.execute(text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name='evidence_claim_links'"
        ))
        assert result.scalar() == 1

    async def test_exact_ordered_columns(self, session):
        result = await session.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='evidence_claim_links' ORDER BY ordinal_position"
        ))
        cols = [r[0] for r in result.fetchall()]
        expected = [
            "id", "tenant_id", "case_id", "claim_id", "evidence_id",
            "relation_type", "created_at", "updated_at", "deleted_at", "version",
        ]
        assert cols == expected, f"Expected {expected}, got {cols}"

    async def test_primary_key_remains_id_only(self, session):
        result = await session.execute(text(
            "SELECT a.attname FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey) "
            "WHERE t.relname = 'evidence_claim_links' AND c.contype = 'p' "
            "ORDER BY array_position(c.conkey, a.attnum)"
        ))
        assert [r[0] for r in result.fetchall()] == ["id"]

    async def test_claim_fk_shape_and_backing(self, session):
        result = await session.execute(text(
            "SELECT contype, confdeltype FROM pg_constraint "
            "WHERE conname = 'fk_evidence_claim_links_claim'"
        ))
        row = result.fetchone()
        assert row is not None
        assert _normalize_pg_char(row[0]) == "f"
        assert _normalize_pg_char(row[1]) == "r"

        result = await session.execute(
            text(_FK_LOCAL_COLUMNS_SQL), {"fk_name": "fk_evidence_claim_links_claim"}
        )
        assert [r[0] for r in result.fetchall()] == ["tenant_id", "case_id", "claim_id"]

        result = await session.execute(
            text(_FK_REFERENCED_COLUMNS_SQL), {"fk_name": "fk_evidence_claim_links_claim"}
        )
        assert [r[0] for r in result.fetchall()] == ["tenant_id", "case_id", "id"]

        result = await session.execute(
            text(_FK_UNIQUE_BACKING_SQL), {"fk_name": "fk_evidence_claim_links_claim"}
        )
        assert result.scalar_one() == "uq_claims_tenant_case_id"

    async def test_evidence_fk_shape_and_backing(self, session):
        result = await session.execute(text(
            "SELECT contype, confdeltype FROM pg_constraint "
            "WHERE conname = 'fk_evidence_claim_links_evidence'"
        ))
        row = result.fetchone()
        assert row is not None
        assert _normalize_pg_char(row[0]) == "f"
        assert _normalize_pg_char(row[1]) == "r"

        result = await session.execute(
            text(_FK_LOCAL_COLUMNS_SQL), {"fk_name": "fk_evidence_claim_links_evidence"}
        )
        assert [r[0] for r in result.fetchall()] == ["tenant_id", "case_id", "evidence_id"]

        result = await session.execute(
            text(_FK_REFERENCED_COLUMNS_SQL), {"fk_name": "fk_evidence_claim_links_evidence"}
        )
        assert [r[0] for r in result.fetchall()] == ["tenant_id", "case_id", "id"]

        result = await session.execute(
            text(_FK_UNIQUE_BACKING_SQL), {"fk_name": "fk_evidence_claim_links_evidence"}
        )
        assert result.scalar_one() == "uq_evidence_tenant_case_id"

    async def test_relation_check_exists(self, session):
        result = await session.execute(text(
            "SELECT contype, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'ck_evidence_claim_links_relation_type'"
        ))
        row = result.fetchone()
        assert row is not None
        assert _normalize_pg_char(row[0]) == "c"
        assert "evidence_supports_claim" in row[1]
        assert "evidence_contradicts_claim" in row[1]

    async def test_indexes_and_partial_unique(self, session):
        expected = {
            "ix_evidence_claim_links_tenant_case": ["tenant_id", "case_id"],
            "ix_evidence_claim_links_claim": ["case_id", "claim_id"],
            "ix_evidence_claim_links_evidence": ["case_id", "evidence_id"],
            "uq_evidence_claim_links_active_relation": [
                "tenant_id", "case_id", "claim_id", "evidence_id", "relation_type",
            ],
        }
        for index_name, columns in expected.items():
            result = await session.execute(
                text(_INDEX_COLUMNS_SQL), {"index_name": index_name}
            )
            assert [r[0] for r in result.fetchall()] == columns

        result = await session.execute(text(
            "SELECT i.indisunique, pg_get_expr(i.indpred, i.indrelid) "
            "FROM pg_index i "
            "JOIN pg_class ic ON ic.oid = i.indexrelid "
            "WHERE ic.relname = 'uq_evidence_claim_links_active_relation'"
        ))
        row = result.fetchone()
        assert row is not None
        assert row[0] is True
        assert row[1].strip().strip("()").strip().lower() == "deleted_at is null"

    async def test_single_alembic_head(self, session):
        from alembic.script import ScriptDirectory

        cfg = Config(_ALEMBIC_INI)
        cfg.set_main_option("sqlalchemy.url", TEST_DB_URL.replace("+asyncpg", ""))
        heads = ScriptDirectory.from_config(cfg).get_heads()
        assert len(heads) == 1


class TestEvidenceClaimLinkBehavior:
    pytestmark = pytest.mark.asyncio

    async def test_support_relation_persists(self, session):
        await _seed_core(session, "-sp")
        session.add(EvidenceClaimLink(
            id="lk-sp", tenant_id="t1-sp", case_id="c1-sp",
            claim_id="cl-sp", evidence_id="ev-sp",
            relation_type="evidence_supports_claim",
        ))
        await session.flush()
        loaded = await session.get(EvidenceClaimLink, "lk-sp")
        assert loaded is not None
        assert loaded.relation_type == "evidence_supports_claim"
        assert loaded.version == 1
        assert loaded.deleted_at is None

    async def test_contradiction_relation_persists(self, session):
        await _seed_core(session, "-cn")
        session.add(EvidenceClaimLink(
            id="lk-cn", tenant_id="t1-cn", case_id="c1-cn",
            claim_id="cl-cn", evidence_id="ev-cn",
            relation_type="evidence_contradicts_claim",
        ))
        await session.flush()
        loaded = await session.get(EvidenceClaimLink, "lk-cn")
        assert loaded is not None
        assert loaded.relation_type == "evidence_contradicts_claim"

    async def test_invalid_relation_rejected_by_check(self, session):
        await _seed_core(session, "-iv")
        session.add(EvidenceClaimLink(
            id="lk-iv", tenant_id="t1-iv", case_id="c1-iv",
            claim_id="cl-iv", evidence_id="ev-iv",
            relation_type="related_to",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "ck_evidence_claim_links_relation_type"
        await session.rollback()

    async def test_missing_claim_endpoint_rejected(self, session):
        await _seed_core(session, "-mc")
        session.add(EvidenceClaimLink(
            id="lk-mc", tenant_id="t1-mc", case_id="c1-mc",
            claim_id="ghost-missing", evidence_id="ev-mc",
            relation_type="evidence_supports_claim",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "fk_evidence_claim_links_claim"
        await session.rollback()

    async def test_missing_evidence_endpoint_rejected(self, session):
        await _seed_core(session, "-me")
        session.add(EvidenceClaimLink(
            id="lk-me", tenant_id="t1-me", case_id="c1-me",
            claim_id="cl-me", evidence_id="ghost-missing",
            relation_type="evidence_supports_claim",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "fk_evidence_claim_links_evidence"
        await session.rollback()

    async def test_cross_case_claim_endpoint_rejected(self, session):
        await _seed_core(session, "-ccc")
        session.add(Claim(id="cx-ccc", tenant_id="t1-ccc", case_id="c2-ccc", title="Other claim"))
        await session.flush()
        session.add(EvidenceClaimLink(
            id="lk-ccc", tenant_id="t1-ccc", case_id="c1-ccc",
            claim_id="cx-ccc", evidence_id="ev-ccc",
            relation_type="evidence_supports_claim",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "fk_evidence_claim_links_claim"
        await session.rollback()

    async def test_cross_case_evidence_endpoint_rejected(self, session):
        await _seed_core(session, "-cce")
        session.add(Evidence(id="ex-cce", tenant_id="t1-cce", case_id="c2-cce", title="Other evidence"))
        await session.flush()
        session.add(EvidenceClaimLink(
            id="lk-cce", tenant_id="t1-cce", case_id="c1-cce",
            claim_id="cl-cce", evidence_id="ex-cce",
            relation_type="evidence_supports_claim",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "fk_evidence_claim_links_evidence"
        await session.rollback()

    async def test_cross_tenant_claim_endpoint_rejected(self, session):
        await _seed_core(session, "-ctc")
        session.add(Tenant(id="t2-ctc", name="T2", slug="t2-ctc", status="active"))
        await session.flush()
        session.add(Claim(id="cx-ctc", tenant_id="t2-ctc", case_id="c1-ctc", title="Other tenant claim"))
        await session.flush()
        session.add(EvidenceClaimLink(
            id="lk-ctc", tenant_id="t1-ctc", case_id="c1-ctc",
            claim_id="cx-ctc", evidence_id="ev-ctc",
            relation_type="evidence_supports_claim",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "fk_evidence_claim_links_claim"
        await session.rollback()

    async def test_cross_tenant_evidence_endpoint_rejected(self, session):
        await _seed_core(session, "-cte")
        session.add(Tenant(id="t2-cte", name="T2", slug="t2-cte", status="active"))
        await session.flush()
        session.add(Evidence(id="ex-cte", tenant_id="t2-cte", case_id="c1-cte", title="Other tenant evidence"))
        await session.flush()
        session.add(EvidenceClaimLink(
            id="lk-cte", tenant_id="t1-cte", case_id="c1-cte",
            claim_id="cl-cte", evidence_id="ex-cte",
            relation_type="evidence_supports_claim",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "fk_evidence_claim_links_evidence"
        await session.rollback()

    async def test_duplicate_active_support_rejected(self, session):
        await _seed_core(session, "-ds")
        session.add(EvidenceClaimLink(
            id="lk-ds1", tenant_id="t1-ds", case_id="c1-ds",
            claim_id="cl-ds", evidence_id="ev-ds",
            relation_type="evidence_supports_claim",
        ))
        await session.flush()
        session.add(EvidenceClaimLink(
            id="lk-ds2", tenant_id="t1-ds", case_id="c1-ds",
            claim_id="cl-ds", evidence_id="ev-ds",
            relation_type="evidence_supports_claim",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "uq_evidence_claim_links_active_relation"
        await session.rollback()

    async def test_duplicate_active_contradiction_rejected(self, session):
        await _seed_core(session, "-dc")
        session.add(EvidenceClaimLink(
            id="lk-dc1", tenant_id="t1-dc", case_id="c1-dc",
            claim_id="cl-dc", evidence_id="ev-dc",
            relation_type="evidence_contradicts_claim",
        ))
        await session.flush()
        session.add(EvidenceClaimLink(
            id="lk-dc2", tenant_id="t1-dc", case_id="c1-dc",
            claim_id="cl-dc", evidence_id="ev-dc",
            relation_type="evidence_contradicts_claim",
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "uq_evidence_claim_links_active_relation"
        await session.rollback()

    async def test_support_and_contradiction_coexist(self, session):
        await _seed_core(session, "-cx")
        session.add(EvidenceClaimLink(
            id="lk-cx1", tenant_id="t1-cx", case_id="c1-cx",
            claim_id="cl-cx", evidence_id="ev-cx",
            relation_type="evidence_supports_claim",
        ))
        session.add(EvidenceClaimLink(
            id="lk-cx2", tenant_id="t1-cx", case_id="c1-cx",
            claim_id="cl-cx", evidence_id="ev-cx",
            relation_type="evidence_contradicts_claim",
        ))
        await session.flush()
        result = await session.execute(
            select(EvidenceClaimLink).where(EvidenceClaimLink.case_id == "c1-cx")
        )
        assert {r.relation_type for r in result.scalars().all()} == {
            "evidence_supports_claim", "evidence_contradicts_claim",
        }

    async def test_soft_delete_then_recreate_active_relation(self, session):
        await _seed_core(session, "-sd")
        first = EvidenceClaimLink(
            id="lk-sd1", tenant_id="t1-sd", case_id="c1-sd",
            claim_id="cl-sd", evidence_id="ev-sd",
            relation_type="evidence_supports_claim",
        )
        session.add(first)
        await session.flush()
        first.deleted_at = datetime.now(timezone.utc)
        await session.flush()
        session.add(EvidenceClaimLink(
            id="lk-sd2", tenant_id="t1-sd", case_id="c1-sd",
            claim_id="cl-sd", evidence_id="ev-sd",
            relation_type="evidence_supports_claim",
        ))
        await session.flush()
        assert (await session.get(EvidenceClaimLink, "lk-sd2")) is not None
        assert (await session.get(EvidenceClaimLink, "lk-sd1")).deleted_at is not None

    async def test_claim_physical_delete_rejected_rows_survive(self, session):
        await _seed_core(session, "-pdc")
        session.add(EvidenceClaimLink(
            id="lk-pdc", tenant_id="t1-pdc", case_id="c1-pdc",
            claim_id="cl-pdc", evidence_id="ev-pdc",
            relation_type="evidence_supports_claim",
        ))
        await session.commit()

        maker = async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)
        try:
            async with maker() as s2:
                with pytest.raises(IntegrityError) as exc_info:
                    await s2.execute(text("DELETE FROM claims WHERE id = 'cl-pdc'"))
                assert _violated_constraint(exc_info) == "fk_evidence_claim_links_claim"
                await s2.rollback()

            async with maker() as fresh:
                assert await fresh.get(EvidenceClaimLink, "lk-pdc") is not None
                assert await fresh.get(Claim, "cl-pdc") is not None
                assert await fresh.get(Evidence, "ev-pdc") is not None
        finally:
            async with maker() as cleanup:
                await cleanup.execute(text("DELETE FROM evidence_claim_links WHERE tenant_id = 't1-pdc'"))
                await cleanup.execute(text("DELETE FROM evidence WHERE tenant_id = 't1-pdc'"))
                await cleanup.execute(text("DELETE FROM claims WHERE tenant_id = 't1-pdc'"))
                await cleanup.execute(text("DELETE FROM cases WHERE tenant_id = 't1-pdc'"))
                await cleanup.execute(text("DELETE FROM users WHERE tenant_id = 't1-pdc'"))
                await cleanup.execute(text("DELETE FROM tenants WHERE id = 't1-pdc'"))
                await cleanup.commit()

    async def test_evidence_physical_delete_rejected_rows_survive(self, session):
        await _seed_core(session, "-pde")
        session.add(EvidenceClaimLink(
            id="lk-pde", tenant_id="t1-pde", case_id="c1-pde",
            claim_id="cl-pde", evidence_id="ev-pde",
            relation_type="evidence_contradicts_claim",
        ))
        await session.commit()

        maker = async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)
        try:
            async with maker() as s2:
                with pytest.raises(IntegrityError) as exc_info:
                    await s2.execute(text("DELETE FROM evidence WHERE id = 'ev-pde'"))
                assert _violated_constraint(exc_info) == "fk_evidence_claim_links_evidence"
                await s2.rollback()

            async with maker() as fresh:
                assert await fresh.get(EvidenceClaimLink, "lk-pde") is not None
                assert await fresh.get(Claim, "cl-pde") is not None
                assert await fresh.get(Evidence, "ev-pde") is not None
        finally:
            async with maker() as cleanup:
                await cleanup.execute(text("DELETE FROM evidence_claim_links WHERE tenant_id = 't1-pde'"))
                await cleanup.execute(text("DELETE FROM evidence WHERE tenant_id = 't1-pde'"))
                await cleanup.execute(text("DELETE FROM claims WHERE tenant_id = 't1-pde'"))
                await cleanup.execute(text("DELETE FROM cases WHERE tenant_id = 't1-pde'"))
                await cleanup.execute(text("DELETE FROM users WHERE tenant_id = 't1-pde'"))
                await cleanup.execute(text("DELETE FROM tenants WHERE id = 't1-pde'"))
                await cleanup.commit()
