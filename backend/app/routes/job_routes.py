"""P1.8 — Background job API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.session import get_session, get_sessionmaker
from app.services.auth_service import SecurityContext, require_authenticated
from app.services.job_service import job_service, KNOWN_JOB_TYPES
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/jobs", tags=["Arka Plan Görevleri"])


class JobEnqueueRequest(BaseModel):
    job_type: str = Field(min_length=1, max_length=50)
    payload: dict = Field(default_factory=dict)
    case_id: str | None = None
    priority: int = Field(default=0, ge=-100, le=100)


@router.post("", status_code=202)
async def enqueue_job(
    body: JobEnqueueRequest,
    ctx: SecurityContext = Depends(require_authenticated),
    db: AsyncSession = Depends(get_session),
):
    try:
        job = await job_service.enqueue(
            db,
            tenant_id=ctx.tenant_id,
            job_type=body.job_type,
            payload=body.payload,
            case_id=body.case_id,
            created_by=ctx.actor_id,
            priority=body.priority,
        )
        return job
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("")
async def list_jobs(
    case_id: str = Query(""),
    status: str = Query(""),
    job_type: str = Query(""),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: SecurityContext = Depends(require_authenticated),
    db: AsyncSession = Depends(get_session),
):
    return await job_service.list(
        db, tenant_id=ctx.tenant_id, case_id=case_id, status=status, job_type=job_type,
        limit=limit, offset=offset,
    )


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    ctx: SecurityContext = Depends(require_authenticated),
    db: AsyncSession = Depends(get_session),
):
    job = await job_service.get(db, tenant_id=ctx.tenant_id, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/events")
async def get_events(
    job_id: str,
    since: int = Query(0, ge=0),
    ctx: SecurityContext = Depends(require_authenticated),
    db: AsyncSession = Depends(get_session),
):
    try:
        return await job_service.events(db, tenant_id=ctx.tenant_id, job_id=job_id, since=since)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    ctx: SecurityContext = Depends(require_authenticated),
    db: AsyncSession = Depends(get_session),
):
    try:
        return await job_service.cancel(db, tenant_id=ctx.tenant_id, job_id=job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/{job_id}/retry")
async def retry_job(
    job_id: str,
    ctx: SecurityContext = Depends(require_authenticated),
    db: AsyncSession = Depends(get_session),
):
    try:
        return await job_service.retry(db, tenant_id=ctx.tenant_id, job_id=job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job not found")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/{job_id}/artifacts")
async def get_artifacts(
    job_id: str,
    ctx: SecurityContext = Depends(require_authenticated),
    db: AsyncSession = Depends(get_session),
):
    try:
        return await job_service.artifacts(db, tenant_id=ctx.tenant_id, job_id=job_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/types")
async def list_job_types():
    return {"job_types": sorted(KNOWN_JOB_TYPES)}
