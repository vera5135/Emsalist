"""P2.6C — Persistence for controlled official-provider ingestion runs/items.

Stores controlled operational and traceability metadata, bounded durable
non-query run parameters, counters, hashes, provider external identifiers,
canonical source/version references, statuses, outcomes, and safe error codes.
It never stores raw fetched source content or raw provider search query text.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SourceIngestionItem, SourceIngestionRun

RUN_QUEUED = "queued"
RUN_RUNNING = "running"
RUN_COMPLETED = "completed"
RUN_COMPLETED_WITH_ERRORS = "completed_with_errors"
RUN_FAILED = "failed"
RUN_CANCELLED = "cancelled"

RUN_STATUSES = frozenset({
    RUN_QUEUED, RUN_RUNNING, RUN_COMPLETED,
    RUN_COMPLETED_WITH_ERRORS, RUN_FAILED, RUN_CANCELLED,
})

TERMINAL_RUN_STATUSES = frozenset({
    RUN_COMPLETED, RUN_COMPLETED_WITH_ERRORS, RUN_FAILED, RUN_CANCELLED,
})


def _now() -> datetime:
    return datetime.now(UTC)


class SourceIngestionRunRepository:
    @staticmethod
    async def create(
        session: AsyncSession, *, provider_code: str, run_type: str,
        created_by: str | None = None, cursor: dict | None = None,
    ) -> SourceIngestionRun:
        run = SourceIngestionRun(
            provider_code=provider_code, run_type=run_type,
            status=RUN_QUEUED, cursor_json=cursor or {}, created_by=created_by,
        )
        session.add(run)
        await session.flush()
        return run

    @staticmethod
    async def get(session: AsyncSession, run_id: str) -> SourceIngestionRun | None:
        return await session.get(SourceIngestionRun, run_id)

    @staticmethod
    async def list(
        session: AsyncSession, *, provider_code: str = "", status: str = "",
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[SourceIngestionRun], int]:
        from sqlalchemy import func

        stmt = select(SourceIngestionRun)
        count_stmt = select(func.count()).select_from(SourceIngestionRun)
        if provider_code:
            stmt = stmt.where(SourceIngestionRun.provider_code == provider_code)
            count_stmt = count_stmt.where(SourceIngestionRun.provider_code == provider_code)
        if status:
            stmt = stmt.where(SourceIngestionRun.status == status)
            count_stmt = count_stmt.where(SourceIngestionRun.status == status)
        total = (await session.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(SourceIngestionRun.created_at.desc()).limit(limit).offset(offset)
        rows = list((await session.execute(stmt)).scalars().all())
        return rows, int(total)

    @staticmethod
    async def latest_run_for_provider(
        session: AsyncSession, provider_code: str,
    ) -> SourceIngestionRun | None:
        stmt = (
            select(SourceIngestionRun)
            .where(SourceIngestionRun.provider_code == provider_code)
            .order_by(SourceIngestionRun.created_at.desc())
            .limit(1)
        )
        return (await session.execute(stmt)).scalars().first()

    @staticmethod
    async def latest_terminal_run_for_provider(
        session: AsyncSession, provider_code: str,
    ) -> SourceIngestionRun | None:
        stmt = (
            select(SourceIngestionRun)
            .where(
                SourceIngestionRun.provider_code == provider_code,
                SourceIngestionRun.status.in_(TERMINAL_RUN_STATUSES),
            )
            .order_by(SourceIngestionRun.created_at.desc())
            .limit(1)
        )
        return (await session.execute(stmt)).scalars().first()

    @staticmethod
    async def latest_successful_run_for_provider(
        session: AsyncSession, provider_code: str,
    ) -> SourceIngestionRun | None:
        successful_work = or_(
            SourceIngestionRun.discovered_count > 0,
            SourceIngestionRun.fetched_count > 0,
            SourceIngestionRun.ingested_count > 0,
            SourceIngestionRun.duplicate_count > 0,
            SourceIngestionRun.new_version_count > 0,
        )
        stmt = (
            select(SourceIngestionRun)
            .where(
                SourceIngestionRun.provider_code == provider_code,
                SourceIngestionRun.status.in_((RUN_COMPLETED, RUN_COMPLETED_WITH_ERRORS)),
                successful_work,
            )
            .order_by(SourceIngestionRun.created_at.desc())
            .limit(1)
        )
        return (await session.execute(stmt)).scalars().first()

    @staticmethod
    async def mark_running(session: AsyncSession, run: SourceIngestionRun) -> None:
        run.status = RUN_RUNNING
        run.started_at = _now()
        await session.flush()

    @staticmethod
    async def finalize(
        session: AsyncSession, run: SourceIngestionRun, *, status: str,
        cursor: dict | None = None, last_safe_error_code: str = "",
    ) -> None:
        run.status = status
        run.completed_at = _now()
        if cursor is not None:
            run.cursor_json = cursor
        if last_safe_error_code:
            run.last_safe_error_code = last_safe_error_code
        await session.flush()

    @staticmethod
    async def cancel(session: AsyncSession, run: SourceIngestionRun) -> bool:
        if run.status in TERMINAL_RUN_STATUSES:
            return False
        run.status = RUN_CANCELLED
        run.completed_at = _now()
        await session.flush()
        return True


class SourceIngestionItemRepository:
    @staticmethod
    async def find_by_dedupe(
        session: AsyncSession, provider_code: str, dedupe_key: str
    ) -> SourceIngestionItem | None:
        stmt = select(SourceIngestionItem).where(
            SourceIngestionItem.provider_code == provider_code,
            SourceIngestionItem.dedupe_key == dedupe_key,
        ).limit(1)
        return (await session.execute(stmt)).scalars().first()

    @staticmethod
    async def create(
        session: AsyncSession, *, run_id: str, provider_code: str,
        external_id: str | None, candidate_url_hash: str, dedupe_key: str,
        status: str = "discovered",
    ) -> SourceIngestionItem:
        item = SourceIngestionItem(
            run_id=run_id, provider_code=provider_code, external_id=external_id,
            candidate_url_hash=candidate_url_hash, dedupe_key=dedupe_key, status=status,
        )
        session.add(item)
        await session.flush()
        return item

    @staticmethod
    async def complete(
        session: AsyncSession, item: SourceIngestionItem, *, status: str,
        source_record_id: str | None = None, source_version_id: str | None = None,
        outcome: str | None = None, safe_error_code: str = "",
    ) -> None:
        item.status = status
        item.source_record_id = source_record_id
        item.source_version_id = source_version_id
        item.outcome = outcome
        item.safe_error_code = safe_error_code
        item.completed_at = _now()
        await session.flush()

    @staticmethod
    async def list_for_run(session: AsyncSession, run_id: str) -> list[SourceIngestionItem]:
        stmt = select(SourceIngestionItem).where(
            SourceIngestionItem.run_id == run_id
        ).order_by(SourceIngestionItem.created_at.asc())
        return list((await session.execute(stmt)).scalars().all())
