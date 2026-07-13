"""P2.6C — Editor/admin official provider ingestion operations.

Provider ingestion is a global editor/admin action (reuses the P2.6
``require_editor`` boundary). A normal lawyer and a tenant_admin are rejected
with 403. Endpoints never expose raw provider HTML, fetch URLs, secrets or
stack traces. Runs are created as queued resources (202); execution is
performed by the CLI runner / worker seam.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.source_ingestion_repository import (
    RUN_COMPLETED,
    RUN_COMPLETED_WITH_ERRORS,
    SourceIngestionRunRepository,
)
from app.models.provider_models import (
    CreateRunRequest,
    IngestionRunListResponse,
    IngestionRunResponse,
    ProviderCapabilitiesModel,
    ProviderInfoResponse,
    ProviderListResponse,
)
from app.routes.source_routes import require_editor
from app.services.auth_service import SecurityContext
from app.services.source_providers import registry
from app.services.source_providers.base import (
    RUN_MODES,
    STATUS_AVAILABLE,
    STATUS_DISABLED,
    STATUS_UNSUPPORTED_REQUIRES_AUTH,
    ProviderError,
)

logger = logging.getLogger(__name__)

provider_router = APIRouter(prefix="/official-source-providers", tags=["Official Source Providers"])
run_router = APIRouter(prefix="/official-source-ingestion-runs", tags=["Official Source Ingestion Runs"])


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


def _provider_status(code: str) -> str:
    definition = registry.get_definition(code)
    if not registry.is_enabled(code):
        return STATUS_DISABLED
    if definition.capabilities.requires_auth:
        return STATUS_UNSUPPORTED_REQUIRES_AUTH
    return STATUS_AVAILABLE


async def _provider_info(db: AsyncSession, code: str) -> ProviderInfoResponse:
    definition = registry.get_definition(code)
    runs, _ = await SourceIngestionRunRepository.list(db, provider_code=code, limit=20, offset=0)
    last_run_at = _iso(runs[0].created_at) if runs else None
    last_success_at = None
    for r in runs:
        if r.status in (RUN_COMPLETED, RUN_COMPLETED_WITH_ERRORS):
            last_success_at = _iso(r.completed_at or r.created_at)
            break
    caps = definition.capabilities
    return ProviderInfoResponse(
        code=code,
        name=definition.provider_name,
        enabled=registry.is_enabled(code),
        source_types=list(definition.source_types),
        official_domains=list(definition.official_domains),
        capabilities=ProviderCapabilitiesModel(
            discovery=caps.discovery, fetch=caps.fetch, parse=caps.parse,
            incremental=caps.incremental, bounded_window=caps.bounded_window,
            requires_browser=caps.requires_browser, requires_auth=caps.requires_auth,
        ),
        status=_provider_status(code),
        last_run_at=last_run_at,
        last_success_at=last_success_at,
    )


def _run_response(run) -> IngestionRunResponse:
    return IngestionRunResponse(
        id=run.id, provider_code=run.provider_code, run_type=run.run_type,
        status=run.status, discovered_count=run.discovered_count,
        fetched_count=run.fetched_count, ingested_count=run.ingested_count,
        duplicate_count=run.duplicate_count, new_version_count=run.new_version_count,
        conflict_count=run.conflict_count, failed_count=run.failed_count,
        last_safe_error_code=run.last_safe_error_code, created_by=run.created_by,
        created_at=_iso(run.created_at) or "", started_at=_iso(run.started_at),
        completed_at=_iso(run.completed_at),
    )


@provider_router.get("", response_model=ProviderListResponse, operation_id="official_provider_list")
async def list_providers(
    ctx: SecurityContext = Depends(require_editor),
    db: AsyncSession = Depends(get_session),
) -> ProviderListResponse:
    items = [await _provider_info(db, code) for code in registry.all_provider_codes()]
    return ProviderListResponse(items=items)


@provider_router.get("/{provider_code}", response_model=ProviderInfoResponse, operation_id="official_provider_get")
async def get_provider(
    provider_code: str,
    ctx: SecurityContext = Depends(require_editor),
    db: AsyncSession = Depends(get_session),
) -> ProviderInfoResponse:
    if not registry.is_known(provider_code):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bilinmeyen sağlayıcı.")
    return await _provider_info(db, provider_code)


@provider_router.post(
    "/{provider_code}/runs", response_model=IngestionRunResponse,
    status_code=status.HTTP_202_ACCEPTED, operation_id="official_provider_create_run",
)
async def create_run(
    provider_code: str,
    body: CreateRunRequest,
    ctx: SecurityContext = Depends(require_editor),
    db: AsyncSession = Depends(get_session),
) -> IngestionRunResponse:
    if not registry.is_known(provider_code):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bilinmeyen sağlayıcı.")
    if body.run_type not in RUN_MODES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Geçersiz run_type.")
    if not registry.is_enabled(provider_code):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sağlayıcı etkin değil.")
    definition = registry.get_definition(provider_code)
    # Capability gate.
    from app.services.provider_ingestion_service import _capability_supports
    if not _capability_supports(definition, body.run_type):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Sağlayıcı bu run_type'ı desteklemiyor.")
    # Persist run parameters (no secrets) in cursor_json for the runner.
    params = {
        "query": body.query, "from_date": body.from_date, "to_date": body.to_date,
        "max_items": body.max_items,
    }
    if body.candidate is not None:
        params["candidate"] = body.candidate.model_dump()
    run = await SourceIngestionRunRepository.create(
        db, provider_code=provider_code, run_type=body.run_type,
        created_by=ctx.actor_id or None, cursor=params,
    )
    await db.commit()
    logger.info("official_provider_run_created provider=%s run_type=%s run_id=%s",
                provider_code, body.run_type, run.id)
    return _run_response(run)


@run_router.get("", response_model=IngestionRunListResponse, operation_id="official_ingestion_run_list")
async def list_runs(
    ctx: SecurityContext = Depends(require_editor),
    db: AsyncSession = Depends(get_session),
    provider_code: str = Query(default=""),
    run_status: str = Query(default="", alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> IngestionRunListResponse:
    runs, total = await SourceIngestionRunRepository.list(
        db, provider_code=provider_code, status=run_status, limit=limit, offset=offset)
    return IngestionRunListResponse(
        items=[_run_response(r) for r in runs], total=total, limit=limit, offset=offset,
        has_more=(offset + len(runs)) < total,
    )


@run_router.get("/{run_id}", response_model=IngestionRunResponse, operation_id="official_ingestion_run_get")
async def get_run(
    run_id: str,
    ctx: SecurityContext = Depends(require_editor),
    db: AsyncSession = Depends(get_session),
) -> IngestionRunResponse:
    run = await SourceIngestionRunRepository.get(db, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Çalışma bulunamadı.")
    return _run_response(run)


@run_router.post("/{run_id}/cancel", response_model=IngestionRunResponse, operation_id="official_ingestion_run_cancel")
async def cancel_run(
    run_id: str,
    ctx: SecurityContext = Depends(require_editor),
    db: AsyncSession = Depends(get_session),
) -> IngestionRunResponse:
    run = await SourceIngestionRunRepository.get(db, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Çalışma bulunamadı.")
    cancelled = await SourceIngestionRunRepository.cancel(db, run)
    if not cancelled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Çalışma zaten sonlanmış.")
    await db.commit()
    return _run_response(run)
