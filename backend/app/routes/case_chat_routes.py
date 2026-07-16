"""P2.3 — DB-backed Case CRUD and conversation/message endpoints.

Every route is tenant-scoped via the authenticated ``SecurityContext`` and
enforces ownership so a user can never read or mutate another tenant's or
another user's case (IDOR protection). Message content is never logged.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.case_chat_repository import (
    CaseRepository,
    ConversationRepository,
    MessageRepository,
)
from app.db.models import Case, Conversation
from app.db.session import get_session
from app.models.case_chat_models import (
    CaseCreateRequest,
    CaseListResponse,
    CaseResponse,
    CaseUpdateRequest,
    ConversationListResponse,
    ConversationResponse,
    MessageCreateRequest,
    MessageListResponse,
    MessageResponse,
)
from app.services.auth_service import SecurityContext, resolve_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cases", tags=["Cases"])
conversation_router = APIRouter(tags=["Conversations"])


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


def _case_to_response(case: Case) -> CaseResponse:
    return CaseResponse(
        id=case.id,
        title=case.title,
        legal_topic=case.legal_topic,
        status=case.status,
        version=case.version,
        created_at=_iso(case.created_at) or "",
        updated_at=_iso(case.updated_at) or "",
        archived_at=_iso(case.archived_at),
    )


def _conversation_to_response(conv: Conversation) -> ConversationResponse:
    return ConversationResponse(
        id=conv.id,
        case_id=conv.case_id,
        title=conv.title,
        status=conv.status,
        created_at=_iso(conv.created_at) or "",
    )


def _message_to_response(m) -> MessageResponse:
    return MessageResponse(
        id=m.id,
        conversation_id=m.conversation_id,
        case_id=m.case_id,
        role=m.role,
        content=m.content,
        status=m.status,
        parent_message_id=m.parent_message_id,
        client_request_id=m.client_request_id,
        created_at=_iso(m.created_at) or "",
        completed_at=_iso(m.completed_at),
    )


async def _load_owned_case(
    db: AsyncSession, ctx: SecurityContext, case_id: str
) -> Case:
    case = await CaseRepository.get(db, ctx.tenant_id, case_id)
    if case is None or case.owner_user_id != ctx.actor_id:
        # Same 404 for "not found" and "not yours" — no existence disclosure.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Case not found"
        )
    return case


# ---------------------------------------------------------------------------
# Case CRUD
# ---------------------------------------------------------------------------
@router.post("", response_model=CaseResponse, status_code=201, operation_id="case_create")
async def create_case(
    body: CaseCreateRequest,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> CaseResponse:
    from app.db.auth_repository import AuthAuditRepository, CaseMemberRepository

    case = await CaseRepository.create(
        db,
        tenant_id=ctx.tenant_id,
        owner_user_id=ctx.actor_id,
        title=(body.title or "").strip(),
        legal_topic=body.legal_topic.strip(),
        event_text=body.initial_narrative.strip(),
    )
    await CaseMemberRepository.ensure_member(
        db,
        case_id=case.id,
        tenant_id=ctx.tenant_id,
        user_id=ctx.actor_id,
        role="owner",
    )
    await AuthAuditRepository.write_event(
        db, ctx.tenant_id, ctx.actor_id, case.id, "case_created", "success",
        {"resource": "case"},
    )
    await db.commit()
    return _case_to_response(case)


@router.get("", response_model=CaseListResponse, operation_id="case_list")
async def list_cases(
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
    archived: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> CaseListResponse:
    cases, total = await CaseRepository.list(
        db,
        ctx.tenant_id,
        ctx.actor_id,
        archived_only=archived,
        limit=limit,
        offset=offset,
    )
    return CaseListResponse(
        items=[_case_to_response(c) for c in cases],
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + len(cases)) < total,
    )


@router.get("/{case_id}", response_model=CaseResponse, operation_id="case_get")
async def get_case(
    case_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> CaseResponse:
    case = await _load_owned_case(db, ctx, case_id)
    return _case_to_response(case)


@router.patch("/{case_id}", response_model=CaseResponse, operation_id="case_update")
async def update_case(
    case_id: str,
    body: CaseUpdateRequest,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> CaseResponse:
    from app.db.auth_repository import AuthAuditRepository

    case = await _load_owned_case(db, ctx, case_id)
    await CaseRepository.update(
        db,
        case,
        title=body.title.strip() if body.title is not None else None,
        legal_topic=body.legal_topic.strip() if body.legal_topic is not None else None,
        event_text=body.event_text if body.event_text is not None else None,
    )
    await AuthAuditRepository.write_event(
        db, ctx.tenant_id, ctx.actor_id, case.id, "case_updated", "success",
        {"resource": "case"},
    )
    await db.commit()
    return _case_to_response(case)


@router.post("/{case_id}/archive", response_model=CaseResponse, operation_id="case_archive")
async def archive_case(
    case_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> CaseResponse:
    from app.db.auth_repository import AuthAuditRepository

    case = await _load_owned_case(db, ctx, case_id)
    await CaseRepository.archive(db, case)
    await AuthAuditRepository.write_event(
        db, ctx.tenant_id, ctx.actor_id, case.id, "case_archived", "success",
        {"resource": "case"},
    )
    await db.commit()
    return _case_to_response(case)


@router.post("/{case_id}/restore", response_model=CaseResponse, operation_id="case_restore")
async def restore_case(
    case_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> CaseResponse:
    from app.db.auth_repository import AuthAuditRepository

    case = await _load_owned_case(db, ctx, case_id)
    await CaseRepository.restore(db, case)
    await AuthAuditRepository.write_event(
        db, ctx.tenant_id, ctx.actor_id, case.id, "case_restored", "success",
        {"resource": "case"},
    )
    await db.commit()
    return _case_to_response(case)


@router.delete("/{case_id}", status_code=204, operation_id="case_delete")
async def delete_case(
    case_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> None:
    from app.db.auth_repository import AuthAuditRepository

    case = await _load_owned_case(db, ctx, case_id)
    await CaseRepository.soft_delete(db, case)
    await AuthAuditRepository.write_event(
        db, ctx.tenant_id, ctx.actor_id, case.id, "case_deleted", "success",
        {"resource": "case"},
    )
    await db.commit()
    return None


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------
@router.post(
    "/{case_id}/conversations",
    response_model=ConversationResponse,
    status_code=201,
    operation_id="conversation_create",
)
async def create_or_get_conversation(
    case_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> ConversationResponse:
    case = await _load_owned_case(db, ctx, case_id)
    conv = await ConversationRepository.get_or_create_for_case(
        db, ctx.tenant_id, case.id, ctx.actor_id
    )
    await db.commit()
    return _conversation_to_response(conv)


@router.get(
    "/{case_id}/conversations",
    response_model=ConversationListResponse,
    operation_id="conversation_list",
)
async def list_conversations(
    case_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> ConversationListResponse:
    case = await _load_owned_case(db, ctx, case_id)
    conversations = await ConversationRepository.list_for_case(
        db, ctx.tenant_id, case.id
    )
    return ConversationListResponse(
        items=[_conversation_to_response(c) for c in conversations]
    )


# ---------------------------------------------------------------------------
# Messages (mounted under /conversations/{conversation_id})
# ---------------------------------------------------------------------------
async def _load_owned_conversation(
    db: AsyncSession, ctx: SecurityContext, conversation_id: str
) -> Conversation:
    conv = await ConversationRepository.get(db, ctx.tenant_id, conversation_id)
    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )
    # Verify the parent case is owned by the caller (IDOR guard across tenants).
    case = await CaseRepository.get(db, ctx.tenant_id, conv.case_id)
    if case is None or case.owner_user_id != ctx.actor_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        )
    return conv


@conversation_router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessageListResponse,
    operation_id="message_list",
)
async def list_messages(
    conversation_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
    limit: int = Query(default=30, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> MessageListResponse:
    conv = await _load_owned_conversation(db, ctx, conversation_id)
    messages, total = await MessageRepository.list_for_conversation(
        db, ctx.tenant_id, conv.id, limit=limit, offset=offset
    )
    return MessageListResponse(
        items=[_message_to_response(m) for m in messages],
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + len(messages)) < total,
    )


@conversation_router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=201,
    operation_id="message_create",
)
async def create_message(
    conversation_id: str,
    body: MessageCreateRequest,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> MessageResponse:
    from app.db.auth_repository import AuthAuditRepository

    conv = await _load_owned_conversation(db, ctx, conversation_id)

    client_request_id = (body.client_request_id or "").strip() or uuid.uuid4().hex
    existing = await MessageRepository.get_by_client_request_id(
        db, conv.id, client_request_id
    )
    if existing is not None:
        # Idempotent replay — return the original without creating a duplicate.
        return _message_to_response(existing)

    message = await MessageRepository.create(
        db,
        tenant_id=ctx.tenant_id,
        case_id=conv.case_id,
        conversation_id=conv.id,
        role="user",
        content=body.content,
        client_request_id=client_request_id,
        created_by=ctx.actor_id,
        status="completed",
    )
    await AuthAuditRepository.write_event(
        db, ctx.tenant_id, ctx.actor_id, conv.case_id, "message_created", "success",
        {"resource": "message", "conversation_id": conv.id},
    )
    await db.commit()
    return _message_to_response(message)
