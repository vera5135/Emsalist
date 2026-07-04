"""Document upload, analysis and lifecycle endpoints."""

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status

from app.models.document_models import DocumentAnalyzeRequest, DocumentAnalyzeResponse, DocumentRecord
from app.services.case_state_service import case_state_service
from app.services.case_session_service import case_session_service
from app.services.document_intake_service import (
    DocumentDuplicateError,
    DocumentIntakeError,
    document_intake_service,
)


router = APIRouter(prefix="/documents", tags=["Document Intake"])


@router.post("/upload", response_model=DocumentRecord, status_code=status.HTTP_200_OK)
async def upload_document(
    file: UploadFile = File(...),
    document_type: str | None = Form(default=None),
    case_id: str | None = Form(default=None),
) -> DocumentRecord:
    content = bytearray()
    while chunk := await file.read(1024 * 1024):
        content.extend(chunk)
        if len(content) > document_intake_service.max_file_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Dosya boyutu {document_intake_service.max_file_size // (1024 * 1024)} MB sÄ±nÄ±rÄ±nÄ± aÅŸÄ±yor.",
            )
    resolved_case_id = case_session_service.resolve_case_id(case_id)
    try:
        record = document_intake_service.create_document(
            case_id=resolved_case_id,
            file_name=file.filename or "belge",
            content=bytes(content),
            document_type=document_type,
        )
        current_documents = document_intake_service.list_documents(case_id=resolved_case_id)
        case_session_service.update_case(
            resolved_case_id,
            documents=[item.model_dump(mode="json") for item in current_documents],
        )
        return record
    except DocumentDuplicateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except DocumentIntakeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        await file.close()


@router.post("/analyze", response_model=DocumentAnalyzeResponse)
def analyze_documents(request: DocumentAnalyzeRequest) -> DocumentAnalyzeResponse:
    try:
        resolved_case_id = case_session_service.resolve_case_id(request.case_id)
        response = document_intake_service.analyze_documents(
            case_id=resolved_case_id,
            document_ids=request.document_ids,
            user_claims=request.user_claims,
            document_types=request.document_types,
        )
        stored = case_session_service.get_case_state(resolved_case_id)
        previous = dict(stored.get("case_state") or {})
        document_facts = [f"{item.fact_key}: {item.fact_value}" for item in response.confirmed_facts]
        documents = [item.model_dump(mode="json") for item in response.documents]
        canonical_state = case_state_service.build(
            case_id=resolved_case_id,
            event_text=str(stored.get("event_text") or previous.get("event_text") or ""),
            area=str(previous.get("area") or stored.get("legal_topic") or ""),
            case_type=str(previous.get("case_type") or ""),
            document_facts=document_facts,
            question_answers=dict(stored.get("question_answers") or {}),
            legal_sources=list(previous.get("legal_sources") or []),
            precedent_candidates=list(stored.get("final_precedents") or []),
            drafting_package=dict(stored.get("drafting_package") or {}),
            analysis_context={
                "documents": documents,
                "warnings": [*list(previous.get("warnings") or []), *response.warnings],
            },
        )
        case_session_service.update_case_state(
            resolved_case_id,
            canonical_state,
            documents=documents,
            document_facts=document_facts,
        )
        return response
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Belge bulunamadÄ±.") from exc
    except DocumentIntakeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("", response_model=list[DocumentRecord])
def list_documents(case_id: Annotated[str | None, Query()] = None) -> list[DocumentRecord]:
    resolved_case_id = case_session_service.resolve_case_id(case_id)
    return document_intake_service.list_documents(case_id=resolved_case_id)


@router.get("/{document_id}", response_model=DocumentRecord)
def get_document(document_id: str, case_id: Annotated[str | None, Query()] = None) -> DocumentRecord:
    try:
        resolved_case_id = case_session_service.resolve_case_id(case_id)
        return document_intake_service.get_document(document_id, case_id=resolved_case_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Belge bulunamadÄ±.") from exc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str, case_id: Annotated[str | None, Query()] = None) -> None:
    try:
        resolved_case_id = case_session_service.resolve_case_id(case_id)
        document_intake_service.delete_document(document_id, case_id=resolved_case_id)
        remaining = document_intake_service.list_documents(case_id=resolved_case_id)
        documents = [item.model_dump(mode="json") for item in remaining]
        document_facts = [
            f"{fact.fact_key}: {fact.fact_value}"
            for record in remaining
            for fact in record.extracted_facts
            if fact.verification_status == "fact_confirmed"
        ]
        stored = case_session_service.get_case_state(resolved_case_id)
        previous = dict(stored.get("case_state") or {})
        canonical_state = case_state_service.build(
            case_id=resolved_case_id,
            event_text=str(stored.get("event_text") or previous.get("event_text") or ""),
            area=str(previous.get("area") or stored.get("legal_topic") or ""),
            case_type=str(previous.get("case_type") or ""),
            document_facts=document_facts,
            question_answers=dict(stored.get("question_answers") or {}),
            legal_sources=list(previous.get("legal_sources") or []),
            precedent_candidates=list(stored.get("final_precedents") or []),
            drafting_package=dict(stored.get("drafting_package") or {}),
            analysis_context={
                "documents": documents,
                "warnings": list(previous.get("warnings") or []),
            },
        )
        case_session_service.update_case_state(
            resolved_case_id,
            canonical_state,
            documents=documents,
            document_facts=document_facts,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Belge bulunamadÄ±.") from exc
