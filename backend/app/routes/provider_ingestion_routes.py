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

from app.config import get_settings
from app.db.session import get_session
from app.db.source_ingestion_repository import (
    RUN_COMPLETED,
    RUN_COMPLETED_WITH_ERRORS,
    RUN_FAILED,
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
    STATUS_BROWSER_DISCOVERY_UNAVAILABLE,
    STATUS_DEGRADED,
    STATUS_DISABLED,
    STATUS_FIXTURE_TESTED_ONLY,
    STATUS_MANUAL_REVIEW_REQUIRED,
    STATUS_PROVIDER_CHANGED,
    STATUS_TRANSPORT_UNAVAILABLE,
    STATUS_UNSUPPORTED_REQUIRES_AUTH,
    ProviderError,
)

logger = logging.getLogger(__name__)

provider_router = APIRouter(prefix="/official-source-providers", tags=["Official Source Providers"])
run_router = APIRouter(prefix="/official-source-ingestion-runs", tags=["Official Source Ingestion Runs"])


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


def _automatic_live_transport_configured() -> bool:
    return bool(get_settings().official_provider_live_smoke)


def _provider_status(code: str, definition, latest_terminal, latest_successful) -> str:
    if not registry.is_enabled(code):
        return STATUS_DISABLED
    if definition.capabilities.requires_auth:
        return STATUS_UNSUPPORTED_REQUIRES_AUTH
    if definition.capabilities.requires_browser:
        return STATUS_BROWSER_DISCOVERY_UNAVAILABLE
    if not _automatic_live_transport_configured():
        return STATUS_TRANSPORT_UNAVAILABLE
    terminal_error = (latest_terminal.last_safe_error_code if latest_terminal else "") or ""
    if terminal_error == "provider_structure_changed":
        return STATUS_PROVIDER_CHANGED
    if terminal_error in {"challenge_detected", "manual_review_required"}:
        return STATUS_MANUAL_REVIEW_REQUIRED
    if latest_successful is None:
        return STATUS_FIXTURE_TESTED_ONLY
    if latest_terminal is not None and latest_terminal.status == RUN_FAILED:
        return STATUS_DEGRADED
    if latest_terminal is not None and latest_terminal.status == RUN_COMPLETED_WITH_ERRORS:
        return STATUS_DEGRADED
    if latest_terminal is not None and latest_terminal.status == RUN_COMPLETED:
        return STATUS_AVAILABLE
    return STATUS_FIXTURE_TESTED_ONLY


async def _provider_info(db: AsyncSession, code: str) -> ProviderInfoResponse:
    definition = registry.get_definition(code)
    latest_run = await SourceIngestionRunRepository.latest_run_for_provider(db, code)
    latest_terminal = await SourceIngestionRunRepository.latest_terminal_run_for_provider(db, code)
    latest_successful = await SourceIngestionRunRepository.latest_successful_run_for_provider(db, code)
    last_run_at = _iso(latest_run.created_at) if latest_run else None
    last_success_at = (
        _iso(latest_successful.completed_at or latest_successful.created_at)
        if latest_successful else None
    )
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
        status=_provider_status(code, definition, latest_terminal, latest_successful),
        last_run_at=last_run_at,
        last_success_at=last_success_at,
        last_run_status=latest_run.status if latest_run else None,
        last_safe_error_code=(
            latest_terminal.last_safe_error_code if latest_terminal else ""
        ) or "",
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
        "max_items": body.max_items, "external_id": body.external_id,
    }
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
