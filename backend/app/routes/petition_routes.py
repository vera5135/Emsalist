"""Petition strategy and draft endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.models.petition_models import (
    DraftingPrecedentItem,
    FinalPetitionDraftRequest,
    FinalPetitionDraftResponse,
    GroundingNote,
    PetitionDraftRequest,
    PetitionDraftResponse,
    PetitionStrategyRequest,
    PetitionStrategyResponse,
)
from app.services.case_session_service import case_session_service
from app.services.case_state_service import case_state_service
from app.services.document_intake_service import document_intake_service
from app.services.dynamic_legal_reasoner_service import dynamic_legal_reasoner_service
from app.services.final_petition_writer_service import final_petition_writer_service
from app.services.petition_draft_service import petition_draft_service
from app.services.petition_strategy_service import petition_strategy_service


router = APIRouter(prefix="/petition", tags=["DilekÃ§e"])

ALLOWED_PETITION_USE_CLASSES = {"direct_support", "supporting_with_caution"}


def _decision_value(item: Any, field: str, default: str = "") -> str:
    value = getattr(item, field, None)
    if value is None and isinstance(item, dict):
        value = item.get(field)
    return str(value or default).strip()


def _decision_plain(value: str) -> str:
    return " ".join(
        str(value or "")
        .casefold()
        .replace("Ã§", "c")
        .replace("ÄŸ", "g")
        .replace("Ä±", "i")
        .replace("Ã¶", "o")
        .replace("ÅŸ", "s")
        .replace("Ã¼", "u")
        .split()
    )


def _sanitized_precedent_item(item: Any) -> DraftingPrecedentItem | None:
    use_class = _decision_value(item, "use_class")
    source_type = _decision_value(item, "source_type")
    verification = _decision_value(item, "official_verification_status")
    if use_class and use_class not in ALLOWED_PETITION_USE_CLASSES:
        return None
    if source_type and source_type != "yargitay_live" and verification != "verified_live":
        return None
    court = _decision_value(item, "court", "YargÄ±tay")
    chamber = _decision_value(item, "chamber") or court
    paragraph = _decision_value(item, "petition_use_summary") or _decision_value(item, "petition_paragraph") or _decision_value(item, "summary")
    if not paragraph:
        return None
    return DraftingPrecedentItem(
        court=court,
        chamber=chamber,
        esas_no=_decision_value(item, "esas_no"),
        karar_no=_decision_value(item, "karar_no"),
        date=_decision_value(item, "date"),
        title=_decision_value(item, "title"),
        summary=_decision_value(item, "summary") or paragraph,
        relevance=_decision_value(item, "why_relevant") or paragraph,
        supported_issue=_decision_value(item, "supported_issue") or _decision_value(item, "legal_principle") or paragraph,
        use_class=use_class,
        source_type=source_type,
        official_verification_status=verification,
        petition_use_summary=paragraph,
    )


def _collect_precedent_for_petition(request: FinalPetitionDraftRequest) -> list[DraftingPrecedentItem]:
    enrichment = request.case_enrichment or {}
    final_precedents = enrichment.get("final_precedents") or []
    live_results = enrichment.get("live_yargitay_results") or []
    top_decisions = enrichment.get("top_decisions") or []

    sources: list[Any] = [
        *(request.precedent_for_petition or []),
        *(request.audited_precedents or []),
        *(request.selected_decisions or []),
        *(request.precedent_candidates or []),
        *(final_precedents if isinstance(final_precedents, list) else []),
        *(live_results if isinstance(live_results, list) else []),
        *(top_decisions if isinstance(top_decisions, list) else []),
    ]
    result: list[DraftingPrecedentItem] = []
    seen: set[str] = set()
    for item in sources:
        sanitized = _sanitized_precedent_item(item)
        if not sanitized:
            continue
        key = _decision_plain(" | ".join([sanitized.court, sanitized.esas_no, sanitized.karar_no, sanitized.date]))
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(sanitized)
    return result[:10]


@router.post("/strategy", response_model=PetitionStrategyResponse)
def build_petition_strategy(request: PetitionStrategyRequest) -> PetitionStrategyResponse:
    case_session_service.require_existing_case(request.case_id)
    return petition_strategy_service.build_strategy(
        case_text=request.case_text,
        top_decisions=request.top_decisions,
    )


@router.post("/draft", response_model=PetitionDraftResponse)
def build_petition_draft(request: PetitionDraftRequest) -> PetitionDraftResponse:
    resolved_case_id = case_session_service.require_existing_case(request.case_id)
    selected_decisions = request.audited_precedents or request.selected_decisions
    case_text = request.case_text
    grounded_document_facts = []
    if request.document_ids:
        for document_id in request.document_ids:
            try:
                record = document_intake_service.get_document(document_id, case_id=resolved_case_id)
            except KeyError as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Grounding belgesi bulunamadÄ±: {document_id}",
                ) from exc
            if record.extraction_status not in {"extracted", "partial"}:
                continue
            grounded_document_facts.extend(
                fact for fact in record.extracted_facts
                if fact.verification_status == "fact_confirmed"
            )
    else:
        grounded_document_facts = [
            fact for fact in request.document_facts
            if fact.verification_status == "fact_confirmed"
        ]
    grounded_document_facts = list({
        (fact.source_document_id, fact.fact_key, fact.fact_value): fact
        for fact in grounded_document_facts
    }.values())
    document_fact_lines = [
        (
            f"{fact.fact_key}: {fact.fact_value} "
            f"(Kaynak belge: {fact.source_file_name}"
            f"{f', s. {fact.page_number}' if fact.page_number else ''}; alÄ±ntÄ±: {fact.excerpt})"
        )
        for fact in grounded_document_facts
    ]
    confirmed_facts = list(dict.fromkeys([*request.confirmed_facts, *document_fact_lines]))[:30]
    response = petition_draft_service.build_draft(
        case_text=case_text,
        case_enrichment=request.case_enrichment,
        confirmed_facts=confirmed_facts,
        missing_facts=request.missing_facts,
        petition_strategy_hint=request.petition_strategy_hint,
        answers=request.answers,
        selected_decisions=selected_decisions,
        precedent_candidates=request.precedent_candidates,
        tone=request.tone,
        request_type=request.request_type,
        use_legal_brain=request.use_legal_brain,
        legal_language_level=request.legal_language_level,
    )
    response.grounding_notes.extend(
        GroundingNote(
            status="source_confirmed",
            title=f"Belgeyle doÄŸrulanan bilgi: {fact.fact_key}",
            detail=(
                f"{fact.fact_value} â€” Kaynak: {fact.source_file_name}"
                f"{f', sayfa {fact.page_number}' if fact.page_number else ''}; "
                f"alÄ±ntÄ±: {fact.excerpt}; gÃ¼ven: %{round(fact.confidence_score * 100)}"
            ),
        )
        for fact in grounded_document_facts
    )
    return response


@router.post("/final-draft", response_model=FinalPetitionDraftResponse)
def build_final_petition_draft(request: FinalPetitionDraftRequest) -> FinalPetitionDraftResponse:
    resolved_case_id = case_session_service.require_existing_case(request.case_id)
    has_explicit_case_id = bool(str(request.case_id or "").strip())
    stored_case = case_session_service.get_case_state(resolved_case_id) if has_explicit_case_id else {
        "documents": [],
        "question_answers": {},
        "case_enrichment": {},
        "final_precedents": [],
        "live_yargitay_results": [],
        "drafting_package": {},
        "precedent_for_petition": [],
    }

    grounded_document_facts = []
    document_types: list[str] = []
    effective_document_ids = request.document_ids or [
        item.get("document_id", "")
        for item in stored_case.get("documents", [])
        if isinstance(item, dict)
    ]
    if effective_document_ids:
        for document_id in dict.fromkeys(effective_document_ids):
            try:
                record = document_intake_service.get_document(document_id, case_id=resolved_case_id)
            except KeyError as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"DilekÃ§e belgesi bulunamadÄ±: {document_id}",
                ) from exc
            if record.extraction_status not in {"extracted", "partial"}:
                continue
            document_types.append(record.document_type)
            grounded_document_facts.extend(
                fact for fact in record.extracted_facts
                if fact.verification_status == "fact_confirmed"
            )
    else:
        grounded_document_facts = [
            fact for fact in request.document_facts
            if fact.verification_status == "fact_confirmed"
        ]

    grounded_document_facts = list({
        (fact.fact_key, fact.fact_value.casefold(), fact.source_file_name.casefold()): fact
        for fact in grounded_document_facts
    }.values())
    stored_answers = {
        str(key): str(value)
        for key, value in dict(stored_case.get("question_answers") or {}).items()
        if str(key).strip() and str(value).strip()
    }
    question_answers = {
        **stored_answers,
        **{
            str(key): str(value)
            for key, value in request.answers.items()
            if str(key).strip() and str(value).strip()
        },
    }
    document_fact_lines = [f"{fact.fact_key}: {fact.fact_value}" for fact in grounded_document_facts]
    enriched_case = {
        **dict(stored_case.get("case_enrichment") or {}),
        **request.case_enrichment,
        "final_precedents": request.case_enrichment.get("final_precedents") or stored_case.get("final_precedents") or [],
        "live_yargitay_results": request.case_enrichment.get("live_yargitay_results") or stored_case.get("live_yargitay_results") or [],
    }
    reasoning = dynamic_legal_reasoner_service.analyze(
        event_text=request.case_text,
        document_facts=document_fact_lines,
        question_answers=question_answers,
    )
    case_state = case_state_service.build(
        case_id=resolved_case_id,
        event_text=request.case_text,
        area=request.request_type,
        case_type=enriched_case.get("detected_case_type", ""),
        document_facts=document_fact_lines,
        question_answers=question_answers,
        legal_sources=[*request.legal_grounds, *reasoning.get("research_queries", [])],
        precedent_candidates=request.precedent_candidates or list(stored_case.get("final_precedents") or []),
        drafting_package=dict(stored_case.get("drafting_package") or {}),
        analysis_context={
            "documents": [{"document_type": item} for item in document_types],
            "warnings": [*request.drafting_warnings, *list(enriched_case.get("risk_flags") or [])],
        },
    )
    package = final_petition_writer_service.build_package(
        case_text=request.case_text,
        request_type=request.request_type,
        answers=question_answers,
        confirmed_facts=[
            *request.confirmed_facts,
            *list(enriched_case.get("confirmed_facts") or []),
        ],
        missing_facts=[
            *request.missing_facts,
            *list(enriched_case.get("missing_facts") or []),
        ],
        document_facts=grounded_document_facts,
        document_types=document_types,
        evidence_items=request.evidence_items,
        legal_grounds=request.legal_grounds,
        relief_requests=request.relief_requests,
        drafting_warnings=request.drafting_warnings,
        writer_mode=getattr(request, "writer_mode", "local"),
        case_state=case_state,
        legal_ground_validation=stored_case.get("legal_ground_validation"),
    )
    precedent_request = request.model_copy(deep=True)
    precedent_request.case_enrichment = enriched_case

    # ── P0.5.1: Canonical precedent authority ──
    authority_data = stored_case.get("precedent_authority") or {}
    if authority_data.get("records"):
        from app.models.precedent_models import CanonicalPrecedent
        accepted_records = [
            r for r in authority_data.get("records", [])
            if isinstance(r, dict)
            and r.get("selection_status") in ("accepted", "used_in_petition")
            and r.get("duplicate_status") == "unique"
            and r.get("authority_status") not in ("fallback_only", "prohibited")
            and r.get("relevance_status") in ("directly_relevant", "partially_relevant")
            and r.get("verification_status") in ("verified", "partially_verified")
        ]
        package.precedent_for_petition = [
            DraftingPrecedentItem(
                court=rec.get("court", ""),
                chamber=rec.get("chamber", ""),
                esas_no=rec.get("normalized_docket_number", rec.get("docket_number", "")),
                karar_no=rec.get("normalized_decision_number", rec.get("decision_number", "")),
                date=rec.get("normalized_decision_date", rec.get("decision_date", "")),
                title=rec.get("title", ""),
                summary=rec.get("summary", rec.get("holding", "")),
                relevance=rec.get("summary", ""),
                supported_issue=", ".join(rec.get("related_issue_node_ids", [])),
                use_class="direct_support",
                source_type=rec.get("source_type", ""),
                official_verification_status=rec.get("verification_status", ""),
                petition_use_summary=rec.get("summary", ""),
            ) for rec in accepted_records
        ]
        for rec in authority_data.get("records", []):
            if rec.get("selection_status") == "used_in_petition" or rec.get("precedent_id") in [r.get("precedent_id") for r in accepted_records]:
                pass
    else:
        if not precedent_request.precedent_candidates:
            precedent_request.precedent_candidates = list(stored_case.get("final_precedents") or [])
        if not precedent_request.precedent_for_petition:
            precedent_request.precedent_for_petition = [
                DraftingPrecedentItem.model_validate(item)
                for item in stored_case.get("precedent_for_petition", [])
                if isinstance(item, dict)
            ]
        package.precedent_for_petition = _collect_precedent_for_petition(precedent_request)

    package.precedents_for_petition = [
        " | ".join(part for part in [item.court, item.esas_no, item.karar_no, item.date, item.summary] if part)
        for item in package.precedent_for_petition
    ]
    if package.precedent_for_petition:
        case_state["precedent_for_petition"] = [item.model_dump(mode="json") for item in package.precedent_for_petition]
    package.risks = list(dict.fromkeys([*package.risks, *request.drafting_warnings, *list(enriched_case.get("risk_flags") or []), *case_state.get("risk_items", [])]))
    package.legal_sources = list(dict.fromkeys([*package.legal_sources, *case_state.get("research_queries", [])]))

    graph = dict(case_state.get("legal_issue_graph") or {})
    package.drafting_plan = list(graph.get("drafting_plan") or [])
    package.graph_summary = " | ".join(
        f"{item.get('title', '')}: {str(item.get('risk_level') or '').upper()}"
        for item in graph.get("issues", [])
        if isinstance(item, dict) and item.get("title")
    )
    case_state["drafting_package"] = package.model_dump(mode="json")

    if getattr(package, "writer_mode", "local") == "ai":
        try:
            from app.services.ai_run_service import ai_run_service
            response = ai_run_service.track_call(
                case_id=resolved_case_id,
                operation="final_petition_write",
                request_id=request.request_id if hasattr(request, "request_id") else "",
                fn=lambda: final_petition_writer_service.write(package),
            )
        except Exception:
            response = final_petition_writer_service.write(package)
    else:
        response = final_petition_writer_service.write(package)

    response.case_state = case_state
    case_session_service.update_case_state(
        resolved_case_id,
        case_state,
        event_text=request.case_text,
        question_answers=question_answers,
        dynamic_reasoning=reasoning,
        drafting_package=package.model_dump(mode="json"),
        precedent_for_petition=[item.model_dump(mode="json") for item in package.precedent_for_petition],
        final_draft={
            "petition_text": response.petition_text,
            "generation_mode": response.generation_mode,
            "warnings": response.warnings,
        },
    )
    # ── P0.6: Claim grounding ──
    try:
        from app.services.claim_grounding_service import claim_grounding_service
        grounding_result = claim_grounding_service.analyze(
            case_id=resolved_case_id,
            petition_text=response.petition_text,
            case_state=stored_case,
        )
        case_session_service.update_case(resolved_case_id, claim_grounding=grounding_result.model_dump(mode="json"))
        response.grounding_ready = grounding_result.grounding_ready
        response.grounding_warnings = grounding_result.warnings
        response.claim_grounding = grounding_result.model_dump(mode="json")
    except Exception:
        response.grounding_ready = False
        response.grounding_warnings = ["Claim grounding başarısız oldu"]
        response.claim_grounding = {}
    return response
