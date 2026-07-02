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
    sources: list[Any] = [
        *(request.precedent_for_petition or []),
        *(request.audited_precedents or []),
        *(request.selected_decisions or []),
        *(request.precedent_candidates or []),
        *list(request.case_enrichment.get("final_precedents") or []),
        *list(request.case_enrichment.get("live_yargitay_results") or []),
        *list(request.case_enrichment.get("top_decisions") or []),
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
    return petition_strategy_service.build_strategy(
        case_text=request.case_text,
        top_decisions=request.top_decisions,
    )


@router.post("/draft", response_model=PetitionDraftResponse)
def build_petition_draft(request: PetitionDraftRequest) -> PetitionDraftResponse:
    resolved_case_id = case_session_service.resolve_case_id(request.case_id)
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
    resolved_case_id = case_session_service.resolve_case_id(request.case_id)
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
    )
    precedent_request = request.model_copy(deep=True)
    precedent_request.case_enrichment = enriched_case
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
    case_state["drafting_package"] = package.model_dump(mode="json")
    response = final_petition_writer_service.write(package)
    response.case_state = case_state
    case_session_service.update_case(
        resolved_case_id,
        event_text=request.case_text,
        question_answers=question_answers,
        case_state=case_state,
        dynamic_reasoning=reasoning,
        drafting_package=package.model_dump(mode="json"),
        precedent_for_petition=[item.model_dump(mode="json") for item in package.precedent_for_petition],
        final_draft={
            "petition_text": response.petition_text,
            "generation_mode": response.generation_mode,
            "warnings": response.warnings,
        },
    )
    return response
