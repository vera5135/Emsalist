"""P1.6.1 — Full lifecycle and retention API endpoints."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.services.auth_service import SecurityContext, require_authenticated
from app.services.lifecycle_service import lifecycle_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lifecycle", tags=["Lifecycle"])


def _check_owner_or_admin(ctx: SecurityContext) -> SecurityContext:
    return ctx


# ── case soft delete ───────────────────────────────────────────────────

@router.delete("/cases/{case_id}")
async def delete_case(
    case_id: str,
    reason_code: str = Query("", description="Deletion reason code"),
    ctx: SecurityContext = Depends(require_authenticated),
) -> dict:
    result = lifecycle_service.soft_delete_case(
        case_id, ctx.tenant_id, ctx.actor_id, ctx.role, reason_code,
    )
    if result.get("error") == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if result.get("error") == "forbidden":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return result


@router.delete("/cases/{case_id}/version/{expected_version}")
async def delete_case_versioned(
    case_id: str,
    expected_version: int,
    reason_code: str = Query(""),
    ctx: SecurityContext = Depends(require_authenticated),
) -> dict:
    result = lifecycle_service.soft_delete_case_with_version(
        case_id, ctx.tenant_id, ctx.actor_id, ctx.role, expected_version, reason_code,
    )
    if result.get("error") == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if result.get("error") == "forbidden":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    if result.get("error") == "version_conflict":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version conflict: expected {expected_version}, current {result.get('current')}",
        )
    return result


# ── case restore ───────────────────────────────────────────────────────

@router.post("/cases/{case_id}/restore")
async def restore_case(
    case_id: str,
    ctx: SecurityContext = Depends(require_authenticated),
) -> dict:
    result = lifecycle_service.restore_case(case_id, ctx.tenant_id, ctx.actor_id, ctx.role)
    if result.get("error") == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if result.get("error") == "forbidden":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    if result.get("error") == "not_deleted":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Case is not deleted")
    if result.get("error") == "restore_deadline_passed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Restore deadline has passed")
    return result


# ── deleted case listing ───────────────────────────────────────────────

@router.get("/cases/deleted")
async def list_deleted_cases(
    ctx: SecurityContext = Depends(require_authenticated),
) -> list[dict]:
    return lifecycle_service.list_deleted_cases(ctx.tenant_id, ctx.actor_id, ctx.role)


# ── document soft delete ───────────────────────────────────────────────

@router.delete("/cases/{case_id}/documents/{document_id}")
async def delete_document(
    case_id: str,
    document_id: str,
    ctx: SecurityContext = Depends(require_authenticated),
) -> dict:
    result = lifecycle_service.soft_delete_document(
        case_id, document_id, ctx.tenant_id, ctx.actor_id, ctx.role,
    )
    if result.get("error") == "case_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if result.get("error") == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if result.get("error") == "forbidden":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return result


# ── document restore ───────────────────────────────────────────────────

@router.post("/cases/{case_id}/documents/{document_id}/restore")
async def restore_document(
    case_id: str,
    document_id: str,
    ctx: SecurityContext = Depends(require_authenticated),
) -> dict:
    result = lifecycle_service.restore_document(
        case_id, document_id, ctx.tenant_id, ctx.actor_id, ctx.role,
    )
    if result.get("error") == "case_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if result.get("error") == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if result.get("error") == "forbidden":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    if result.get("error") == "case_deleted_or_purged":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Cannot restore document: parent case is deleted or purged")
    if result.get("error") == "restore_deadline_passed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Restore deadline has passed")
    return result


# ── deleted document listing ───────────────────────────────────────────

@router.get("/cases/{case_id}/documents/deleted")
async def list_deleted_documents(
    case_id: str,
    ctx: SecurityContext = Depends(require_authenticated),
) -> list[dict]:
    return lifecycle_service.list_deleted_documents(
        case_id, ctx.tenant_id, ctx.actor_id, ctx.role,
    )


# ── legal hold ─────────────────────────────────────────────────────────

@router.post("/cases/{case_id}/legal-hold")
async def create_legal_hold(
    case_id: str,
    body: dict,
    ctx: SecurityContext = Depends(require_authenticated),
) -> dict:
    reason_code = str(body.get("reason_code", "")).strip()
    if not reason_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="reason_code is required")
    safe_metadata = body.get("safe_metadata")

    result = lifecycle_service.create_legal_hold(
        case_id, ctx.tenant_id, ctx.actor_id, ctx.role, reason_code, safe_metadata,
    )
    if result.get("error") == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if result.get("error") == "forbidden":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return result


@router.delete("/cases/{case_id}/legal-hold")
async def release_legal_hold(
    case_id: str,
    ctx: SecurityContext = Depends(require_authenticated),
) -> dict:
    result = lifecycle_service.release_legal_hold(
        case_id, ctx.tenant_id, ctx.actor_id, ctx.role,
    )
    if result.get("error") == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if result.get("error") == "forbidden":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return result


# ── retention ──────────────────────────────────────────────────────────

@router.get("/retention/preview")
async def retention_preview(
    ctx: SecurityContext = Depends(require_authenticated),
) -> dict:
    policy = lifecycle_service.get_retention_policy(ctx.tenant_id, "case")
    from app.services.case_session_service import case_session_service

    now = datetime.now(UTC)
    state = case_session_service._state
    cases = state.get("cases", {})

    eligible = 0
    held = 0
    for _cid, cdata in cases.items():
        if cdata.get("status") != "deleted":
            continue
        if cdata.get("legal_hold"):
            held += 1
            continue
        rt = cdata.get("retention_until", "")
        if rt:
            try:
                if datetime.fromisoformat(rt) <= now:
                    eligible += 1
            except Exception:
                pass
    return {"policy": policy, "eligible_for_purge": eligible, "held_by_legal_hold": held}


@router.post("/retention/run")
async def retention_run(
    body: dict | None = None,
    ctx: SecurityContext = Depends(require_authenticated),
) -> dict:
    body = body or {}
    dry_run = body.get("dry_run", True)
    batch = int(body.get("batch", 10))
    return lifecycle_service.run_purge(
        tenant_id=ctx.tenant_id, dry_run=dry_run, batch=batch,
    )


# ── purge ──────────────────────────────────────────────────────────────

@router.get("/purge/preview")
async def purge_preview(
    ctx: SecurityContext = Depends(require_authenticated),
) -> dict:
    return lifecycle_service.run_purge(tenant_id=ctx.tenant_id, dry_run=True, batch=50)


@router.post("/purge/run")
async def purge_run(
    body: dict | None = None,
    ctx: SecurityContext = Depends(require_authenticated),
) -> dict:
    body = body or {}
    batch = int(body.get("batch", 10))
    return lifecycle_service.run_purge(tenant_id=ctx.tenant_id, dry_run=False, batch=batch)


@router.post("/purge/resume/{run_id}")
async def purge_resume(
    run_id: str,
    body: dict | None = None,
    ctx: SecurityContext = Depends(require_authenticated),
) -> dict:
    body = body or {}
    dry_run = body.get("dry_run", False)
    batch = int(body.get("batch", 10))
    result = lifecycle_service.purge_resume(run_id, ctx.tenant_id, dry_run, batch)
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


@router.get("/purge/status/{run_id}")
async def purge_status(
    run_id: str,
    ctx: SecurityContext = Depends(require_authenticated),
) -> dict:
    result = lifecycle_service.purge_item_status(run_id)
    if result.get("error"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result["error"])
    return result


# ── audit ──────────────────────────────────────────────────────────────

@router.get("/audit")
async def list_audit_events(
    limit: int = Query(100, ge=1, le=1000),
    ctx: SecurityContext = Depends(require_authenticated),
) -> list[dict]:
    events = lifecycle_service.get_audit_events(ctx.tenant_id, limit=limit)
    safe_events = []
    for event in events:
        meta = dict(event.get("safe_metadata", {}))
        for key in ("password", "token", "access_token", "refresh_token", "email", "raw_email"):
            meta.pop(key, None)
        safe_events.append({
            "id": event.get("id", ""),
            "action": event.get("action", ""),
            "outcome": event.get("outcome", ""),
            "case_id": event.get("case_id", ""),
            "event_hash": event.get("event_hash", ""),
            "previous_event_hash": event.get("previous_event_hash", ""),
            "created_at": event.get("created_at", ""),
            "safe_metadata": meta,
        })
    return safe_events


@router.get("/audit/verify")
async def verify_audit_chain(
    ctx: SecurityContext = Depends(require_authenticated),
) -> dict:
    return lifecycle_service.verify_tenant_audit_chain(ctx.tenant_id)


# ── retention policy config ────────────────────────────────────────────

@router.get("/retention/policy")
async def get_retention_policy(
    ctx: SecurityContext = Depends(require_authenticated),
) -> dict:
    return lifecycle_service.get_retention_policy(ctx.tenant_id, "case")


@router.post("/retention/policy/validate")
async def validate_retention_policy(
    body: dict,
    ctx: SecurityContext = Depends(require_authenticated),
) -> dict:
    issues = lifecycle_service.validate_retention_policy(body)
    return {"valid": len(issues) == 0, "issues": issues}
