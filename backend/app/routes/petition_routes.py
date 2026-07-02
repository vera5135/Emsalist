"""Petition strategy and draft endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.models.petition_models import (
    FinalPetitionDraftRequest,
    FinalPetitionDraftResponse,
    GroundingNote,
    PetitionDraftRequest,
    PetitionDraftResponse,
    PetitionStrategyRequest,
    PetitionStrategyResponse,
)
from app.services.petition_draft_service import petition_draft_service
from app.services.final_petition_writer_service import final_petition_writer_service
from app.services.petition_strategy_service import petition_strategy_service
from app.services.document_intake_service import document_intake_service
from app.services.case_state_service import case_state_service
from app.services.dynamic_legal_reasoner_service import dynamic_legal_reasoner_service


router = APIRouter(prefix="/petition", tags=["Dilekçe"])


@router.post("/strategy", response_model=PetitionStrategyResponse)
def build_petition_strategy(request: PetitionStrategyRequest) -> PetitionStrategyResponse:
    return petition_strategy_service.build_strategy(
        case_text=request.case_text,
        top_decisions=request.top_decisions,
    )


@router.post("/draft", response_model=PetitionDraftResponse)
def build_petition_draft(request: PetitionDraftRequest) -> PetitionDraftResponse:
    selected_decisions = request.audited_precedents or request.selected_decisions
    # AI enrichment fields are internal signals for search, questions and quality checks.
    # They must not be appended to the petition narrative as raw analysis text.
    case_text = request.case_text
    grounded_document_facts = []
    if request.document_ids:
        for document_id in request.document_ids:
            try:
                record = document_intake_service.get_document(document_id)
            except KeyError as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Grounding belgesi bulunamadı: {document_id}",
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
            f"{f', s. {fact.page_number}' if fact.page_number else ''}; alıntı: {fact.excerpt})"
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
            title=f"Belgeyle doğrulanan bilgi: {fact.fact_key}",
            detail=(
                f"{fact.fact_value} — Kaynak: {fact.source_file_name}"
                f"{f', sayfa {fact.page_number}' if fact.page_number else ''}; "
                f"alıntı: {fact.excerpt}; güven: %{round(fact.confidence_score * 100)}"
            ),
        )
        for fact in grounded_document_facts
    )
    return response


@router.post("/final-draft", response_model=FinalPetitionDraftResponse)
def build_final_petition_draft(request: FinalPetitionDraftRequest) -> FinalPetitionDraftResponse:
    # Onay zorunluluğu kaldırıldı; dilekçe her durumda hazırlanabilir.

    grounded_document_facts = []
    document_types: list[str] = []
    if request.document_ids:
        for document_id in dict.fromkeys(request.document_ids):
            try:
                record = document_intake_service.get_document(document_id)
            except KeyError as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Dilekçe belgesi bulunamadı: {document_id}",
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
    question_answers = {
        str(key): str(value)
        for key, value in request.answers.items()
        if str(key).strip() and str(value).strip()
    }
    document_fact_lines = [f"{fact.fact_key}: {fact.fact_value}" for fact in grounded_document_facts]
    reasoning = dynamic_legal_reasoner_service.analyze(
        event_text=request.case_text,
        document_facts=document_fact_lines,
        question_answers=question_answers,
    )
    case_state = case_state_service.build(
        event_text=request.case_text,
        area=request.request_type,
        case_type=request.case_enrichment.get("detected_case_type", ""),
        document_facts=document_fact_lines,
        question_answers=question_answers,
        legal_sources=[*request.legal_grounds, *reasoning.get("research_queries", [])],
        precedent_candidates=request.precedent_candidates,
        drafting_package={},
        analysis_context={
            "documents": [{"document_type": item} for item in document_types],
            "warnings": [*request.drafting_warnings, *list(request.case_enrichment.get("risk_flags") or [])],
        },
    )
    package = final_petition_writer_service.build_package(
        case_text=request.case_text,
        request_type=request.request_type,
        answers=question_answers,
        confirmed_facts=[
            *request.confirmed_facts,
            *list(request.case_enrichment.get("confirmed_facts") or []),
        ],
        missing_facts=[
            *request.missing_facts,
            *list(request.case_enrichment.get("missing_facts") or []),
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
    package.precedent_for_petition = [
        " | ".join(part for part in [decision.court, decision.esas_no, decision.karar_no, decision.date, decision.petition_paragraph] if part)
        for decision in (request.audited_precedents or request.selected_decisions)
    ]
    package.precedents_for_petition = list(package.precedent_for_petition)
    package.risks = list(dict.fromkeys([*package.risks, *request.drafting_warnings, *list(request.case_enrichment.get("risk_flags") or []), *case_state.get("risk_items", [])]))
    package.legal_sources = list(dict.fromkeys([*package.legal_sources, *case_state.get("research_queries", [])]))
    case_state["drafting_package"] = package.model_dump(mode="json")
    response = final_petition_writer_service.write(package)
    response.case_state = case_state
    return response
