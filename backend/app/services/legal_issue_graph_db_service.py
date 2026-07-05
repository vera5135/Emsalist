"""P1.7 — Legal Issue Graph database-backed service with full tenant/case isolation.

Provides CRUD for legal_issue_nodes and legal_issue_edges backed by the
SQLAlchemy async session, with tenant isolation, membership checks, soft-delete,
audit events, and graph validation.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, and_, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.db.models import LegalIssueNode, LegalIssueEdge, new_uuid

logger = logging.getLogger(__name__)

NODE_TYPES = frozenset({
    "fact", "legal_issue", "legal_element", "evidence",
    "official_source", "argument", "counterargument",
    "risk", "remedy", "missing_information",
})

NODE_STATUSES = frozenset({
    "proposed", "confirmed", "disputed", "missing", "rejected",
})

EDGE_RELATIONS = frozenset({
    "supports", "contradicts", "requires", "proven_by",
    "based_on", "leads_to", "rebuts", "depends_on",
    "missing_for", "requested_as",
})

SOURCE_TYPES = frozenset({
    "user_input", "document", "research", "petition", "system", "ai",
})


async def _get_active_membership_role(
    db: AsyncSession, tenant_id: str, case_id: str, actor_id: str
) -> str | None:
    """Return the membership role for an actor in a case, or None if not a member."""
    from app.db.models import CaseMember
    result = await db.execute(
        select(CaseMember.membership_role).where(
            CaseMember.tenant_id == tenant_id,
            CaseMember.case_id == case_id,
            CaseMember.user_id == actor_id,
            CaseMember.revoked_at.is_(None),
        )
    )
    row = result.first()
    return row[0] if row else None


_ROLE_WRITE = frozenset({"owner", "editor"})
_ROLE_READ = frozenset({"owner", "editor", "viewer"})


async def _require_write(db: AsyncSession, tenant_id: str, case_id: str, actor_id: str) -> str:
    role = await _get_active_membership_role(db, tenant_id, case_id, actor_id)
    if role is None:
        raise PermissionError("CASE_MEMBERSHIP_REQUIRED")
    if role not in _ROLE_WRITE:
        raise PermissionError("INSUFFICIENT_PERMISSION")
    return role


async def _require_read(db: AsyncSession, tenant_id: str, case_id: str, actor_id: str) -> str:
    role = await _get_active_membership_role(db, tenant_id, case_id, actor_id)
    if role is None:
        raise PermissionError("CASE_MEMBERSHIP_REQUIRED")
    if role not in _ROLE_READ:
        raise PermissionError("INSUFFICIENT_PERMISSION")
    return role


async def _check_case_legal_hold(db: AsyncSession, case_id: str) -> bool:
    from app.db.models import LegalHold
    result = await db.execute(
        select(LegalHold.id).where(
            LegalHold.case_id == case_id,
            LegalHold.active.is_(True),
        ).limit(1)
    )
    return result.first() is not None


async def _write_audit(
    db: AsyncSession,
    tenant_id: str,
    actor_id: str,
    case_id: str,
    action: str,
    resource_id: str = "",
    outcome: str = "success",
    safe_metadata: dict | None = None,
) -> None:
    try:
        from app.db.models import AuditEvent
        event = AuditEvent(
            id=new_uuid(),
            tenant_id=tenant_id,
            actor_id=actor_id,
            case_id=case_id,
            action=action,
            resource_type="legal_issue_graph",
            resource_id=resource_id,
            outcome=outcome,
            safe_metadata=safe_metadata or {},
        )
        db.add(event)
        await db.flush()
    except Exception:
        logger.exception("Failed to write audit event for %s", action)


# ── Node operations ──


async def create_node(
    db: AsyncSession,
    *,
    tenant_id: str,
    case_id: str,
    actor_id: str,
    node_type: str,
    title: str,
    description: str = "",
    status: str = "proposed",
    confidence: float | None = None,
    source_type: str = "user_input",
    source_id: str = "",
    metadata: dict | None = None,
) -> dict[str, Any]:
    await _require_write(db, tenant_id, case_id, actor_id)
    if node_type not in NODE_TYPES:
        raise ValueError(f"Invalid node_type: {node_type}")
    if status not in NODE_STATUSES:
        raise ValueError(f"Invalid status: {status}")
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"Invalid source_type: {source_type}")
    if confidence is not None and not (0.0 <= confidence <= 1.0):
        raise ValueError("confidence must be between 0.0 and 1.0")

    node = LegalIssueNode(
        id=new_uuid(),
        tenant_id=tenant_id,
        case_id=case_id,
        node_type=node_type,
        title=title.strip(),
        description=description.strip(),
        status=status,
        confidence=confidence,
        source_type=source_type,
        source_id=source_id.strip(),
        metadata_json=metadata or {},
        created_by=actor_id,
    )
    db.add(node)
    await db.flush()
    await _write_audit(db, tenant_id, actor_id, case_id, "LEGAL_GRAPH_NODE_CREATED", node.id)
    return _node_to_dict(node)


async def update_node(
    db: AsyncSession,
    *,
    tenant_id: str,
    case_id: str,
    actor_id: str,
    node_id: str,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    confidence: float | None = None,
    metadata: dict | None = None,
) -> dict[str, Any]:
    await _require_write(db, tenant_id, case_id, actor_id)
    node = await _get_node_including_deleted(db, tenant_id, case_id, node_id)
    if node is None:
        raise KeyError(f"Node not found: {node_id}")
    if node.deleted_at is not None:
        raise ValueError("Cannot update a deleted node")

    if title is not None:
        node.title = title.strip()
    if description is not None:
        node.description = description.strip()
    if status is not None:
        if status not in NODE_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        node.status = status
    if confidence is not None:
        if not (0.0 <= confidence <= 1.0):
            raise ValueError("confidence must be between 0.0 and 1.0")
        node.confidence = confidence
    if metadata is not None:
        node.metadata_json = metadata

    node.updated_at = datetime.now(UTC)
    await db.flush()
    await _write_audit(db, tenant_id, actor_id, case_id, "LEGAL_GRAPH_NODE_UPDATED", node.id)
    return _node_to_dict(node)


async def delete_node(
    db: AsyncSession,
    *,
    tenant_id: str,
    case_id: str,
    actor_id: str,
    node_id: str,
) -> dict[str, Any]:
    await _require_write(db, tenant_id, case_id, actor_id)
    node = await _get_node_including_deleted(db, tenant_id, case_id, node_id)
    if node is None:
        raise KeyError(f"Node not found: {node_id}")
    if node.deleted_at is not None:
        raise ValueError("Node already deleted")

    node.deleted_at = datetime.now(UTC)
    node.updated_at = datetime.now(UTC)
    await db.flush()
    await _write_audit(db, tenant_id, actor_id, case_id, "LEGAL_GRAPH_NODE_DELETED", node.id)
    return _node_to_dict(node)


async def restore_node(
    db: AsyncSession,
    *,
    tenant_id: str,
    case_id: str,
    actor_id: str,
    node_id: str,
) -> dict[str, Any]:
    await _require_write(db, tenant_id, case_id, actor_id)
    node = await _get_node_including_deleted(db, tenant_id, case_id, node_id)
    if node is None:
        raise KeyError(f"Node not found: {node_id}")
    if node.deleted_at is None:
        raise ValueError("Node is not deleted")

    node.deleted_at = None
    node.updated_at = datetime.now(UTC)
    await db.flush()
    await _write_audit(db, tenant_id, actor_id, case_id, "LEGAL_GRAPH_NODE_RESTORED", node.id)
    return _node_to_dict(node)


async def get_node(
    db: AsyncSession,
    *,
    tenant_id: str,
    case_id: str,
    actor_id: str,
    node_id: str,
) -> dict[str, Any] | None:
    await _require_read(db, tenant_id, case_id, actor_id)
    node = await _get_node(db, tenant_id, case_id, node_id)
    return _node_to_dict(node) if node else None


async def list_nodes(
    db: AsyncSession,
    *,
    tenant_id: str,
    case_id: str,
    actor_id: str,
    node_type: str = "",
    status: str = "",
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    await _require_read(db, tenant_id, case_id, actor_id)
    query = select(LegalIssueNode).where(
        LegalIssueNode.tenant_id == tenant_id,
        LegalIssueNode.case_id == case_id,
    )
    if not include_deleted:
        query = query.where(LegalIssueNode.deleted_at.is_(None))
    if node_type:
        query = query.where(LegalIssueNode.node_type == node_type)
    if status:
        query = query.where(LegalIssueNode.status == status)
    query = query.order_by(LegalIssueNode.created_at.desc())
    result = await db.execute(query)
    return [_node_to_dict(row) for row in result.scalars()]


# ── Edge operations ──


async def create_edge(
    db: AsyncSession,
    *,
    tenant_id: str,
    case_id: str,
    actor_id: str,
    source_node_id: str,
    target_node_id: str,
    relation_type: str,
    description: str = "",
    weight: float = 0.5,
    metadata: dict | None = None,
) -> dict[str, Any]:
    await _require_write(db, tenant_id, case_id, actor_id)
    if relation_type not in EDGE_RELATIONS:
        raise ValueError(f"Invalid relation_type: {relation_type}")
    if source_node_id == target_node_id:
        raise ValueError("Self-loop edges are not allowed")

    source = await _get_node(db, tenant_id, case_id, source_node_id)
    if source is None:
        raise KeyError(f"Source node not found: {source_node_id}")
    target = await _get_node(db, tenant_id, case_id, target_node_id)
    if target is None:
        raise KeyError(f"Target node not found: {target_node_id}")

    existing = await db.execute(
        select(LegalIssueEdge).where(
            LegalIssueEdge.source_node_id == source_node_id,
            LegalIssueEdge.target_node_id == target_node_id,
            LegalIssueEdge.relation_type == relation_type,
            LegalIssueEdge.deleted_at.is_(None),
        ).limit(1)
    )
    if existing.first() is not None:
        raise ValueError("Duplicate edge with same source, target, and relation_type")

    edge = LegalIssueEdge(
        id=new_uuid(),
        tenant_id=tenant_id,
        case_id=case_id,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        relation_type=relation_type,
        description=description.strip(),
        weight=float(weight),
        metadata_json=metadata or {},
        created_by=actor_id,
    )
    db.add(edge)
    await db.flush()
    await _write_audit(db, tenant_id, actor_id, case_id, "LEGAL_GRAPH_EDGE_CREATED", edge.id)
    return _edge_to_dict(edge)


async def update_edge(
    db: AsyncSession,
    *,
    tenant_id: str,
    case_id: str,
    actor_id: str,
    edge_id: str,
    description: str | None = None,
    weight: float | None = None,
    metadata: dict | None = None,
) -> dict[str, Any]:
    await _require_write(db, tenant_id, case_id, actor_id)
    edge = await _get_edge(db, tenant_id, case_id, edge_id)
    if edge is None:
        raise KeyError(f"Edge not found: {edge_id}")
    if edge.deleted_at is not None:
        raise ValueError("Cannot update a deleted edge")

    if description is not None:
        edge.description = description.strip()
    if weight is not None:
        edge.weight = float(weight)
    if metadata is not None:
        edge.metadata_json = metadata

    edge.updated_at = datetime.now(UTC)
    await db.flush()
    await _write_audit(db, tenant_id, actor_id, case_id, "LEGAL_GRAPH_EDGE_UPDATED", edge.id)
    return _edge_to_dict(edge)


async def delete_edge(
    db: AsyncSession,
    *,
    tenant_id: str,
    case_id: str,
    actor_id: str,
    edge_id: str,
) -> dict[str, Any]:
    await _require_write(db, tenant_id, case_id, actor_id)
    edge = await _get_edge(db, tenant_id, case_id, edge_id)
    if edge is None:
        raise KeyError(f"Edge not found: {edge_id}")
    if edge.deleted_at is not None:
        raise ValueError("Edge already deleted")

    edge.deleted_at = datetime.now(UTC)
    edge.updated_at = datetime.now(UTC)
    await db.flush()
    await _write_audit(db, tenant_id, actor_id, case_id, "LEGAL_GRAPH_EDGE_DELETED", edge.id)
    return _edge_to_dict(edge)


async def restore_edge(
    db: AsyncSession,
    *,
    tenant_id: str,
    case_id: str,
    actor_id: str,
    edge_id: str,
) -> dict[str, Any]:
    await _require_write(db, tenant_id, case_id, actor_id)
    edge = await _get_edge_including_deleted(db, tenant_id, case_id, edge_id)
    if edge is None:
        raise KeyError(f"Edge not found: {edge_id}")
    if edge.deleted_at is None:
        raise ValueError("Edge is not deleted")

    edge.deleted_at = None
    edge.updated_at = datetime.now(UTC)
    await db.flush()
    await _write_audit(db, tenant_id, actor_id, case_id, "LEGAL_GRAPH_EDGE_RESTORED", edge.id)
    return _edge_to_dict(edge)


async def list_edges(
    db: AsyncSession,
    *,
    tenant_id: str,
    case_id: str,
    actor_id: str,
    relation_type: str = "",
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
    await _require_read(db, tenant_id, case_id, actor_id)
    query = select(LegalIssueEdge).where(
        LegalIssueEdge.tenant_id == tenant_id,
        LegalIssueEdge.case_id == case_id,
    )
    if not include_deleted:
        query = query.where(LegalIssueEdge.deleted_at.is_(None))
    if relation_type:
        query = query.where(LegalIssueEdge.relation_type == relation_type)
    query = query.order_by(LegalIssueEdge.created_at.desc())
    result = await db.execute(query)
    return [_edge_to_dict(row) for row in result.scalars()]


# ── Graph-level operations ──


async def get_case_graph(
    db: AsyncSession,
    *,
    tenant_id: str,
    case_id: str,
    actor_id: str,
) -> dict[str, Any]:
    await _require_read(db, tenant_id, case_id, actor_id)
    nodes = await _list_active_nodes(db, tenant_id, case_id)
    edges = await _list_active_edges(db, tenant_id, case_id)
    return {
        "case_id": case_id,
        "tenant_id": tenant_id,
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


async def validate_graph(
    db: AsyncSession,
    *,
    tenant_id: str,
    case_id: str,
    actor_id: str,
) -> dict[str, Any]:
    await _require_read(db, tenant_id, case_id, actor_id)
    nodes = await _list_active_nodes(db, tenant_id, case_id)
    edges = await _list_active_edges(db, tenant_id, case_id)

    node_map: dict[str, dict] = {n["id"]: n for n in nodes}
    errors: list[dict] = []
    warnings: list[dict] = []

    # Check dangling edges
    for edge in edges:
        src = edge["source_node_id"]
        tgt = edge["target_node_id"]
        if src not in node_map:
            errors.append({
                "type": "dangling_edge_source",
                "edge_id": edge["id"],
                "detail": f"Source node {src} is not active in this case",
            })
        if tgt not in node_map:
            errors.append({
                "type": "dangling_edge_target",
                "edge_id": edge["id"],
                "detail": f"Target node {tgt} is not active in this case",
            })

    # Check orphan nodes
    connected: set[str] = set()
    for edge in edges:
        connected.add(edge["source_node_id"])
        connected.add(edge["target_node_id"])
    for node in nodes:
        if node["id"] not in connected:
            warnings.append({
                "type": "orphan_node",
                "node_id": node["id"],
                "node_type": node["node_type"],
                "detail": f"Node '{node['title']}' has no connections",
            })

    # Check source-less official_source
    for node in nodes:
        if node["node_type"] == "official_source" and not node.get("source_id"):
            warnings.append({
                "type": "sourceless_official_source",
                "node_id": node["id"],
                "detail": f"Official source '{node['title']}' has no source reference",
            })

    # Check confirmed fact without evidence connected
    fact_node_ids = {n["id"] for n in nodes if n["node_type"] == "fact" and n["status"] == "confirmed"}
    fact_to_evidence: dict[str, bool] = {fid: False for fid in fact_node_ids}
    evidence_node_ids = {n["id"] for n in nodes if n["node_type"] == "evidence"}
    for edge in edges:
        if edge["relation_type"] in ("proven_by", "based_on"):
            if edge["source_node_id"] in fact_to_evidence and edge["target_node_id"] in evidence_node_ids:
                fact_to_evidence[edge["source_node_id"]] = True
    for fid, has_evidence in fact_to_evidence.items():
        if not has_evidence:
            node = node_map.get(fid, {})
            warnings.append({
                "type": "confirmed_fact_no_evidence",
                "node_id": fid,
                "detail": f"Confirmed fact '{node.get('title', fid)}' has no evidence connection",
            })

    # Check legal_issue without elements
    issue_node_ids = {n["id"] for n in nodes if n["node_type"] == "legal_issue"}
    issue_to_element: dict[str, bool] = {iid: False for iid in issue_node_ids}
    element_node_ids = {n["id"] for n in nodes if n["node_type"] == "legal_element"}
    for edge in edges:
        if edge["relation_type"] in ("requires", "depends_on"):
            if edge["source_node_id"] in issue_to_element and edge["target_node_id"] in element_node_ids:
                issue_to_element[edge["source_node_id"]] = True
    for iid, has_element in issue_to_element.items():
        if not has_element:
            node = node_map.get(iid, {})
            warnings.append({
                "type": "legal_issue_no_elements",
                "node_id": iid,
                "detail": f"Legal issue '{node.get('title', iid)}' has no defined elements",
            })

    # Check remedy not linked to any legal_issue
    remedy_ids = {n["id"] for n in nodes if n["node_type"] == "remedy"}
    remedy_to_issue: dict[str, bool] = {rid: False for rid in remedy_ids}
    for edge in edges:
        if edge["relation_type"] in ("leads_to", "requested_as"):
            if edge["source_node_id"] in issue_node_ids and edge["target_node_id"] in remedy_to_issue:
                remedy_to_issue[edge["target_node_id"]] = True
    for rid, linked in remedy_to_issue.items():
        if not linked:
            node = node_map.get(rid, {})
            warnings.append({
                "type": "remedy_not_linked",
                "node_id": rid,
                "detail": f"Remedy '{node.get('title', rid)}' is not linked to any legal issue",
            })

    # Critical missing_information
    for node in nodes:
        if node["node_type"] == "missing_information":
            warnings.append({
                "type": "critical_missing_information",
                "node_id": node["id"],
                "detail": f"Critical missing: {node['title']}",
            })

    statistics = {
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "node_type_counts": {},
        "edge_relation_counts": {},
    }
    for n in nodes:
        nt = n["node_type"]
        statistics["node_type_counts"][nt] = statistics["node_type_counts"].get(nt, 0) + 1
    for e in edges:
        rt = e["relation_type"]
        statistics["edge_relation_counts"][rt] = statistics["edge_relation_counts"].get(rt, 0) + 1

    await _write_audit(db, tenant_id, actor_id, case_id, "LEGAL_GRAPH_VALIDATED",
                       safe_metadata={"valid": len(errors) == 0, "errors": len(errors), "warnings": len(warnings)})

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "statistics": statistics,
    }


async def get_graph_summary(
    db: AsyncSession,
    *,
    tenant_id: str,
    case_id: str,
    actor_id: str,
) -> dict[str, Any]:
    await _require_read(db, tenant_id, case_id, actor_id)
    nodes = await _list_active_nodes(db, tenant_id, case_id)
    edges = await _list_active_edges(db, tenant_id, case_id)

    type_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for n in nodes:
        type_counts[n["node_type"]] = type_counts.get(n["node_type"], 0) + 1
        status_counts[n["status"]] = status_counts.get(n["status"], 0) + 1

    validation = await validate_graph(db, tenant_id=tenant_id, case_id=case_id, actor_id=actor_id)

    return {
        "case_id": case_id,
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "node_type_counts": type_counts,
        "status_counts": status_counts,
        "legal_issue_count": type_counts.get("legal_issue", 0),
        "fact_count": type_counts.get("fact", 0),
        "evidence_count": type_counts.get("evidence", 0),
        "official_source_count": type_counts.get("official_source", 0),
        "argument_count": type_counts.get("argument", 0),
        "counterargument_count": type_counts.get("counterargument", 0),
        "risk_count": type_counts.get("risk", 0),
        "remedy_count": type_counts.get("remedy", 0),
        "missing_information_count": type_counts.get("missing_information", 0),
        "validation_valid": validation["valid"],
        "validation_error_count": len(validation["errors"]),
        "validation_warning_count": len(validation["warnings"]),
    }


async def rebuild_case_graph(
    db: AsyncSession,
    *,
    tenant_id: str,
    case_id: str,
    actor_id: str,
) -> dict[str, Any]:
    """Rebuild graph from existing case data. Idempotent — preserves user-confirmed nodes."""
    await _require_write(db, tenant_id, case_id, actor_id)

    # Get existing nodes to preserve user-confirmed ones
    existing_nodes = await _list_active_nodes(db, tenant_id, case_id)
    user_confirmed_ids = {
        n["id"] for n in existing_nodes
        if n["status"] == "confirmed" and n["source_type"] in ("user_input", "ai")
    }

    # Collect data from case session
    from app.services.case_session_service import case_session_service
    try:
        state = case_session_service.get_case_state(case_id)
    except KeyError:
        state = {}

    created = 0

    # Helper to create node idempotently
    async def _ensure_node(
        ntype: str, title: str, desc: str = "", src_type: str = "system",
        src_id: str = "", confidence_val: float | None = None,
        status_val: str = "proposed",
    ) -> str | None:
        nonlocal created
        result = await db.execute(
            select(LegalIssueNode.id).where(
                LegalIssueNode.tenant_id == tenant_id,
                LegalIssueNode.case_id == case_id,
                LegalIssueNode.node_type == ntype,
                LegalIssueNode.title == title,
                LegalIssueNode.deleted_at.is_(None),
            ).limit(1)
        )
        existing_id = result.first()
        if existing_id is not None:
            return existing_id[0]
        node = LegalIssueNode(
            id=new_uuid(),
            tenant_id=tenant_id,
            case_id=case_id,
            node_type=ntype,
            title=title.strip()[:500],
            description=desc.strip()[:2000],
            status=status_val,
            confidence=confidence_val,
            source_type=src_type,
            source_id=src_id.strip()[:32],
            created_by=actor_id,
            metadata_json={},
        )
        db.add(node)
        created += 1
        await db.flush()
        return node.id

    event_text = str(state.get("event_text") or "")
    facts_dict = {f.split(":", 1)[0].strip(): f.split(":", 1)[1].strip() if ":" in f else ""
                  for f in (state.get("document_facts") or [])}

    # Build facts from event_text sentences
    fact_ids: list[str] = []
    if event_text:
        sentences = [s.strip(" -.") for s in event_text.replace("\n", ". ").split(". ") if len(s.strip()) > 3]
        for s in sentences[:8]:
            fid = await _ensure_node("fact", s[:500], src_type="user_input", status_val="confirmed", confidence_val=0.9)
            if fid:
                fact_ids.append(fid)

    # Build legal issues from case enrichment
    enrichment = state.get("case_enrichment") or {}
    legal_theory = enrichment.get("legal_theory") or []
    if not legal_theory and state.get("legal_topic"):
        legal_theory = [state["legal_topic"]]

    issue_ids = []
    for theory in legal_theory[:5]:
        iid = await _ensure_node("legal_issue", str(theory)[:500], src_type="research", src_id=case_id,
                                 status_val="proposed", confidence_val=0.7)
        if iid:
            issue_ids.append(iid)

    # Build evidence from documents
    documents = state.get("documents") or []
    evidence_ids = []
    for doc in documents[:5]:
        doc_name = str(doc.get("original_filename") or doc.get("storage_key") or "Belge")[:500]
        eid = await _ensure_node("evidence", doc_name, src_type="document",
                                 src_id=str(doc.get("id", "")), status_val="confirmed", confidence_val=0.95)
        if eid:
            evidence_ids.append(eid)

    # Build risks
    risks = enrichment.get("risk_flags") or []
    risk_ids = []
    for risk in risks[:5]:
        rid = await _ensure_node("risk", str(risk)[:500], src_type="research", status_val="proposed", confidence_val=0.6)
        if rid:
            risk_ids.append(rid)

    # Build missing information
    missing = enrichment.get("missing_facts") or []
    for m in missing[:5]:
        await _ensure_node("missing_information", str(m)[:500], src_type="research", status_val="missing")

    # Build remedies from petition strategy
    strategy = enrichment.get("petition_strategy_hint") or ""
    if strategy:
        await _ensure_node("remedy", strategy[:500], src_type="petition", status_val="proposed", confidence_val=0.6)

    # Build sources from relevant_articles and relevant_codes
    articles = enrichment.get("relevant_articles") or []
    for art in articles[:5]:
        await _ensure_node("official_source", str(art)[:500], src_type="research", status_val="proposed", confidence_val=0.8)

    # Connect related items with edges
    async def _ensure_edge(src_id: str, tgt_id: str, rel: str, desc: str = "") -> None:
        nonlocal created
        if src_id == tgt_id:
            return
        existing = await db.execute(
            select(LegalIssueEdge.id).where(
                LegalIssueEdge.source_node_id == src_id,
                LegalIssueEdge.target_node_id == tgt_id,
                LegalIssueEdge.relation_type == rel,
                LegalIssueEdge.deleted_at.is_(None),
            ).limit(1)
        )
        if existing.first() is not None:
            return
        edge = LegalIssueEdge(
            id=new_uuid(),
            tenant_id=tenant_id,
            case_id=case_id,
            source_node_id=src_id,
            target_node_id=tgt_id,
            relation_type=rel,
            description=desc.strip(),
            created_by=actor_id,
            metadata_json={},
        )
        db.add(edge)
        created += 1
        await db.flush()

    # Connect facts to legal issues
    for fid in fact_ids[:3]:
        for iid in issue_ids[:2]:
            await _ensure_edge(fid, iid, "supports")

    # Connect evidence to facts
    for eid in evidence_ids[:3]:
        for fid in fact_ids[:2]:
            await _ensure_edge(fid, eid, "proven_by")

    # Connect risks to legal issues
    for rid in risk_ids[:3]:
        for iid in issue_ids[:1]:
            await _ensure_edge(rid, iid, "depends_on")

    await _write_audit(db, tenant_id, actor_id, case_id, "LEGAL_GRAPH_REBUILT",
                       safe_metadata={"nodes_created": created})

    return await get_case_graph(db, tenant_id=tenant_id, case_id=case_id, actor_id=actor_id)


async def purge_case_graph(
    db: AsyncSession,
    *,
    tenant_id: str,
    case_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Purge all graph data for a case. Respects legal hold."""
    has_hold = await _check_case_legal_hold(db, case_id)
    if has_hold:
        return {"purged": False, "reason": "legal_hold_active", "node_count": 0, "edge_count": 0}

    node_result = await db.execute(
        select(func.count(LegalIssueNode.id)).where(
            LegalIssueNode.tenant_id == tenant_id,
            LegalIssueNode.case_id == case_id,
        )
    )
    edge_result = await db.execute(
        select(func.count(LegalIssueEdge.id)).where(
            LegalIssueEdge.tenant_id == tenant_id,
            LegalIssueEdge.case_id == case_id,
        )
    )
    node_count = node_result.scalar() or 0
    edge_count = edge_result.scalar() or 0

    if not dry_run:
        await db.execute(
            delete(LegalIssueNode).where(
                LegalIssueNode.tenant_id == tenant_id,
                LegalIssueNode.case_id == case_id,
            )
        )
        await db.execute(
            delete(LegalIssueEdge).where(
                LegalIssueEdge.tenant_id == tenant_id,
                LegalIssueEdge.case_id == case_id,
            )
        )
        await db.flush()

    return {
        "purged": not dry_run,
        "dry_run": dry_run,
        "node_count": node_count,
        "edge_count": edge_count,
    }


# ── Internal helpers ──


async def _get_node(
    db: AsyncSession, tenant_id: str, case_id: str, node_id: str
) -> LegalIssueNode | None:
    result = await db.execute(
        select(LegalIssueNode).where(
            LegalIssueNode.id == node_id,
            LegalIssueNode.tenant_id == tenant_id,
            LegalIssueNode.case_id == case_id,
            LegalIssueNode.deleted_at.is_(None),
        ).limit(1)
    )
    return result.scalar()


async def _get_node_including_deleted(
    db: AsyncSession, tenant_id: str, case_id: str, node_id: str
) -> LegalIssueNode | None:
    result = await db.execute(
        select(LegalIssueNode).where(
            LegalIssueNode.id == node_id,
            LegalIssueNode.tenant_id == tenant_id,
            LegalIssueNode.case_id == case_id,
        ).limit(1)
    )
    return result.scalar()


async def _get_edge(
    db: AsyncSession, tenant_id: str, case_id: str, edge_id: str
) -> LegalIssueEdge | None:
    result = await db.execute(
        select(LegalIssueEdge).where(
            LegalIssueEdge.id == edge_id,
            LegalIssueEdge.tenant_id == tenant_id,
            LegalIssueEdge.case_id == case_id,
            LegalIssueEdge.deleted_at.is_(None),
        ).limit(1)
    )
    return result.scalar()


async def _get_edge_including_deleted(
    db: AsyncSession, tenant_id: str, case_id: str, edge_id: str
) -> LegalIssueEdge | None:
    result = await db.execute(
        select(LegalIssueEdge).where(
            LegalIssueEdge.id == edge_id,
            LegalIssueEdge.tenant_id == tenant_id,
            LegalIssueEdge.case_id == case_id,
        ).limit(1)
    )
    return result.scalar()


async def _list_active_nodes(
    db: AsyncSession, tenant_id: str, case_id: str
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(LegalIssueNode).where(
            LegalIssueNode.tenant_id == tenant_id,
            LegalIssueNode.case_id == case_id,
            LegalIssueNode.deleted_at.is_(None),
        ).order_by(LegalIssueNode.created_at.desc())
    )
    return [_node_to_dict(row) for row in result.scalars()]


async def _list_active_edges(
    db: AsyncSession, tenant_id: str, case_id: str
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(LegalIssueEdge).where(
            LegalIssueEdge.tenant_id == tenant_id,
            LegalIssueEdge.case_id == case_id,
            LegalIssueEdge.deleted_at.is_(None),
        ).order_by(LegalIssueEdge.created_at.desc())
    )
    return [_edge_to_dict(row) for row in result.scalars()]


# ── Serialization ──


def _node_to_dict(node: LegalIssueNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "tenant_id": node.tenant_id,
        "case_id": node.case_id,
        "node_type": node.node_type,
        "title": node.title,
        "description": node.description,
        "status": node.status,
        "confidence": node.confidence,
        "source_type": node.source_type,
        "source_id": node.source_id,
        "metadata": node.metadata_json or {},
        "created_by": node.created_by,
        "created_at": node.created_at.isoformat() if node.created_at else "",
        "updated_at": node.updated_at.isoformat() if node.updated_at else "",
        "deleted_at": node.deleted_at.isoformat() if node.deleted_at else None,
    }


def _edge_to_dict(edge: LegalIssueEdge) -> dict[str, Any]:
    return {
        "id": edge.id,
        "tenant_id": edge.tenant_id,
        "case_id": edge.case_id,
        "source_node_id": edge.source_node_id,
        "target_node_id": edge.target_node_id,
        "relation_type": edge.relation_type,
        "description": edge.description,
        "weight": edge.weight,
        "metadata": edge.metadata_json or {},
        "created_by": edge.created_by,
        "created_at": edge.created_at.isoformat() if edge.created_at else "",
        "updated_at": edge.updated_at.isoformat() if edge.updated_at else "",
        "deleted_at": edge.deleted_at.isoformat() if edge.deleted_at else None,
    }
