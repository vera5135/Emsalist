"""P2.8B2 - Burden of proof PostgreSQL acceptance tests."""
from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models import (
    BURDEN_OF_PROOF_STATUSES,
    BurdenOfProof,
    Case,
    EVIDENCE_SUFFICIENCY_STATUSES,
    LegalIssue,
    Tenant,
    User,
)


POSTGRES_HOST = os.environ.get("PGHOST", "127.0.0.1")
POSTGRES_PORT = os.environ.get("PGPORT", "5432")
POSTGRES_USER = os.environ.get("PGUSER", "emsalist")
POSTGRES_PASSWORD = os.environ.get("PGPASSWORD", "emsalist_test_pwd")
POSTGRES_DB = "emsalist_p28b2_burden_of_proof_acceptance"

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


async def _seed_case_with_issue(session: AsyncSession, suffix: str):
    session.add(Tenant(id=f"t{suffix}", name="T", slug=f"t{suffix}", status="active"))
    await session.flush()
    session.add(User(
        id=f"u{suffix}", tenant_id=f"t{suffix}",
        email_normalized=f"u{suffix}@t.com", display_name="U",
        status="active", role="editor",
    ))
    await session.flush()
    session.add(Case(
        id=f"c{suffix}", tenant_id=f"t{suffix}", owner_user_id=f"u{suffix}",
        title="Case", status="active",
    ))
    await session.flush()
    session.add(LegalIssue(
        id=f"issue{suffix}", tenant_id=f"t{suffix}", case_id=f"c{suffix}",
        title="Defect issue", status="proposed",
    ))
    await session.flush()


def _burden(suffix: str, **overrides) -> BurdenOfProof:
    values = {
        "id": f"b{suffix}",
        "tenant_id": f"t{suffix}",
        "case_id": f"c{suffix}",
        "issue_id": f"issue{suffix}",
        "burden_party_id": "plaintiff",
        "burden_type": "initial_burden",
        "required_standard": "preponderance",
        "legal_source_refs": [],
        "evidence_status": "unsupported",
        "status": "candidate",
        "notes": "Needs source-backed review.",
    }
    values.update(overrides)
    return BurdenOfProof(**values)


class TestBurdenOfProofModel:
    def test_exact_vocabularies(self):
        assert BURDEN_OF_PROOF_STATUSES == frozenset({
            "candidate", "review_required", "finalized",
        })
        assert EVIDENCE_SUFFICIENCY_STATUSES == frozenset({
            "supported", "partially_supported", "unsupported", "contradicted",
            "inadmissibility_risk", "authenticity_risk",
        })

    def test_no_hidden_reasoning_columns(self):
        cols = {c.name for c in BurdenOfProof.__table__.columns}
        for forbidden in ("chain_of_thought", "thinking", "reasoning_trace",
                          "hidden_reasoning", "scratchpad"):
            assert forbidden not in cols


class TestBurdenOfProofCatalog:
    pytestmark = pytest.mark.asyncio

    async def test_exact_columns(self, session):
        result = await session.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='burdens_of_proof' ORDER BY ordinal_position"
        ))
        assert [r[0] for r in result.fetchall()] == [
            "id", "tenant_id", "case_id", "issue_id", "burden_party_id",
            "burden_type", "required_standard", "legal_source_refs",
            "evidence_status", "status", "notes", "created_at", "updated_at",
            "deleted_at", "version",
        ]

    async def test_constraints_indexes_and_fk_backing(self, session):
        for name in (
            "ck_burdens_of_proof_status",
            "ck_burdens_of_proof_evidence_status",
            "ck_burdens_of_proof_finalized_requires_sources",
        ):
            row = (await session.execute(text(
                "SELECT contype FROM pg_constraint WHERE conname = :name"
            ), {"name": name})).fetchone()
            assert row is not None
            assert _normalize_pg_char(row[0]) == "c"

        got = (await session.execute(text(
            "SELECT rc.unique_constraint_name "
            "FROM information_schema.referential_constraints rc "
            "JOIN information_schema.table_constraints tc "
            "  ON rc.constraint_name = tc.constraint_name "
            "  AND rc.constraint_schema = tc.constraint_schema "
            "WHERE tc.table_name = 'burdens_of_proof' "
            "  AND tc.constraint_name = 'fk_burdens_of_proof_issue'"
        ))).scalar_one()
        assert got == "uq_legal_issues_tenant_case_id"

        unique_index = (await session.execute(text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE tablename='burdens_of_proof' "
            "  AND indexname='uq_burdens_of_proof_active_scope'"
        ))).scalar_one()
        assert "UNIQUE INDEX" in unique_index
        assert "deleted_at IS NULL" in unique_index


class TestBurdenOfProofBehavior:
    pytestmark = pytest.mark.asyncio

    async def test_candidate_can_persist_without_sources(self, session):
        await _seed_case_with_issue(session, "-cand")
        session.add(_burden("-cand"))
        await session.flush()
        assert await session.get(BurdenOfProof, "b-cand") is not None

    async def test_finalized_requires_sources_and_accepts_source_refs(self, session):
        await _seed_case_with_issue(session, "-fin")
        session.add(_burden("-fin", status="finalized", legal_source_refs=[]))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "ck_burdens_of_proof_finalized_requires_sources"
        await session.rollback()

        await _seed_case_with_issue(session, "-fsrc")
        session.add(_burden(
            "-fsrc",
            status="finalized",
            legal_source_refs=[{
                "source_record_id": "src-1",
                "source_version_id": "ver-1",
                "source_paragraph_id": "para-1",
                "relation_type": "source_governs_issue",
            }],
            evidence_status="supported",
        ))
        await session.flush()
        assert await session.get(BurdenOfProof, "b-fsrc") is not None

    async def test_invalid_statuses_are_rejected_by_exact_constraints(self, session):
        await _seed_case_with_issue(session, "-voc")
        await session.commit()
        for burden, constraint in (
            (_burden("-voc", id="b-bad-status", status="accepted"), "ck_burdens_of_proof_status"),
            (
                _burden("-voc", id="b-bad-evidence", evidence_status="weak"),
                "ck_burdens_of_proof_evidence_status",
            ),
        ):
            session.add(burden)
            with pytest.raises(IntegrityError) as exc_info:
                await session.flush()
            assert _violated_constraint(exc_info) == constraint
            await session.rollback()

    async def test_issue_tuple_fk_rejects_cross_case_burden(self, session):
        await _seed_case_with_issue(session, "-fk")
        session.add(Case(
            id="c2-fk", tenant_id="t-fk", owner_user_id="u-fk",
            title="Other", status="active",
        ))
        await session.flush()
        await session.commit()

        session.add(_burden("-fk", id="b-fk-cross", case_id="c2-fk"))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "fk_burdens_of_proof_issue"
        await session.rollback()

    async def test_active_scope_is_unique_but_soft_delete_allows_replacement(self, session):
        await _seed_case_with_issue(session, "-uniq")
        session.add(_burden("-uniq", id="b-uniq-a"))
        await session.commit()

        session.add(_burden("-uniq", id="b-uniq-b"))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "uq_burdens_of_proof_active_scope"
        await session.rollback()

        existing = await session.get(BurdenOfProof, "b-uniq-a")
        existing.deleted_at = datetime.now(UTC)
        await session.commit()

        session.add(_burden("-uniq", id="b-uniq-c"))
        await session.flush()
        assert await session.get(BurdenOfProof, "b-uniq-c") is not None
