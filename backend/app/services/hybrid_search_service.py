"""P2.7 — Hybrid legal search pipeline service."""
from __future__ import annotations

import hashlib
import json
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import (
    Case,
    SearchFeedback,
    SearchQuery,
    SourceParagraph,
    SourceRecord,
    SourceRelationship,
    SourceVersion,
)
from app.db.session import get_sessionmaker
from app.db.source_repository import (
    SourceParagraphRepository,
    SourceRecordRepository,
    SourceRelationshipRepository,
    SourceVersionRepository,
)
from app.models.search_models import (
    LegalSearchRequest,
    LegalSearchResponse,
    LegalSearchResult,
    OpposingSearchRequest,
    OpposingSearchResponse,
    SearchFeedbackRequest,
    SearchFeedbackResponse,
    SearchSuggestionResponse,
    SimilarSearchRequest,
    SimilarSearchResponse,
)
from app.services.search_embedding_provider import (
    SearchEmbeddingProvider,
    create_embedding_provider,
    is_sensitive_query,
)
from app.services.search_privacy import (
    compute_filter_hash,
    compute_index_version,
    compute_query_hash,
    sign_cursor,
    sign_result_id,
    verify_cursor,
    verify_result_id,
)
from app.services.search_query_grammar import (
    MalformedQueryError,
    SearchQueryPlan,
    normalize_phrase,
    parse_query,
    _tokens,
    _tokenset,
)
from app.services.source_ingestion_service import resolve_version_verification_status
from app.services.source_verification import (
    IndexEligibility,
    index_eligibility,
    evaluate_source_validity,
    TRUSTED_STATUSES,
)

MAX_CANDIDATE_POOL = 5000


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


# ── Lexical retrieval ──────────────────────────────────────────────────────────


async def _retrieve_lexical_candidates(
    session: AsyncSession,
    plan: SearchQueryPlan,
    max_candidates: int,
) -> list[dict]:
    positive = plan.positive_clauses()
    if not positive:
        return []

    conditions = []
    for clause in positive:
        normalized = normalize_phrase(clause)
        if not normalized:
            continue
        conditions.append(SourceParagraph.text.ilike(f"%{normalized}%"))
        conditions.append(SourceParagraph.heading_path.ilike(f"%{normalized}%"))
        conditions.append(SourceParagraph.article_number.ilike(f"%{normalized}%"))

    if not conditions:
        return []

    query = (
        select(SourceParagraph, SourceVersion, SourceRecord)
        .join(SourceVersion, SourceParagraph.source_version_id == SourceVersion.id)
        .join(SourceRecord, SourceVersion.source_record_id == SourceRecord.id)
        .where(
            or_(*conditions),
            SourceRecord.deleted_at.is_(None),
            SourceVersion.status == "active",
        )
        .limit(max_candidates)
    )
    result = await session.execute(query)
    rows = result.all()

    candidates = []
    for par, ver, rec in rows:
        candidates.append({
            "source_record": rec,
            "source_version": ver,
            "source_paragraph": par,
            "origin": "lexical",
        })
    return candidates


# ── Semantic retrieval ─────────────────────────────────────────────────────────


async def _retrieve_semantic_candidates(
    session: AsyncSession,
    plan: SearchQueryPlan,
    provider: SearchEmbeddingProvider,
    max_candidates: int,
) -> list[dict]:
    semantic_text = plan.semantic_query()
    if not semantic_text or not provider.is_available:
        return []

    query_embedding = provider.embed_query(semantic_text)
    if not query_embedding:
        return []

    rows_result = await session.execute(
        select(SourceParagraph, SourceVersion, SourceRecord)
        .join(SourceVersion, SourceParagraph.source_version_id == SourceVersion.id)
        .join(SourceRecord, SourceVersion.source_record_id == SourceRecord.id)
        .where(
            SourceParagraph.embedding_status == "indexed",
            SourceRecord.deleted_at.is_(None),
            SourceVersion.status == "active",
        )
        .limit(max_candidates * 2)
    )
    rows = rows_result.all()

    scored = []
    for par, ver, rec in rows:
        try:
            vec = json.loads(par.embedding_vector_json or "[]")
        except (json.JSONDecodeError, TypeError):
            continue
        if not vec:
            continue
        sim = _cosine_similarity(query_embedding, vec)
        if sim > 0.3:
            scored.append((sim, {
                "source_record": rec,
                "source_version": ver,
                "source_paragraph": par,
                "origin": "semantic",
            }))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:max_candidates]]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Scoring helpers ────────────────────────────────────────────────────────────


def _lexical_score(plan: SearchQueryPlan, text: str) -> float:
    if not text or not plan.positive_clauses():
        return 0.0
    normalized = normalize_phrase(text)
    tokens = _tokenset(normalized)
    positive = [c for c in plan.positive_clauses() if c]
    if not positive:
        return 0.0
    hits = 0.0
    for clause in positive:
        n = normalize_phrase(clause)
        if n in normalized:
            hits += 1.0
        else:
            clause_tokens = set(_tokens(n))
            overlap = clause_tokens & tokens
            if overlap:
                hits += 0.3 * len(overlap) / max(len(clause_tokens), 1)
    return min(hits / len(positive), 1.0)


def _authority_score(eligibility: IndexEligibility) -> float:
    weight_map = {
        "full_weight": 1.0,
        "reduced_weight": 0.7,
        "low_weight": 0.4,
        "historical_only": 0.2,
    }
    return weight_map.get(eligibility.weight, 0.0)


# ── Main search pipeline ───────────────────────────────────────────────────────


async def execute_legal_search(
    db: AsyncSession,
    request: LegalSearchRequest,
    security_context,
) -> LegalSearchResponse:
    settings = get_settings()
    secret = settings.jwt_secret_key or "emsalist-local-dev-key-change-in-production"
    max_candidates = min(settings.search_max_candidate_pool, MAX_CANDIDATE_POOL)

    # 1. Parse query grammar
    try:
        plan = parse_query(request.query)
    except MalformedQueryError as e:
        from fastapi import HTTPException
        from fastapi import status
        raise HTTPException(status_code=422, detail=str(e))

    # 2. Verify case ownership
    if request.case_id:
        case_result = await db.execute(
            select(Case).where(
                Case.id == request.case_id,
                Case.tenant_id == security_context.tenant_id,
                Case.deleted_at.is_(None),
            )
        )
        case = case_result.scalar_one_or_none()
        if case is None:
            from fastapi import HTTPException
            from fastapi import status
            raise HTTPException(status_code=404, detail="Dava bulunamadi.")

    # 3. Compute query_hash
    query_hash = compute_query_hash(plan, security_context.tenant_id, secret)

    # 4. Compute safe_query_summary
    safe_summary = plan.safe_summary()

    # 5. Build filters dict
    filters = {}
    if request.source_types:
        filters["source_types"] = sorted(request.source_types)
    if request.date_range:
        filters["date_range"] = list(request.date_range)
    if request.court:
        filters["court"] = request.court
    if request.official_only:
        filters["official_only"] = True
    filters_json = {"filters": filters}

    # 6. Compute index_version
    index_version = await compute_index_version(db)

    # 7. Create SearchQuery record
    search_query = SearchQuery(
        id=_new_id(),
        tenant_id=security_context.tenant_id,
        user_id=security_context.actor_id,
        case_id=request.case_id,
        query_hash=query_hash,
        safe_query_summary=safe_summary,
        filters_json=filters_json,
        index_version=index_version,
    )
    db.add(search_query)
    await db.flush()

    # 8. Cursor pagination check
    cursor_data = None
    if request.cursor:
        cursor_data = verify_cursor(request.cursor, secret)
        if cursor_data is None:
            from fastapi import HTTPException
            from fastapi import status
            raise HTTPException(status_code=422, detail="Geçersiz sayfalama imleci.")
        if cursor_data.get("query_hash_binding") != query_hash:
            from fastapi import HTTPException
            from fastapi import status
            raise HTTPException(status_code=422, detail="Imleç sorgu ile uyuşmuyor. Lütfen yeniden arayın.")

    # 9. Retrieve lexical candidates
    lexical_candidates = await _retrieve_lexical_candidates(db, plan, max_candidates)

    # 10. Semantic retrieval (if enabled and not sensitive)
    provider = create_embedding_provider(settings)
    semantic_available = provider.is_available
    degraded_mode = False
    semantic_candidates = []

    if semantic_available and not is_sensitive_query(plan.semantic_query()):
        semantic_candidates = await _retrieve_semantic_candidates(db, plan, provider, max_candidates)
    else:
        degraded_mode = provider.is_available  # available but skipped due to sensitivity

    if not semantic_available:
        degraded_mode = True

    # 11. Union candidates by (source_version_id, paragraph_id)
    candidate_map: dict[tuple[str, str], dict] = {}
    for c in lexical_candidates:
        key = (c["source_version"].id, c["source_paragraph"].id)
        if key not in candidate_map:
            candidate_map[key] = c
    for c in semantic_candidates:
        key = (c["source_version"].id, c["source_paragraph"].id)
        if key not in candidate_map:
            candidate_map[key] = c
        else:
            existing = candidate_map[key]
            existing["origin"] = existing.get("origin", "") + "+semantic"

    candidates = list(candidate_map.values())
    if not candidates:
        return LegalSearchResponse(
            results=[],
            total=0,
            has_more=False,
            semantic_available=semantic_available,
            degraded_mode=degraded_mode,
            query_id=search_query.id,
        )

    # 12. Resolve verification status & eligibility
    for c in candidates:
        rec = c["source_record"]
        ver = c["source_version"]
        resolved_status = await resolve_version_verification_status(
            db, rec.id, ver.id, rec.verification_status
        )
        c["resolved_status"] = resolved_status
        c["eligibility"] = index_eligibility(resolved_status)

    # 13. Apply index_eligibility filter
    candidates = [c for c in candidates if c["eligibility"].eligible]

    # 14. Apply hard grammar constraints
    candidates = [
        c for c in candidates
        if plan.matches((c["source_paragraph"].text or "") + " " + (c["source_paragraph"].heading_path or ""))
    ]

    # 15. Apply metadata/temporal filters
    if request.source_types:
        candidates = [
            c for c in candidates
            if c["source_record"].source_type in request.source_types
        ]
    if request.court:
        court_lower = request.court.lower()
        candidates = [
            c for c in candidates
            if court_lower in (c["source_record"].court or "").lower()
        ]
    if request.official_only:
        from app.services.source_verification import VERIFIED_OFFICIAL
        candidates = [
            c for c in candidates
            if c["resolved_status"] == VERIFIED_OFFICIAL
        ]
    if request.date_range:
        start, end = request.date_range
        filtered = []
        for c in candidates:
            rec = c["source_record"]
            dates = [
                rec.decision_date or "",
                rec.publication_date or "",
                rec.effective_date or "",
            ]
            for d in dates:
                if d and start <= d <= end:
                    filtered.append(c)
                    break
        candidates = filtered

    if not candidates:
        return LegalSearchResponse(
            results=[],
            total=0,
            has_more=False,
            semantic_available=semantic_available,
            degraded_mode=degraded_mode,
            query_id=search_query.id,
        )

    # 16. Compute scores
    weighted = []
    for c in candidates:
        lex = _lexical_score(plan, c["source_paragraph"].text or "")
        authority = _authority_score(c["eligibility"])
        para = c["source_paragraph"]
        text = (para.text or "") + " " + (para.heading_path or "")
        sem = 0.0
        if semantic_available and c.get("origin", "").endswith("+semantic"):
            sem_candidates = [sc for sc in semantic_candidates if sc["source_paragraph"].id == para.id]
            if sem_candidates:
                sem = 0.7  # was semantically matched

        w_lex = 0.35
        w_sem = 0.30
        w_auth = 0.15
        w_temp = 0.10
        w_case = 0.10

        if not semantic_available:
            w_lex = 0.50
            w_sem = 0.0
            w_auth = 0.22
            w_temp = 0.15
            w_case = 0.13

        temporal = 0.5  # neutral default
        rec = c["source_record"]
        if rec.temporal_status == "current":
            temporal = 1.0
        elif rec.temporal_status in ("expired", "repealed", "superseded"):
            temporal = 0.1

        case_ctx = 0.5
        if request.case_id and c["source_record"].court:
            case_ctx = 0.6

        relevance = (
            w_lex * lex
            + w_sem * sem
            + w_auth * authority
            + w_temp * temporal
            + w_case * case_ctx
        )

        match_reasons = plan.explain_match(
            (c["source_paragraph"].text or "") + " " + (c["source_paragraph"].heading_path or "")
        )

        weighted.append({
            **c,
            "lexical_score": round(lex, 4),
            "semantic_score": round(sem, 4) if sem > 0 else None,
            "authority_score": round(authority, 4),
            "relevance_score": round(relevance, 4),
            "match_reasons": match_reasons,
        })

    # 17. Deterministic stable sort
    # Sort by canonical_key then relevance for determinism
    weighted.sort(
        key=lambda c: (
            -c["relevance_score"],
            c["source_record"].canonical_key or "",
            c["source_paragraph"].paragraph_index,
        )
    )

    # 18. Deduplicate by canonical SourceRecord (keep best)
    seen_records: dict[str, dict] = {}
    for c in weighted:
        rec_id = c["source_record"].id
        if rec_id not in seen_records:
            seen_records[rec_id] = c
    deduped = list(seen_records.values())
    deduped.sort(key=lambda c: -c["relevance_score"])

    # 19. Cursor pagination
    total = len(deduped)
    limit = request.limit
    offset = int(cursor_data.get("last_sort_key", 0)) if cursor_data else 0
    page = deduped[offset : offset + limit]
    has_more = offset + limit < total
    next_cursor = None
    if has_more:
        next_cursor = sign_cursor({
            "query_id": search_query.id,
            "query_hash_binding": query_hash,
            "filter_hash": compute_filter_hash(filters),
            "index_version": index_version,
            "last_sort_key": offset + limit,
        }, secret)

    # 20. Build results
    results = []
    for idx, c in enumerate(page):
        rec = c["source_record"]
        ver = c["source_version"]
        para = c["source_paragraph"]

        result_id = sign_result_id(
            query_id=search_query.id,
            source_id=rec.id,
            source_version_id=ver.id,
            paragraph_id=para.id,
            index_version=index_version,
            secret=secret,
        )

        snippet = (para.text or "")[:300]
        if len(para.text or "") > 300:
            snippet = snippet[:297] + "..."

        results.append(LegalSearchResult(
            result_id=result_id,
            source_id=rec.id,
            source_type=rec.source_type or "",
            canonical_key=rec.canonical_key or "",
            title=rec.title or "",
            court=rec.court or "",
            chamber=rec.chamber or "",
            case_number=rec.case_number or "",
            decision_number=rec.decision_number or "",
            decision_date=rec.decision_date or "",
            publication_date=rec.publication_date or "",
            effective_date=rec.effective_date or "",
            issuing_authority=rec.issuing_authority or "",
            jurisdiction=rec.jurisdiction or "TR",
            verification_status=c["resolved_status"],
            temporal_status=rec.temporal_status or "unknown",
            paragraph_id=para.id,
            paragraph_text=para.text or "",
            snippet=snippet,
            relevance_score=c["relevance_score"],
            semantic_score=c.get("semantic_score"),
            lexical_score=c.get("lexical_score"),
            match_reasons=c.get("match_reasons", []),
        ))

    return LegalSearchResponse(
        results=results,
        total=total,
        has_more=has_more,
        next_cursor=next_cursor,
        semantic_available=semantic_available,
        degraded_mode=degraded_mode,
        query_id=search_query.id,
    )


# ── Similar search ─────────────────────────────────────────────────────────────


async def execute_similar_search(
    db: AsyncSession,
    request: SimilarSearchRequest,
    security_context,
) -> SimilarSearchResponse:
    settings = get_settings()
    provider = create_embedding_provider(settings)

    source = await SourceRecordRepository.get(db, request.source_id)
    if source is None:
        from fastapi import HTTPException
        from fastapi import status
        raise HTTPException(status_code=404, detail="Kaynak bulunamadı.")

    version_id = source.current_version_id
    if not version_id:
        return SimilarSearchResponse(
            results=[],
            similarity_basis="no_current_version",
        )

    version = await SourceVersionRepository.get(db, version_id)
    if version is None:
        return SimilarSearchResponse(
            results=[],
            similarity_basis="version_not_found",
        )

    if request.source_paragraph_id:
        source_paragraph = await SourceParagraphRepository.get(db, request.source_paragraph_id)
        if source_paragraph is None:
            return SimilarSearchResponse(results=[], similarity_basis="paragraph_not_found")
        source_paragraphs = [source_paragraph]
    else:
        source_paragraphs = await SourceParagraphRepository.list_for_version(db, version_id)

    if not source_paragraphs:
        return SimilarSearchResponse(results=[], similarity_basis="no_paragraphs")

    if provider.is_available:
        return await _similar_search_semantic(
            db, provider, source, source_paragraphs, request.limit, security_context, settings
        )
    else:
        return await _similar_search_metadata(db, source, request.limit, security_context, settings)


async def _similar_search_semantic(
    db: AsyncSession,
    provider: SearchEmbeddingProvider,
    source: SourceRecord,
    source_paragraphs: list[SourceParagraph],
    limit: int,
    security_context,
    settings,
) -> SimilarSearchResponse:
    texts = [sp.text or "" for sp in source_paragraphs]
    combined = " ".join(texts)[:5000]
    query_embedding = provider.embed_query(combined)
    if not query_embedding:
        return SimilarSearchResponse(results=[], similarity_basis="embedding_failed")

    rows_result = await db.execute(
        select(SourceParagraph, SourceVersion, SourceRecord)
        .join(SourceVersion, SourceParagraph.source_version_id == SourceVersion.id)
        .join(SourceRecord, SourceVersion.source_record_id == SourceRecord.id)
        .where(
            SourceParagraph.embedding_status == "indexed",
            SourceRecord.id != source.id,
            SourceRecord.deleted_at.is_(None),
            SourceVersion.status == "active",
        )
        .limit(500)
    )
    rows = rows_result.all()

    secret = settings.jwt_secret_key or "emsalist-local-dev-key-change-in-production"
    index_version = await compute_index_version(db)

    scored = []
    for par, ver, rec in rows:
        try:
            vec = json.loads(par.embedding_vector_json or "[]")
        except (json.JSONDecodeError, TypeError):
            continue
        if not vec:
            continue
        sim = _cosine_similarity(query_embedding, vec)
        if sim > 0.4:
            scored.append((sim, rec, ver, par))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for sim, rec, ver, par in scored[:limit]:
        resolved_status = await resolve_version_verification_status(
            db, rec.id, ver.id, rec.verification_status
        )
        eligibility = index_eligibility(resolved_status)
        if not eligibility.eligible:
            continue
        result_id = sign_result_id(
            query_id="similar",
            source_id=rec.id,
            source_version_id=ver.id,
            paragraph_id=par.id,
            index_version=index_version,
            secret=secret,
        )
        results.append(LegalSearchResult(
            result_id=result_id,
            source_id=rec.id,
            source_type=rec.source_type or "",
            canonical_key=rec.canonical_key or "",
            title=rec.title or "",
            court=rec.court or "",
            chamber=rec.chamber or "",
            case_number=rec.case_number or "",
            decision_number=rec.decision_number or "",
            decision_date=rec.decision_date or "",
            publication_date=rec.publication_date or "",
            effective_date=rec.effective_date or "",
            issuing_authority=rec.issuing_authority or "",
            jurisdiction=rec.jurisdiction or "TR",
            verification_status=resolved_status,
            temporal_status=rec.temporal_status or "unknown",
            paragraph_id=par.id,
            paragraph_text=(par.text or "")[:500],
            snippet=(par.text or "")[:300],
            relevance_score=round(sim, 4),
            semantic_score=round(sim, 4),
            lexical_score=None,
        ))

    return SimilarSearchResponse(
        results=results,
        similarity_basis="semantic_text_embedding",
    )


async def _similar_search_metadata(
    db: AsyncSession,
    source: SourceRecord,
    limit: int,
    security_context,
    settings,
) -> SimilarSearchResponse:
    conditions = [SourceRecord.id != source.id, SourceRecord.deleted_at.is_(None)]
    if source.source_type:
        conditions.append(SourceRecord.source_type == source.source_type)
    if source.court:
        conditions.append(SourceRecord.court == source.court)

    rows_result = await db.execute(
        select(SourceRecord, SourceVersion, SourceParagraph)
        .join(SourceVersion, SourceVersion.source_record_id == SourceRecord.id)
        .join(SourceParagraph, SourceParagraph.source_version_id == SourceVersion.id)
        .where(
            *conditions,
            SourceVersion.status == "active",
            SourceRecord.current_version_id == SourceVersion.id,
        )
        .limit(limit * 3)
    )
    rows = rows_result.all()

    secret = settings.jwt_secret_key or "emsalist-local-dev-key-change-in-production"
    index_version = await compute_index_version(db)

    results = []
    for rec, ver, par in rows[:limit]:
        resolved_status = await resolve_version_verification_status(
            db, rec.id, ver.id, rec.verification_status
        )
        eligibility = index_eligibility(resolved_status)
        if not eligibility.eligible:
            continue
        result_id = sign_result_id(
            query_id="similar_metadata",
            source_id=rec.id,
            source_version_id=ver.id,
            paragraph_id=par.id,
            index_version=index_version,
            secret=secret,
        )
        results.append(LegalSearchResult(
            result_id=result_id,
            source_id=rec.id,
            source_type=rec.source_type or "",
            canonical_key=rec.canonical_key or "",
            title=rec.title or "",
            court=rec.court or "",
            chamber=rec.chamber or "",
            case_number=rec.case_number or "",
            decision_number=rec.decision_number or "",
            decision_date=rec.decision_date or "",
            publication_date=rec.publication_date or "",
            effective_date=rec.effective_date or "",
            issuing_authority=rec.issuing_authority or "",
            jurisdiction=rec.jurisdiction or "TR",
            verification_status=resolved_status,
            temporal_status=rec.temporal_status or "unknown",
            paragraph_id=par.id,
            paragraph_text=(par.text or "")[:500],
            snippet=(par.text or "")[:300],
            relevance_score=0.3,
            semantic_score=None,
            lexical_score=None,
        ))

    return SimilarSearchResponse(
        results=results,
        similarity_basis="degraded_lexical_metadata",
    )


# ── Opposing search ────────────────────────────────────────────────────────────


async def execute_opposing_search(
    db: AsyncSession,
    request: OpposingSearchRequest,
    security_context,
) -> OpposingSearchResponse:
    relationships = await SourceRelationshipRepository.list_for_record(db, request.source_id)

    opposing_rels = [
        r for r in relationships
        if r.relationship_type in ("contradicted_by", "argued_against_by")
    ]

    if not opposing_rels:
        return OpposingSearchResponse(
            results=[],
            opposition_basis="no_controlled_opposition",
        )

    settings = get_settings()
    secret = settings.jwt_secret_key or "emsalist-local-dev-key-change-in-production"
    index_version = await compute_index_version(db)

    results = []
    for rel in opposing_rels:
        rec = await SourceRecordRepository.get(db, rel.related_source_record_id)
        if rec is None or rec.deleted_at is not None:
            continue
        version_id = rec.current_version_id
        if not version_id:
            continue
        ver = await SourceVersionRepository.get(db, version_id)
        if ver is None:
            continue
        paragraphs = await SourceParagraphRepository.list_for_version(db, version_id)
        par = paragraphs[0] if paragraphs else None

        resolved_status = await resolve_version_verification_status(
            db, rec.id, ver.id, rec.verification_status
        )
        eligibility = index_eligibility(resolved_status)
        if not eligibility.eligible:
            continue

        result_id = sign_result_id(
            query_id="opposing",
            source_id=rec.id,
            source_version_id=ver.id,
            paragraph_id=par.id if par else "",
            index_version=index_version,
            secret=secret,
        )

        results.append(LegalSearchResult(
            result_id=result_id,
            source_id=rec.id,
            source_type=rec.source_type or "",
            canonical_key=rec.canonical_key or "",
            title=rec.title or "",
            court=rec.court or "",
            chamber=rec.chamber or "",
            case_number=rec.case_number or "",
            decision_number=rec.decision_number or "",
            decision_date=rec.decision_date or "",
            publication_date=rec.publication_date or "",
            effective_date=rec.effective_date or "",
            issuing_authority=rec.issuing_authority or "",
            jurisdiction=rec.jurisdiction or "TR",
            verification_status=resolved_status,
            temporal_status=rec.temporal_status or "unknown",
            paragraph_id=par.id if par else None,
            paragraph_text=(par.text or "")[:500] if par else None,
            snippet=(par.text or "")[:300] if par else "",
            relevance_score=0.6,
            semantic_score=None,
            lexical_score=None,
        ))

    results.sort(key=lambda r: -r.relevance_score)

    return OpposingSearchResponse(
        results=results,
        opposition_basis="controlled_opposition_evidence",
    )


# ── Search suggestions ─────────────────────────────────────────────────────────


_COURT_NAMES = [
    "Yargıtay", "Danıştay", "Anayasa Mahkemesi", "AYM", "Uyuşmazlık Mahkemesi",
    "Bölge Adliye Mahkemesi", "Bölge İdare Mahkemesi", "Asliye Hukuk Mahkemesi",
    "Asliye Ticaret Mahkemesi", "Asliye Ceza Mahkemesi", "İş Mahkemesi",
    "Aile Mahkemesi", "İcra Hukuk Mahkemesi", "Fikri ve Sınai Haklar Mahkemesi",
    "Sulh Hukuk Mahkemesi", "İdare Mahkemesi", "Vergi Mahkemesi",
]

_CITATION_PATTERNS = [
    "E.", "K.", "Esas", "Karar",
    "TMK", "TBK", "HMK", "HUMK", "TCK", "CMK", "İİK", "TTK", "İYUK",
    "m.", "madde",
    "sayılı",
]


async def get_search_suggestions(
    query_prefix: str,
    limit: int = 10,
) -> SearchSuggestionResponse:
    prefix = (query_prefix or "").strip().lower()
    if not prefix:
        return SearchSuggestionResponse(suggestions=[])

    suggestions: list[str] = []

    for court in _COURT_NAMES:
        if court.lower().startswith(prefix) and court not in suggestions:
            suggestions.append(court)
            if len(suggestions) >= limit:
                return SearchSuggestionResponse(suggestions=suggestions)

    for pattern in _CITATION_PATTERNS:
        combined = f"{pattern} "
        if combined.lower().startswith(prefix) and combined not in suggestions:
            suggestions.append(combined.strip())
        if len(suggestions) >= limit:
            return SearchSuggestionResponse(suggestions=suggestions)

    return SearchSuggestionResponse(suggestions=suggestions[:limit])


# ── Feedback ───────────────────────────────────────────────────────────────────


async def submit_feedback(
    db: AsyncSession,
    result_id: str,
    feedback_request: SearchFeedbackRequest,
    security_context,
) -> SearchFeedbackResponse:
    settings = get_settings()
    secret = settings.jwt_secret_key or "emsalist-local-dev-key-change-in-production"

    query_id = feedback_request.query_id
    if not query_id:
        from fastapi import HTTPException
        from fastapi import status
        raise HTTPException(status_code=422, detail="query_id gerekli.")

    payload = verify_result_id(result_id, query_id, secret)
    if payload is None:
        from fastapi import HTTPException
        from fastapi import status
        raise HTTPException(status_code=422, detail="Geçersiz sonuç kimliği.")

    search_query = await db.execute(
        select(SearchQuery).where(
            SearchQuery.id == query_id,
            SearchQuery.tenant_id == security_context.tenant_id,
        )
    )
    sq = search_query.scalar_one_or_none()
    if sq is None:
        from fastapi import HTTPException
        from fastapi import status
        raise HTTPException(status_code=404, detail="Sorgu bulunamadi.")

    valid_feedback_types = {"relevant", "not_relevant", "authoritative", "outdated", "incorrect"}
    if feedback_request.feedback_type not in valid_feedback_types:
        from fastapi import HTTPException
        from fastapi import status
        raise HTTPException(
            status_code=422,
            detail=f"Geçersiz geri bildirim türü. Kabul edilen: {', '.join(sorted(valid_feedback_types))}",
        )

    feedback = SearchFeedback(
        id=_new_id(),
        search_query_id=query_id,
        result_id=result_id,
        source_id=payload.get("sid", ""),
        feedback_type=feedback_request.feedback_type,
        user_id=security_context.actor_id,
    )
    db.add(feedback)
    await db.flush()

    return SearchFeedbackResponse(
        acknowledged=True,
        feedback_id=feedback.id,
    )
