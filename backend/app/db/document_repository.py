"""P2.5 — Document / page / extraction repository + status state machine.

Tenant-scoped, soft-delete aware. Callers own the transaction. Optimistic
locking via ``version``; invalid status transitions raise
:class:`InvalidTransitionError`.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentExtraction, DocumentPage


def _now() -> datetime:
    return datetime.now(UTC)


# Canonical document statuses (P2.5 state machine).
STATUS_UPLOADING = "uploading"
STATUS_QUEUED = "queued"
STATUS_PROCESSING = "processing"
STATUS_ANALYZED = "analyzed"
STATUS_AWAITING = "awaiting_confirmation"
STATUS_FAILED = "failed"
STATUS_UNSUPPORTED = "unsupported"
STATUS_QUARANTINED = "quarantined"
STATUS_DELETED = "deleted"

_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    STATUS_UPLOADING: {STATUS_QUEUED, STATUS_QUARANTINED, STATUS_FAILED, STATUS_DELETED},
    STATUS_QUEUED: {STATUS_PROCESSING, STATUS_QUARANTINED, STATUS_FAILED, STATUS_DELETED},
    STATUS_PROCESSING: {
        STATUS_ANALYZED, STATUS_AWAITING, STATUS_UNSUPPORTED, STATUS_FAILED, STATUS_DELETED,
    },
    STATUS_ANALYZED: {STATUS_AWAITING, STATUS_DELETED, STATUS_QUEUED},
    STATUS_AWAITING: {STATUS_ANALYZED, STATUS_DELETED, STATUS_QUEUED},
    STATUS_UNSUPPORTED: {STATUS_DELETED, STATUS_QUEUED},
    STATUS_FAILED: {STATUS_QUEUED, STATUS_DELETED},
    STATUS_QUARANTINED: {STATUS_DELETED},  # never directly to analyzed
    STATUS_DELETED: set(),  # terminal
}


class InvalidTransitionError(Exception):
    def __init__(self, current: str, target: str):
        self.current = current
        self.target = target
        super().__init__(f"invalid transition {current} -> {target}")


class VersionConflictError(Exception):
    def __init__(self, expected: int, current: int):
        self.expected = expected
        self.current = current
        super().__init__(f"version conflict: expected {expected}, current {current}")


def can_transition(current: str, target: str) -> bool:
    return target in _ALLOWED_TRANSITIONS.get(current, set())


class DocumentRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        tenant_id: str,
        case_id: str,
        original_filename: str,
        safe_filename: str,
        extension: str,
        mime_type: str,
        size_bytes: int,
        sha256: str,
        storage_key: str,
        support_level: str,
        uploaded_by: str,
        document_type: str = "",
    ) -> Document:
        doc = Document(
            tenant_id=tenant_id,
            case_id=case_id,
            original_filename=original_filename,
            safe_filename=safe_filename,
            extension=extension,
            mime_type=mime_type,
            size_bytes=size_bytes,
            sha256=sha256,
            storage_key=storage_key,
            support_level=support_level,
            uploaded_by=uploaded_by,
            document_type=document_type,
            document_type_source="suggested",
            status=STATUS_UPLOADING,
            analysis_status="pending",
            version=1,
        )
        session.add(doc)
        await session.flush()
        return doc

    @staticmethod
    async def get(
        session: AsyncSession, tenant_id: str, case_id: str, document_id: str
    ) -> Document | None:
        result = await session.execute(
            select(Document).where(
                Document.id == document_id,
                Document.tenant_id == tenant_id,
                Document.case_id == case_id,
                Document.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def find_by_sha256(
        session: AsyncSession, tenant_id: str, case_id: str, sha256: str
    ) -> Document | None:
        result = await session.execute(
            select(Document).where(
                Document.tenant_id == tenant_id,
                Document.case_id == case_id,
                Document.sha256 == sha256,
                Document.deleted_at.is_(None),
            )
        )
        return result.scalars().first()

    @staticmethod
    async def list_for_case(
        session: AsyncSession,
        tenant_id: str,
        case_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Document], int]:
        conditions = [
            Document.tenant_id == tenant_id,
            Document.case_id == case_id,
            Document.deleted_at.is_(None),
        ]
        total = int(
            (await session.execute(
                select(func.count()).select_from(Document).where(*conditions)
            )).scalar_one()
        )
        result = await session.execute(
            select(Document).where(*conditions)
            .order_by(Document.created_at.desc())
            .limit(limit).offset(offset)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def transition(session: AsyncSession, doc: Document, target: str) -> Document:
        if doc.status == target:
            return doc
        if not can_transition(doc.status, target):
            raise InvalidTransitionError(doc.status, target)
        doc.status = target
        doc.version += 1
        await session.flush()
        return doc

    @staticmethod
    async def set_analysis(
        session: AsyncSession,
        doc: Document,
        *,
        analysis_status: str,
        page_count: int | None = None,
        extracted_text_available: bool | None = None,
        failure_code: str | None = None,
    ) -> Document:
        doc.analysis_status = analysis_status
        if page_count is not None:
            doc.page_count = page_count
        if extracted_text_available is not None:
            doc.extracted_text_available = extracted_text_available
        doc.failure_code = failure_code
        await session.flush()
        return doc

    @staticmethod
    async def set_document_type(
        session: AsyncSession, doc: Document, document_type: str, source: str
    ) -> Document:
        doc.document_type = document_type
        doc.document_type_source = source
        doc.version += 1
        await session.flush()
        return doc

    @staticmethod
    async def soft_delete(session: AsyncSession, doc: Document) -> None:
        doc.status = STATUS_DELETED
        doc.deleted_at = _now()
        await session.flush()


class DocumentPageRepository:
    @staticmethod
    async def replace_pages(
        session: AsyncSession,
        *,
        tenant_id: str,
        document_id: str,
        pages: list[tuple[int | None, str, str]],
    ) -> None:
        """pages = list of (page_number, text, extraction_status)."""
        from sqlalchemy import delete as _delete

        await session.execute(
            _delete(DocumentPage).where(DocumentPage.document_id == document_id)
        )
        import hashlib

        for index, (page_number, text, status) in enumerate(pages, start=1):
            session.add(DocumentPage(
                tenant_id=tenant_id,
                document_id=document_id,
                page_number=page_number if page_number is not None else index,
                text=text,
                text_hash=hashlib.sha256(text.encode("utf-8")).hexdigest() if text else "",
                extraction_status=status,
            ))
        await session.flush()

    @staticmethod
    async def list_for_document(
        session: AsyncSession, tenant_id: str, document_id: str
    ) -> list[DocumentPage]:
        result = await session.execute(
            select(DocumentPage)
            .where(
                DocumentPage.tenant_id == tenant_id,
                DocumentPage.document_id == document_id,
            )
            .order_by(DocumentPage.page_number.asc())
        )
        return list(result.scalars().all())


class DocumentExtractionRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        tenant_id: str,
        case_id: str,
        document_id: str,
        extraction_type: str,
        field_key: str,
        value: str,
        normalized_value: str,
        page_number: int | None,
        text_span: str,
        source_quote_hash: str,
        confidence: float,
        created_by: str,
        source_quote: str = "",
        provider_name: str = "deterministic",
        provider_model: str = "",
        analysis_run_id: str = "",
    ) -> DocumentExtraction:
        extraction = DocumentExtraction(
            tenant_id=tenant_id,
            case_id=case_id,
            document_id=document_id,
            extraction_type=extraction_type,
            field_key=field_key,
            value=value,
            normalized_value=normalized_value,
            page_number=page_number,
            text_span=text_span,
            source_quote=source_quote,
            source_quote_hash=source_quote_hash,
            confidence=confidence,
            verification_status="detected",
            provider_name=provider_name,
            provider_model=provider_model,
            analysis_run_id=analysis_run_id,
            created_by=created_by,
        )
        session.add(extraction)
        await session.flush()
        return extraction

    @staticmethod
    async def exists(
        session: AsyncSession, document_id: str, field_key: str, normalized_value: str
    ) -> bool:
        result = await session.execute(
            select(DocumentExtraction.id).where(
                DocumentExtraction.document_id == document_id,
                DocumentExtraction.field_key == field_key,
                DocumentExtraction.normalized_value == normalized_value,
                DocumentExtraction.deleted_at.is_(None),
            )
        )
        return result.first() is not None

    @staticmethod
    async def get(
        session: AsyncSession, tenant_id: str, case_id: str, extraction_id: str
    ) -> DocumentExtraction | None:
        result = await session.execute(
            select(DocumentExtraction).where(
                DocumentExtraction.id == extraction_id,
                DocumentExtraction.tenant_id == tenant_id,
                DocumentExtraction.case_id == case_id,
                DocumentExtraction.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_document(
        session: AsyncSession, tenant_id: str, document_id: str
    ) -> list[DocumentExtraction]:
        result = await session.execute(
            select(DocumentExtraction)
            .where(
                DocumentExtraction.tenant_id == tenant_id,
                DocumentExtraction.document_id == document_id,
                DocumentExtraction.deleted_at.is_(None),
            )
            .order_by(DocumentExtraction.created_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def set_status(
        session: AsyncSession,
        extraction: DocumentExtraction,
        verification_status: str,
        *,
        memory_fact_id: str | None = None,
    ) -> DocumentExtraction:
        extraction.verification_status = verification_status
        if memory_fact_id is not None:
            extraction.memory_fact_id = memory_fact_id
        extraction.version += 1
        await session.flush()
        return extraction
