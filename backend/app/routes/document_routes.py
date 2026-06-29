"""Document upload, analysis and lifecycle endpoints."""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.models.document_models import DocumentAnalyzeRequest, DocumentAnalyzeResponse, DocumentRecord
from app.services.document_intake_service import DocumentIntakeError, document_intake_service


router = APIRouter(prefix="/documents", tags=["Document Intake"])


@router.post("/upload", response_model=DocumentRecord, status_code=status.HTTP_200_OK)
async def upload_document(
    file: UploadFile = File(...),
    document_type: str | None = Form(default=None),
) -> DocumentRecord:
    content = bytearray()
    while chunk := await file.read(1024 * 1024):
        content.extend(chunk)
        if len(content) > document_intake_service.max_file_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Dosya boyutu {document_intake_service.max_file_size // (1024 * 1024)} MB sınırını aşıyor.",
            )
    try:
        return document_intake_service.create_document(
            file_name=file.filename or "belge",
            content=bytes(content),
            document_type=document_type,
        )
    except DocumentIntakeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        await file.close()


@router.post("/analyze", response_model=DocumentAnalyzeResponse)
def analyze_documents(request: DocumentAnalyzeRequest) -> DocumentAnalyzeResponse:
    try:
        return document_intake_service.analyze_documents(
            document_ids=request.document_ids,
            user_claims=request.user_claims,
            document_types=request.document_types,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Belge bulunamadı.") from exc
    except DocumentIntakeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("", response_model=list[DocumentRecord])
def list_documents() -> list[DocumentRecord]:
    return document_intake_service.list_documents()


@router.get("/{document_id}", response_model=DocumentRecord)
def get_document(document_id: str) -> DocumentRecord:
    try:
        return document_intake_service.get_document(document_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Belge bulunamadı.") from exc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str) -> None:
    try:
        document_intake_service.delete_document(document_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Belge bulunamadı.") from exc
