"""P2.4 — Structured case memory repository layer.

All queries are tenant-scoped and honour soft-delete (``deleted_at IS NULL``).
Callers own the transaction (``await db.commit()``); repository methods only
``flush``. Optimistic locking is enforced via the ``version`` column: a stale
``expected_version`` raises :class:`VersionConflictError` (mapped to HTTP 409).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Claim,
    Contradiction,
    Deadline,
    Defense,
    Evidence,
    MissingInformation,
    Risk,
    TimelineEvent,
)
from app.db.models import CaseFact


def _now() -> datetime:
    return datetime.now(UTC)


class VersionConflictError(Exception):
    """Raised when an update targets a stale row version."""

    def __init__(self, expected: int, current: int):
        self.expected = expected
        self.current = current
        super().__init__(f"version conflict: expected {expected}, current {current}")


# Verification statuses that count as "trusted" for completion/risk rules.
CONFIRMED_STATUSES = frozenset(
    {"user_confirmed", "document_verified", "uyap_verified"}
)


def _normalize(value: str) -> str:
    return " ".join(value.strip().casefold().split())


class CaseFactRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        tenant_id: str,
        case_id: str,
        fact_type: str,
        value: str,
        created_by: str,
        source_type: str = "user_message",
        source_id: str = "",
        confidence: float = 0.0,
        importance: str = "medium",
        verification_status: str = "suggested",
    ) -> CaseFact:
        fact = CaseFact(
            tenant_id=tenant_id,
            case_id=case_id,
            fact_type=fact_type,
            value=value,
            normalized_value=_normalize(value),
            source_type=source_type,
            source_id=source_id,
            confidence=confidence,
            importance=importance,
            verification_status=verification_status,
            created_by=created_by,
        )
        session.add(fact)
        await session.flush()
        return fact

    @staticmethod
    async def get(
        session: AsyncSession, tenant_id: str, case_id: str, fact_id: str
    ) -> CaseFact | None:
        result = await session.execute(
            select(CaseFact).where(
                CaseFact.id == fact_id,
                CaseFact.tenant_id == tenant_id,
                CaseFact.case_id == case_id,
                CaseFact.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_case(
        session: AsyncSession, tenant_id: str, case_id: str
    ) -> list[CaseFact]:
        result = await session.execute(
            select(CaseFact)
            .where(
                CaseFact.tenant_id == tenant_id,
                CaseFact.case_id == case_id,
                CaseFact.deleted_at.is_(None),
            )
            .order_by(CaseFact.created_at.asc(), CaseFact.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def update(
        session: AsyncSession,
        fact: CaseFact,
        expected_version: int,
        *,
        value: str | None = None,
        importance: str | None = None,
    ) -> CaseFact:
        if fact.version != expected_version:
            raise VersionConflictError(expected_version, fact.version)
        if value is not None:
            fact.value = value
            fact.normalized_value = _normalize(value)
        if importance is not None:
            fact.importance = importance
        fact.version += 1
        await session.flush()
        return fact

    @staticmethod
    async def set_status(
        session: AsyncSession, fact: CaseFact, verification_status: str
    ) -> CaseFact:
        fact.verification_status = verification_status
        fact.version += 1
        await session.flush()
        return fact


class TimelineRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        tenant_id: str,
        case_id: str,
        event_type: str,
        description: str,
        created_by: str,
        event_date: str = "",
        event_time: str = "",
        is_approximate: bool = False,
        party_reference: str = "",
        legal_significance: str = "",
        source_type: str = "user_message",
        source_id: str = "",
    ) -> TimelineEvent:
        event = TimelineEvent(
            tenant_id=tenant_id,
            case_id=case_id,
            event_type=event_type,
            description=description,
            event_date=event_date,
            event_time=event_time,
            is_approximate=is_approximate,
            party_reference=party_reference,
            legal_significance=legal_significance,
            source_type=source_type,
            source_id=source_id,
            created_by=created_by,
        )
        session.add(event)
        await session.flush()
        return event

    @staticmethod
    async def list_for_case(
        session: AsyncSession, tenant_id: str, case_id: str
    ) -> list[TimelineEvent]:
        # Undated events sort last; dated events ascending by date then time.
        result = await session.execute(
            select(TimelineEvent)
            .where(
                TimelineEvent.tenant_id == tenant_id,
                TimelineEvent.case_id == case_id,
                TimelineEvent.deleted_at.is_(None),
            )
            .order_by(
                (TimelineEvent.event_date == "").asc(),
                TimelineEvent.event_date.asc(),
                TimelineEvent.event_time.asc(),
                TimelineEvent.created_at.asc(),
            )
        )
        return list(result.scalars().all())


class MissingInformationRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        tenant_id: str,
        case_id: str,
        field_key: str,
        label: str,
        created_by: str,
        reason_required: str = "",
        importance: str = "medium",
        related_legal_issue: str = "",
        expected_source: str = "",
        completion_condition: dict | None = None,
    ) -> MissingInformation:
        item = MissingInformation(
            tenant_id=tenant_id,
            case_id=case_id,
            field_key=field_key,
            label=label,
            reason_required=reason_required,
            importance=importance,
            related_legal_issue=related_legal_issue,
            expected_source=expected_source,
            completion_condition=completion_condition or {},
            status="open",
            created_by=created_by,
        )
        session.add(item)
        await session.flush()
        return item

    @staticmethod
    async def get(
        session: AsyncSession, tenant_id: str, case_id: str, item_id: str
    ) -> MissingInformation | None:
        result = await session.execute(
            select(MissingInformation).where(
                MissingInformation.id == item_id,
                MissingInformation.tenant_id == tenant_id,
                MissingInformation.case_id == case_id,
                MissingInformation.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_case(
        session: AsyncSession, tenant_id: str, case_id: str
    ) -> list[MissingInformation]:
        result = await session.execute(
            select(MissingInformation)
            .where(
                MissingInformation.tenant_id == tenant_id,
                MissingInformation.case_id == case_id,
                MissingInformation.deleted_at.is_(None),
            )
            .order_by(MissingInformation.created_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    def completion_satisfied(
        item: MissingInformation, facts: list[CaseFact]
    ) -> CaseFact | None:
        """Returns the fact that satisfies the completion condition, or None.

        A missing-information item is only completable by a concrete, verified
        value — never merely by the presence of a fact category. The condition
        may require: matching ``fact_type``, a non-empty value, and a
        verification_status within an allowed set.
        """
        cond = item.completion_condition or {}
        required_type = cond.get("fact_type") or item.field_key
        allowed_statuses = set(
            cond.get("verification_status_in", list(CONFIRMED_STATUSES))
        )
        value_required = cond.get("value_required", True)
        for fact in facts:
            if fact.fact_type != required_type:
                continue
            if value_required and not fact.value.strip():
                continue
            if fact.verification_status not in allowed_statuses:
                continue
            return fact
        return None

    @staticmethod
    async def resolve(
        session: AsyncSession, item: MissingInformation, fact: CaseFact
    ) -> MissingInformation:
        item.status = "supplied"
        item.resolved_by_fact_id = fact.id
        item.resolved_at = _now()
        item.version += 1
        await session.flush()
        return item


class ContradictionRepository:
    @staticmethod
    async def get(
        session: AsyncSession, tenant_id: str, case_id: str, cid: str
    ) -> Contradiction | None:
        result = await session.execute(
            select(Contradiction).where(
                Contradiction.id == cid,
                Contradiction.tenant_id == tenant_id,
                Contradiction.case_id == case_id,
                Contradiction.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_case(
        session: AsyncSession, tenant_id: str, case_id: str
    ) -> list[Contradiction]:
        result = await session.execute(
            select(Contradiction)
            .where(
                Contradiction.tenant_id == tenant_id,
                Contradiction.case_id == case_id,
                Contradiction.deleted_at.is_(None),
            )
            .order_by(Contradiction.created_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def find_open_for_subject(
        session: AsyncSession, tenant_id: str, case_id: str, subject_key: str
    ) -> Contradiction | None:
        result = await session.execute(
            select(Contradiction).where(
                Contradiction.tenant_id == tenant_id,
                Contradiction.case_id == case_id,
                Contradiction.subject_key == subject_key,
                Contradiction.status == "open",
                Contradiction.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        tenant_id: str,
        case_id: str,
        contradiction_type: str,
        subject_key: str,
        description: str,
        fact_ids: list[str],
        severity: str,
        created_by: str,
    ) -> Contradiction:
        contradiction = Contradiction(
            tenant_id=tenant_id,
            case_id=case_id,
            contradiction_type=contradiction_type,
            subject_key=subject_key,
            description=description,
            fact_ids=fact_ids,
            severity=severity,
            status="open",
            created_by=created_by,
        )
        session.add(contradiction)
        await session.flush()
        return contradiction

    @staticmethod
    async def detect_for_fact_type(
        session: AsyncSession,
        tenant_id: str,
        case_id: str,
        fact_type: str,
        created_by: str,
    ) -> Contradiction | None:
        """Deterministically detects conflicting values for one fact_type.

        Two or more non-deleted, non-rejected facts of the same ``fact_type``
        with different normalized values raise a contradiction. No LLM is used.
        Idempotent: reuses an open contradiction for the same subject_key.
        """
        facts = [
            f
            for f in await CaseFactRepository.list_for_case(session, tenant_id, case_id)
            if f.fact_type == fact_type and f.verification_status != "rejected"
        ]
        distinct_values = {f.normalized_value for f in facts if f.normalized_value}
        if len(distinct_values) < 2:
            return None

        subject_key = f"fact:{fact_type}"
        existing = await ContradictionRepository.find_open_for_subject(
            session, tenant_id, case_id, subject_key
        )
        fact_ids = [f.id for f in facts]
        if existing is not None:
            existing.fact_ids = fact_ids
            await session.flush()
            return existing

        # Mark the conflicting facts so they never appear as trusted values.
        for f in facts:
            if f.verification_status not in ("rejected",):
                f.verification_status = "conflicting"
        return await ContradictionRepository.create(
            session,
            tenant_id=tenant_id,
            case_id=case_id,
            contradiction_type="value_mismatch",
            subject_key=subject_key,
            description=f"'{fact_type}' için {len(distinct_values)} farklı değer bulundu.",
            fact_ids=fact_ids,
            severity="high",
            created_by=created_by,
        )

    @staticmethod
    async def resolve(
        session: AsyncSession,
        contradiction: Contradiction,
        *,
        resolution_fact: CaseFact,
        resolved_by: str,
        note: str = "",
    ) -> Contradiction:
        """Resolves by confirming the chosen fact; other facts are preserved as
        rejected/conflicting, never deleted."""
        contradiction.status = "resolved"
        contradiction.resolution_fact_id = resolution_fact.id
        contradiction.resolution_note = note
        contradiction.resolved_by = resolved_by
        contradiction.resolved_at = _now()
        contradiction.version += 1

        for fact_id in contradiction.fact_ids or []:
            fact = await CaseFactRepository.get(
                session, contradiction.tenant_id, contradiction.case_id, fact_id
            )
            if fact is None:
                continue
            if fact.id == resolution_fact.id:
                fact.verification_status = "user_confirmed"
            else:
                # Preserve, do not delete.
                fact.verification_status = "rejected"
            fact.version += 1
        await session.flush()
        return contradiction


class RiskRepository:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        tenant_id: str,
        case_id: str,
        risk_type: str,
        severity: str,
        title: str,
        created_by: str,
        rationale: str = "",
        affected_claim: str = "",
        supporting_reference: str = "",
        mitigation: str = "",
        related_missing_information: str | None = None,
        source_type: str = "system_inference",
        source_id: str = "",
    ) -> Risk:
        risk = Risk(
            tenant_id=tenant_id,
            case_id=case_id,
            risk_type=risk_type,
            severity=severity,
            title=title,
            rationale=rationale,
            affected_claim=affected_claim,
            supporting_reference=supporting_reference,
            mitigation=mitigation,
            related_missing_information=related_missing_information,
            source_type=source_type,
            source_id=source_id,
            created_by=created_by,
        )
        session.add(risk)
        await session.flush()
        return risk

    @staticmethod
    async def get(
        session: AsyncSession, tenant_id: str, case_id: str, risk_id: str
    ) -> Risk | None:
        result = await session.execute(
            select(Risk).where(
                Risk.id == risk_id,
                Risk.tenant_id == tenant_id,
                Risk.case_id == case_id,
                Risk.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_case(
        session: AsyncSession, tenant_id: str, case_id: str
    ) -> list[Risk]:
        result = await session.execute(
            select(Risk)
            .where(
                Risk.tenant_id == tenant_id,
                Risk.case_id == case_id,
                Risk.deleted_at.is_(None),
            )
            .order_by(Risk.created_at.asc())
        )
        return list(result.scalars().all())


_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def overall_risk_level(
    risks: list[Risk],
    *,
    open_critical_contradiction: bool,
    critical_missing: bool,
) -> str:
    """Computes the case's overall risk band.

    Rules (P2.4 §9): a low band is impossible while a critical value/date is
    missing or an unresolved critical contradiction exists. Otherwise the band
    is the maximum severity of active risks.
    """
    level = 0
    for r in risks:
        if r.status in ("open", "accepted"):
            level = max(level, _SEVERITY_ORDER.get(r.severity, 0))
    if critical_missing or open_critical_contradiction:
        level = max(level, _SEVERITY_ORDER["medium"])
    for name, value in _SEVERITY_ORDER.items():
        if value == level:
            return name
    return "low"
