"""P2.5 — DB-backed document pipeline endpoints (case-scoped, authenticated).

Every route first calls ``_load_owned_case`` (tenant + owner) → 404 on
missing/foreign. Upload runs the full validation→hash→dedup→store→persist→
extract→page→suggest pipeline synchronously and records the resulting status.
Raw document text and extraction values are never written to logs/audit.
"""
from __future__ import annotations

import logging

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.case_chat_repository import CaseRepository
from app.db.document_repository import (
    DocumentExtractionRepository,
    DocumentPageRepository,
    DocumentRepository,
    InvalidTransitionError,
    STATUS_ANALYZED,
    STATUS_AWAITING,
    STATUS_FAILED,
    STATUS_PROCESSING,
    STATUS_QUEUED,
    STATUS_UNSUPPORTED,
)
from app.db.models import Case, Document, new_uuid
from app.db.session import get_session
from app.models.document_pipeline_models import (
    DocumentAnalysisResponse,
    DocumentListResponse,
    DocumentPageResponse,
    DocumentResponse,
    DocumentTypeUpdateRequest,
    ExtractionResponse,
)
from app.services import document_parsing as parsing
from app.services import document_storage as storage
from app.services.document_extractor import extract_from_pages
from app.services.document_intelligence_provider import (
    DocumentAnalysisInput,
    DocumentIntelligenceError,
    create_configured_document_intelligence_provider,
)
from app.services.auth_service import SecurityContext, resolve_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cases/{case_id}/documents", tags=["Documents"])


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


async def _load_owned_case(db: AsyncSession, ctx: SecurityContext, case_id: str) -> Case:
    case = await CaseRepository.get(db, ctx.tenant_id, case_id)
    if case is None or case.owner_user_id != ctx.actor_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return case


async def _load_owned_document(
    db: AsyncSession, ctx: SecurityContext, case_id: str, document_id: str
) -> Document:
    await _load_owned_case(db, ctx, case_id)
    doc = await DocumentRepository.get(db, ctx.tenant_id, case_id, document_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc


async def _audit(db, ctx, case_id, action, metadata):
    from app.db.auth_repository import AuthAuditRepository

    await AuthAuditRepository.write_event(
        db, ctx.tenant_id, ctx.actor_id, case_id, action, "success", metadata
    )


def _doc_resp(d: Document) -> DocumentResponse:
    return DocumentResponse(
        id=d.id, case_id=d.case_id, original_filename=d.original_filename,
        mime_type=d.mime_type, extension=d.extension, size_bytes=d.size_bytes,
        document_type=d.document_type, document_type_source=d.document_type_source,
        status=d.status, analysis_status=d.analysis_status, support_level=d.support_level,
        page_count=d.page_count, extracted_text_available=d.extracted_text_available,
        failure_code=d.failure_code, version=d.version,
        created_at=_iso(d.created_at) or "", updated_at=_iso(d.updated_at) or "",
    )


def _extraction_resp(e) -> ExtractionResponse:
    return ExtractionResponse(
        id=e.id, document_id=e.document_id, case_id=e.case_id,
        extraction_type=e.extraction_type, field_key=e.field_key, value=e.value,
        page_number=e.page_number, text_span=e.text_span,
        source_quote=e.source_quote, confidence=e.confidence,
        verification_status=e.verification_status,
        provider_name=e.provider_name, provider_model=e.provider_model,
        analysis_run_id=e.analysis_run_id, memory_fact_id=e.memory_fact_id,
        version=e.version, created_at=_iso(e.created_at) or "",
    )


# Native text below this length is treated as an insufficient extraction and
# becomes eligible for AI document intelligence (when a provider is enabled).
_MIN_NATIVE_TEXT_CHARS = 20

# Provider outcomes that mean "AI analysis is simply not available for this
# document"; the pipeline then keeps today's honest non-AI behavior.
_AI_UNAVAILABLE_CODES = {
    "document_intelligence_unavailable",
    "gemini_disabled",
    "gemini_api_key_missing",
    "gemini_unsupported_document",
}

_DETERMINISTIC_EXTRACTOR_VERSION = "p2.5-regex-1"


def _document_intelligence_provider():
    """Route-local factory; tests may monkeypatch this to inject a fake provider."""
    return create_configured_document_intelligence_provider()


async def _persist_deterministic_extractions(
    db: AsyncSession, ctx: SecurityContext, doc: Document,
    pages: list[parsing.ParsedPage], analysis_run_id: str,
) -> None:
    for cand in extract_from_pages(pages):
        if await DocumentExtractionRepository.exists(
            db, doc.id, cand.field_key, cand.normalized_value
        ):
            continue
        await DocumentExtractionRepository.create(
            db, tenant_id=ctx.tenant_id, case_id=doc.case_id, document_id=doc.id,
            extraction_type=cand.extraction_type, field_key=cand.field_key,
            value=cand.value, normalized_value=cand.normalized_value,
            page_number=cand.page_number, text_span=cand.text_span,
            source_quote=cand.source_quote,
            source_quote_hash=parsing.text_hash(cand.source_quote),
            confidence=cand.confidence, created_by=ctx.actor_id,
            provider_name="deterministic",
            provider_model=_DETERMINISTIC_EXTRACTOR_VERSION,
            analysis_run_id=analysis_run_id,
        )


async def _finish_analyzed(
    db: AsyncSession, doc: Document, page_count: int
) -> None:
    extractions = await DocumentExtractionRepository.list_for_document(
        db, doc.tenant_id, doc.id
    )
    await DocumentRepository.set_analysis(
        db, doc, analysis_status="analyzed",
        page_count=page_count, extracted_text_available=page_count > 0,
    )
    target = STATUS_AWAITING if extractions else STATUS_ANALYZED
    await DocumentRepository.transition(db, doc, target)


async def _run_document_intelligence(
    db: AsyncSession, ctx: SecurityContext, doc: Document,
    content: bytes, analysis_run_id: str,
) -> bool:
    """Run the configured AI provider; returns False when AI is unavailable.

    Hard provider failures (timeout, invalid schema, provenance mismatch, ...)
    fail the document closed with a sanitized failure code. Raw document bytes,
    OCR text and provider responses are never logged.
    """
    provider = _document_intelligence_provider()
    request = DocumentAnalysisInput(
        document_id=doc.id, extension=doc.extension,
        mime_type=doc.mime_type or "application/octet-stream", content=content,
    )
    started_metrics = {"document_id": doc.id, "case_id": doc.case_id,
                       "provider": provider.provider_name,
                       "model": provider.model_version}
    try:
        result = await provider.analyze(request)
    except DocumentIntelligenceError as exc:
        if exc.code in _AI_UNAVAILABLE_CODES:
            return False
        logger.warning(
            "document_intelligence_failed document_id=%s case_id=%s provider=%s "
            "model=%s safe_error_code=%s",
            doc.id, doc.case_id, provider.provider_name,
            provider.model_version, exc.code,
        )
        await DocumentRepository.set_analysis(
            db, doc, analysis_status="ai_failed",
            page_count=0, extracted_text_available=False, failure_code=exc.code[:50],
        )
        await DocumentRepository.transition(db, doc, STATUS_FAILED)
        return True

    pages_payload = [
        (page["page_number"],
         "\n".join(block["text"] for block in page["text_blocks"]),
         "ocr")
        for page in result["pages"]
    ]
    pages_payload = [(number, text, status) for number, text, status in pages_payload if text]
    if pages_payload:
        await DocumentPageRepository.replace_pages(
            db, tenant_id=ctx.tenant_id, document_id=doc.id, pages=pages_payload
        )
    for entry in result["extractions"]:
        if await DocumentExtractionRepository.exists(
            db, doc.id, entry["field_key"], entry["normalized_value"]
        ):
            continue
        await DocumentExtractionRepository.create(
            db, tenant_id=ctx.tenant_id, case_id=doc.case_id, document_id=doc.id,
            extraction_type=entry["extraction_type"], field_key=entry["field_key"],
            value=entry["value"], normalized_value=entry["normalized_value"],
            page_number=entry["page_number"], text_span="",
            source_quote=entry["source_quote"],
            source_quote_hash=parsing.text_hash(entry["source_quote"]),
            confidence=entry["confidence"], created_by=ctx.actor_id,
            provider_name=provider.provider_name,
            provider_model=provider.model_version,
            analysis_run_id=analysis_run_id,
        )
    suggestion = result["document_type_suggestion"]
    if suggestion and not (doc.document_type or "").strip():
        await DocumentRepository.set_document_type(db, doc, suggestion, "ai_suggested")
    await _finish_analyzed(db, doc, len(pages_payload))
    logger.info(
        "document_intelligence_completed document_id=%s case_id=%s provider=%s "
        "model=%s page_count=%d status=%s",
        started_metrics["document_id"], started_metrics["case_id"],
        started_metrics["provider"], started_metrics["model"],
        len(pages_payload), doc.status,
    )
    return True


async def _run_pipeline(
    db: AsyncSession, ctx: SecurityContext, doc: Document, content: bytes
) -> None:
    """Extract text → persist pages → suggestions → set status.

    Native extraction is always preferred. AI document intelligence only runs
    for image/scanned/empty-text documents and only when a provider is enabled;
    otherwise images / unparseable UDF keep a clear non-analyzed status rather
    than a fabricated result.
    """
    await DocumentRepository.transition(db, doc, STATUS_PROCESSING)
    result = parsing.parse_document(doc.extension, content)
    analysis_run_id = new_uuid()

    native_ok = result.status in ("extracted", "partial")
    text_sufficient = len(result.full_text.strip()) >= _MIN_NATIVE_TEXT_CHARS
    if result.status == "ocr_required" or (native_ok and not text_sufficient):
        handled = await _run_document_intelligence(db, ctx, doc, content, analysis_run_id)
        if handled:
            return

    pages_payload = [
        (p.page_number, p.text, "extracted") for p in result.pages if p.text
    ]
    if pages_payload:
        await DocumentPageRepository.replace_pages(
            db, tenant_id=ctx.tenant_id, document_id=doc.id, pages=pages_payload
        )

    if native_ok:
        await _persist_deterministic_extractions(db, ctx, doc, result.pages, analysis_run_id)
        await DocumentRepository.set_analysis(
            db, doc, analysis_status="analyzed",
            page_count=len(pages_payload), extracted_text_available=True,
        )
        extractions = await DocumentExtractionRepository.list_for_document(
            db, ctx.tenant_id, doc.id
        )
        target = STATUS_AWAITING if extractions else STATUS_ANALYZED
        await DocumentRepository.transition(db, doc, target)
    elif result.status == "ocr_required":
        await DocumentRepository.set_analysis(
            db, doc, analysis_status="ocr_pending",
            page_count=0, extracted_text_available=False, failure_code="DOC-OCR-07",
        )
        await DocumentRepository.transition(db, doc, STATUS_UNSUPPORTED)
    elif result.status == "unsupported":
        await DocumentRepository.set_analysis(
            db, doc, analysis_status="unsupported",
            page_count=0, extracted_text_available=False, failure_code="DOC-TYPE-02",
        )
        await DocumentRepository.transition(db, doc, STATUS_UNSUPPORTED)
    else:  # failed
        await DocumentRepository.set_analysis(
            db, doc, analysis_status="failed",
            page_count=0, extracted_text_available=False, failure_code="DOC-EXTRACT-06",
        )
        await DocumentRepository.transition(db, doc, STATUS_FAILED)


# ---------------------------------------------------------------------------
# Upload / list / detail / delete
# ---------------------------------------------------------------------------
@router.post("", response_model=DocumentResponse, status_code=201, operation_id="document_upload")
async def upload_document(
    case_id: str,
    file: UploadFile = File(...),
    document_type: str | None = Form(default=None),
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> DocumentResponse:
    case = await _load_owned_case(db, ctx, case_id)
    settings = get_settings()
    max_size = settings.max_upload_size_bytes

    content = bytearray()
    while chunk := await file.read(1024 * 1024):
        content.extend(chunk)
        if len(content) > max_size:
            await file.close()
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Dosya boyutu {max_size // (1024 * 1024)} MB sınırını aşıyor.",
            )
    await file.close()
    raw = bytes(content)

    try:
        extension = parsing.validate_upload(file.filename or "belge", raw, max_size)
    except parsing.DocumentValidationError as e:
        code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if e.code == "DOC-SIZE-03" else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=e.message)

    sha = parsing.sha256_hex(raw)
    # Deterministic duplicate result within the same case (never a silent copy).
    duplicate = await DocumentRepository.find_by_sha256(db, ctx.tenant_id, case.id, sha)
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu belge bu dosyada zaten mevcut.",
            headers={"X-Duplicate-Document-Id": duplicate.id},
        )

    safe_name = parsing.sanitize_filename(file.filename or "belge")
    support_level = parsing.support_level_for(extension)
    doc = await DocumentRepository.create(
        db, tenant_id=ctx.tenant_id, case_id=case.id,
        original_filename=(file.filename or "belge")[:500], safe_filename=safe_name,
        extension=extension, mime_type=parsing.MIME_TYPES.get(extension, "application/octet-stream"),
        size_bytes=len(raw), sha256=sha,
        storage_key="", support_level=support_level, uploaded_by=ctx.actor_id,
        document_type=(document_type or "").strip(),
    )
    storage_key = storage.build_storage_key(ctx.tenant_id, case.id, doc.id, extension)
    storage.write_blob(storage_key, raw)
    doc.storage_key = storage_key
    await DocumentRepository.transition(db, doc, STATUS_QUEUED)

    try:
        await _run_pipeline(db, ctx, doc, raw)
    except parsing.DocumentValidationError:
        await DocumentRepository.set_analysis(
            db, doc, analysis_status="failed", failure_code="DOC-SECURITY-04"
        )
        if doc.status not in (STATUS_FAILED,):
            try:
                await DocumentRepository.transition(db, doc, STATUS_FAILED)
            except InvalidTransitionError:
                pass

    await _audit(db, ctx, case.id, "document_uploaded",
                 {"resource": "document", "document_id": doc.id,
                  "status": doc.status, "support_level": doc.support_level})
    await db.commit()
    return _doc_resp(doc)


@router.get("", response_model=DocumentListResponse, operation_id="document_list")
async def list_documents(
    case_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> DocumentListResponse:
    case = await _load_owned_case(db, ctx, case_id)
    docs, total = await DocumentRepository.list_for_case(
        db, ctx.tenant_id, case.id, limit=limit, offset=offset
    )
    return DocumentListResponse(
        items=[_doc_resp(d) for d in docs], total=total, limit=limit, offset=offset,
        has_more=(offset + len(docs)) < total,
    )


@router.get("/{document_id}", response_model=DocumentResponse, operation_id="document_get")
async def get_document(
    case_id: str,
    document_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> DocumentResponse:
    doc = await _load_owned_document(db, ctx, case_id, document_id)
    return _doc_resp(doc)


@router.delete("/{document_id}", status_code=204, operation_id="document_delete")
async def delete_document(
    case_id: str,
    document_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> None:
    doc = await _load_owned_document(db, ctx, case_id, document_id)
    await DocumentRepository.soft_delete(db, doc)
    storage.delete_blob(doc.storage_key)
    await _audit(db, ctx, case_id, "document_deleted",
                 {"resource": "document", "document_id": doc.id})
    await db.commit()
    return None


@router.get("/{document_id}/content", operation_id="document_content")
async def get_document_content(
    case_id: str,
    document_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    doc = await _load_owned_document(db, ctx, case_id, document_id)
    if doc.status == "quarantined":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Belge karantinada.")
    try:
        blob = storage.read_blob(doc.storage_key)
    except storage.DocumentStorageError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document content not found")
    return Response(
        content=blob, media_type=doc.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{doc.safe_filename}"'},
    )


@router.post("/{document_id}/retry", response_model=DocumentResponse, operation_id="document_retry")
async def retry_document(
    case_id: str,
    document_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> DocumentResponse:
    doc = await _load_owned_document(db, ctx, case_id, document_id)
    try:
        await DocumentRepository.transition(db, doc, STATUS_QUEUED)
    except InvalidTransitionError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{doc.status}' durumundaki belge yeniden işlenemez.",
        )
    try:
        blob = storage.read_blob(doc.storage_key)
    except storage.DocumentStorageError:
        await DocumentRepository.transition(db, doc, STATUS_FAILED)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document content not found")
    await _run_pipeline(db, ctx, doc, blob)
    await _audit(db, ctx, case_id, "document_retried",
                 {"resource": "document", "document_id": doc.id, "status": doc.status})
    await db.commit()
    return _doc_resp(doc)


@router.get("/{document_id}/pages", response_model=list[DocumentPageResponse], operation_id="document_pages")
async def list_pages(
    case_id: str,
    document_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[DocumentPageResponse]:
    doc = await _load_owned_document(db, ctx, case_id, document_id)
    pages = await DocumentPageRepository.list_for_document(db, ctx.tenant_id, doc.id)
    return [
        DocumentPageResponse(
            page_number=p.page_number, text=p.text, extraction_status=p.extraction_status
        )
        for p in pages
    ]


@router.get("/{document_id}/analysis", response_model=DocumentAnalysisResponse, operation_id="document_analysis")
async def get_analysis(
    case_id: str,
    document_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> DocumentAnalysisResponse:
    doc = await _load_owned_document(db, ctx, case_id, document_id)
    extractions = await DocumentExtractionRepository.list_for_document(db, ctx.tenant_id, doc.id)
    return DocumentAnalysisResponse(
        document_id=doc.id, status=doc.status, analysis_status=doc.analysis_status,
        support_level=doc.support_level, page_count=doc.page_count,
        extracted_text_available=doc.extracted_text_available,
        document_type=doc.document_type, document_type_source=doc.document_type_source,
        failure_code=doc.failure_code,
        extractions=[_extraction_resp(e) for e in extractions],
    )


@router.post("/{document_id}/type", response_model=DocumentResponse, operation_id="document_set_type")
async def set_document_type(
    case_id: str,
    document_id: str,
    body: DocumentTypeUpdateRequest,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> DocumentResponse:
    doc = await _load_owned_document(db, ctx, case_id, document_id)
    await DocumentRepository.set_document_type(db, doc, body.document_type.strip(), "user_selected")
    await _audit(db, ctx, case_id, "document_type_set",
                 {"resource": "document", "document_id": doc.id})
    await db.commit()
    return _doc_resp(doc)


# ---------------------------------------------------------------------------
# Extraction confirm / reject → P2.4 case memory
# ---------------------------------------------------------------------------
@router.post(
    "/{document_id}/extractions/{extraction_id}/confirm",
    response_model=ExtractionResponse,
    operation_id="document_extraction_confirm",
)
async def confirm_extraction(
    case_id: str,
    document_id: str,
    extraction_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> ExtractionResponse:
    from app.db.case_memory_repository import CaseFactRepository, ContradictionRepository

    doc = await _load_owned_document(db, ctx, case_id, document_id)
    extraction = await DocumentExtractionRepository.get(db, ctx.tenant_id, case_id, extraction_id)
    if extraction is None or extraction.document_id != doc.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Extraction not found")

    # Confirming creates a document_verified CaseFact and reuses the P2.4
    # contradiction engine — never bypasses P2.4 verification rules.
    fact = await CaseFactRepository.create(
        db, tenant_id=ctx.tenant_id, case_id=case_id, fact_type=extraction.field_key,
        value=extraction.value, created_by=ctx.actor_id, source_type="document_verified",
        source_id=doc.id, confidence=extraction.confidence, importance="high",
        verification_status="document_verified",
    )
    await ContradictionRepository.detect_for_fact_type(
        db, ctx.tenant_id, case_id, extraction.field_key, ctx.actor_id
    )
    await DocumentExtractionRepository.set_status(
        db, extraction, "user_confirmed", memory_fact_id=fact.id
    )
    await _audit(db, ctx, case_id, "document_extraction_confirmed",
                 {"resource": "document_extraction", "extraction_id": extraction.id,
                  "document_id": doc.id, "memory_fact_id": fact.id,
                  "verification_status": extraction.verification_status})
    await db.commit()
    return _extraction_resp(extraction)


@router.post(
    "/{document_id}/extractions/{extraction_id}/reject",
    response_model=ExtractionResponse,
    operation_id="document_extraction_reject",
)
async def reject_extraction(
    case_id: str,
    document_id: str,
    extraction_id: str,
    ctx: SecurityContext = Depends(resolve_current_user),
    db: AsyncSession = Depends(get_session),
) -> ExtractionResponse:
    doc = await _load_owned_document(db, ctx, case_id, document_id)
    extraction = await DocumentExtractionRepository.get(db, ctx.tenant_id, case_id, extraction_id)
    if extraction is None or extraction.document_id != doc.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Extraction not found")
    # Reject preserves the record; no memory fact is created.
    await DocumentExtractionRepository.set_status(db, extraction, "rejected")
    await _audit(db, ctx, case_id, "document_extraction_rejected",
                 {"resource": "document_extraction", "extraction_id": extraction.id,
                  "document_id": doc.id, "verification_status": extraction.verification_status})
    await db.commit()
    return _extraction_resp(extraction)
