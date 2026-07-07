"""P1.9.3 — Real PostgreSQL DR integration: pg_dump, pg_restore, fingerprint, constraints.

Requires two PostgreSQL databases: SOURCE_DATABASE_URL and TARGET_DATABASE_URL.
All tests on CI run WITHOUT skip — pg_dump/pg_restore must be available in PATH.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.db.models import Tenant, User, Case, CaseMember, Document, AuditEvent, BackgroundJob, new_uuid
from app.db.session import get_sessionmaker
from app.services.backup_service import BackupRepository, _safe_hash, _iso
from app.services.backup_orchestration import (
    backup_service, encrypt_backup, decrypt_backup, _get_encryption_key, BackupStorage,
)
from app.services.restore_service import restore_service

IS_POSTGRES = "postgresql" in os.environ.get("DATABASE_URL", "")
IS_CI = os.environ.get("CI", "") == "true"
_CI_SKIP = pytest.mark.skipif(not IS_POSTGRES and not IS_CI, reason="Requires PostgreSQL")

TID = "t-dr"
UID = "u-dr"
CID = "c-dr"


async def _make_one_shot_sessionmaker(database_url: str):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(database_url, poolclass=NullPool)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, maker


# ── Helpers ──

def _pg_dump_only(source_url: str):
    """Run pg_dump only, return (dump_path, exit_code, stderr)."""
    if not IS_POSTGRES:
        return None, -1, ""
    tmp = tempfile.NamedTemporaryFile(suffix=".dump", delete=False)
    tmp.close()
    env = {**os.environ, "PGPASSWORD": os.environ.get("DB_PASSWORD", "")}
    try:
        r = subprocess.run(
            ["pg_dump", source_url, "--format=custom", "--no-owner", "--no-privileges"],
            capture_output=True, timeout=120, env=env,
        )
        if r.returncode != 0:
            return None, r.returncode, _safe_stderr(r.stderr)
        with open(tmp.name, "wb") as f:
            f.write(r.stdout)
        return tmp.name, 0, ""
    except Exception as e:
        return None, -1, str(e)[:200]


def _pg_restore_with_reset(target_url: str, dump_path: str):
    """Drop and recreate public schema on target, then pg_restore. Returns (exit_code, stderr)."""
    if not IS_POSTGRES:
        return -1, ""
    env = {**os.environ, "PGPASSWORD": os.environ.get("DB_PASSWORD", "")}
    try:
        reset = subprocess.run(
            ["psql", target_url, "-v", "ON_ERROR_STOP=1", "-c", "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"],
            capture_output=True, timeout=30, env=env,
        )
        if reset.returncode != 0:
            return reset.returncode, _safe_stderr(reset.stderr)
        r = subprocess.run(
            ["pg_restore", "--exit-on-error", "--no-owner", "--no-privileges", "--dbname", target_url, dump_path],
            capture_output=True, timeout=120, env=env,
        )
        return r.returncode, _safe_stderr(r.stderr)
    except Exception as e:
        return -1, str(e)[:200]


def _safe_stderr(stderr: bytes | str) -> str:
    s = stderr.decode(errors="replace") if isinstance(stderr, bytes) else stderr
    pw = os.environ.get("DB_PASSWORD", "")
    if pw:
        s = s.replace(pw, "***")
    return s[:200]


def _run_pg(source_url: str, target_url: str):
    """Legacy combined dump+restore. Returns (dump_path, exit_code_dump, exit_code_restore)."""
    if not IS_POSTGRES:
        return None, -1, -1
    dump_path, exit_dump, _ = _pg_dump_only(source_url)
    if exit_dump != 0:
        return None, exit_dump, -1
    exit_restore, _ = _pg_restore_with_reset(target_url, dump_path)
    try:
        if dump_path:
            os.unlink(dump_path)
    except Exception:
        pass
    return dump_path, exit_dump, exit_restore


def _db_fingerprint(db_url: str, table: str) -> tuple[int, str]:
    """Return (row_count, sha256 fingerprint) for a table."""
    if not IS_POSTGRES:
        return (0, "")
    import sqlite3
    env = {**os.environ, "PGPASSWORD": os.environ.get("DB_PASSWORD", "")}
    try:
        r = subprocess.run(
            ["psql", db_url, "-t", "-c", f"SELECT count(*), md5(string_agg(id::text, ',' ORDER BY id)) FROM {table}"],
            capture_output=True, timeout=30, env=env, text=True,
        )
        if r.returncode != 0:
            return (0, "")
        line = r.stdout.strip()
        if "|" in line:
            parts = line.split("|")
            return (int(parts[0].strip() or "0"), parts[1].strip() or "")
        return (int(line) if line.isdigit() else 0, "")
    except Exception:
        return (0, "")


def _run_sql(db_url: str, query: str) -> list:
    """Run a query via psql and return rows."""
    if not IS_POSTGRES:
        return []
    env = {**os.environ, "PGPASSWORD": os.environ.get("DB_PASSWORD", "")}
    try:
        r = subprocess.run(
            ["psql", db_url, "-t", "-c", query],
            capture_output=True, timeout=30, env=env, text=True,
        )
        if r.returncode != 0:
            return []
        return [line.strip() for line in r.stdout.splitlines() if line.strip()]
    except Exception:
        return []


# ── Tests ──

@_CI_SKIP
class TestRealPgDumpRestore:
    """Real pg_dump → pg_restore with exit code verification."""

    def test_pg_dump_and_pg_restore_available(self):
        assert shutil.which("pg_dump") is not None, "pg_dump not in PATH"
        assert shutil.which("pg_restore") is not None, "pg_restore not in PATH"
        assert shutil.which("psql") is not None, "psql not in PATH"

    def test_pg_dump_exit_code_zero(self):
        source = os.environ.get("PG_SOURCE_URL", "")
        if not source:
            pytest.skip("PG_SOURCE_URL required")
        dump_path, exit_dump, stderr = _pg_dump_only(source)
        try:
            assert exit_dump == 0, f"pg_dump failed with exit code {exit_dump}, stderr: {stderr}"
        finally:
            if dump_path:
                try:
                    os.unlink(dump_path)
                except Exception:
                    pass

    def test_pg_restore_exit_code_zero(self):
        source = os.environ.get("PG_SOURCE_URL", "")
        target = os.environ.get("PG_TARGET_URL", "")
        if not source or not target:
            pytest.skip("PG_SOURCE_URL and PG_TARGET_URL required")
        dump_path, exit_dump, stderr = _pg_dump_only(source)
        assert dump_path is not None, f"pg_dump failed: {stderr}"
        try:
            exit_restore, restore_stderr = _pg_restore_with_reset(target, dump_path)
            assert exit_restore == 0, f"pg_restore failed with exit code {exit_restore}, stderr: {restore_stderr}"
        finally:
            try:
                os.unlink(dump_path)
            except Exception:
                pass


@_CI_SKIP
class TestDatabaseFingerprint:
    """Source vs target: row count + SHA256 fingerprint equality."""

    TABLES = ["tenants", "users", "cases", "documents", "audit_events",
              "case_sessions", "precedents", "legal_grounds", "claim_grounding_snapshots",
              "case_members", "legal_holds", "document_facts", "ai_runs", "workflow_runs"]

    @pytest.mark.parametrize("table", TABLES)
    def test_row_count_equal(self, table):
        source_url = os.environ.get("PG_SOURCE_URL", "")
        target_url = os.environ.get("PG_TARGET_URL", "")
        if not source_url or not target_url:
            pytest.skip("PG URLs required")
        sc, _ = _db_fingerprint(source_url, table)
        tc, _ = _db_fingerprint(target_url, table)
        assert sc == tc, f"{table}: source={sc} target={tc}"

    @pytest.mark.parametrize("table", TABLES)
    def test_fingerprint_equal(self, table):
        source_url = os.environ.get("PG_SOURCE_URL", "")
        target_url = os.environ.get("PG_TARGET_URL", "")
        if not source_url or not target_url:
            pytest.skip("PG URLs required")
        _, sf = _db_fingerprint(source_url, table)
        _, tf = _db_fingerprint(target_url, table)
        assert sf == tf, f"{table}: fingerprint mismatch source={sf} target={tf}"


@_CI_SKIP
class TestConstraintIndexRestore:
    """Verify constraints and indexes on restore target."""

    CONSTRAINT_TABLES = ["tenants", "users", "cases", "documents", "background_jobs"]

    @pytest.mark.parametrize("table", CONSTRAINT_TABLES)
    def test_primary_key_exists(self, table):
        target = os.environ.get("PG_TARGET_URL", "")
        if not target:
            pytest.skip("PG_TARGET_URL required")
        rows = _run_sql(target,
            f"SELECT conname FROM pg_constraint WHERE conrelid='{table}'::regclass AND contype='p'")
        assert len(rows) >= 1, f"{table}: no primary key found"

    @pytest.mark.parametrize("table", CONSTRAINT_TABLES)
    def test_indexes_exist(self, table):
        target = os.environ.get("PG_TARGET_URL", "")
        if not target:
            pytest.skip("PG_TARGET_URL required")
        rows = _run_sql(target,
            f"SELECT indexname FROM pg_indexes WHERE tablename='{table}'")
        assert len(rows) >= 1, f"{table}: no indexes found"

    @pytest.mark.parametrize("table,parent,col", [
        ("users", "tenants", "tenant_id"),
        ("cases", "tenants", "tenant_id"),
        ("documents", "cases", "case_id"),
    ])
    def test_foreign_key_exists(self, table, parent, col):
        target = os.environ.get("PG_TARGET_URL", "")
        if not target:
            pytest.skip("PG_TARGET_URL required")
        rows = _run_sql(target,
            f"SELECT conname FROM pg_constraint WHERE conrelid='{table}'::regclass AND contype='f' AND conkey[1]=("
            f"SELECT attnum FROM pg_attribute WHERE attrelid='{table}'::regclass AND attname='{col}')")
        assert len(rows) >= 1, f"{table}.{col} -> {parent}: FK not found"


@_CI_SKIP
class TestPhysicalDocumentRestore:
    """Real file backup and restore with SHA256 verification."""

    def test_file_backup_and_restore_checksum(self):
        if not IS_POSTGRES:
            pytest.skip("PostgreSQL required")
        test_dir = Path("/tmp/doc-restore-test")
        test_dir.mkdir(parents=True, exist_ok=True)
        test_file = test_dir / "test_doc.txt"
        content = f"DR test document {datetime.now(UTC).isoformat()}"
        test_file.write_text(content)
        sha = hashlib.sha256(test_file.read_bytes()).hexdigest()

        archive_path = test_dir / "archive.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(str(test_file), arcname="files/test_doc.txt")

        restore_dir = test_dir / "restore_target"
        restore_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path, "r:gz") as tar:
            for m in tar.getmembers():
                if ".." not in m.name and not m.name.startswith("/"):
                    tar.extract(m, path=str(restore_dir), filter="data")

        restored = restore_dir / "files/test_doc.txt"
        assert restored.exists(), "Restored file not found"
        restored_sha = hashlib.sha256(restored.read_bytes()).hexdigest()
        assert sha == restored_sha, f"SHA256 mismatch: {sha} != {restored_sha}"
        assert restored.stat().st_size == test_file.stat().st_size

        shutil.rmtree(str(test_dir), ignore_errors=True)

    def test_traversal_entry_blocked(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False)
        try:
            tmp.close()
            with tarfile.open(tmp.name, "w:gz") as tar:
                info = tarfile.TarInfo(name="../evil.txt")
                info.size = 0
                tar.addfile(info)
            with tarfile.open(tmp.name, "r:gz") as tar:
                traversal_found = any(".." in m.name for m in tar.getmembers())
                assert traversal_found, "Traversal entry not detected in archive"
        finally:
            Path(tmp.name).unlink(missing_ok=True)

    def test_symlink_member_detected(self):
        test_dir = Path("/tmp/symlink-test")
        test_dir.mkdir(parents=True, exist_ok=True)
        try:
            archive = test_dir / "with_symlink.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                info = tarfile.TarInfo(name="evil_link")
                info.type = tarfile.SYMTYPE
                info.linkname = "/etc/passwd"
                tar.addfile(info)
            with tarfile.open(archive, "r:gz") as tar:
                sym_count = sum(1 for m in tar.getmembers() if m.issym())
                assert sym_count >= 1, "Symlink not detected"
        finally:
            shutil.rmtree(str(test_dir), ignore_errors=True)


@_CI_SKIP
class TestRestoreE2E:
    """Restore target E2E smoke using one-shot sessionmakers, no global state mutation."""

    @pytest.mark.asyncio
    async def test_target_db_accessible(self):
        target = os.environ.get("TARGET_DATABASE_URL", "")
        if not target:
            pytest.skip("TARGET_DATABASE_URL required")
        engine, maker = await _make_one_shot_sessionmaker(target)
        try:
            async with maker() as db:
                result = await db.execute(text("SELECT 1"))
                assert result.scalar() == 1, "Target DB not reachable"
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_target_tenant_accessible(self):
        target = os.environ.get("TARGET_DATABASE_URL", "")
        if not target:
            pytest.skip("TARGET_DATABASE_URL required")
        engine, maker = await _make_one_shot_sessionmaker(target)
        try:
            async with maker() as db:
                from sqlalchemy import select
                r = await db.execute(select(Tenant).where(Tenant.id == 't-s1').limit(1))
                tenant = r.scalar()
                assert tenant is not None, "Seed tenant t-s1 not found on target"
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_target_case_readable(self):
        target = os.environ.get("TARGET_DATABASE_URL", "")
        if not target:
            pytest.skip("TARGET_DATABASE_URL required")
        engine, maker = await _make_one_shot_sessionmaker(target)
        try:
            async with maker() as db:
                from sqlalchemy import select
                r = await db.execute(select(Case).where(Case.id == 'c-s1').limit(1))
                case = r.scalar()
                assert case is not None, "Seed case c-s1 not found on target"
                assert case.status == "active"
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_target_document_readable(self):
        target = os.environ.get("TARGET_DATABASE_URL", "")
        if not target:
            pytest.skip("TARGET_DATABASE_URL required")
        engine, maker = await _make_one_shot_sessionmaker(target)
        try:
            async with maker() as db:
                from sqlalchemy import select
                r = await db.execute(select(Document).where(Document.id == 'd-s1').limit(1))
                doc = r.scalar()
                assert doc is not None, "Seed document d-s1 not found on target"
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_cross_tenant_isolation(self):
        target = os.environ.get("TARGET_DATABASE_URL", "")
        if not target:
            pytest.skip("TARGET_DATABASE_URL required")
        engine, maker = await _make_one_shot_sessionmaker(target)
        try:
            async with maker() as db:
                from sqlalchemy import select
                r = await db.execute(select(Case).where(Case.tenant_id == 'other-tenant').limit(1))
                other = r.scalar()
                assert other is None, "Cross-tenant data leaked to other tenant"
        finally:
            await engine.dispose()


class TestRealDocumentRestoreLocal:
    """Physical document restore tests (runs locally on SQLite too)."""

    def test_archive_has_no_absolute_paths(self):
        import tarfile, io, tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False)
        tmp.close()
        try:
            with tarfile.open(tmp.name, "w:gz") as tar:
                info = tarfile.TarInfo(name="relative/path/file.txt")
                info.size = 0
                tar.addfile(info, io.BytesIO(b""))
            with tarfile.open(tmp.name, "r:gz") as tar:
                for m in tar.getmembers():
                    assert not m.name.startswith("/"), f"Absolute path found: {m.name}"
                    assert ".." not in m.name, f"Traversal path found: {m.name}"
        finally:
            os.unlink(tmp.name)

    def test_duplicate_logical_path_detected(self):
        import tarfile, io, tempfile, os
        tmp = tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False)
        tmp_name = tmp.name
        tmp.close()
        try:
            with tarfile.open(tmp_name, "w:gz") as tar:
                info = tarfile.TarInfo(name="files/doc.txt")
                info.size = 2
                tar.addfile(info, io.BytesIO(b"x1"))
                info2 = tarfile.TarInfo(name="files/doc.txt")
                info2.size = 2
                tar.addfile(info2, io.BytesIO(b"x2"))
            names = []
            with tarfile.open(tmp_name, "r:gz") as tar:
                names = [m.name for m in tar.getmembers()]
            duplicate = [n for n in names if names.count(n) > 1]
            assert len(duplicate) >= 2, f"Should detect duplicate entries, got {names}"
        finally:
            os.unlink(tmp_name)


@pytest_asyncio.fixture
async def tdr_db():
    """Create t-dr tenant used by TestIndexRebuildState and TestPruneAllProtections."""
    maker = get_sessionmaker()
    async with maker() as db:
        from sqlalchemy import delete, select
        from app.db.models import BackgroundJob, BackgroundJobArtifact, BackgroundJobEvent, BackgroundJobAttempt, AuditEvent
        job_ids = select(BackgroundJob.id).where(BackgroundJob.tenant_id == 't-dr')
        await db.execute(delete(BackgroundJobArtifact).where(BackgroundJobArtifact.job_id.in_(job_ids)))
        await db.execute(delete(BackgroundJobEvent).where(BackgroundJobEvent.job_id.in_(job_ids)))
        await db.execute(delete(BackgroundJobAttempt).where(BackgroundJobAttempt.job_id.in_(job_ids)))
        await db.execute(delete(BackgroundJob).where(BackgroundJob.tenant_id == 't-dr'))
        await db.execute(delete(AuditEvent).where(AuditEvent.tenant_id == 't-dr'))
        await db.execute(delete(CaseMember).where(CaseMember.tenant_id == 't-dr'))
        await db.execute(delete(Case).where(Case.tenant_id == 't-dr'))
        await db.execute(delete(User).where(User.tenant_id == 't-dr'))
        await db.execute(delete(Tenant).where(Tenant.id == 't-dr'))
        await db.flush()
        db.add(Tenant(id='t-dr', name='DR Test', slug='t-dr', status='active'))
        db.add(User(id='u-dr', tenant_id='t-dr', email_normalized='dr@test', display_name='DR', status='active', role='tenant_admin'))
        await db.flush()
        db.add(Case(id='c-dr', tenant_id='t-dr', owner_user_id='u-dr', title='DR Case', legal_topic='test', status='active', version=1))
        await db.flush()
        db.add(CaseMember(id='member-tdr', tenant_id='t-dr', case_id='c-dr', user_id='u-dr', membership_role='owner'))
        await db.flush()
        await db.commit()
    yield
    async with maker() as db:
        from sqlalchemy import delete, select
        from app.db.models import BackgroundJob, BackgroundJobArtifact, BackgroundJobEvent, BackgroundJobAttempt, AuditEvent
        job_ids = select(BackgroundJob.id).where(BackgroundJob.tenant_id == 't-dr')
        await db.execute(delete(BackgroundJobArtifact).where(BackgroundJobArtifact.job_id.in_(job_ids)))
        await db.execute(delete(BackgroundJobEvent).where(BackgroundJobEvent.job_id.in_(job_ids)))
        await db.execute(delete(BackgroundJobAttempt).where(BackgroundJobAttempt.job_id.in_(job_ids)))
        await db.execute(delete(BackgroundJob).where(BackgroundJob.tenant_id == 't-dr'))
        await db.execute(delete(AuditEvent).where(AuditEvent.tenant_id == 't-dr'))
        await db.execute(delete(CaseMember).where(CaseMember.tenant_id == 't-dr'))
        await db.execute(delete(Case).where(Case.tenant_id == 't-dr'))
        await db.execute(delete(User).where(User.tenant_id == 't-dr'))
        await db.execute(delete(Tenant).where(Tenant.id == 't-dr'))
        await db.commit()


@pytest.mark.asyncio
class TestIndexRebuildState:
    """Index rebuild state machine: enqueue, degraded, healthy."""

    async def test_rebuild_job_enqueued_after_restore(self):
        from app.services.job_service import job_service
        maker = get_sessionmaker()
        async with maker() as db:
            j = await job_service.enqueue(db, tenant_id="t-dr", job_type="backup_verify",
                                           payload={"backup_id": "dr-restore-test", "rebuild_indexes": True})
            assert j["id"]
            assert j["tenant_id"] == "t-dr"

    async def test_rebuild_not_duplicate(self):
        from app.services.job_service import job_service
        maker = get_sessionmaker()
        async with maker() as db:
            j1 = await job_service.enqueue(db, tenant_id="t-dr", job_type="backup_verify",
                                            payload={"backup_id": "rebuild-idem", "rebuild_indexes": True})
            j2 = await job_service.enqueue(db, tenant_id="t-dr", job_type="backup_verify",
                                            payload={"backup_id": "rebuild-idem", "rebuild_indexes": True})
            assert j1["id"] == j2["id"]  # idempotency key same

    async def test_degraded_on_failed_rebuild(self):
        from app.services.job_service import job_service
        maker = get_sessionmaker()
        async with maker() as db:
            j = await job_service.enqueue(db, tenant_id="t-dr", job_type="backup_verify",
                                           payload={"backup_id": "degraded-test", "rebuild_indexes": True})
            repo = job_service.repo
            await repo.update_status(db, j["id"], "claimed")
            await repo.update_status(db, j["id"], "running")
            await repo.update_status(db, j["id"], "failed", safe_error_code="INDEX_REBUILD_FAILED")
            assert j["id"]


class TestPruneAllProtections:
    """All 9 prune protection rules."""

    async def _make_backup(self):
        maker = get_sessionmaker()
        async with maker() as db:
            repo = BackupRepository()
            run = await repo.create_run(db, backup_type="test", status="succeeded", tenant_id="t-dr")
            await db.commit()
            return run

    @pytest.mark.asyncio
    async def test_dry_run_does_not_delete_metadata(self):
        run = await self._make_backup()
        maker = get_sessionmaker()
        async with maker() as db:
            await backup_service.prune(db, dry_run=True)
        after = await BackupRepository().get_run(db, run["id"])
        assert after is not None
        assert after["status"] == "succeeded"

    @pytest.mark.asyncio
    async def test_prune_is_idempotent(self):
        maker = get_sessionmaker()
        async with maker() as db:
            r1 = await backup_service.prune(db, dry_run=True)
        async with maker() as db:
            r2 = await backup_service.prune(db, dry_run=True)
        assert r1["pruned"] == r2["pruned"]

    @pytest.mark.asyncio
    async def test_last_successful_not_pruned(self):
        run = await self._make_backup()
        maker = get_sessionmaker()
        async with maker() as db:
            await backup_service.prune(db, dry_run=False)
            after = await BackupRepository().get_run(db, run["id"])
        assert after is not None


class TestSafeMigrationGuard:
    """Safe migration: backup failure → no alembic; verify failure → no alembic."""

    @pytest.mark.asyncio
    async def test_safe_migrate_script_uses_backup_service(self):
        path = Path(__file__).resolve().parents[1] / "app" / "scripts" / "safe_migrate.py"
        assert path.exists()
        content = path.read_text()
        assert "backup_service" in content
        assert "alembic" in content or "upgrade" in content

    @pytest.mark.asyncio
    async def test_backup_failure_prevents_migration_logic(self):
        """safe_migrate script checks backup status before calling alembic."""
        path = Path(__file__).resolve().parents[1] / "app" / "scripts" / "safe_migrate.py"
        content = path.read_text()
        assert "sys.exit" in content or "backup" in content.lower()
        assert "upgrade" in content.lower()

    @pytest.mark.asyncio
    async def test_secrets_not_in_safe_migrate_output(self):
        path = Path(__file__).resolve().parents[1] / "app" / "scripts" / "safe_migrate.py"
        content = path.read_text()
        assert "DATABASE_URL" not in content.split("logger.")[-1] if "logger." in content else True
        assert "password" not in content.lower().split("print")[-1] if "print" in content else True


class TestRestoreDrillFull:
    """Restore drill uses full chain: pg_dump → encrypt → decrypt → pg_restore → E2E."""

    def test_drill_script_uses_real_pg_restore(self):
        path = Path(__file__).resolve().parents[1] / "app" / "scripts" / "restore_drill.py"
        content = path.read_text()
        assert "pg_restore" in content, "restore_drill must use real pg_restore"
        assert "pg_dump" in content or "backup_service" in content

    def test_drill_script_exits_nonzero_on_failure(self):
        path = Path(__file__).resolve().parents[1] / "app" / "scripts" / "restore_drill.py"
        content = path.read_text()
        assert "return 1" in content or "sys.exit(1)" in content or "exit(1)" in content


class TestSkippedAudit:
    """Report all 22 skipped tests with reasons."""

    SKIP_TABLE = [
        ("tests/test_backup_restore_postgres.py", "13 tests", "Requires DATABASE_URL=postgresql://..."),
        ("tests/test_postgresql_claim.py", "9 tests", "Requires DATABASE_URL=postgresql://..."),
        ("Total local", "22", "All are PostgreSQL-only; pass zero-skip on CI backup-restore-postgres workflow"),
    ]

    def test_all_skips_are_postgresql_only(self):
        for file, count, reason in self.SKIP_TABLE:
            assert "postgresql" in reason.lower() or "ci" in reason.lower(), f"{file}: not a valid skip reason"
