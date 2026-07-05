"""P1.7 — Legal Issue Graph API routes with tenant isolation and auth."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.db.session import get_session
from app.services.auth_service import SecurityContext, require_authenticated
from app.services import legal_issue_graph_db_service as graph_svc
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/cases/{case_id}/legal-graph", tags=["Hukuki Mesele Haritası"])


class NodeCreate(BaseModel):
    node_type: str = Field(min_length=1, max_length=30)
    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    status: str = "proposed"
    confidence: float | None = None
    source_type: str = "user_input"
    source_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class NodeUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    confidence: float | None = None
    metadata: dict[str, Any] | None = None


class EdgeCreate(BaseModel):
    source_node_id: str = Field(min_length=1, max_length=32)
    target_node_id: str = Field(min_length=1, max_length=32)
    relation_type: str = Field(min_length=1, max_length=30)
    description: str = ""
    weight: float = 0.5
    metadata: dict[str, Any] = Field(default_factory=dict)


class EdgeUpdate(BaseModel):
    description: str | None = None
    weight: float | None = None
    metadata: dict[str, Any] | None = None


def _error_response(exc: Exception) -> HTTPException:
    msg = str(exc)
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=msg)
    if isinstance(exc, ValueError):
        if "already deleted" in msg.lower() or "not deleted" in msg.lower() or "duplicate" in msg.lower():
            return HTTPException(status_code=409, detail=msg)
        return HTTPException(status_code=400, detail=msg)
    if isinstance(exc, PermissionError):
        err = str(exc)
        if "MEMBERSHIP" in err or "PERMISSION" in err:
            return HTTPException(status_code=403, detail=err)
        return HTTPException(status_code=403, detail="access_denied")
    return HTTPException(status_code=500, detail="internal_error")


# ── Graph-level ──

@router.post("")
@router.get("")
async def get_graph(
    case_id: str,
    ctx: SecurityContext = Depends(require_authenticated),
    db: AsyncSession = Depends(get_session),
):
    try:
        return await graph_svc.get_case_graph(
            db, tenant_id=ctx.tenant_id, case_id=case_id, actor_id=ctx.actor_id,
        )
    except Exception as e:
        raise _error_response(e)


@router.post("/rebuild")
async def rebuild_graph(
    case_id: str,
    ctx: SecurityContext = Depends(require_authenticated),
    db: AsyncSession = Depends(get_session),
):
    try:
        return await graph_svc.rebuild_case_graph(
            db, tenant_id=ctx.tenant_id, case_id=case_id, actor_id=ctx.actor_id,
        )
    except Exception as e:
        raise _error_response(e)


@router.post("/validate")
@router.get("/validate")
async def validate_graph(
    case_id: str,
    ctx: SecurityContext = Depends(require_authenticated),
    db: AsyncSession = Depends(get_session),
):
    try:
        return await graph_svc.validate_graph(
            db, tenant_id=ctx.tenant_id, case_id=case_id, actor_id=ctx.actor_id,
        )
    except Exception as e:
        raise _error_response(e)


@router.post("/summary")
@router.get("/summary")
async def get_summary(
    case_id: str,
    ctx: SecurityContext = Depends(require_authenticated),
    db: AsyncSession = Depends(get_session),
):
    try:
        return await graph_svc.get_graph_summary(
            db, tenant_id=ctx.tenant_id, case_id=case_id, actor_id=ctx.actor_id,
        )
    except Exception as e:
        raise _error_response(e)


# ── Node CRUD ──

@router.post("/nodes", status_code=201)
async def create_node(
    case_id: str,
    body: NodeCreate,
    ctx: SecurityContext = Depends(require_authenticated),
    db: AsyncSession = Depends(get_session),
):
    try:
        return await graph_svc.create_node(
            db,
            tenant_id=ctx.tenant_id,
            case_id=case_id,
            actor_id=ctx.actor_id,
            node_type=body.node_type,
            title=body.title,
            description=body.description,
            status=body.status,
            confidence=body.confidence,
            source_type=body.source_type,
            source_id=body.source_id,
            metadata=body.metadata,
        )
    except Exception as e:
        raise _error_response(e)


@router.post("/nodes/list")
@router.get("/nodes")
async def list_nodes(
    case_id: str,
    node_type: str = Query(""),
    status: str = Query(""),
    include_deleted: bool = Query(False),
    ctx: SecurityContext = Depends(require_authenticated),
    db: AsyncSession = Depends(get_session),
):
    try:
        return await graph_svc.list_nodes(
            db,
            tenant_id=ctx.tenant_id,
            case_id=case_id,
            actor_id=ctx.actor_id,
            node_type=node_type,
            status=status,
            include_deleted=include_deleted,
        )
    except Exception as e:
        raise _error_response(e)


@router.post("/nodes/{node_id}/get")
@router.get("/nodes/{node_id}")
async def get_node(
    case_id: str,
    node_id: str,
    ctx: SecurityContext = Depends(require_authenticated),
    db: AsyncSession = Depends(get_session),
):
    try:
        result = await graph_svc.get_node(
            db, tenant_id=ctx.tenant_id, case_id=case_id, actor_id=ctx.actor_id, node_id=node_id,
        )
        if result is None:
            raise HTTPException(status_code=404, detail=f"Node not found: {node_id}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise _error_response(e)


@router.patch("/nodes/{node_id}")
async def update_node(
    case_id: str,
    node_id: str,
    body: NodeUpdate,
    ctx: SecurityContext = Depends(require_authenticated),
    db: AsyncSession = Depends(get_session),
):
    try:
        return await graph_svc.update_node(
            db,
            tenant_id=ctx.tenant_id,
            case_id=case_id,
            actor_id=ctx.actor_id,
            node_id=node_id,
            title=body.title,
            description=body.description,
            status=body.status,
            confidence=body.confidence,
            metadata=body.metadata,
        )
    except Exception as e:
        raise _error_response(e)


@router.delete("/nodes/{node_id}")
async def delete_node(
    case_id: str,
    node_id: str,
    ctx: SecurityContext = Depends(require_authenticated),
    db: AsyncSession = Depends(get_session),
):
    try:
        return await graph_svc.delete_node(
            db, tenant_id=ctx.tenant_id, case_id=case_id, actor_id=ctx.actor_id, node_id=node_id,
        )
    except Exception as e:
        raise _error_response(e)


@router.post("/nodes/{node_id}/restore")
async def restore_node(
    case_id: str,
    node_id: str,
    ctx: SecurityContext = Depends(require_authenticated),
    db: AsyncSession = Depends(get_session),
):
    try:
        return await graph_svc.restore_node(
            db, tenant_id=ctx.tenant_id, case_id=case_id, actor_id=ctx.actor_id, node_id=node_id,
        )
    except Exception as e:
        raise _error_response(e)


# ── Edge CRUD ──

@router.post("/edges", status_code=201)
async def create_edge(
    case_id: str,
    body: EdgeCreate,
    ctx: SecurityContext = Depends(require_authenticated),
    db: AsyncSession = Depends(get_session),
):
    try:
        return await graph_svc.create_edge(
            db,
            tenant_id=ctx.tenant_id,
            case_id=case_id,
            actor_id=ctx.actor_id,
            source_node_id=body.source_node_id,
            target_node_id=body.target_node_id,
            relation_type=body.relation_type,
            description=body.description,
            weight=body.weight,
            metadata=body.metadata,
        )
    except Exception as e:
        raise _error_response(e)


@router.post("/edges/list")
@router.get("/edges")
async def list_edges(
    case_id: str,
    relation_type: str = Query(""),
    include_deleted: bool = Query(False),
    ctx: SecurityContext = Depends(require_authenticated),
    db: AsyncSession = Depends(get_session),
):
    try:
        return await graph_svc.list_edges(
            db,
            tenant_id=ctx.tenant_id,
            case_id=case_id,
            actor_id=ctx.actor_id,
            relation_type=relation_type,
            include_deleted=include_deleted,
        )
    except Exception as e:
        raise _error_response(e)


@router.patch("/edges/{edge_id}")
async def update_edge(
    case_id: str,
    edge_id: str,
    body: EdgeUpdate,
    ctx: SecurityContext = Depends(require_authenticated),
    db: AsyncSession = Depends(get_session),
):
    try:
        return await graph_svc.update_edge(
            db,
            tenant_id=ctx.tenant_id,
            case_id=case_id,
            actor_id=ctx.actor_id,
            edge_id=edge_id,
            description=body.description,
            weight=body.weight,
            metadata=body.metadata,
        )
    except Exception as e:
        raise _error_response(e)


@router.delete("/edges/{edge_id}")
async def delete_edge(
    case_id: str,
    edge_id: str,
    ctx: SecurityContext = Depends(require_authenticated),
    db: AsyncSession = Depends(get_session),
):
    try:
        return await graph_svc.delete_edge(
            db, tenant_id=ctx.tenant_id, case_id=case_id, actor_id=ctx.actor_id, edge_id=edge_id,
        )
    except Exception as e:
        raise _error_response(e)


@router.post("/edges/{edge_id}/restore")
async def restore_edge(
    case_id: str,
    edge_id: str,
    ctx: SecurityContext = Depends(require_authenticated),
    db: AsyncSession = Depends(get_session),
):
    try:
        return await graph_svc.restore_edge(
            db, tenant_id=ctx.tenant_id, case_id=case_id, actor_id=ctx.actor_id, edge_id=edge_id,
        )
    except Exception as e:
        raise _error_response(e)
