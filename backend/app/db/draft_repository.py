"""P2.9A — Grounded draft persistence repository + status state machine.

Tenant/case-scoped, soft-delete aware. Callers own the transaction.
Optimistic locking via ``version``; invalid status transitions raise
:class:`InvalidDraftTransitionError`. No draft text is ever logged here.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    DraftDocument,
    DraftParagraph,
    DraftParagraphIssueLink,
    DraftParagraphSourceLink,
)


def _now() -> datetime:
    return datetime.now(UTC)


# Canonical draft statuses (P2.9A state machine).
DRAFT_STATUS_DRAFT = "draft"
DRAFT_STATUS_REVIEWING = "reviewing"
DRAFT_STATUS_FINALIZED = "finalized"
DRAFT_STATUS_SUPERSEDED = "superseded"
DRAFT_STATUS_DELETED = "deleted"

# finalized is reachable only through the finalize endpoint; superseded only
# through a superseding draft creation. deleted and superseded are terminal.
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    DRAFT_STATUS_DRAFT: {DRAFT_STATUS_REVIEWING, DRAFT_STATUS_FINALIZED, DRAFT_STATUS_DELETED},
    DRAFT_STATUS_REVIEWING: {DRAFT_STATUS_DRAFT, DRAFT_STATUS_FINALIZED, DRAFT_STATUS_DELETED},
    DRAFT_STATUS_FINALIZED: {DRAFT_STATUS_SUPERSEDED},
    DRAFT_STATUS_SUPERSEDED: set(),  # terminal (history/audit preserved)
    DRAFT_STATUS_DELETED: set(),  # terminal
}

# Statuses whose content may still change (paragraph/link mutations allowed).
EDITABLE_DRAFT_STATUSES = frozenset({DRAFT_STATUS_DRAFT, DRAFT_STATUS_REVIEWING})


class InvalidDraftTransitionError(Exception):
    def __init__(self, current: str, target: str):
        self.current = current
        self.target = target
        super().__init__(f"invalid draft transition {current} -> {target}")


def can_transition(current: str, target: str) -> bool:
    return target in _ALLOWED_TRANSITIONS.get(current, set())


class DraftDocumentRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        tenant_id: str,
        case_id: str,
        title: str,
        draft_type: str,
        created_by: str,
        supersedes_draft_id: str | None = None,
    ) -> DraftDocument:
        draft = DraftDocument(
            tenant_id=tenant_id,
            case_id=case_id,
            title=title,
            draft_type=draft_type,
            status=DRAFT_STATUS_DRAFT,
            supersedes_draft_id=supersedes_draft_id,
            created_by=created_by,
            version=1,
        )
        session.add(draft)
        await session.flush()
        return draft

    @staticmethod
    async def get(
        session: AsyncSession, tenant_id: str, case_id: str, draft_id: str,
        *, include_deleted: bool = False,
    ) -> DraftDocument | None:
        query = select(DraftDocument).where(
            DraftDocument.id == draft_id,
            DraftDocument.tenant_id == tenant_id,
            DraftDocument.case_id == case_id,
        )
        if not include_deleted:
            query = query.where(DraftDocument.status != DRAFT_STATUS_DELETED)
        return (await session.execute(query)).scalar_one_or_none()

    @staticmethod
    async def list_for_case(
        session: AsyncSession, tenant_id: str, case_id: str,
    ) -> list[DraftDocument]:
        result = await session.execute(
            select(DraftDocument).where(
                DraftDocument.tenant_id == tenant_id,
                DraftDocument.case_id == case_id,
                DraftDocument.status != DRAFT_STATUS_DELETED,
            ).order_by(DraftDocument.created_at.asc(), DraftDocument.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    def transition(draft: DraftDocument, target: str) -> None:
        if not can_transition(draft.status, target):
            raise InvalidDraftTransitionError(draft.status, target)
        draft.status = target
        if target == DRAFT_STATUS_DELETED:
            draft.deleted_at = _now()
        if target == DRAFT_STATUS_FINALIZED:
            draft.finalized_at = _now()


class DraftParagraphRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        tenant_id: str,
        case_id: str,
        draft_document_id: str,
        paragraph_order: int,
        paragraph_type: str,
        text: str,
        generated_by: str = "user",
        model_name: str = "",
    ) -> DraftParagraph:
        paragraph = DraftParagraph(
            tenant_id=tenant_id,
            case_id=case_id,
            draft_document_id=draft_document_id,
            paragraph_order=paragraph_order,
            paragraph_type=paragraph_type,
            text=text,
            verification_status="pending_review",
            generated_by=generated_by,
            model_name=model_name,
            version=1,
        )
        session.add(paragraph)
        await session.flush()
        return paragraph

    @staticmethod
    async def get(
        session: AsyncSession, tenant_id: str, case_id: str,
        draft_document_id: str, paragraph_id: str,
    ) -> DraftParagraph | None:
        result = await session.execute(
            select(DraftParagraph).where(
                DraftParagraph.id == paragraph_id,
                DraftParagraph.tenant_id == tenant_id,
                DraftParagraph.case_id == case_id,
                DraftParagraph.draft_document_id == draft_document_id,
                DraftParagraph.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_draft(
        session: AsyncSession, tenant_id: str, draft_document_id: str,
    ) -> list[DraftParagraph]:
        result = await session.execute(
            select(DraftParagraph).where(
                DraftParagraph.tenant_id == tenant_id,
                DraftParagraph.draft_document_id == draft_document_id,
                DraftParagraph.deleted_at.is_(None),
            ).order_by(DraftParagraph.paragraph_order.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def active_order_exists(
        session: AsyncSession, draft_document_id: str, paragraph_order: int,
    ) -> bool:
        result = await session.execute(
            select(DraftParagraph.id).where(
                DraftParagraph.draft_document_id == draft_document_id,
                DraftParagraph.paragraph_order == paragraph_order,
                DraftParagraph.deleted_at.is_(None),
            )
        )
        return result.first() is not None

    @staticmethod
    def soft_delete(paragraph: DraftParagraph) -> None:
        paragraph.deleted_at = _now()


class DraftParagraphIssueLinkRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        tenant_id: str,
        case_id: str,
        draft_paragraph_id: str,
        legal_issue_id: str,
        created_by: str,
        relation_type: str = "issue_drafted_in_paragraph",
    ) -> DraftParagraphIssueLink:
        link = DraftParagraphIssueLink(
            tenant_id=tenant_id,
            case_id=case_id,
            draft_paragraph_id=draft_paragraph_id,
            legal_issue_id=legal_issue_id,
            relation_type=relation_type,
            created_by=created_by,
            version=1,
        )
        session.add(link)
        await session.flush()
        return link

    @staticmethod
    async def get(
        session: AsyncSession, tenant_id: str, case_id: str,
        draft_paragraph_id: str, link_id: str,
    ) -> DraftParagraphIssueLink | None:
        result = await session.execute(
            select(DraftParagraphIssueLink).where(
                DraftParagraphIssueLink.id == link_id,
                DraftParagraphIssueLink.tenant_id == tenant_id,
                DraftParagraphIssueLink.case_id == case_id,
                DraftParagraphIssueLink.draft_paragraph_id == draft_paragraph_id,
                DraftParagraphIssueLink.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def active_exists(
        session: AsyncSession, tenant_id: str, case_id: str,
        draft_paragraph_id: str, legal_issue_id: str,
    ) -> bool:
        result = await session.execute(
            select(DraftParagraphIssueLink.id).where(
                DraftParagraphIssueLink.tenant_id == tenant_id,
                DraftParagraphIssueLink.case_id == case_id,
                DraftParagraphIssueLink.draft_paragraph_id == draft_paragraph_id,
                DraftParagraphIssueLink.legal_issue_id == legal_issue_id,
                DraftParagraphIssueLink.deleted_at.is_(None),
            )
        )
        return result.first() is not None

    @staticmethod
    async def list_for_paragraphs(
        session: AsyncSession, tenant_id: str, paragraph_ids: list[str],
    ) -> list[DraftParagraphIssueLink]:
        if not paragraph_ids:
            return []
        result = await session.execute(
            select(DraftParagraphIssueLink).where(
                DraftParagraphIssueLink.tenant_id == tenant_id,
                DraftParagraphIssueLink.draft_paragraph_id.in_(paragraph_ids),
                DraftParagraphIssueLink.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())


class DraftParagraphSourceLinkRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        tenant_id: str,
        case_id: str,
        draft_paragraph_id: str,
        source_record_id: str,
        source_version_id: str,
        source_paragraph_id: str,
        usage_type: str,
        quote_hash: str,
        created_by: str,
        verification_status: str = "verified",
    ) -> DraftParagraphSourceLink:
        link = DraftParagraphSourceLink(
            tenant_id=tenant_id,
            case_id=case_id,
            draft_paragraph_id=draft_paragraph_id,
            source_record_id=source_record_id,
            source_version_id=source_version_id,
            source_paragraph_id=source_paragraph_id,
            usage_type=usage_type,
            quote_hash=quote_hash,
            verification_status=verification_status,
            created_by=created_by,
            version=1,
        )
        session.add(link)
        await session.flush()
        return link

    @staticmethod
    async def get(
        session: AsyncSession, tenant_id: str, case_id: str,
        draft_paragraph_id: str, link_id: str,
    ) -> DraftParagraphSourceLink | None:
        result = await session.execute(
            select(DraftParagraphSourceLink).where(
                DraftParagraphSourceLink.id == link_id,
                DraftParagraphSourceLink.tenant_id == tenant_id,
                DraftParagraphSourceLink.case_id == case_id,
                DraftParagraphSourceLink.draft_paragraph_id == draft_paragraph_id,
                DraftParagraphSourceLink.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def active_exists(
        session: AsyncSession, tenant_id: str, case_id: str, draft_paragraph_id: str,
        source_record_id: str, source_version_id: str, source_paragraph_id: str,
    ) -> bool:
        result = await session.execute(
            select(DraftParagraphSourceLink.id).where(
                DraftParagraphSourceLink.tenant_id == tenant_id,
                DraftParagraphSourceLink.case_id == case_id,
                DraftParagraphSourceLink.draft_paragraph_id == draft_paragraph_id,
                DraftParagraphSourceLink.source_record_id == source_record_id,
                DraftParagraphSourceLink.source_version_id == source_version_id,
                DraftParagraphSourceLink.source_paragraph_id == source_paragraph_id,
                DraftParagraphSourceLink.deleted_at.is_(None),
            )
        )
        return result.first() is not None

    @staticmethod
    async def list_for_paragraphs(
        session: AsyncSession, tenant_id: str, paragraph_ids: list[str],
    ) -> list[DraftParagraphSourceLink]:
        if not paragraph_ids:
            return []
        result = await session.execute(
            select(DraftParagraphSourceLink).where(
                DraftParagraphSourceLink.tenant_id == tenant_id,
                DraftParagraphSourceLink.draft_paragraph_id.in_(paragraph_ids),
                DraftParagraphSourceLink.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())
