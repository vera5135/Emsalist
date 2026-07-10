"""P2.3 — Case & conversation/message repository layer.

All queries are tenant-scoped and honour soft-delete (``deleted_at IS NULL``).
Callers own the transaction (``await db.commit()``); repository methods only
``flush`` so several operations can be batched atomically.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Case, Conversation, Message


def _now() -> datetime:
    return datetime.now(UTC)


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


class CaseRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        tenant_id: str,
        owner_user_id: str,
        title: str,
        legal_topic: str = "",
        event_text: str = "",
    ) -> Case:
        case = Case(
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            title=title,
            legal_topic=legal_topic,
            event_text=event_text or None,
            status="active",
            version=1,
        )
        session.add(case)
        await session.flush()
        return case

    @staticmethod
    async def get(
        session: AsyncSession, tenant_id: str, case_id: str
    ) -> Case | None:
        result = await session.execute(
            select(Case).where(
                Case.id == case_id,
                Case.tenant_id == tenant_id,
                Case.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list(
        session: AsyncSession,
        tenant_id: str,
        owner_user_id: str,
        *,
        include_archived: bool = False,
        archived_only: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Case], int]:
        conditions = [
            Case.tenant_id == tenant_id,
            Case.owner_user_id == owner_user_id,
            Case.deleted_at.is_(None),
        ]
        if archived_only:
            conditions.append(Case.status == "archived")
        elif not include_archived:
            conditions.append(Case.status == "active")

        count_result = await session.execute(
            select(func.count()).select_from(Case).where(*conditions)
        )
        total = int(count_result.scalar_one())

        result = await session.execute(
            select(Case)
            .where(*conditions)
            .order_by(Case.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def update(
        session: AsyncSession,
        case: Case,
        *,
        title: str | None = None,
        legal_topic: str | None = None,
        event_text: str | None = None,
    ) -> Case:
        if title is not None:
            case.title = title
        if legal_topic is not None:
            case.legal_topic = legal_topic
        if event_text is not None:
            case.event_text = event_text
        case.version += 1
        await session.flush()
        return case

    @staticmethod
    async def archive(session: AsyncSession, case: Case) -> Case:
        case.status = "archived"
        case.archived_at = _now()
        case.version += 1
        await session.flush()
        return case

    @staticmethod
    async def restore(session: AsyncSession, case: Case) -> Case:
        case.status = "active"
        case.archived_at = None
        case.version += 1
        await session.flush()
        return case

    @staticmethod
    async def soft_delete(session: AsyncSession, case: Case) -> None:
        case.status = "deleted"
        case.deleted_at = _now()
        await session.flush()


class ConversationRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        tenant_id: str,
        case_id: str,
        created_by: str,
        title: str = "",
    ) -> Conversation:
        conversation = Conversation(
            tenant_id=tenant_id,
            case_id=case_id,
            title=title,
            status="active",
            created_by=created_by,
        )
        session.add(conversation)
        await session.flush()
        return conversation

    @staticmethod
    async def get(
        session: AsyncSession, tenant_id: str, conversation_id: str
    ) -> Conversation | None:
        result = await session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.tenant_id == tenant_id,
                Conversation.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_or_create_for_case(
        session: AsyncSession,
        tenant_id: str,
        case_id: str,
        created_by: str,
    ) -> Conversation:
        result = await session.execute(
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.case_id == case_id,
                Conversation.deleted_at.is_(None),
            )
            .order_by(Conversation.created_at.asc())
            .limit(1)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing
        return await ConversationRepository.create(
            session, tenant_id, case_id, created_by
        )

    @staticmethod
    async def list_for_case(
        session: AsyncSession, tenant_id: str, case_id: str
    ) -> list[Conversation]:
        result = await session.execute(
            select(Conversation)
            .where(
                Conversation.tenant_id == tenant_id,
                Conversation.case_id == case_id,
                Conversation.deleted_at.is_(None),
            )
            .order_by(Conversation.created_at.asc())
        )
        return list(result.scalars().all())


class MessageRepository:
    @staticmethod
    async def get_by_client_request_id(
        session: AsyncSession, conversation_id: str, client_request_id: str
    ) -> Message | None:
        if not client_request_id:
            return None
        result = await session.execute(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.client_request_id == client_request_id,
                Message.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get(
        session: AsyncSession, tenant_id: str, message_id: str
    ) -> Message | None:
        result = await session.execute(
            select(Message).where(
                Message.id == message_id,
                Message.tenant_id == tenant_id,
                Message.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        tenant_id: str,
        case_id: str,
        conversation_id: str,
        role: str,
        content: str,
        client_request_id: str,
        created_by: str,
        status: str = "completed",
        parent_message_id: str | None = None,
    ) -> Message:
        message = Message(
            tenant_id=tenant_id,
            case_id=case_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            content_hash=content_hash(content),
            status=status,
            parent_message_id=parent_message_id,
            client_request_id=client_request_id,
            created_by=created_by,
            completed_at=_now() if status == "completed" else None,
        )
        session.add(message)
        await session.flush()
        return message

    @staticmethod
    async def list_for_conversation(
        session: AsyncSession,
        tenant_id: str,
        conversation_id: str,
        *,
        limit: int = 30,
        offset: int = 0,
    ) -> tuple[list[Message], int]:
        conditions = [
            Message.tenant_id == tenant_id,
            Message.conversation_id == conversation_id,
            Message.deleted_at.is_(None),
        ]
        count_result = await session.execute(
            select(func.count()).select_from(Message).where(*conditions)
        )
        total = int(count_result.scalar_one())
        result = await session.execute(
            select(Message)
            .where(*conditions)
            .order_by(Message.created_at.asc(), Message.id.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), total
