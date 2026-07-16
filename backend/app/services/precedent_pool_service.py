"""Case-scoped dynamic precedent pool persistence and analysis."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.auth_repository import CaseMemberRepository
from app.db.case_chat_repository import CaseRepository
from app.db.models import (
    PrecedentDecisionAnalysis,
    PrecedentPool,
    PrecedentPoolDecision,
    SourceParagraph,
    SourceRecord,
    SourceVersion,
    new_uuid,
)
from app.models.case_models import CaseSearchProfileResponse
from app.models.search_models import (
    AnalyzePrecedentPoolRequest,
    DynamicPrecedentIngestionRun,
    DynamicPrecedentPoolRequest,
    LegalSearchResult,
    PrecedentAnalysisResponse,
    PrecedentPoolDecisionResponse,
    PrecedentPoolDetail,
    PrecedentPoolSummary,
)
from app.services.auth_service import SecurityContext, get_auth_mode

PLANNER_VERSION = "p2.8-final-planner-1"
ANALYSIS_SCHEMA_VERSION = "p2.8-analysis-v1"
ANALYSIS_PROMPT_VERSION = "p2.8-source-grounded-analysis-1"


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _hash_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _profile_summary(profile: CaseSearchProfileResponse) -> dict[str, Any]:
    return {
        "case_id": profile.case_id,
        "legal_area": profile.legal_area,
        "dispute_type": profile.dispute_type,
        "party_roles": profile.party_roles,
        "claims": profile.claims,
        "legal_issues": profile.legal_issues,
        "evidence_issues": profile.evidence_issues,
        "legislation_hypotheses": profile.legislation_hypotheses,
        "missing_information": profile.missing_information,
        "extraction_mode": profile.extraction_mode,
        "confidence": profile.confidence,
    }


def profile_fingerprint(profile: CaseSearchProfileResponse) -> str:
    return _hash_json(_profile_summary(profile))


def input_fingerprint(request: DynamicPrecedentPoolRequest) -> str:
    return _hash_json({
        "case_id": request.case_id,
        "case_text_hash": hashlib.sha256(request.case_text.encode("utf-8")).hexdigest(),
        "preferred_relief": request.preferred_relief,
        "max_queries": request.max_queries,
        "max_candidates": request.max_candidates,
        "shortlist_size": request.shortlist_size,
    })


def query_strategy_summary(queries: list[str], budgets: list[int]) -> list[dict[str, Any]]:
    strategies: list[dict[str, Any]] = []
    for index, (query, budget) in enumerate(zip(queries, budgets), start=1):
        tokens = [token for token in query.split() if token]
        strategies.append({
            "strategy_index": index,
            "query_hash": hashlib.sha256(query.encode("utf-8")).hexdigest(),
            "token_count": len(tokens),
            "budget": budget,
            "planner_version": PLANNER_VERSION,
        })
    return strategies


async def authorize_case(
    db: AsyncSession,
    ctx: SecurityContext,
    case_id: str | None,
    *,
    write: bool,
) -> str:
    if not case_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="case_id is required")
    case = await CaseRepository.get(db, ctx.tenant_id, case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if get_auth_mode() == "local" or ctx.role == "tenant_admin":
        return case_id
    membership = await CaseMemberRepository.get_active_membership(db, ctx.tenant_id, case_id, ctx.actor_id)
    if membership is None or (write and membership.membership_role == "viewer"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return case_id


async def start_pool(
    db: AsyncSession,
    *,
    ctx: SecurityContext,
    request: DynamicPrecedentPoolRequest,
    profile: CaseSearchProfileResponse,
    queries: list[str],
    budgets: list[int],
) -> PrecedentPool:
    case_id = await authorize_case(db, ctx, request.case_id, write=True)
    fingerprint = profile_fingerprint(profile)
    result = await db.execute(
        select(PrecedentPool).where(
            PrecedentPool.tenant_id == ctx.tenant_id,
            PrecedentPool.case_id == case_id,
            PrecedentPool.profile_fingerprint == fingerprint,
            PrecedentPool.provider_code == "yargitay",
        )
    )
    pool = result.scalar_one_or_none()
    now = _now()
    if pool is None:
        pool = PrecedentPool(
            id=new_uuid(),
            tenant_id=ctx.tenant_id,
            case_id=case_id,
            initiated_by=ctx.actor_id,
            profile_fingerprint=fingerprint,
            input_fingerprint=input_fingerprint(request),
            query_strategies_json=query_strategy_summary(queries, budgets),
            provider_code="yargitay",
            candidate_cap=request.max_candidates,
            status="running",
            profile_summary_json=_profile_summary(profile),
            stats_json={},
            planner_version=PLANNER_VERSION,
            model_version=profile.extraction_mode,
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(pool)
    else:
        pool.initiated_by = ctx.actor_id
        pool.input_fingerprint = input_fingerprint(request)
        pool.query_strategies_json = query_strategy_summary(queries, budgets)
        pool.candidate_cap = request.max_candidates
        pool.status = "running"
        pool.safe_error_code = ""
        pool.provider_status = ""
        pool.source_ingestion_run_ids = []
        pool.profile_summary_json = _profile_summary(profile)
        pool.stats_json = {}
        pool.started_at = now
        pool.completed_at = None
        pool.updated_at = now
    await db.flush()
    return pool


async def complete_pool(
    db: AsyncSession,
    *,
    pool: PrecedentPool,
    ctx: SecurityContext,
    provider_status: str,
    runs: list[DynamicPrecedentIngestionRun],
    shortlist: list[LegalSearchResult],
) -> None:
    pool.provider_status = provider_status
    pool.status = provider_status
    pool.safe_error_code = next((run.safe_error_code for run in runs if run.safe_error_code), "")
    pool.source_ingestion_run_ids = [run.run_id for run in runs if run.run_id]
    pool.stats_json = {
        "total_discovered": sum(run.discovered for run in runs),
        "total_ingested": sum(run.ingested for run in runs),
        "total_duplicate": sum(run.duplicate for run in runs),
        "total_failed": sum(run.failed for run in runs),
    }
    pool.completed_at = _now()
    pool.updated_at = pool.completed_at

    seen_sources: dict[str, str] = {}
    for rank, result in enumerate(shortlist, start=1):
        existing = await db.execute(
            select(PrecedentPoolDecision).where(
                PrecedentPoolDecision.pool_id == pool.id,
                PrecedentPoolDecision.source_record_id == result.source_id,
                PrecedentPoolDecision.source_version_id == result.source_version_id,
            )
        )
        decision = existing.scalar_one_or_none()
        duplicate_of = seen_sources.get(result.source_id)
        selection_state = "duplicate" if duplicate_of else "shortlisted"
        if decision is None:
            decision = PrecedentPoolDecision(
                id=new_uuid(),
                pool_id=pool.id,
                tenant_id=ctx.tenant_id,
                case_id=pool.case_id,
                source_record_id=result.source_id,
                source_version_id=result.source_version_id,
            )
            db.add(decision)
        decision.selected_source_paragraph_ids = [result.source_paragraph_id] if result.source_paragraph_id else []
        decision.retrieval_rank = rank
        decision.scores_json = {
            "final_score": result.final_score,
            "lexical_score": result.lexical_score,
            "semantic_score": result.semantic_score,
            "authority_score": result.authority_score,
            "temporal_score": result.temporal_score,
            "case_context_score": result.case_context_score,
        }
        decision.selection_state = selection_state
        decision.duplicate_of_decision_id = duplicate_of
        decision.match_reasons_json = result.match_reasons
        decision.updated_at = _now()
        await db.flush()
        seen_sources.setdefault(result.source_id, decision.id)
    await db.flush()


async def list_pools(db: AsyncSession, ctx: SecurityContext, case_id: str) -> list[PrecedentPoolSummary]:
    await authorize_case(db, ctx, case_id, write=False)
    rows = list((await db.execute(
        select(PrecedentPool).where(
            PrecedentPool.tenant_id == ctx.tenant_id,
            PrecedentPool.case_id == case_id,
        ).order_by(PrecedentPool.created_at.desc())
    )).scalars().all())
    return [_pool_summary(row) for row in rows]


async def get_pool(db: AsyncSession, ctx: SecurityContext, pool_id: str) -> PrecedentPool:
    row = (await db.execute(
        select(PrecedentPool).where(
            PrecedentPool.id == pool_id,
            PrecedentPool.tenant_id == ctx.tenant_id,
        )
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Precedent pool not found")
    await authorize_case(db, ctx, row.case_id, write=False)
    return row


def pool_detail(pool: PrecedentPool) -> PrecedentPoolDetail:
    base = _pool_summary(pool).model_dump()
    return PrecedentPoolDetail(
        **base,
        query_strategies=pool.query_strategies_json or [],
        source_ingestion_run_ids=pool.source_ingestion_run_ids or [],
        planner_version=pool.planner_version,
        model_version=pool.model_version,
    )


async def list_pool_decisions(
    db: AsyncSession,
    ctx: SecurityContext,
    pool_id: str,
) -> list[PrecedentPoolDecisionResponse]:
    pool = await get_pool(db, ctx, pool_id)
    rows = (await db.execute(
        select(PrecedentPoolDecision, SourceRecord)
        .join(SourceRecord, SourceRecord.id == PrecedentPoolDecision.source_record_id)
        .where(PrecedentPoolDecision.pool_id == pool.id)
        .order_by(PrecedentPoolDecision.retrieval_rank.asc())
    )).all()
    responses: list[PrecedentPoolDecisionResponse] = []
    for decision, record in rows:
        paragraph = None
        paragraph_ids = decision.selected_source_paragraph_ids or []
        if paragraph_ids:
            paragraph = (await db.execute(
                select(SourceParagraph).where(
                    SourceParagraph.id == paragraph_ids[0],
                    SourceParagraph.source_version_id == decision.source_version_id,
                )
            )).scalar_one_or_none()
        responses.append(_decision_response(decision, record, paragraph))
    return responses


def _pool_summary(pool: PrecedentPool) -> PrecedentPoolSummary:
    stats = pool.stats_json or {}
    return PrecedentPoolSummary(
        id=pool.id,
        case_id=pool.case_id,
        provider_code=pool.provider_code,
        provider_status=pool.provider_status,
        status=pool.status,
        candidate_cap=pool.candidate_cap,
        total_discovered=int(stats.get("total_discovered", 0)),
        total_ingested=int(stats.get("total_ingested", 0)),
        total_duplicate=int(stats.get("total_duplicate", 0)),
        total_failed=int(stats.get("total_failed", 0)),
        safe_error_code=pool.safe_error_code,
        profile_summary=pool.profile_summary_json or {},
        started_at=_iso(pool.started_at) or "",
        completed_at=_iso(pool.completed_at),
    )


def _decision_response(
    decision: PrecedentPoolDecision,
    record: SourceRecord,
    paragraph: SourceParagraph | None,
) -> PrecedentPoolDecisionResponse:
    return PrecedentPoolDecisionResponse(
        id=decision.id,
        pool_id=decision.pool_id,
        source_record_id=decision.source_record_id,
        source_version_id=decision.source_version_id,
        selected_source_paragraph_ids=decision.selected_source_paragraph_ids or [],
        retrieval_rank=decision.retrieval_rank,
        scores=decision.scores_json or {},
        selection_state=decision.selection_state,
        duplicate_of_decision_id=decision.duplicate_of_decision_id,
        match_reasons=decision.match_reasons_json or [],
        title=record.title or "",
        court=record.court or "",
        chamber=record.chamber or "",
        case_number=record.case_number or "",
        decision_number=record.decision_number or "",
        decision_date=record.decision_date or "",
        official_url=record.official_url or "",
        relevant_paragraph=(paragraph.text if paragraph is not None else "")[:1000],
    )


class DeterministicDecisionAnalysisProvider:
    provider = "deterministic"
    model_version = "deterministic-source-analysis-1"
    prompt_version = ANALYSIS_PROMPT_VERSION
    schema_version = ANALYSIS_SCHEMA_VERSION

    def analyze(
        self,
        *,
        pool: PrecedentPool,
        decision: PrecedentPoolDecision,
        record: SourceRecord,
        version: SourceVersion,
        paragraphs: list[SourceParagraph],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        selected = [p for p in paragraphs if p.id in set(decision.selected_source_paragraph_ids or [])]
        if not selected:
            selected = paragraphs[:1]
        provenance: list[dict[str, Any]] = []
        relevant: list[dict[str, Any]] = []
        for paragraph in selected[:3]:
            text = paragraph.text or ""
            quote = text[:500]
            start = 0
            end = len(quote)
            if quote and quote not in text:
                continue
            provenance.append({
                "source_record_id": record.id,
                "source_version_id": version.id,
                "source_paragraph_id": paragraph.id,
                "start_offset": start,
                "end_offset": end,
            })
            relevant.append({
                "source_paragraph_id": paragraph.id,
                "text": quote,
                "start_offset": start,
                "end_offset": end,
            })

        facts_text = " ".join((p.text or "") for p in selected)
        analysis: dict[str, Any] = {
            "material_event_chronology": _sentences_with(facts_text, ("tarih", "satış", "teslim", "ihbar"))[:5],
            "claimant_request": _first_sentence_with(facts_text, ("dava", "talep", "istem")),
            "defendant_defense": _first_sentence_with(facts_text, ("savun", "cevap", "davalı")),
            "first_instance_result": _first_sentence_with(facts_text, ("mahkemece", "ilk derece", "karar veril")),
            "yargitay_legal_reasoning": _first_sentence_with(facts_text, ("gerek", "ayıp", "ispat", "bilirkişi")),
            "final_disposition": _first_sentence_with(facts_text, ("bozul", "onan", "düzeltil", "redd")),
            "applied_statutes": _statutes(facts_text),
            "burden_of_proof_findings": _sentences_with(facts_text, ("ispat", "delil", "bilirkişi"))[:3],
            "decisive_legal_issue": _first_non_empty(decision.match_reasons_json or []),
            "relevant_paragraphs": relevant,
            "similarities_to_case": _similarities(pool.profile_summary_json or {}, facts_text),
            "material_differences": pool.profile_summary_json.get("missing_information", [])[:5],
            "favorable_use": _first_sentence_with(facts_text, ("ayıp", "soruml", "tüketici")) or "",
            "adverse_opposing_use": _first_sentence_with(facts_text, ("ihbar", "zamanaş", "ispatlanamad")) or "",
            "relevance_score": float((decision.scores_json or {}).get("final_score") or 0.0),
            "confidence": 0.72 if relevant else 0.0,
            "missing_information": pool.profile_summary_json.get("missing_information", [])[:8],
        }
        return {k: v for k, v in analysis.items() if v not in ("", [], None)}, provenance


def _sentences_with(text: str, needles: tuple[str, ...]) -> list[str]:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    return [s[:800] for s in sentences if any(n in s.casefold() for n in needles)]


def _first_sentence_with(text: str, needles: tuple[str, ...]) -> str:
    found = _sentences_with(text, needles)
    return found[0] if found else ""


def _first_non_empty(values: list[Any]) -> str:
    for value in values:
        cleaned = str(value).strip()
        if cleaned:
            return cleaned
    return ""


def _statutes(text: str) -> list[dict[str, str]]:
    statutes: list[dict[str, str]] = []
    for match in re.finditer(r"\b(TBK|TKHK|HMK|TMK|TTK|İİK|TCK|CMK)\s*(?:m\.?|madde)?\s*(\d+)?", text, re.I):
        item = {"statute": match.group(1).upper()}
        if match.group(2):
            item["article"] = match.group(2)
        statutes.append(item)
    return statutes[:10]


def _similarities(profile_summary: dict[str, Any], text: str) -> list[str]:
    folded = text.casefold()
    similarities: list[str] = []
    for field in ("legal_issues", "evidence_issues", "claims"):
        for value in profile_summary.get(field, []):
            tokens = [token for token in str(value).casefold().split() if len(token) >= 5]
            if any(token in folded for token in tokens):
                similarities.append(str(value))
                break
    return similarities[:5]


def _contains_hidden_reasoning(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).casefold() in {"chain_of_thought", "hidden_reasoning", "reasoning_trace"}
            or _contains_hidden_reasoning(child)
            for key, child in value.items()
        )
    if isinstance(value, list):
        return any(_contains_hidden_reasoning(child) for child in value)
    return False


def _validate_provenance(
    analysis: dict[str, Any],
    provenance: list[dict[str, Any]],
    paragraphs_by_id: dict[str, SourceParagraph],
) -> None:
    if _contains_hidden_reasoning(analysis):
        raise ValueError("hidden reasoning fields are not allowed")
    for item in provenance:
        paragraph = paragraphs_by_id.get(str(item.get("source_paragraph_id", "")))
        if paragraph is None:
            raise ValueError("analysis provenance paragraph is missing")
        start = int(item.get("start_offset", 0))
        end = int(item.get("end_offset", 0))
        if start < 0 or end < start or end > len(paragraph.text or ""):
            raise ValueError("analysis provenance offsets are invalid")
    for paragraph_ref in analysis.get("relevant_paragraphs", []):
        paragraph = paragraphs_by_id.get(str(paragraph_ref.get("source_paragraph_id", "")))
        text = str(paragraph_ref.get("text", ""))
        if paragraph is None or text not in (paragraph.text or ""):
            raise ValueError("analysis quote is not present in source paragraph")


async def analyze_pool(
    db: AsyncSession,
    ctx: SecurityContext,
    pool_id: str,
    body: AnalyzePrecedentPoolRequest,
    *,
    provider: DeterministicDecisionAnalysisProvider | None = None,
) -> list[PrecedentAnalysisResponse]:
    pool = await get_pool(db, ctx, pool_id)
    provider = provider or DeterministicDecisionAnalysisProvider()
    query = select(PrecedentPoolDecision).where(PrecedentPoolDecision.pool_id == pool.id)
    if body.decision_ids:
        query = query.where(PrecedentPoolDecision.id.in_(body.decision_ids))
    decisions = list((await db.execute(query.order_by(PrecedentPoolDecision.retrieval_rank.asc()))).scalars().all())
    responses: list[PrecedentAnalysisResponse] = []
    for decision in decisions:
        record, version, paragraphs = await _source_bundle(db, decision)
        if not body.force:
            existing = await _current_analysis(db, decision.id, version.content_hash)
            if existing is not None:
                responses.append(_analysis_response(existing))
                continue
        await _mark_stale(db, decision.id, version.content_hash)
        analysis, provenance = provider.analyze(
            pool=pool, decision=decision, record=record, version=version, paragraphs=paragraphs,
        )
        _validate_provenance(analysis, provenance, {p.id: p for p in paragraphs})
        output_hash = _hash_json({"analysis": analysis, "provenance": provenance})
        row = PrecedentDecisionAnalysis(
            id=new_uuid(),
            pool_id=pool.id,
            pool_decision_id=decision.id,
            tenant_id=ctx.tenant_id,
            case_id=pool.case_id,
            source_record_id=record.id,
            source_version_id=version.id,
            provider=provider.provider,
            model_version=provider.model_version,
            prompt_version=provider.prompt_version,
            schema_version=provider.schema_version,
            source_fingerprint=version.content_hash,
            output_fingerprint=output_hash,
            analysis_json=analysis,
            provenance_json=provenance,
            status="current",
            stale=False,
            created_by=ctx.actor_id,
        )
        db.add(row)
        await db.flush()
        responses.append(_analysis_response(row))
    await db.commit()
    return responses


async def list_analyses(
    db: AsyncSession,
    ctx: SecurityContext,
    pool_id: str,
) -> list[PrecedentAnalysisResponse]:
    pool = await get_pool(db, ctx, pool_id)
    rows = list((await db.execute(
        select(PrecedentDecisionAnalysis).where(
            PrecedentDecisionAnalysis.pool_id == pool.id,
            PrecedentDecisionAnalysis.tenant_id == ctx.tenant_id,
        ).order_by(PrecedentDecisionAnalysis.created_at.desc())
    )).scalars().all())
    return [_analysis_response(row) for row in rows]


async def _source_bundle(
    db: AsyncSession,
    decision: PrecedentPoolDecision,
) -> tuple[SourceRecord, SourceVersion, list[SourceParagraph]]:
    row = (await db.execute(
        select(SourceRecord, SourceVersion).join(
            SourceVersion,
            SourceVersion.source_record_id == SourceRecord.id,
        ).where(
            SourceRecord.id == decision.source_record_id,
            SourceVersion.id == decision.source_version_id,
            SourceVersion.source_record_id == decision.source_record_id,
            SourceRecord.deleted_at.is_(None),
        )
    )).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source provenance not found")
    record, version = row
    paragraphs = list((await db.execute(
        select(SourceParagraph).where(
            SourceParagraph.source_version_id == version.id,
        ).order_by(SourceParagraph.paragraph_index.asc())
    )).scalars().all())
    return record, version, paragraphs


async def _current_analysis(
    db: AsyncSession,
    decision_id: str,
    source_fingerprint: str,
) -> PrecedentDecisionAnalysis | None:
    return (await db.execute(
        select(PrecedentDecisionAnalysis).where(
            PrecedentDecisionAnalysis.pool_decision_id == decision_id,
            PrecedentDecisionAnalysis.source_fingerprint == source_fingerprint,
            PrecedentDecisionAnalysis.status == "current",
            PrecedentDecisionAnalysis.stale.is_(False),
        ).order_by(PrecedentDecisionAnalysis.created_at.desc()).limit(1)
    )).scalar_one_or_none()


async def _mark_stale(db: AsyncSession, decision_id: str, source_fingerprint: str) -> None:
    rows = list((await db.execute(
        select(PrecedentDecisionAnalysis).where(
            PrecedentDecisionAnalysis.pool_decision_id == decision_id,
            PrecedentDecisionAnalysis.status == "current",
        )
    )).scalars().all())
    for row in rows:
        if row.source_fingerprint != source_fingerprint:
            row.status = "stale"
            row.stale = True
            row.updated_at = _now()
    await db.flush()


def _analysis_response(row: PrecedentDecisionAnalysis) -> PrecedentAnalysisResponse:
    return PrecedentAnalysisResponse(
        id=row.id,
        pool_id=row.pool_id,
        pool_decision_id=row.pool_decision_id,
        source_record_id=row.source_record_id,
        source_version_id=row.source_version_id,
        provider=row.provider,
        model_version=row.model_version,
        prompt_version=row.prompt_version,
        schema_version=row.schema_version,
        source_fingerprint=row.source_fingerprint,
        output_fingerprint=row.output_fingerprint,
        status=row.status,
        stale=row.stale,
        analysis=row.analysis_json or {},
        provenance=row.provenance_json or [],
        created_at=_iso(row.created_at) or "",
    )
