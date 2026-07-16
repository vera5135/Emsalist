"""P2.8B1 - Reasoning foundation PostgreSQL acceptance tests."""
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

from app.db.models import (
    Case,
    CaseFact,
    LegalIssue,
    LegalIssueSourceLink,
    LegalReasoningRun,
    LEGAL_REASONING_RUN_STATUSES,
    MemoryRevision,
    MEMORY_REVISION_TRIGGER_TYPES,
    SourceParagraph,
    SourceRecord,
    SourceVersion,
    Tenant,
    User,
)
from app.services.legal_reasoning_reproducibility import (
    compute_case_source_fingerprint,
    compute_memory_fingerprint,
    output_hash,
)


POSTGRES_HOST = os.environ.get("PGHOST", "127.0.0.1")
POSTGRES_PORT = os.environ.get("PGPORT", "5432")
POSTGRES_USER = os.environ.get("PGUSER", "emsalist")
POSTGRES_PASSWORD = os.environ.get("PGPASSWORD", "emsalist_test_pwd")
POSTGRES_DB = "emsalist_p28b1_reasoning_foundation_acceptance"

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


async def _seed_case(session: AsyncSession, suffix: str):
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


async def _seed_memory(session: AsyncSession, suffix: str):
    await _seed_case(session, suffix)
    session.add(CaseFact(
        id=f"fact{suffix}", tenant_id=f"t{suffix}", case_id=f"c{suffix}",
        fact_type="vehicle_defect", value="Engine fault after delivery.",
        verification_status="verified",
    ))
    await session.flush()
    session.add(LegalIssue(
        id=f"issue{suffix}", tenant_id=f"t{suffix}", case_id=f"c{suffix}",
        title="Defect issue", status="proposed",
    ))
    await session.flush()


async def _seed_source_chain(session: AsyncSession, suffix: str):
    session.add(SourceRecord(
        id=f"src{suffix}", source_type="legislation",
        canonical_key=f"LAW:{suffix}:1", title="Law",
        verification_status="editor_verified", current_version_id=f"ver{suffix}",
    ))
    await session.flush()
    session.add(SourceVersion(
        id=f"ver{suffix}", source_record_id=f"src{suffix}",
        version_label="v1", content_hash=f"hash{suffix}",
        normalized_text="Article text.", status="active",
    ))
    await session.flush()
    session.add(SourceParagraph(
        id=f"para{suffix}", source_version_id=f"ver{suffix}",
        paragraph_index=1, text="Article paragraph.", text_hash=f"phash{suffix}",
        article_number="12",
    ))
    await session.flush()
    session.add(LegalIssueSourceLink(
        id=f"source-link{suffix}", tenant_id=f"t{suffix}", case_id=f"c{suffix}",
        issue_id=f"issue{suffix}", source_record_id=f"src{suffix}",
        source_version_id=f"ver{suffix}", source_paragraph_id=f"para{suffix}",
        relation_type="source_governs_issue",
    ))
    await session.flush()


class TestReasoningFoundationModel:
    def test_exact_vocabularies(self):
        assert MEMORY_REVISION_TRIGGER_TYPES == frozenset({
            "user_message", "document_analysis", "uyap_sync", "manual_edit", "system_recompute",
        })
        assert LEGAL_REASONING_RUN_STATUSES == frozenset({
            "started", "succeeded", "failed", "stale",
        })

    def test_no_hidden_reasoning_columns(self):
        for model in (MemoryRevision, LegalReasoningRun):
            cols = {c.name for c in model.__table__.columns}
            for forbidden in ("chain_of_thought", "thinking", "reasoning_trace",
                              "hidden_reasoning", "scratchpad"):
                assert forbidden not in cols


class TestReasoningFoundationCatalog:
    pytestmark = pytest.mark.asyncio

    async def test_exact_columns(self, session):
        expected = {
            "memory_revisions": [
                "id", "tenant_id", "case_id", "revision_number",
                "memory_fingerprint", "trigger_type", "trigger_id",
                "change_summary_json", "created_by", "created_at",
            ],
            "legal_reasoning_runs": [
                "id", "tenant_id", "case_id", "memory_revision_id",
                "source_fingerprint", "provider", "model_version", "prompt_version",
                "output_hash", "status", "safe_summary_json", "created_at", "completed_at",
            ],
        }
        for table, cols in expected.items():
            result = await session.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name=:table ORDER BY ordinal_position"
            ), {"table": table})
            assert [r[0] for r in result.fetchall()] == cols

    async def test_constraints_and_fk_backing(self, session):
        for name in (
            "ck_memory_revisions_trigger_type",
            "ck_memory_revisions_fingerprint_len",
            "ck_legal_reasoning_runs_status",
            "ck_legal_reasoning_runs_source_fingerprint_len",
            "ck_legal_reasoning_runs_output_hash_len",
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
            "WHERE tc.table_name = 'legal_reasoning_runs' "
            "  AND tc.constraint_name = 'fk_legal_reasoning_runs_memory_revision'"
        ))).scalar_one()
        assert got == "uq_memory_revisions_tenant_case_id"

    async def test_single_alembic_head(self, session):
        from alembic.script import ScriptDirectory

        cfg = Config(_ALEMBIC_INI)
        cfg.set_main_option("sqlalchemy.url", TEST_DB_URL.replace("+asyncpg", ""))
        assert len(ScriptDirectory.from_config(cfg).get_heads()) == 1


class TestReasoningFoundationBehavior:
    pytestmark = pytest.mark.asyncio

    async def test_memory_revision_and_run_persist(self, session):
        await _seed_memory(session, "-ok")
        mem_fp = await compute_memory_fingerprint(session, tenant_id="t-ok", case_id="c-ok")
        rev = MemoryRevision(
            id="mr-ok", tenant_id="t-ok", case_id="c-ok", revision_number=1,
            memory_fingerprint=mem_fp, trigger_type="manual_edit",
            trigger_id="fact-ok", change_summary_json={"facts": 1}, created_by="u-ok",
        )
        session.add(rev)
        await session.flush()
        out_hash = output_hash({"short_rationale": "Deterministic basis", "basis": ["fact-ok"]})
        session.add(LegalReasoningRun(
            id="rr-ok", tenant_id="t-ok", case_id="c-ok", memory_revision_id="mr-ok",
            source_fingerprint="a" * 64, provider="deterministic",
            model_version="rule-evaluator-v1", prompt_version="p2.8b-legal-reasoning-1",
            output_hash=out_hash, status="succeeded",
            safe_summary_json={"short_rationale": "Deterministic basis"},
        ))
        await session.flush()
        assert await session.get(LegalReasoningRun, "rr-ok") is not None

    async def test_invalid_vocabularies_and_lengths_rejected(self, session):
        await _seed_memory(session, "-iv")
        await session.commit()
        cases = [
            MemoryRevision(
                id="mr-bad-trigger", tenant_id="t-iv", case_id="c-iv",
                revision_number=1, memory_fingerprint="a" * 64,
                trigger_type="other", change_summary_json={}, created_by="u-iv",
            ),
            MemoryRevision(
                id="mr-bad-fp", tenant_id="t-iv", case_id="c-iv",
                revision_number=2, memory_fingerprint="short",
                trigger_type="manual_edit", change_summary_json={}, created_by="u-iv",
            ),
        ]
        for item, constraint in (
            (cases[0], "ck_memory_revisions_trigger_type"),
            (cases[1], "ck_memory_revisions_fingerprint_len"),
        ):
            session.add(item)
            with pytest.raises(IntegrityError) as exc_info:
                await session.flush()
            assert _violated_constraint(exc_info) == constraint
            await session.rollback()

        session.add(MemoryRevision(
            id="mr-good", tenant_id="t-iv", case_id="c-iv", revision_number=1,
            memory_fingerprint="b" * 64, trigger_type="manual_edit",
            change_summary_json={}, created_by="u-iv",
        ))
        await session.commit()
        for run_id, status_value, source_fp, out_hash, constraint in (
            ("rr-bad-status", "processing_error", "c" * 64, "d" * 64, "ck_legal_reasoning_runs_status"),
            ("rr-bad-srcfp", "succeeded", "short", "d" * 64, "ck_legal_reasoning_runs_source_fingerprint_len"),
            ("rr-bad-out", "succeeded", "c" * 64, "short", "ck_legal_reasoning_runs_output_hash_len"),
        ):
            session.add(LegalReasoningRun(
                id=run_id, tenant_id="t-iv", case_id="c-iv",
                memory_revision_id="mr-good", source_fingerprint=source_fp,
                provider="deterministic", model_version="rule-evaluator-v1",
                prompt_version="p2.8b-legal-reasoning-1", output_hash=out_hash,
                status=status_value, safe_summary_json={},
            ))
            with pytest.raises(IntegrityError) as exc_info:
                await session.flush()
            assert _violated_constraint(exc_info) == constraint
            await session.rollback()

    async def test_memory_revision_case_tuple_fk_rejects_cross_case_run(self, session):
        await _seed_memory(session, "-fk")
        session.add(Case(
            id="c2-fk", tenant_id="t-fk", owner_user_id="u-fk",
            title="Other", status="active",
        ))
        await session.flush()
        session.add(MemoryRevision(
            id="mr-fk", tenant_id="t-fk", case_id="c-fk", revision_number=1,
            memory_fingerprint="e" * 64, trigger_type="manual_edit",
            change_summary_json={}, created_by="u-fk",
        ))
        await session.flush()
        session.add(LegalReasoningRun(
            id="rr-fk", tenant_id="t-fk", case_id="c2-fk", memory_revision_id="mr-fk",
            source_fingerprint="f" * 64, provider="deterministic",
            model_version="rule-evaluator-v1", prompt_version="p2.8b-legal-reasoning-1",
            output_hash="1" * 64, status="succeeded", safe_summary_json={},
        ))
        with pytest.raises(IntegrityError) as exc_info:
            await session.flush()
        assert _violated_constraint(exc_info) == "fk_legal_reasoning_runs_memory_revision"
        await session.rollback()

    async def test_fingerprints_change_on_fact_and_source_changes(self, session):
        await _seed_memory(session, "-fp")
        await _seed_source_chain(session, "-fp")
        mem1 = await compute_memory_fingerprint(session, tenant_id="t-fp", case_id="c-fp")
        src1 = await compute_case_source_fingerprint(session, tenant_id="t-fp", case_id="c-fp")

        fact = await session.get(CaseFact, "fact-fp")
        fact.value = "Engine fault and gearbox fault after delivery."
        fact.version += 1
        await session.flush()
        mem2 = await compute_memory_fingerprint(session, tenant_id="t-fp", case_id="c-fp")
        assert mem2 != mem1

        paragraph = await session.get(SourceParagraph, "para-fp")
        paragraph.text_hash = "changed-para-hash"
        await session.flush()
        src2 = await compute_case_source_fingerprint(session, tenant_id="t-fp", case_id="c-fp")
        assert src2 != src1

    async def test_output_hash_rejects_hidden_reasoning_keys(self):
        with pytest.raises(ValueError) as exc_info:
            output_hash({"short_rationale": "ok", "chain_of_thought": "hidden"})
        assert "hidden_reasoning_fields_not_allowed" in str(exc_info.value)
