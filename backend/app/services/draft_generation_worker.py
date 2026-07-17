"""P2.9C3A — Leased async draft generation worker (PostgreSQL-backed).

No Celery/Redis/Kafka. A single asyncio background task runs claim→execute→
sleep in a loop under the app's lifespan. Claim uses FOR UPDATE SKIP LOCKED
so at-most-one worker processes any job. Expired leases are recovered on
startup and periodically. The worker reuses the existing synchronous
generation service and its atomic persistence exactly — it only orchestrates
stage/progress updates and the single DeepSeek call through the existing
provider factory.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config import get_settings
from app.db.draft_repository import (
    DraftParagraphIssueLinkRepository,
    DraftParagraphRepository,
    DraftParagraphRevisionRepository,
    DraftParagraphSourceLinkRepository,
    EDITABLE_DRAFT_STATUSES,
)
from app.db.draft_generation_job_repository import DraftGenerationJobRepository
from app.db.models import (
    DRAFT_GEN_JOB_STAGE_PROGRESS,
    DraftDocument,
    DraftGenerationJob,
    new_uuid,
)
from app.db.session import get_sessionmaker
from app.services.draft_generation_input import (
    UnknownSelectionError,
    build_generation_input,
)
from app.services.draft_generation_provider import (
    DraftGenerationError,
    create_configured_draft_generation_provider,
    generation_input_fingerprint,
)
from app.services.draft_readiness import compute_draft_readiness
from app.services.draft_section_plan import build_section_plan
from app.services.source_paragraphs import text_hash as source_text_hash

logger = logging.getLogger(__name__)

_WORKER_ID = uuid.uuid4().hex[:12]
_task: asyncio.Task | None = None
_stopping = False


def _now() -> datetime:
    return datetime.now(UTC)


def progress_for(stage: str) -> int:
    return DRAFT_GEN_JOB_STAGE_PROGRESS.get(stage, 0)


# ── External interface (called from main.py lifespan) ───────────────────────
async def start_worker():
    global _stopping, _task
    settings = get_settings()
    if not settings.draft_generation_job_worker_enabled:
        logger.info("draft_generation_worker disabled_by_config")
        return
    if settings.environment == "test":
        logger.info("draft_generation_worker disabled_in_test_env")
        return
    if _task is not None and not _task.done():
        logger.info("draft_generation_worker already_running")
        return
    await recover_expired_jobs()
    _stopping = False
    _task = asyncio.create_task(
        _worker_loop(settings.draft_generation_job_poll_seconds,
                     settings.draft_generation_job_max_recovery_attempts))
    logger.info("draft_generation_worker started worker_id=%s", _WORKER_ID)


async def stop_worker():
    global _stopping
    _stopping = True
    if _task is not None and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    logger.info("draft_generation_worker stopped worker_id=%s", _WORKER_ID)


# ── Deterministic, injectable helpers (testable without the loop) ───────────
async def recover_expired_jobs(
    *, max_recovery_attempts: int | None = None, clock: callable = _now,
):
    """Return any job whose lease has expired back to 'queued'.

    After ``max_recovery_attempts`` total attempts the job is failed.
    """
    settings = get_settings()
    limit = (settings.draft_generation_job_max_recovery_attempts
             if max_recovery_attempts is None else max_recovery_attempts)
    maker = get_sessionmaker()
    async with maker() as session:
        now = clock()
        expired = list((await session.execute(select(DraftGenerationJob).where(
            DraftGenerationJob.status == "running",
            DraftGenerationJob.lease_expires_at < now,
            DraftGenerationJob.lease_expires_at.is_not(None),
        ))).scalars().all())
        for job in expired:
            if job.attempt_count + 1 > limit:
                job.status = "failed"
                job.stage = "failed"
                job.safe_error_code = "draft_generation_worker_recovery_exhausted"
                job.completed_at = now
            else:
                job.status = "queued"
                job.stage = "queued"
                job.progress_percent = 0
                job.lease_owner = None
                job.lease_expires_at = None
                job.attempt_count += 1
        if expired:
            await session.commit()


async def claim_next_job(
    *, lease_seconds: int | None = None, clock: callable = _now,
):
    """FOR UPDATE SKIP LOCKED: atomically claim one 'queued' job.

    Returns (job, session) or (None, session). The caller MUST commit or
    rollback the session.
    """
    settings = get_settings()
    secs = (settings.draft_generation_job_lease_seconds
            if lease_seconds is None else lease_seconds)
    maker = get_sessionmaker()
    session = maker()
    try:
        result = await session.execute(
            select(DraftGenerationJob)
            .where(DraftGenerationJob.status == "queued")
            .order_by(DraftGenerationJob.queued_at.asc(),
                      DraftGenerationJob.id.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = result.scalar_one_or_none()
        if job is None:
            await session.close()
            return None, None
        now = clock()
        job.status = "running"
        job.stage = "preflight"
        job.progress_percent = progress_for("preflight")
        job.started_at = now
        job.lease_owner = _WORKER_ID
        job.lease_expires_at = now + timedelta(seconds=secs)
        job.attempt_count += 1
        await session.flush()
        # Persist the claim independently so run_one_claimed_job can
        # manage its own transaction without undoing the claim on error.
        await session.commit()
        return job, session
    except Exception:
        await session.rollback()
        await session.close()
        raise


async def run_one_claimed_job(job: DraftGenerationJob, session):

    settings = get_settings()
    _lease = lambda: _now() + timedelta(
        seconds=settings.draft_generation_job_lease_seconds)

    def _stage(name: str):
        job.stage = name
        job.progress_percent = progress_for(name)
        job.lease_expires_at = _lease()

    async def _fail(code: str):
        job.status = 'failed'
        job.stage = 'failed'
        job.progress_percent = 0
        job.safe_error_code = code
        job.completed_at = _now()
        await session.commit()

    try:
        draft = (await session.execute(select(DraftDocument).where(
            DraftDocument.id == job.draft_document_id,
            DraftDocument.tenant_id == job.tenant_id,
            DraftDocument.case_id == job.case_id,
        ))).scalar_one_or_none()
        if draft is None or draft.status not in EDITABLE_DRAFT_STATUSES:
            await _fail('draft_generation_job_not_editable')
            return
        if draft.version != job.requested_draft_version:
            await _fail('draft_generation_job_version_conflict')
            return
        if await DraftParagraphRepository.list_for_draft(
                session, job.tenant_id, draft.id):
            await _fail('draft_generation_job_not_empty')
            return
        readiness = await compute_draft_readiness(
            session, job.tenant_id, job.case_id, draft)
        if readiness.status == 'blocked':
            await _fail('draft_generation_job_readiness_blocked')
            return

        _stage('preparing_input')
        sections = build_section_plan(draft.draft_type,
                                      readiness.active_issue_ids)
        try:
            payload, provenance_context = await build_generation_input(
                session, job.tenant_id, job.case_id, draft, sections,
                readiness.trusted_sources, readiness.active_issue_ids,
                selected_legal_issue_ids=[],
                selected_source_usage_ids=[],
            )
        except UnknownSelectionError as exc:
            await _fail(exc.code)
            return

        _stage('provider_generation')
        try:
            from app.routes.draft_routes import _draft_generation_provider
            provider = _draft_generation_provider()
        except Exception:
            provider = create_configured_draft_generation_provider()
        try:
            result = await provider.generate(payload)
        except DraftGenerationError as exc:
            await session.rollback()
            await _fail(exc.code)
            return

        _stage('validating_output')
        entries = result['paragraphs']
        for entry in entries:
            for ref in entry['source_references']:
                key = (ref['source_record_id'], ref['source_version_id'],
                       ref['source_paragraph_id'])
                ctx = provenance_context.get(key)
                if ctx is None:
                    await session.rollback()
                    await _fail('draft_generation_unknown_source')
                    return
                row = (await session.execute(
                    select(SourceRecord.id, SourceRecord.verification_status)
                    .where(SourceRecord.id == key[0],
                           SourceRecord.current_version_id == key[1],
                           SourceRecord.deleted_at.is_(None))
                )).first()
                if row is None:
                    await session.rollback()
                    await _fail('draft_generation_provenance_mismatch')
                    return
                trust = await _resolve_trust(
                    session, row.id, key[1], row.verification_status)
                if trust not in {'verified_official', 'verified_secondary',
                                  'editor_verified'}:
                    await session.rollback()
                    await _fail('draft_generation_provenance_mismatch')
                    return
                sp = (await session.execute(select(SourceParagraph).where(
                    SourceParagraph.id == key[2],
                    SourceParagraph.source_version_id == key[1],
                ))).scalar_one_or_none()
                if sp is None or (sp.text_hash or '') != ctx.text_hash \
                        or source_text_hash(sp.text or '') != ctx.text_hash:
                    await session.rollback()
                    await _fail('draft_generation_provenance_mismatch')
                    return

        _stage('persisting')
        run_id = new_uuid(); input_fp = generation_input_fingerprint(payload)
        created_paragraphs = []; issue_link_count = 0; source_link_count = 0
        for entry in entries:
            paragraph = await DraftParagraphRepository.create(
                session, tenant_id=job.tenant_id, case_id=job.case_id,
                draft_document_id=draft.id,
                paragraph_order=entry['section_order'],
                paragraph_type=entry['paragraph_type'],
                text=entry['text'], generated_by='ai',
                model_name=provider.model_version,
            )
            paragraph.generation_run_id = run_id
            paragraph.generation_input_fingerprint = input_fp
            created_paragraphs.append(paragraph)
            await DraftParagraphRevisionRepository.create(
                session, tenant_id=job.tenant_id, case_id=job.case_id,
                draft_document_id=draft.id,
                draft_paragraph_id=paragraph.id, revision_number=1,
                base_paragraph_version=paragraph.version,
                text=entry['text'], change_type='initial_generation',
                created_by=job.requested_by_user_id,
            )
            for iid in entry['legal_issue_ids']:
                if await DraftParagraphIssueLinkRepository.active_exists(
                        session, job.tenant_id, job.case_id, paragraph.id, iid):
                    continue
                await DraftParagraphIssueLinkRepository.create(
                    session, tenant_id=job.tenant_id, case_id=job.case_id,
                    draft_paragraph_id=paragraph.id, legal_issue_id=iid,
                    created_by=job.requested_by_user_id)
                issue_link_count += 1
            for ref in entry['source_references']:
                key_tuple = (ref['source_record_id'], ref['source_version_id'],
                             ref['source_paragraph_id'])
                ctx2 = provenance_context[key_tuple]
                if await DraftParagraphSourceLinkRepository.active_exists(
                        session, job.tenant_id, job.case_id,
                        paragraph.id, *key_tuple):
                    continue
                await DraftParagraphSourceLinkRepository.create(
                    session, tenant_id=job.tenant_id, case_id=job.case_id,
                    draft_paragraph_id=paragraph.id,
                    source_record_id=key_tuple[0],
                    source_version_id=key_tuple[1],
                    source_paragraph_id=key_tuple[2],
                    usage_type='citation', quote_hash=ctx2.text_hash,
                    created_by=job.requested_by_user_id,
                    verification_status='verified')
                source_link_count += 1

        draft.version += 1
        metrics = getattr(provider, 'last_metrics', {}) or {}
        job.provider_name = provider.provider_name
        job.model_name = provider.model_version
        job.logical_call_count = int(metrics.get('logical_call_count', 1))
        job.request_attempt_count = int(metrics.get('request_attempt_count', 0))
        job.prompt_tokens = int(metrics.get('prompt_tokens', 0))
        job.completion_tokens = int(metrics.get('completion_tokens', 0))
        job.total_tokens = int(metrics.get('total_tokens', 0))
        job.reasoning_tokens = int(metrics.get('reasoning_tokens', 0))
        job.finish_reasons_json = [str(r) for r in metrics.get('finish_reasons', [])]
        job.result_draft_version = draft.version
        job.status = 'succeeded'
        job.stage = 'completed'
        job.progress_percent = 100
        job.completed_at = _now()
        await session.commit()
        logger.info('draft_generation_worker succeeded job_id=%s draft_id=%s '
                    'paragraph_count=%d provider=%s model=%s',
                    job.id, draft.id, len(created_paragraphs),
                    provider.provider_name, provider.model_version)
    except Exception:
        await session.rollback()
        raise


async def _resolve_trust(session, record_id, version_id, record_status):
    from app.services.source_ingestion_service import resolve_version_verification_status as _r

    return await _r(session, record_id, version_id, record_status)


def _fail_job(job: DraftGenerationJob, code: str):
    job.status = "failed"
    job.stage = "failed"
    job.progress_percent = 0
    job.safe_error_code = code
    job.completed_at = _now()
    logger.warning("draft_generation_worker failed job_id=%s "
                   "safe_error_code=%s", job.id, code)


async def _worker_loop(poll_seconds: int, max_recovery_attempts: int):
    recovery_counter = 0
    while not _stopping:
        session = None
        try:
            job, session = await claim_next_job()
            if job is not None:
                await run_one_claimed_job(job, session)
                await recover_expired_jobs(
                    max_recovery_attempts=max_recovery_attempts)
                recovery_counter = 0
                continue
            recovery_counter += 1
            if recovery_counter >= 6:
                await recover_expired_jobs(
                    max_recovery_attempts=max_recovery_attempts)
                recovery_counter = 0
            await asyncio.sleep(poll_seconds)
        except Exception:
            if session is not None:
                try:
                    await session.rollback()
                except Exception:
                    pass
                try:
                    await session.close()
                except Exception:
                    pass
            await asyncio.sleep(min(poll_seconds * 2, 30))
        finally:
            if session is not None:
                try:
                    await session.close()
                except Exception:
                    pass
