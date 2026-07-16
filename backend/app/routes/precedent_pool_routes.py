"""Case-scoped dynamic precedent pool endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.search_models import (
    AnalyzePrecedentPoolRequest,
    PrecedentAnalysisListResponse,
    PrecedentAnalysisResponse,
    PrecedentPoolDecisionResponse,
    PrecedentPoolDetail,
    PrecedentPoolSummary,
)
from app.services.auth_service import SecurityContext, resolve_current_user
from app.services.precedent_pool_service import (
    analyze_pool,
    get_pool,
    list_analyses,
    list_pool_decisions,
    list_pools,
    pool_detail,
)


router = APIRouter(tags=["Precedent Pools"])


@router.get(
    "/cases/{case_id}/precedent-pools",
    response_model=list[PrecedentPoolSummary],
    operation_id="list_case_precedent_pools",
)
async def list_case_precedent_pools(
    case_id: str,
    db: AsyncSession = Depends(get_session),
    ctx: SecurityContext = Depends(resolve_current_user),
) -> list[PrecedentPoolSummary]:
    return await list_pools(db, ctx, case_id)


@router.get(
    "/precedent-pools/{pool_id}",
    response_model=PrecedentPoolDetail,
    operation_id="get_precedent_pool",
)
async def get_precedent_pool(
    pool_id: str,
    db: AsyncSession = Depends(get_session),
    ctx: SecurityContext = Depends(resolve_current_user),
) -> PrecedentPoolDetail:
    return pool_detail(await get_pool(db, ctx, pool_id))


@router.get(
    "/precedent-pools/{pool_id}/decisions",
    response_model=list[PrecedentPoolDecisionResponse],
    operation_id="list_precedent_pool_decisions",
)
async def get_precedent_pool_decisions(
    pool_id: str,
    db: AsyncSession = Depends(get_session),
    ctx: SecurityContext = Depends(resolve_current_user),
) -> list[PrecedentPoolDecisionResponse]:
    return await list_pool_decisions(db, ctx, pool_id)


@router.post(
    "/precedent-pools/{pool_id}/analyze",
    response_model=PrecedentAnalysisListResponse,
    operation_id="analyze_precedent_pool",
)
async def analyze_precedent_pool(
    pool_id: str,
    body: AnalyzePrecedentPoolRequest,
    db: AsyncSession = Depends(get_session),
    ctx: SecurityContext = Depends(resolve_current_user),
) -> PrecedentAnalysisListResponse:
    items = await analyze_pool(db, ctx, pool_id, body)
    return PrecedentAnalysisListResponse(items=items)


@router.get(
    "/precedent-pools/{pool_id}/analyses",
    response_model=PrecedentAnalysisListResponse,
    operation_id="list_precedent_pool_analyses",
)
async def get_precedent_pool_analyses(
    pool_id: str,
    db: AsyncSession = Depends(get_session),
    ctx: SecurityContext = Depends(resolve_current_user),
) -> PrecedentAnalysisListResponse:
    return PrecedentAnalysisListResponse(items=await list_analyses(db, ctx, pool_id))
