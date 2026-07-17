"""P2.9C3A — Draft generation job repository (PostgreSQL-backend lease-safe).

Worker logic (claim / lease) lives in the worker module; this repository
provides pure query helpers for enqueue and status that the route layer can
use synchronously without any worker knowledge.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DraftGenerationJob


def _now() -> datetime:
    return datetime.now(UTC)


class DraftGenerationJobRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        tenant_id: str,
        case_id: str,
        draft_document_id: str,
        requested_by_user_id: str,
        requested_draft_version: int,
        client_request_id: str,
        request_fingerprint: str,
    ) -> DraftGenerationJob:
        job = DraftGenerationJob(
            tenant_id=tenant_id,
            case_id=case_id,
            draft_document_id=draft_document_id,
            requested_by_user_id=requested_by_user_id,
            requested_draft_version=requested_draft_version,
            client_request_id=client_request_id,
            request_fingerprint=request_fingerprint,
            status="queued",
            stage="queued",
            progress_percent=0,
            attempt_count=0,
            queued_at=_now(),
        )
        session.add(job)
        await session.flush()
        return job

    @staticmethod
    async def get(
        session: AsyncSession, tenant_id: str, case_id: str, draft_id: str,
        job_id: str,
    ) -> DraftGenerationJob | None:
        result = await session.execute(select(DraftGenerationJob).where(
            DraftGenerationJob.id == job_id,
            DraftGenerationJob.tenant_id == tenant_id,
            DraftGenerationJob.case_id == case_id,
            DraftGenerationJob.draft_document_id == draft_id,
        ))
        return result.scalar_one_or_none()

    @staticmethod
    async def find_by_request(
        session: AsyncSession, tenant_id: str, case_id: str,
        draft_document_id: str, client_request_id: str,
    ) -> DraftGenerationJob | None:
        result = await session.execute(select(DraftGenerationJob).where(
            DraftGenerationJob.tenant_id == tenant_id,
            DraftGenerationJob.case_id == case_id,
            DraftGenerationJob.draft_document_id == draft_document_id,
            DraftGenerationJob.client_request_id == client_request_id,
        ))
        return result.scalar_one_or_none()

    @staticmethod
    async def find_active_for_draft(
        session: AsyncSession, tenant_id: str, case_id: str,
        draft_document_id: str,
    ) -> DraftGenerationJob | None:
        result = await session.execute(select(DraftGenerationJob).where(
            DraftGenerationJob.tenant_id == tenant_id,
            DraftGenerationJob.case_id == case_id,
            DraftGenerationJob.draft_document_id == draft_document_id,
            DraftGenerationJob.status.in_(("queued", "running")),
        ))
        return result.scalar_one_or_none()
