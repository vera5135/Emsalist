"""Tenant/case-scoped repositories for the canonical P2.8 graph."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BurdenOfProof, Claim, Counterargument, Evidence, EvidenceClaimLink,
    EvidenceSufficiencyAssessment, LegalIssue, LegalIssueDependency,
    LegalIssueFactLink, LegalIssueRiskLink, LegalIssueSourceLink,
    LegalReasoningRun, MemoryRevision,
)


class LegalReasoningRepository:
    @staticmethod
    async def issue(session: AsyncSession, tenant_id: str, case_id: str, issue_id: str):
        result = await session.execute(select(LegalIssue).where(
            LegalIssue.id == issue_id, LegalIssue.tenant_id == tenant_id,
            LegalIssue.case_id == case_id, LegalIssue.deleted_at.is_(None),
        ))
        return result.scalar_one_or_none()

    @staticmethod
    async def issue_by_id(session: AsyncSession, tenant_id: str, issue_id: str):
        result = await session.execute(select(LegalIssue).where(
            LegalIssue.id == issue_id, LegalIssue.tenant_id == tenant_id,
            LegalIssue.deleted_at.is_(None),
        ))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_issues(session: AsyncSession, tenant_id: str, case_id: str):
        result = await session.execute(select(LegalIssue).where(
            LegalIssue.tenant_id == tenant_id, LegalIssue.case_id == case_id,
            LegalIssue.deleted_at.is_(None),
        ).order_by(LegalIssue.parent_issue_id.asc(), LegalIssue.created_at.asc(), LegalIssue.id.asc()))
        return list(result.scalars().all())

    @staticmethod
    async def list_runs(session: AsyncSession, tenant_id: str, case_id: str):
        result = await session.execute(select(LegalReasoningRun).where(
            LegalReasoningRun.tenant_id == tenant_id,
            LegalReasoningRun.case_id == case_id,
        ).order_by(LegalReasoningRun.created_at.desc(), LegalReasoningRun.id.desc()))
        return list(result.scalars().all())

    @staticmethod
    async def graph(session: AsyncSession, tenant_id: str, case_id: str, issue_id: str | None = None):
        issue_filter = [LegalIssue.tenant_id == tenant_id, LegalIssue.case_id == case_id,
                        LegalIssue.deleted_at.is_(None)]
        if issue_id:
            issue_filter.append(LegalIssue.id == issue_id)
        issues = list((await session.execute(select(LegalIssue).where(*issue_filter))).scalars().all())
        ids = [item.id for item in issues]
        async def rows(model):
            if not ids:
                return []
            return list((await session.execute(select(model).where(
                model.tenant_id == tenant_id, model.case_id == case_id,
                model.issue_id.in_(ids), model.deleted_at.is_(None),
            ))).scalars().all())
        return {
            "issues": issues,
            "fact_links": await rows(LegalIssueFactLink),
            "risk_links": await rows(LegalIssueRiskLink),
            "source_links": await rows(LegalIssueSourceLink),
            "dependencies": await rows(LegalIssueDependency),
            "burdens": await rows(BurdenOfProof),
            "assessments": await rows(EvidenceSufficiencyAssessment),
            "counterarguments": await rows(Counterargument),
        }

    @staticmethod
    async def add_evidence_link(session: AsyncSession, *, tenant_id: str, case_id: str,
                                issue_id: str, claim_id: str, evidence_id: str,
                                relation_type: str):
        # The assessment is the canonical issue/claim/evidence endpoint; the typed
        # evidence-claim relation remains reusable outside the issue graph.
        evidence = (await session.execute(select(Evidence).where(
            Evidence.id == evidence_id, Evidence.tenant_id == tenant_id,
            Evidence.case_id == case_id, Evidence.deleted_at.is_(None),
        ))).scalar_one_or_none()
        if evidence is None:
            return None
        claim = (await session.execute(select(Claim).where(
            Claim.id == claim_id, Claim.tenant_id == tenant_id,
            Claim.case_id == case_id, Claim.deleted_at.is_(None),
        ))).scalar_one_or_none()
        if claim is None:
            return None
        link = EvidenceClaimLink(tenant_id=tenant_id, case_id=case_id,
                                 claim_id=claim_id, evidence_id=evidence_id,
                                 relation_type=relation_type)
        session.add(link)
        await session.flush()
        return link

    @staticmethod
    async def add_source_link(session: AsyncSession, **values):
        link = LegalIssueSourceLink(**values)
        session.add(link)
        await session.flush()
        return link


def iso(value) -> str | None:
    return value.isoformat() if value is not None else None
