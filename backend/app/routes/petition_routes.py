"""Petition strategy and draft endpoints."""

from fastapi import APIRouter, HTTPException, status

from app.models.petition_models import (
    GroundingNote,
    PetitionDraftRequest,
    PetitionDraftResponse,
    PetitionStrategyRequest,
    PetitionStrategyResponse,
)
from app.services.petition_draft_service import petition_draft_service
from app.services.petition_strategy_service import petition_strategy_service
from app.services.document_intake_service import document_intake_service


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
