"""P1.6 — Lifecycle and retention API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.services.auth_service import SecurityContext, resolve_current_user
from app.services.lifecycle_service import lifecycle_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lifecycle", tags=["Lifecycle"])


@router.delete("/cases/{case_id}")
async def delete_case(case_id: str, ctx: SecurityContext = Depends(resolve_current_user)) -> dict:
    result = lifecycle_service.soft_delete_case(case_id, ctx.tenant_id, ctx.actor_id)
    if "error" in result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.post("/cases/{case_id}/restore")
async def restore_case(case_id: str, ctx: SecurityContext = Depends(resolve_current_user)) -> dict:
    result = lifecycle_service.restore_case(case_id, ctx.tenant_id, ctx.actor_id)
    if "error" in result:
        code = status.HTTP_400_BAD_REQUEST if result["error"] == "restore_deadline_passed" else status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=code, detail=result["error"])
    return result


@router.get("/purge/preview")
async def purge_preview(ctx: SecurityContext = Depends(resolve_current_user)) -> dict:
    return lifecycle_service.run_purge(tenant_id=ctx.tenant_id, dry_run=True, batch=50)


@router.post("/purge/run")
async def purge_run(ctx: SecurityContext = Depends(resolve_current_user)) -> dict:
    return lifecycle_service.run_purge(tenant_id=ctx.tenant_id, dry_run=False, batch=50)
