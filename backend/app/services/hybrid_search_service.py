"""P2.7 — Forensic-corrected hybrid legal search pipeline service."""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
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
    DisabledSearchEmbeddingProvider,
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
    VERIFIED_OFFICIAL,
    index_eligibility,
)

MAX_CANDIDATE_POOL = 5000
APPROVED_FEEDBACK_TYPES = frozenset({
    "relevant", "irrelevant", "valuable_opposing",
    "wrong_metadata", "duplicate", "used_in_draft",
})


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


def _build_candidate_key(rec_id: str, ver_id: str, par_id: str) -> tuple:
    return (rec_id, ver_id, par_id)


# ── Embedding provenance check ─────────────────────────────────────────────────

def _embedding_compatible(paragraph, provider: SearchEmbeddingProvider) -> bool:
    if paragraph.embedding_status != "indexed":
        return False
    if paragraph.embedding_model != provider.model_name:
        return False
    if paragraph.embedding_version != provider.embedding_version:
        return False
    try:
        vec = json.loads(paragraph.embedding_vector_json or "[]")
    except (json.JSONDecodeError, TypeError):
        return False
    if not vec or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in vec):
        return False
    if len(vec) != provider.embedding_dimension:
        return False
    return True


def _stored_vector(paragraph) -> list[float]:
    try:
        return json.loads(paragraph.embedding_vector_json or "[]")
    except (json.JSONDecodeError, TypeError):
        return []


# ── Cosine similarity ──────────────────────────────────────────────────────────

def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ── Lexical retrieval (current-version only) ───────────────────────────────────

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
            SourceRecord.current_version_id == SourceVersion.id,
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
            "semantic_similarity": None,
        })
    return candidates


# ── Semantic retrieval (current-version + provenance-aware) ────────────────────

async def _retrieve_semantic_candidates(
    session: AsyncSession,
    plan: SearchQueryPlan,
    provider: SearchEmbeddingProvider,
    max_candidates: int,
    is_sensitive: bool,
) -> tuple[list[dict], dict]:
    stats = {
        "provider_capable": provider.is_available,
        "query_sensitive": is_sensitive,
        "query_embedding_succeeded": False,
        "compatible_index_available": False,
        "semantic_signal_active": False,
        "degraded_reason": "",
    }
    if not provider.is_available:
        stats["degraded_reason"] = "provider_disabled"
        return [], stats
    if is_sensitive:
        stats["degraded_reason"] = "sensitive_query"
        return [], stats

    semantic_text = plan.semantic_query()
    if not semantic_text:
        stats["degraded_reason"] = "empty_semantic_query"
        return [], stats

    query_embedding = provider.embed_query(semantic_text)
    if not query_embedding:
        stats["degraded_reason"] = "embedding_failed"
        return [], stats

    stats["query_embedding_succeeded"] = True
    query_dim = len(query_embedding)

    rows_result = await session.execute(
        select(SourceParagraph, SourceVersion, SourceRecord)
        .join(SourceVersion, SourceParagraph.source_version_id == SourceVersion.id)
        .join(SourceRecord, SourceVersion.source_record_id == SourceRecord.id)
        .where(
            SourceParagraph.embedding_status == "indexed",
            SourceRecord.deleted_at.is_(None),
            SourceRecord.current_version_id == SourceVersion.id,
        )
        .limit(max_candidates * 2)
    )
    rows = rows_result.all()

    scored = []
    compatible_found = False
    for par, ver, rec in rows:
        if not _embedding_compatible(par, provider):
            continue
        compatible_found = True
        vec = _stored_vector(par)
        if len(vec) != query_dim:
            continue
        sim = _cosine_similarity(query_embedding, vec)
        if sim > 0.3:
            scored.append((sim, {
                "source_record": rec,
                "source_version": ver,
                "source_paragraph": par,
                "origin": "semantic",
                "semantic_similarity": sim,
            }))

    stats["compatible_index_available"] = compatible_found
    stats["semantic_signal_active"] = len(scored) > 0
    if not compatible_found:
        stats["degraded_reason"] = "no_compatible_vectors"

    scored.sort(key=lambda x: x[0], reverse=True)
    candidates = [c for _, c in scored[:max_candidates]]
    return candidates, stats


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


def _citation_score(plan: SearchQueryPlan, rec) -> float:
    score = 0.0
    for cit in plan.exact_citation_candidates:
        cit_norm = normalize_phrase(cit)
        if cit_norm in normalize_phrase(rec.case_number or ""):
            score = max(score, 1.0)
        if cit_norm in normalize_phrase(rec.decision_number or ""):
            score = max(score, 0.95)
        if cit_norm in normalize_phrase(rec.title or ""):
            score = max(score, 0.3)
    return score


def _citation_reasons(plan: SearchQueryPlan, rec) -> list[str]:
    reasons = []
    for cit in plan.exact_citation_candidates:
        c = normalize_phrase(cit)
        if c in normalize_phrase(rec.case_number or ""):
            reasons.append(f"Esas numarası tam eşleşti: {cit}")
        if c in normalize_phrase(rec.decision_number or ""):
            reasons.append(f"Karar numarası tam eşleşti: {cit}")
    for art in plan.article_candidates:
        a = normalize_phrase(art)
        if a in normalize_phrase(rec.title or ""):
            reasons.append(f"Mevzuat maddesi eşleşti: {art}")
    return reasons


def _authority_score(eligibility: IndexEligibility) -> float:
    weight_map = {
        "full_weight": 1.0,
        "reduced_weight": 0.7,
        "low_weight": 0.4,
        "historical_only": 0.2,
    }
    return weight_map.get(eligibility.weight, 0.0)


def _temporal_score(rec) -> float:
    if rec.temporal_status == "current":
        return 1.0
    if rec.temporal_status in ("expired", "repealed", "superseded"):
        return 0.1
    return 0.5


def _case_context_score(request: LegalSearchRequest, rec, case) -> float:
    if not request.case_id or case is None:
        return 0.0
    score = 0.0
    if case.legal_topic:
        topic = normalize_phrase(case.legal_topic)
        text = normalize_phrase((rec.title or "") + " " + (rec.court or ""))
        if topic and topic in text:
            score += 0.5
    if case.profile_id and rec.source_type:
        score += 0.2
    return min(score, 1.0)


def _case_context_reason(request, rec, case) -> str | None:
    if not request.case_id or case is None:
        return None
    if case.legal_topic:
        topic = normalize_phrase(case.legal_topic)
        text = normalize_phrase((rec.title or "") + " " + (rec.court or ""))
        if topic and topic in text:
            return "Dosya konusu ile kaynak alanı eşleşti."
    return None


def _article_locator_from_paragraph(para) -> dict:
    loc = {}
    if para.article_number:
        loc["article_number"] = para.article_number
    if para.locator_json and isinstance(para.locator_json, dict):
        lj = para.locator_json
        loc["article_kind"] = lj.get("kind", "")
        loc["article_label"] = lj.get("label", "")
        loc["article_locator_key"] = lj.get("locator_key", "")
    return loc


# ── Main search pipeline ───────────────────────────────────────────────────────

async def execute_legal_search(
    db: AsyncSession,
    request: LegalSearchRequest,
    security_context,
) -> LegalSearchResponse:
    settings = get_settings()
    secret = settings.jwt_secret_key or "emsalist-local-dev-key-change-in-production"
    max_candidates = min(getattr(settings, "search_max_candidate_pool", MAX_CANDIDATE_POOL), MAX_CANDIDATE_POOL)

    try:
        plan = parse_query(request.query)
    except MalformedQueryError as e:
        from fastapi import HTTPException, status as s
        raise HTTPException(status_code=422, detail=str(e))

    case = None
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
            from fastapi import HTTPException, status as s
            raise HTTPException(status_code=404, detail="Dava bulunamadi.")

    query_hash = compute_query_hash(plan, security_context.tenant_id, secret)
    safe_summary = plan.safe_summary()

    filters = {}
    if request.source_types:
        filters["source_types"] = sorted(request.source_types)
    if request.date_range:
        filters["date_range"] = list(request.date_range)
    if request.court:
        filters["court"] = request.court
    if request.official_only:
        filters["official_only"] = True

    index_version = await compute_index_version(db)

    provider = create_embedding_provider(settings)
    semantic_available = provider.is_available
    query_sensitive = is_sensitive_query(plan.semantic_query())

    cursor_data = None
    existing_query = None
    if request.cursor:
        cursor_data = verify_cursor(request.cursor, secret)
        if cursor_data is None:
            from fastapi import HTTPException, status as s
            raise HTTPException(status_code=422, detail="Geçersiz sayfalama imleci.")
        qid = cursor_data.get("query_id")
        if qid:
            qr = await db.execute(
                select(SearchQuery).where(
                    SearchQuery.id == qid,
                    SearchQuery.tenant_id == security_context.tenant_id,
                    SearchQuery.user_id == security_context.actor_id,
                )
            )
            existing_query = qr.scalar_one_or_none()
        if existing_query is None and qid:
            from fastapi import HTTPException, status as s
            raise HTTPException(status_code=404, detail="Imleç geçersiz.")
        if cursor_data.get("query_hash_binding") != query_hash:
            from fastapi import HTTPException, status as s
            raise HTTPException(status_code=422, detail="Imleç sorgu ile uyuşmuyor.")
        if cursor_data.get("filter_hash") != compute_filter_hash(filters):
            from fastapi import HTTPException, status as s
            raise HTTPException(status_code=422, detail="Filtreler degisti. Lütfen yeniden arayin.")
        if cursor_data.get("index_version") != index_version:
            from fastapi import HTTPException, status as s
            raise HTTPException(status_code=409, detail="Indeks guncellendi. Lütfen yeniden arayin.")

    if not existing_query:
        safe_summary = plan.safe_summary()
        safe_summary["case_context_used"] = request.case_id is not None
        safe_summary["semantic_requested"] = semantic_available and not query_sensitive
        search_query = SearchQuery(
            id=_new_id(),
            tenant_id=security_context.tenant_id,
            user_id=security_context.actor_id,
            case_id=request.case_id,
            query_hash=query_hash,
            safe_query_summary=safe_summary,
            filters_json={"filters": filters},
            index_version=index_version,
        )
        db.add(search_query)
        await db.commit()
        # Refresh session after commit
        await db.refresh(search_query)
        query_id = search_query.id
    else:
        query_id = existing_query.id

    # Retrieve candidates
    lexical_candidates = await _retrieve_lexical_candidates(db, plan, max_candidates)
    semantic_candidates, sem_stats = await _retrieve_semantic_candidates(
        db, plan, provider, max_candidates, query_sensitive,
    )

    # Honest per-request semantic execution tracking
    semantic_executed = sem_stats["semantic_signal_active"]
    degraded_mode = not semantic_executed or not sem_stats["compatible_index_available"]
    if not semantic_available:
        degraded_mode = True

    # Union by (source_record_id, source_version_id, paragraph_id)
    candidate_map: dict[tuple, dict] = {}
    for c in lexical_candidates:
        key = _build_candidate_key(c["source_record"].id, c["source_version"].id, c["source_paragraph"].id)
        if key not in candidate_map:
            candidate_map[key] = c
    for c in semantic_candidates:
        key = _build_candidate_key(c["source_record"].id, c["source_version"].id, c["source_paragraph"].id)
        if key not in candidate_map:
            candidate_map[key] = c
        else:
            existing = candidate_map[key]
            if c.get("semantic_similarity"):
                existing["semantic_similarity"] = c["semantic_similarity"]
            existing["origin"] = existing.get("origin", "") + "+semantic"

    candidates = list(candidate_map.values())
    if not candidates:
        return LegalSearchResponse(
            results=[], total=0, has_more=False,
            semantic_available=semantic_available, degraded_mode=degraded_mode,
            query_id=query_id,
        )

    # Resolve verification status + eligibility
    for c in candidates:
        rec = c["source_record"]
        ver = c["source_version"]
        resolved = await resolve_version_verification_status(db, rec.id, ver.id, rec.verification_status)
        c["resolved_status"] = resolved
        c["eligibility"] = index_eligibility(resolved)

    candidates = [c for c in candidates if c["eligibility"].eligible]

    # Hard grammar constraint
    candidates = [
        c for c in candidates
        if plan.matches((c["source_paragraph"].text or "") + " " + (c["source_paragraph"].heading_path or ""))
    ]

    # Metadata filters
    if request.source_types:
        candidates = [c for c in candidates if c["source_record"].source_type in request.source_types]
    if request.court:
        cl = request.court.lower()
        candidates = [c for c in candidates if cl in (c["source_record"].court or "").lower()]
    if request.official_only:
        candidates = [c for c in candidates if c["resolved_status"] == VERIFIED_OFFICIAL]
    if request.date_range and len(request.date_range) == 2:
        start, end = request.date_range
        filtered = []
        for c in candidates:
            rec = c["source_record"]
            for d in [rec.decision_date, rec.publication_date, rec.effective_date]:
                if d and start <= d <= end:
                    filtered.append(c)
                    break
        candidates = filtered

    if not candidates:
        return LegalSearchResponse(
            results=[], total=0, has_more=False,
            semantic_available=semantic_available, degraded_mode=degraded_mode,
            query_id=query_id,
        )

    # Weighted scoring
    weighted = []
    for c in candidates:
        rec = c["source_record"]
        para = c["source_paragraph"]
        lex = _lexical_score(plan, para.text or "")
        auth = _authority_score(c["eligibility"])
        temporal = _temporal_score(rec)
        case_ctx = _case_context_score(request, rec, case)
        cit = _citation_score(plan, rec)

        sem = c.get("semantic_similarity") or 0.0

        w_lex = 0.35
        w_sem = 0.30
        w_auth = 0.15
        w_temp = 0.10
        w_case = 0.10

        if not semantic_executed:
            w_lex = 0.50
            w_sem = 0.0
            w_auth = 0.22
            w_temp = 0.15
            w_case = 0.13

        lex = max(lex, cit)
        relevance = (
            w_lex * lex
            + w_sem * sem
            + w_auth * auth
            + w_temp * temporal
            + w_case * case_ctx
        )

        reasons = plan.explain_match((para.text or "") + " " + (para.heading_path or ""))
        reasons.extend(_citation_reasons(plan, rec))
        cr = _case_context_reason(request, rec, case)
        if cr:
            reasons.append(cr)

        weighted.append({
            **c,
            "lexical_score": round(lex, 4),
            "semantic_score": round(sem, 4) if sem > 0 else None,
            "authority_score": round(auth, 4),
            "temporal_score": round(temporal, 4),
            "case_context_score": round(case_ctx, 4),
            "relevance_score": round(relevance, 4),
            "match_reasons": reasons,
        })

    # Stable sort with unique tiebreaker
    weighted.sort(key=lambda c: (
        -c["relevance_score"],
        c["source_record"].canonical_key or "",
        c["source_record"].id,
        c["source_paragraph"].id,
    ))

    # Deduplicate by canonical SourceRecord (keep best)
    seen = {}
    for c in weighted:
        rid = c["source_record"].id
        if rid not in seen:
            seen[rid] = c
    deduped = list(seen.values())
    deduped.sort(key=lambda c: (
        -c["relevance_score"],
        c["source_record"].canonical_key or "",
        c["source_record"].id,
        c["source_paragraph"].id,
    ))

    total = len(deduped)
    limit = request.limit
    start_idx = 0
    if cursor_data and "last_sort_key" in cursor_data:
        sk = cursor_data["last_sort_key"]
        for i, c in enumerate(deduped):
            ck = f"{c['relevance_score']:.6f}|{c['source_record'].canonical_key}|{c['source_record'].id}|{c['source_paragraph'].id}"
            if ck > sk:
                start_idx = i
                break

    page = deduped[start_idx: start_idx + limit]
    has_more = start_idx + limit < total

    next_cursor = None
    if has_more and page:
        last = page[-1]
        last_sk = f"{last['relevance_score']:.6f}|{last['source_record'].canonical_key}|{last['source_record'].id}|{last['source_paragraph'].id}"
        next_cursor = sign_cursor({
            "query_id": query_id,
            "query_hash_binding": query_hash,
            "filter_hash": compute_filter_hash(filters),
            "index_version": index_version,
            "last_sort_key": last_sk,
        }, secret)

    results = []
    for c in page:
        rec = c["source_record"]
        ver = c["source_version"]
        para = c["source_paragraph"]

        result_id = sign_result_id(query_id, rec.id, ver.id, para.id, index_version, secret)

        snip = (para.text or "")[:300]
        if len(para.text or "") > 300:
            snip = snip[:297] + "..."

        art = _article_locator_from_paragraph(para)

        results.append(LegalSearchResult(
            result_id=result_id,
            source_id=rec.id,
            source_version_id=ver.id,
            source_paragraph_id=para.id,
            source_type=rec.source_type or "",
            title=rec.title or "",
            court=rec.court or "",
            chamber=rec.chamber or "",
            case_number=rec.case_number or "",
            decision_number=rec.decision_number or "",
            decision_date=rec.decision_date or "",
            official_url=rec.official_url or "",
            paragraph_snippet=snip,
            article_number=art.get("article_number", ""),
            article_kind=art.get("article_kind", ""),
            article_label=art.get("article_label", ""),
            article_locator_key=art.get("article_locator_key", ""),
            verification_status=c["resolved_status"],
            temporal_status=rec.temporal_status or "unknown",
            final_score=c["relevance_score"],
            lexical_score=c.get("lexical_score", 0.0),
            semantic_score=c.get("semantic_score"),
            authority_score=c.get("authority_score", 0.0),
            temporal_score=c.get("temporal_score", 0.0),
            case_context_score=c.get("case_context_score", 0.0),
            match_reasons=c.get("match_reasons", []),
            semantic_available=semantic_available,
            degraded_mode=degraded_mode,
        ))

    return LegalSearchResponse(
        results=results, total=total, has_more=has_more, next_cursor=next_cursor,
        semantic_available=semantic_available, degraded_mode=degraded_mode,
        query_id=query_id,
    )


# ── Similar search ─────────────────────────────────────────────────────────────

async def execute_similar_search(
    db: AsyncSession,
    request: SimilarSearchRequest,
    security_context,
) -> SimilarSearchResponse:
    settings = get_settings()
    provider = create_embedding_provider(settings)
    secret = settings.jwt_secret_key or "emsalist-local-dev-key-change-in-production"

    source = await db.execute(
        select(SourceRecord).where(
            SourceRecord.id == request.source_id,
            SourceRecord.deleted_at.is_(None),
        )
    )
    rec = source.scalar_one_or_none()
    if rec is None:
        from fastapi import HTTPException, status as s
        raise HTTPException(status_code=404, detail="Kaynak bulunamadi.")

    if not rec.current_version_id:
        return SimilarSearchResponse(results=[], similarity_basis="no_current_version")

    version = await db.execute(
        select(SourceVersion).where(SourceVersion.id == rec.current_version_id)
    )
    ver = version.scalar_one_or_none()
    if ver is None:
        return SimilarSearchResponse(results=[], similarity_basis="version_not_found")

    resolved = await resolve_version_verification_status(db, rec.id, ver.id, rec.verification_status)
    eligibility = index_eligibility(resolved)
    if not eligibility.eligible:
        return SimilarSearchResponse(results=[], similarity_basis="source_ineligible")

    if request.source_paragraph_id:
        para_result = await db.execute(
            select(SourceParagraph).where(
                SourceParagraph.id == request.source_paragraph_id,
                SourceParagraph.source_version_id == rec.current_version_id,
            )
        )
        ref_para = para_result.scalar_one_or_none()
        if ref_para is None:
            from fastapi import HTTPException, status as s
            raise HTTPException(status_code=404, detail="Paragraf bulunamadi.")
        source_paragraphs = [ref_para]
    else:
        paras = await db.execute(
            select(SourceParagraph).where(
                SourceParagraph.source_version_id == rec.current_version_id
            )
        )
        source_paragraphs = list(paras.scalars().all())

    if not source_paragraphs:
        return SimilarSearchResponse(results=[], similarity_basis="no_paragraphs")

    if provider.is_available:
        return await _similar_search_semantic(db, provider, rec, source_paragraphs, request.limit, security_context, settings, secret)
    else:
        return await _similar_search_metadata(db, rec, request.limit, security_context, settings, secret)


async def _similar_search_semantic(
    db: AsyncSession,
    provider: SearchEmbeddingProvider,
    source: SourceRecord,
    source_paragraphs: list[SourceParagraph],
    limit: int,
    security_context,
    settings,
    secret: str,
) -> SimilarSearchResponse:
    texts = [(sp.text or "") for sp in source_paragraphs]
    combined = " ".join(texts)[:5000]
    query_embedding = provider.embed_query(combined)
    if not query_embedding:
        return SimilarSearchResponse(results=[], similarity_basis="embedding_failed")
    query_dim = len(query_embedding)

    rows_result = await db.execute(
        select(SourceParagraph, SourceVersion, SourceRecord)
        .join(SourceVersion, SourceParagraph.source_version_id == SourceVersion.id)
        .join(SourceRecord, SourceVersion.source_record_id == SourceRecord.id)
        .where(
            SourceParagraph.embedding_status == "indexed",
            SourceRecord.id != source.id,
            SourceRecord.deleted_at.is_(None),
            SourceRecord.current_version_id == SourceVersion.id,
        )
        .limit(500)
    )
    rows = rows_result.all()

    index_version = await compute_index_version(db)

    scored = []
    for par, ver, rec in rows:
        if not _embedding_compatible(par, provider):
            continue
        vec = _stored_vector(par)
        if len(vec) != query_dim:
            continue
        sim = _cosine_similarity(query_embedding, vec)
        if sim > 0.4:
            scored.append((sim, rec, ver, par))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for sim, rec, ver, par in scored[:limit]:
        resolved_status = await resolve_version_verification_status(db, rec.id, ver.id, rec.verification_status)
        eligibility = index_eligibility(resolved_status)
        if not eligibility.eligible:
            continue
        result_id = sign_result_id("similar", rec.id, ver.id, par.id, index_version, secret)
        results.append(LegalSearchResult(
            result_id=result_id, source_id=rec.id, source_version_id=ver.id,
            source_paragraph_id=par.id, source_type=rec.source_type or "",
            title=rec.title or "", court=rec.court or "", chamber=rec.chamber or "",
            case_number=rec.case_number or "", decision_number=rec.decision_number or "",
            decision_date=rec.decision_date or "", official_url=rec.official_url or "",
            paragraph_snippet=(par.text or "")[:300], verification_status=resolved_status,
            temporal_status=rec.temporal_status or "unknown",
            final_score=round(sim, 4), semantic_score=round(sim, 4),
            lexical_score=0.0, authority_score=0.0, temporal_score=0.0, case_context_score=0.0,
        ))
    return SimilarSearchResponse(results=results, similarity_basis="semantic_text_embedding")


async def _similar_search_metadata(
    db: AsyncSession, source: SourceRecord, limit: int, security_context, settings, secret: str,
) -> SimilarSearchResponse:
    conditions = [
        SourceRecord.id != source.id,
        SourceRecord.deleted_at.is_(None),
        SourceRecord.current_version_id == SourceVersion.id,
    ]
    if source.source_type:
        conditions.append(SourceRecord.source_type == source.source_type)
    if source.court:
        conditions.append(SourceRecord.court == source.court)

    rows_result = await db.execute(
        select(SourceRecord, SourceVersion, SourceParagraph)
        .join(SourceVersion, SourceVersion.source_record_id == SourceRecord.id)
        .join(SourceParagraph, SourceParagraph.source_version_id == SourceVersion.id)
        .where(*conditions)
        .limit(limit * 3)
    )
    rows = rows_result.all()

    index_version = await compute_index_version(db)
    results = []
    for rec, ver, par in rows[:limit]:
        resolved_status = await resolve_version_verification_status(db, rec.id, ver.id, rec.verification_status)
        if not index_eligibility(resolved_status).eligible:
            continue
        result_id = sign_result_id("similar_metadata", rec.id, ver.id, par.id, index_version, secret)
        results.append(LegalSearchResult(
            result_id=result_id, source_id=rec.id, source_version_id=ver.id,
            source_paragraph_id=par.id, source_type=rec.source_type or "",
            title=rec.title or "", court=rec.court or "", chamber=rec.chamber or "",
            case_number=rec.case_number or "", decision_number=rec.decision_number or "",
            decision_date=rec.decision_date or "", official_url=rec.official_url or "",
            paragraph_snippet=(par.text or "")[:300], verification_status=resolved_status,
            temporal_status=rec.temporal_status or "unknown",
            final_score=0.3, semantic_score=None, lexical_score=0.0,
            authority_score=0.0, temporal_score=0.0, case_context_score=0.0,
        ))
    return SimilarSearchResponse(results=results, similarity_basis="degraded_lexical_metadata")


# ── Opposing search ────────────────────────────────────────────────────────────

async def execute_opposing_search(
    db: AsyncSession,
    request: OpposingSearchRequest,
    security_context,
) -> OpposingSearchResponse:
    relationships_result = await db.execute(
        select(SourceRelationship).where(
            SourceRelationship.source_record_id == request.source_id,
            SourceRelationship.relationship_type.in_(("contradicted_by", "argued_against_by")),
        )
    )
    opposing_rels = list(relationships_result.scalars().all())

    if not opposing_rels:
        return OpposingSearchResponse(results=[], opposition_basis="no_controlled_opposition")

    settings = get_settings()
    secret = settings.jwt_secret_key or "emsalist-local-dev-key-change-in-production"
    index_version = await compute_index_version(db)

    results = []
    for rel in opposing_rels:
        rec_result = await db.execute(
            select(SourceRecord).where(
                SourceRecord.id == rel.related_source_record_id,
                SourceRecord.deleted_at.is_(None),
            )
        )
        rec = rec_result.scalar_one_or_none()
        if rec is None or not rec.current_version_id:
            continue

        ver_result = await db.execute(
            select(SourceVersion).where(SourceVersion.id == rec.current_version_id)
        )
        ver = ver_result.scalar_one_or_none()
        if ver is None:
            continue

        paras_result = await db.execute(
            select(SourceParagraph).where(
                SourceParagraph.source_version_id == rec.current_version_id
            ).limit(1)
        )
        par = paras_result.scalar_one_or_none()

        resolved = await resolve_version_verification_status(db, rec.id, ver.id, rec.verification_status)
        if not index_eligibility(resolved).eligible:
            continue

        result_id = sign_result_id(
            "opposing", rec.id, ver.id,
            par.id if par else "no_paragraph", index_version, secret,
        )

        results.append(LegalSearchResult(
            result_id=result_id, source_id=rec.id,
            source_version_id=ver.id,
            source_paragraph_id=par.id if par else "",
            source_type=rec.source_type or "", title=rec.title or "",
            court=rec.court or "", chamber=rec.chamber or "",
            case_number=rec.case_number or "", decision_number=rec.decision_number or "",
            decision_date=rec.decision_date or "", official_url=rec.official_url or "",
            paragraph_snippet=(par.text or "")[:300] if par else "",
            verification_status=resolved,
            temporal_status=rec.temporal_status or "unknown",
            final_score=0.6, semantic_score=None, lexical_score=0.0,
            authority_score=0.0, temporal_score=0.0, case_context_score=0.0,
        ))

    results.sort(key=lambda r: -r.final_score)
    return OpposingSearchResponse(results=results, opposition_basis="controlled_opposition_evidence")


# ── Suggestions ─────────────────────────────────────────────────────────────────

_COURT_NAMES = [
    "Yargıtay", "Danıştay", "Anayasa Mahkemesi", "Uyuşmazlık Mahkemesi",
    "Bölge Adliye Mahkemesi", "İş Mahkemesi", "Aile Mahkemesi",
    "Asliye Hukuk", "Asliye Ticaret", "İcra Hukuk", "İdare Mahkemesi",
]
_CIT = ["E.", "K.", "TMK", "TBK", "HMK", "TCK", "CMK", "İİK", "TTK", "İYUK", "m.", "sayılı"]


async def get_search_suggestions(query_prefix: str, limit: int = 10) -> SearchSuggestionResponse:
    prefix = (query_prefix or "").strip().lower()
    if not prefix:
        return SearchSuggestionResponse(suggestions=[])
    suggestions = []
    for court in _COURT_NAMES:
        if court.lower().startswith(prefix):
            suggestions.append(court)
            if len(suggestions) >= limit:
                return SearchSuggestionResponse(suggestions=suggestions)
    for pat in _CIT:
        if pat.lower().startswith(prefix):
            suggestions.append(pat)
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
        from fastapi import HTTPException, status as s
        raise HTTPException(status_code=422, detail="query_id gerekli.")

    payload = verify_result_id(result_id, query_id, secret)
    if payload is None:
        from fastapi import HTTPException, status as s
        raise HTTPException(status_code=422, detail="Geçersiz sonuç kimliği.")

    sq_result = await db.execute(
        select(SearchQuery).where(
            SearchQuery.id == query_id,
            SearchQuery.tenant_id == security_context.tenant_id,
            SearchQuery.user_id == security_context.actor_id,
        )
    )
    sq = sq_result.scalar_one_or_none()
    if sq is None:
        from fastapi import HTTPException, status as s
        raise HTTPException(status_code=404, detail="Sorgu bulunamadi.")

    if feedback_request.feedback_type not in APPROVED_FEEDBACK_TYPES:
        from fastapi import HTTPException, status as s
        raise HTTPException(status_code=422, detail=f"Geçersiz geri bildirim türü.")

    feedback = SearchFeedback(
        id=_new_id(),
        search_query_id=query_id,
        result_id=result_id,
        source_id=payload.get("sid", ""),
        feedback_type=feedback_request.feedback_type,
        user_id=security_context.actor_id,
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    return SearchFeedbackResponse(acknowledged=True, feedback_id=feedback.id)
