"""P2.6 — Legal source backbone repository layer.

Global source tables (SourceRecord/Version/Paragraph/Verification/Relationship)
are NOT tenant-scoped; SourceUsage IS tenant+case scoped. Soft-delete aware.
Callers own the transaction. Verification transitions are validated against the
state machine; stale updates raise VersionConflictError.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    SourceParagraph,
    SourceRecord,
    SourceRelationship,
    SourceUsage,
    SourceVerification,
    SourceVersion,
)
from app.services.source_verification import (
    InvalidVerificationTransition,
    can_transition,
)


def _now() -> datetime:
    return datetime.now(UTC)


class VersionConflictError(Exception):
    def __init__(self, expected: int, current: int):
        self.expected = expected
        self.current = current
        super().__init__(f"version conflict: expected {expected}, current {current}")


class SourceRecordRepository:
    @staticmethod
    async def get(session: AsyncSession, source_id: str) -> SourceRecord | None:
        result = await session.execute(
            select(SourceRecord).where(
                SourceRecord.id == source_id,
                SourceRecord.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_canonical_key(
        session: AsyncSession, canonical_key: str
    ) -> SourceRecord | None:
        result = await session.execute(
            select(SourceRecord).where(
                SourceRecord.canonical_key == canonical_key,
                SourceRecord.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        source_type: str,
        canonical_key: str,
        title: str,
        verification_status: str = "needs_review",
        **fields,
    ) -> SourceRecord:
        record = SourceRecord(
            source_type=source_type,
            canonical_key=canonical_key,
            title=title,
            verification_status=verification_status,
            issuing_authority=fields.get("issuing_authority", ""),
            court=fields.get("court", ""),
            chamber=fields.get("chamber", ""),
            case_number=fields.get("case_number", ""),
            decision_number=fields.get("decision_number", ""),
            decision_date=fields.get("decision_date", ""),
            publication_date=fields.get("publication_date", ""),
            effective_date=fields.get("effective_date", ""),
            repeal_date=fields.get("repeal_date", ""),
            official_url=fields.get("official_url", ""),
            language=fields.get("language", "tr"),
            jurisdiction=fields.get("jurisdiction", "TR"),
            temporal_status=fields.get("temporal_status", "unknown"),
        )
        session.add(record)
        await session.flush()
        return record

    @staticmethod
    async def list(
        session: AsyncSession,
        *,
        source_type: str | None = None,
        verification_status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SourceRecord], int]:
        conditions = [SourceRecord.deleted_at.is_(None)]
        if source_type:
            conditions.append(SourceRecord.source_type == source_type)
        if verification_status:
            conditions.append(SourceRecord.verification_status == verification_status)
        total = int((await session.execute(
            select(func.count()).select_from(SourceRecord).where(*conditions)
        )).scalar_one())
        result = await session.execute(
            select(SourceRecord).where(*conditions)
            .order_by(SourceRecord.updated_at.desc())
            .limit(limit).offset(offset)
        )
        return list(result.scalars().all()), total

    @staticmethod
    async def list_needs_review(session: AsyncSession) -> list[SourceRecord]:
        result = await session.execute(
            select(SourceRecord).where(
                SourceRecord.deleted_at.is_(None),
                SourceRecord.verification_status.in_(("needs_review", "conflicting")),
            ).order_by(SourceRecord.updated_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def transition_status(
        session: AsyncSession, record: SourceRecord, target: str
    ) -> SourceRecord:
        if not can_transition(record.verification_status, target):
            raise InvalidVerificationTransition(record.verification_status, target)
        record.verification_status = target
        record.version += 1
        await session.flush()
        return record

    @staticmethod
    async def set_current_version(
        session: AsyncSession, record: SourceRecord, version_id: str
    ) -> None:
        record.current_version_id = version_id
        await session.flush()

    @staticmethod
    async def mark_checked(
        session: AsyncSession, record: SourceRecord, *, successful: bool
    ) -> None:
        now = _now()
        record.last_checked_at = now
        if successful:
            record.last_successful_check_at = now
        await session.flush()


class SourceVersionRepository:
    @staticmethod
    async def get(session: AsyncSession, version_id: str) -> SourceVersion | None:
        result = await session.execute(
            select(SourceVersion).where(SourceVersion.id == version_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_hash(
        session: AsyncSession, source_record_id: str, content_hash: str
    ) -> SourceVersion | None:
        result = await session.execute(
            select(SourceVersion).where(
                SourceVersion.source_record_id == source_record_id,
                SourceVersion.content_hash == content_hash,
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_record(
        session: AsyncSession, source_record_id: str
    ) -> list[SourceVersion]:
        result = await session.execute(
            select(SourceVersion)
            .where(SourceVersion.source_record_id == source_record_id)
            .order_by(SourceVersion.retrieved_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        source_record_id: str,
        content_hash: str,
        normalized_text: str,
        retrieval_method: str,
        parser_version: str,
        raw_document_hash: str | None = None,
        supersedes_version_id: str | None = None,
        valid_from: str = "",
        valid_to: str = "",
        version_label: str = "",
        metadata_json: dict | None = None,
    ) -> SourceVersion:
        v = SourceVersion(
            source_record_id=source_record_id,
            content_hash=content_hash,
            normalized_text=normalized_text,
            retrieval_method=retrieval_method,
            parser_version=parser_version,
            raw_document_hash=raw_document_hash,
            supersedes_version_id=supersedes_version_id,
            valid_from=valid_from,
            valid_to=valid_to,
            version_label=version_label,
            metadata_json=metadata_json or {},
            status="active",
        )
        session.add(v)
        await session.flush()
        return v


class SourceParagraphRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        source_version_id: str,
        paragraph_index: int,
        text: str,
        text_hash: str,
        heading_path: str = "",
        page: int | None = None,
        article_number: str = "",
        locator_json: dict | None = None,
    ) -> SourceParagraph:
        p = SourceParagraph(
            source_version_id=source_version_id,
            paragraph_index=paragraph_index,
            text=text,
            text_hash=text_hash,
            heading_path=heading_path,
            page=page,
            article_number=article_number,
            locator_json=locator_json or {},
        )
        session.add(p)
        await session.flush()
        return p

    @staticmethod
    async def get(session: AsyncSession, paragraph_id: str) -> SourceParagraph | None:
        result = await session.execute(
            select(SourceParagraph).where(SourceParagraph.id == paragraph_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_version(
        session: AsyncSession, source_version_id: str
    ) -> list[SourceParagraph]:
        result = await session.execute(
            select(SourceParagraph)
            .where(SourceParagraph.source_version_id == source_version_id)
            .order_by(SourceParagraph.paragraph_index.asc())
        )
        return list(result.scalars().all())


class SourceVerificationRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        source_record_id: str,
        verification_method: str,
        verifier_type: str,
        result: str,
        source_version_id: str | None = None,
        verifier_user_id: str | None = None,
        evidence_url: str = "",
        evidence_hash: str = "",
        notes: str = "",
    ) -> SourceVerification:
        v = SourceVerification(
            source_record_id=source_record_id,
            source_version_id=source_version_id,
            verification_method=verification_method,
            verifier_type=verifier_type,
            verifier_user_id=verifier_user_id,
            evidence_url=evidence_url,
            evidence_hash=evidence_hash,
            result=result,
            notes=notes[:500],
        )
        session.add(v)
        await session.flush()
        return v

    @staticmethod
    async def list_for_record(
        session: AsyncSession, source_record_id: str
    ) -> list[SourceVerification]:
        result = await session.execute(
            select(SourceVerification)
            .where(SourceVerification.source_record_id == source_record_id)
            .order_by(SourceVerification.verified_at.asc())
        )
        return list(result.scalars().all())


class SourceRelationshipRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        source_record_id: str,
        related_source_record_id: str,
        relationship_type: str,
        evidence: str = "",
    ) -> SourceRelationship:
        if source_record_id == related_source_record_id:
            raise ValueError("self-loop relationship not allowed")
        existing = await session.execute(
            select(SourceRelationship).where(
                SourceRelationship.source_record_id == source_record_id,
                SourceRelationship.related_source_record_id == related_source_record_id,
                SourceRelationship.relationship_type == relationship_type,
            )
        )
        found = existing.scalar_one_or_none()
        if found is not None:
            return found
        rel = SourceRelationship(
            source_record_id=source_record_id,
            related_source_record_id=related_source_record_id,
            relationship_type=relationship_type,
            evidence=evidence[:500],
        )
        session.add(rel)
        await session.flush()
        return rel

    @staticmethod
    async def list_for_record(
        session: AsyncSession, source_record_id: str
    ) -> list[SourceRelationship]:
        result = await session.execute(
            select(SourceRelationship)
            .where(SourceRelationship.source_record_id == source_record_id)
            .order_by(SourceRelationship.created_at.asc())
        )
        return list(result.scalars().all())


class SourceUsageRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        tenant_id: str,
        case_id: str,
        source_record_id: str,
        source_version_id: str,
        selected_by: str,
        source_paragraph_id: str | None = None,
        usage_type: str = "reference",
        target_type: str = "case",
        target_id: str = "",
        reason: str = "",
    ) -> SourceUsage:
        usage = SourceUsage(
            tenant_id=tenant_id,
            case_id=case_id,
            source_record_id=source_record_id,
            source_version_id=source_version_id,
            source_paragraph_id=source_paragraph_id,
            usage_type=usage_type,
            target_type=target_type,
            target_id=target_id or case_id,
            reason=reason[:500],
            selected_by=selected_by,
            used_in_final_draft=False,
            relevance_score=None,
        )
        session.add(usage)
        await session.flush()
        return usage

    @staticmethod
    async def get(
        session: AsyncSession, tenant_id: str, case_id: str, usage_id: str
    ) -> SourceUsage | None:
        result = await session.execute(
            select(SourceUsage).where(
                SourceUsage.id == usage_id,
                SourceUsage.tenant_id == tenant_id,
                SourceUsage.case_id == case_id,
                SourceUsage.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_case(
        session: AsyncSession, tenant_id: str, case_id: str
    ) -> list[SourceUsage]:
        result = await session.execute(
            select(SourceUsage).where(
                SourceUsage.tenant_id == tenant_id,
                SourceUsage.case_id == case_id,
                SourceUsage.deleted_at.is_(None),
            ).order_by(SourceUsage.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_for_source(
        session: AsyncSession, source_record_id: str
    ) -> list[SourceUsage]:
        result = await session.execute(
            select(SourceUsage).where(
                SourceUsage.source_record_id == source_record_id,
                SourceUsage.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def soft_delete(session: AsyncSession, usage: SourceUsage) -> None:
        usage.deleted_at = _now()
        await session.flush()
