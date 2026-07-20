"""Seed a synthetic development web demo case.

This script is explicit opt-in and refuses to run outside development/test.
It creates no passwords or secrets; local auth issues demo tokens separately.
"""
from __future__ import annotations

import asyncio
import os

from sqlalchemy import select

from app.config import get_settings
from app.db.auth_repository import CaseMemberRepository
from app.db.case_chat_repository import CaseRepository
from app.db.models import (
    CaseFact,
    Claim,
    Evidence,
    EvidenceClaimLink,
    LegalIssue,
    LegalIssueSourceLink,
    SourceUsage,
    Tenant,
    TimelineEvent,
    User,
)
from app.db.session import get_sessionmaker
from app.db.source_repository import (
    SourceParagraphRepository,
    SourceRecordRepository,
    SourceUsageRepository,
    SourceVersionRepository,
)
from app.services import source_paragraphs


TENANT_ID = "local"
USER_ID = "local-user"
CASE_TITLE = "Synthetic Web Demo Case"
CASE_TOPIC = "Synthetic contract dispute"
SOURCE_KEY = "demo:web:synthetic-contract-note:v1"


def _guard() -> None:
    settings = get_settings()
    if settings.environment not in {"development", "test"}:
        raise SystemExit("web_demo_seed_refused_outside_development")
    if os.getenv("EMSALIST_DEMO_SEED_ENABLED", "").lower() not in {"1", "true", "yes"}:
        raise SystemExit("set EMSALIST_DEMO_SEED_ENABLED=1 to seed demo data")


async def _ensure_case(db) -> str:
    tenant = await db.get(Tenant, TENANT_ID)
    if tenant is None:
        db.add(Tenant(id=TENANT_ID, slug="local", name="Local Demo Tenant"))
    user = await db.get(User, USER_ID)
    if user is None:
        db.add(
            User(
                id=USER_ID,
                tenant_id=TENANT_ID,
                email_normalized="demo.local@emsalist.invalid",
                display_name="Synthetic Demo User",
                role="lawyer",
                status="active",
            )
        )
    await db.flush()

    cases, _total = await CaseRepository.list(
        db,
        TENANT_ID,
        USER_ID,
        include_archived=True,
        limit=200,
    )
    for case in cases:
        if case.title == CASE_TITLE:
            await CaseMemberRepository.ensure_member(
                db, case.id, TENANT_ID, USER_ID, "owner"
            )
            return case.id

    case = await CaseRepository.create(
        db,
        tenant_id=TENANT_ID,
        owner_user_id=USER_ID,
        title=CASE_TITLE,
        legal_topic=CASE_TOPIC,
        event_text=(
            "Synthetic demo narrative: a supplier delivered a non-conforming "
            "test item, the buyer documented the defect, and the parties need "
            "a lawyer-reviewed draft."
        ),
    )
    await CaseMemberRepository.ensure_member(db, case.id, TENANT_ID, USER_ID, "owner")
    return case.id


async def _ensure_facts(db, case_id: str) -> None:
    existing = {
        row.fact_type
        for row in (
            await db.execute(
                select(CaseFact).where(
                    CaseFact.tenant_id == TENANT_ID,
                    CaseFact.case_id == case_id,
                    CaseFact.deleted_at.is_(None),
                )
            )
        ).scalars()
    }
    facts = {
        "court_name": "Synthetic Civil Court",
        "party_client": "Synthetic Buyer",
        "party_opponent": "Synthetic Supplier",
    }
    for fact_type, value in facts.items():
        if fact_type in existing:
            continue
        db.add(
            CaseFact(
                tenant_id=TENANT_ID,
                case_id=case_id,
                fact_type=fact_type,
                value=value,
                normalized_value=value.casefold(),
                source_type="synthetic_demo_seed",
                verification_status="user_confirmed",
                importance="high",
                created_by=USER_ID,
            )
        )

    has_timeline = (
        await db.execute(
            select(TimelineEvent.id).where(
                TimelineEvent.tenant_id == TENANT_ID,
                TimelineEvent.case_id == case_id,
                TimelineEvent.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if has_timeline is None:
        db.add(
            TimelineEvent(
                tenant_id=TENANT_ID,
                case_id=case_id,
                event_type="delivery",
                description="Synthetic item delivery and defect notice.",
                event_date="2026-07-01",
                verification_status="user_confirmed",
                source_type="synthetic_demo_seed",
                created_by=USER_ID,
            )
        )


async def _ensure_issue_and_source(db, case_id: str) -> str:
    issue = (
        await db.execute(
            select(LegalIssue).where(
                LegalIssue.tenant_id == TENANT_ID,
                LegalIssue.case_id == case_id,
                LegalIssue.issue_code == "synthetic_delivery_defect",
                LegalIssue.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if issue is None:
        issue = LegalIssue(
            tenant_id=TENANT_ID,
            case_id=case_id,
            issue_code="synthetic_delivery_defect",
            title="Synthetic delivery conformity issue",
            description="Whether the synthetic delivered item conforms to the agreed baseline.",
            status="accepted",
            confidence=0.95,
        )
        db.add(issue)
        await db.flush()

    record = await SourceRecordRepository.get_by_canonical_key(db, SOURCE_KEY)
    text = (
        "Synthetic verified source paragraph. In a controlled demo dispute, "
        "a buyer may request repair, replacement, or refund when a delivered "
        "item materially diverges from the agreed synthetic baseline."
    )
    normalized = source_paragraphs.normalize_text(text)
    content_hash = source_paragraphs.content_hash(normalized)
    if record is None:
        record = await SourceRecordRepository.create(
            db,
            source_type="secondary",
            canonical_key=SOURCE_KEY,
            title="Synthetic Verified Demo Source",
            verification_status="editor_verified",
            issuing_authority="Emsalist Synthetic Demo",
            jurisdiction="TR",
        )
        version = await SourceVersionRepository.create(
            db,
            source_record_id=record.id,
            content_hash=content_hash,
            normalized_text=normalized,
            retrieval_method="synthetic_demo_seed",
            parser_version="synthetic-demo-v1",
            metadata_json={"source_type": "secondary"},
        )
        paragraph = await SourceParagraphRepository.create(
            db,
            source_version_id=version.id,
            paragraph_index=1,
            text=normalized,
            text_hash=source_paragraphs.text_hash(normalized),
        )
        await SourceRecordRepository.set_current_version(db, record, version.id)
    else:
        versions = await SourceVersionRepository.list_for_record(db, record.id)
        current = [v for v in versions if v.id == record.current_version_id]
        version = current[0] if current else versions[0]
        paragraphs = await SourceParagraphRepository.list_for_version(db, version.id)
        paragraph = paragraphs[0]

    existing_usage = (
        await db.execute(
            select(SourceUsage).where(
                SourceUsage.tenant_id == TENANT_ID,
                SourceUsage.case_id == case_id,
                SourceUsage.source_record_id == record.id,
                SourceUsage.source_version_id == version.id,
                SourceUsage.source_paragraph_id == paragraph.id,
                SourceUsage.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing_usage is None:
        await SourceUsageRepository.create(
            db,
            tenant_id=TENANT_ID,
            case_id=case_id,
            source_record_id=record.id,
            source_version_id=version.id,
            source_paragraph_id=paragraph.id,
            usage_type="reference",
            target_type="case",
            target_id=case_id,
            reason="Synthetic demo source selected for draft generation.",
            selected_by=USER_ID,
        )

    existing_link = (
        await db.execute(
            select(LegalIssueSourceLink).where(
                LegalIssueSourceLink.tenant_id == TENANT_ID,
                LegalIssueSourceLink.case_id == case_id,
                LegalIssueSourceLink.issue_id == issue.id,
                LegalIssueSourceLink.source_record_id == record.id,
                LegalIssueSourceLink.source_version_id == version.id,
                LegalIssueSourceLink.source_paragraph_id == paragraph.id,
                LegalIssueSourceLink.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing_link is None:
        db.add(
            LegalIssueSourceLink(
                tenant_id=TENANT_ID,
                case_id=case_id,
                issue_id=issue.id,
                source_record_id=record.id,
                source_version_id=version.id,
                source_paragraph_id=paragraph.id,
                relation_type="source_governs_issue",
            )
        )
    return issue.id


async def _ensure_claim(db, case_id: str) -> None:
    claim = (
        await db.execute(
            select(Claim).where(
                Claim.tenant_id == TENANT_ID,
                Claim.case_id == case_id,
                Claim.claim_type == "synthetic_remedy",
                Claim.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if claim is None:
        claim = Claim(
            tenant_id=TENANT_ID,
            case_id=case_id,
            claim_type="synthetic_remedy",
            title="Synthetic remedy request",
            description="Request a controlled remedy for the synthetic defect.",
            requested_relief="Repair, replacement, or refund in the synthetic scenario.",
            verification_status="user_confirmed",
            created_by=USER_ID,
        )
        db.add(claim)
        await db.flush()
    evidence = (
        await db.execute(
            select(Evidence).where(
                Evidence.tenant_id == TENANT_ID,
                Evidence.case_id == case_id,
                Evidence.title == "Synthetic defect notice",
                Evidence.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if evidence is None:
        evidence = Evidence(
            tenant_id=TENANT_ID,
            case_id=case_id,
            evidence_type="synthetic_notice",
            title="Synthetic defect notice",
            description="Synthetic notice documenting the controlled defect.",
            reliability_status="reliable",
            admissibility_status="admissible",
            verification_status="document_verified",
            created_by=USER_ID,
        )
        db.add(evidence)
        await db.flush()
    link = (
        await db.execute(
            select(EvidenceClaimLink).where(
                EvidenceClaimLink.tenant_id == TENANT_ID,
                EvidenceClaimLink.case_id == case_id,
                EvidenceClaimLink.claim_id == claim.id,
                EvidenceClaimLink.evidence_id == evidence.id,
                EvidenceClaimLink.relation_type == "evidence_supports_claim",
                EvidenceClaimLink.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if link is None:
        db.add(
            EvidenceClaimLink(
                tenant_id=TENANT_ID,
                case_id=case_id,
                claim_id=claim.id,
                evidence_id=evidence.id,
                relation_type="evidence_supports_claim",
            )
        )


async def seed() -> str:
    _guard()
    async with get_sessionmaker()() as db:
        case_id = await _ensure_case(db)
        await _ensure_facts(db, case_id)
        await _ensure_issue_and_source(db, case_id)
        await _ensure_claim(db, case_id)
        await db.commit()
        return case_id


def main() -> None:
    case_id = asyncio.run(seed())
    print(f"Seeded synthetic web demo case: {case_id}")


if __name__ == "__main__":
    main()
