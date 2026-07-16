"""P2.8 — Gemini document intelligence boundary tests.

Provider unit tests use httpx.MockTransport (no real Gemini call is ever
made). Pipeline integration tests monkeypatch the route-local provider
factory and run against the real DB pipeline, proving:
- native extraction is always preferred (no AI call for text documents),
- image / scanned-PDF fallback with real page provenance,
- fail-closed behavior for disabled/missing-key/limit/transport errors,
- detected-only findings, confirm/reject → P2.4 flow, idempotent reruns,
- no API key / raw content leaks into logs and no raw response in the DB.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import tempfile

import pytest
import pytest_asyncio

_BLOB_DIR = tempfile.TemporaryDirectory(prefix="emsalist-p28-docai-blobs-")
os.environ.setdefault("EMSALIST_DOCUMENT_STORE_DIR", _BLOB_DIR.name)

import fitz  # noqa: E402  (pymupdf, dev/test dependency)
import httpx  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.db.models import (  # noqa: E402
    AuditEvent,
    Case,
    CaseFact,
    CaseMember,
    Contradiction,
    Document,
    DocumentExtraction,
    DocumentPage,
    Tenant,
    User,
)
from app.db.session import get_sessionmaker  # noqa: E402
from app.main import app  # noqa: E402
from app.routes import document_pipeline_routes as pipeline_routes  # noqa: E402
from app.services.document_intelligence_provider import (  # noqa: E402
    DeterministicDocumentIntelligenceProvider,
    DocumentAnalysisInput,
    DocumentIntelligenceError,
    GeminiDocumentIntelligenceProvider,
    UnavailableDocumentIntelligenceProvider,
    normalize_document_intelligence,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64

OCR_PAGE_1 = "Fatura tutari 12.500 TL odenmistir."
OCR_PAGE_2 = "Teslim tarihi 12.06.2026 olarak belirlenmistir."


def _ocr_result(needs_review: bool = False) -> dict:
    return {
        "document_type_suggestion": "fatura",
        "pages": [
            {"page_number": 1, "text_blocks": [
                {"text": OCR_PAGE_1, "bounding_box": None, "confidence": 0.9},
            ]},
            {"page_number": 2, "text_blocks": [
                {"text": OCR_PAGE_2, "bounding_box": None, "confidence": 0.85},
            ]},
        ],
        "extractions": [
            {
                "extraction_type": "money", "field_key": "amount",
                "value": "12.500 TL", "normalized_value": "12500.00 TL",
                "page_number": 1, "source_quote": "12.500 TL",
                "confidence": 0.9, "verification_status": "detected",
            },
            {
                "extraction_type": "date", "field_key": "date",
                "value": "12.06.2026", "normalized_value": "2026-06-12",
                "page_number": 2, "source_quote": "12.06.2026",
                "confidence": 0.8, "verification_status": "detected",
            },
        ],
        "needs_review": needs_review,
    }


def _gemini_http_response(payload: dict, finish_reason: str = "STOP") -> dict:
    return {
        "candidates": [{
            "content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]},
            "finishReason": finish_reason,
        }],
        "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50, "totalTokenCount": 150},
    }


def _provider(handler, **kwargs) -> GeminiDocumentIntelligenceProvider:
    defaults = dict(
        api_key="gm-test-key", enabled=True,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    defaults.update(kwargs)
    return GeminiDocumentIntelligenceProvider(**defaults)


def _request(content: bytes = PNG_BYTES, mime: str = "image/png") -> DocumentAnalysisInput:
    return DocumentAnalysisInput(
        document_id="doc-1", extension=".png", mime_type=mime, content=content,
    )


async def _noop_sleep(_seconds: float) -> None:
    return None


# ---------------------------------------------------------------------------
# Provider unit tests (MockTransport — never a real Gemini call)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_disabled_provider_makes_no_external_call():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_gemini_http_response(_ocr_result()))

    provider = _provider(handler, enabled=False)
    with pytest.raises(DocumentIntelligenceError, match="gemini_disabled"):
        await provider.analyze(_request())
    assert calls == []


@pytest.mark.asyncio
async def test_missing_api_key_fails_closed_without_call():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_gemini_http_response(_ocr_result()))

    provider = _provider(handler, api_key="")
    with pytest.raises(DocumentIntelligenceError, match="gemini_api_key_missing"):
        await provider.analyze(_request())
    assert calls == []


@pytest.mark.asyncio
async def test_file_size_limit_enforced_without_call():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_gemini_http_response(_ocr_result()))

    provider = _provider(handler, max_file_bytes=16)
    with pytest.raises(DocumentIntelligenceError, match="gemini_document_too_large"):
        await provider.analyze(_request(content=b"x" * 17))
    assert calls == []


@pytest.mark.asyncio
async def test_unsupported_mime_rejected_without_call():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_gemini_http_response(_ocr_result()))

    provider = _provider(handler)
    with pytest.raises(DocumentIntelligenceError, match="gemini_unsupported_document"):
        await provider.analyze(_request(mime="application/zip"))
    assert calls == []


@pytest.mark.asyncio
async def test_page_limit_enforced():
    over_limit = _ocr_result()
    over_limit["pages"] = [
        {"page_number": index, "text_blocks": [
            {"text": f"sayfa {index}", "bounding_box": None, "confidence": 0.5},
        ]}
        for index in range(1, 22)
    ]
    over_limit["extractions"] = []
    provider = _provider(
        lambda _req: httpx.Response(200, json=_gemini_http_response(over_limit)),
        max_pages_per_run=20,
    )
    with pytest.raises(DocumentIntelligenceError, match="gemini_page_limit_exceeded"):
        await provider.analyze(_request())


@pytest.mark.asyncio
async def test_transport_errors_map_to_safe_codes():
    timeout_provider = _provider(
        lambda _req: (_ for _ in ()).throw(httpx.TimeoutException("raw provider text")),
        max_retries=0,
    )
    with pytest.raises(DocumentIntelligenceError, match="gemini_timeout"):
        await timeout_provider.analyze(_request())

    rate_limited = _provider(lambda _req: httpx.Response(429, json={"error": "raw"}), max_retries=0)
    with pytest.raises(DocumentIntelligenceError, match="gemini_rate_limited"):
        await rate_limited.analyze(_request())

    server_error = _provider(lambda _req: httpx.Response(503, json={"error": "raw"}), max_retries=0)
    with pytest.raises(DocumentIntelligenceError, match="gemini_server_error"):
        await server_error.analyze(_request())


@pytest.mark.asyncio
async def test_transient_errors_are_retried_then_succeed():
    calls = {"count": 0}

    def handler(_req: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(500, json={"error": "server"})
        return httpx.Response(200, json=_gemini_http_response(_ocr_result()))

    provider = _provider(handler, max_retries=1, sleeper=_noop_sleep)
    result = await provider.analyze(_request())
    assert calls["count"] == 2
    assert provider.last_metrics["request_count"] == 2
    assert len(result["pages"]) == 2


@pytest.mark.asyncio
async def test_invalid_json_schema_empty_and_truncated_fail_closed():
    invalid_json = _provider(lambda _req: httpx.Response(200, json=_gemini_http_response({})["candidates"] and {
        "candidates": [{"content": {"parts": [{"text": "{not json"}]}, "finishReason": "STOP"}],
    }))
    with pytest.raises(DocumentIntelligenceError, match="gemini_invalid_json"):
        await invalid_json.analyze(_request())

    invalid_schema = _provider(
        lambda _req: httpx.Response(200, json=_gemini_http_response({"unexpected": True})))
    with pytest.raises(DocumentIntelligenceError, match="gemini_invalid_schema"):
        await invalid_schema.analyze(_request())

    empty = _provider(lambda _req: httpx.Response(200, json={"candidates": []}))
    with pytest.raises(DocumentIntelligenceError, match="gemini_empty_response"):
        await empty.analyze(_request())

    truncated = _provider(
        lambda _req: httpx.Response(200, json=_gemini_http_response(_ocr_result(), finish_reason="MAX_TOKENS")))
    with pytest.raises(DocumentIntelligenceError, match="gemini_output_truncated"):
        await truncated.analyze(_request())


@pytest.mark.asyncio
async def test_unknown_extraction_category_rejected():
    payload = _ocr_result()
    payload["extractions"][0]["extraction_type"] = "secret_party_opinion"
    provider = _provider(lambda _req: httpx.Response(200, json=_gemini_http_response(payload)))
    with pytest.raises(DocumentIntelligenceError, match="gemini_invalid_schema"):
        await provider.analyze(_request())


@pytest.mark.asyncio
async def test_extraction_on_missing_page_is_provenance_mismatch():
    payload = _ocr_result()
    payload["extractions"][0]["page_number"] = 9
    provider = _provider(lambda _req: httpx.Response(200, json=_gemini_http_response(payload)))
    with pytest.raises(DocumentIntelligenceError, match="gemini_provenance_mismatch"):
        await provider.analyze(_request())


@pytest.mark.asyncio
async def test_fabricated_source_quote_is_rejected_and_forces_review():
    payload = _ocr_result(needs_review=False)
    payload["extractions"][0]["source_quote"] = "99.999 TL hic gecmeyen tutar"
    provider = _provider(lambda _req: httpx.Response(200, json=_gemini_http_response(payload)))
    result = await provider.analyze(_request())
    assert [e["extraction_type"] for e in result["extractions"]] == ["date"]
    assert result["needs_review"] is True


@pytest.mark.asyncio
async def test_findings_are_forced_to_detected_status():
    payload = _ocr_result()
    payload["extractions"][0]["verification_status"] = "user_confirmed"
    provider = _provider(lambda _req: httpx.Response(200, json=_gemini_http_response(payload)))
    result = await provider.analyze(_request())
    assert all(e["verification_status"] == "detected" for e in result["extractions"])


@pytest.mark.asyncio
async def test_api_key_travels_in_header_never_in_url_and_is_not_logged(caplog):
    caplog.set_level(logging.DEBUG)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_gemini_http_response(_ocr_result()))

    provider = _provider(handler, api_key="gm-secret-never-logged")
    await provider.analyze(_request())
    assert seen[0].headers["x-goog-api-key"] == "gm-secret-never-logged"
    assert "gm-secret-never-logged" not in str(seen[0].url)
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "gm-secret-never-logged" not in logs
    assert OCR_PAGE_1 not in logs
    assert base64.b64encode(PNG_BYTES).decode("ascii") not in logs
    assert "reasoning" not in json.dumps(provider.last_metrics)


@pytest.mark.asyncio
async def test_unavailable_provider_fails_closed():
    provider = UnavailableDocumentIntelligenceProvider()
    with pytest.raises(DocumentIntelligenceError, match="document_intelligence_unavailable"):
        await provider.analyze(_request())


def test_normalize_rejects_duplicate_or_invalid_pages():
    base = _ocr_result()
    base["pages"].append({"page_number": 1, "text_blocks": []})
    with pytest.raises(DocumentIntelligenceError, match="gemini_invalid_schema"):
        normalize_document_intelligence(base, max_pages=20)


# ---------------------------------------------------------------------------
# Pipeline integration (real DB, fake provider injected at the route boundary)
# ---------------------------------------------------------------------------
OTHER_TENANT = "tenant-docai-other"
OTHER_USER = "user-docai-other"


class _FailingProvider:
    provider_name = "gemini"
    model_version = "gemini-2.5-flash"

    def __init__(self, code: str):
        self._code = code
        self.call_count = 0

    async def analyze(self, request: DocumentAnalysisInput) -> dict:
        self.call_count += 1
        raise DocumentIntelligenceError(self._code)


class _GeminiLikeProvider(DeterministicDocumentIntelligenceProvider):
    provider_name = "gemini"
    model_version = "gemini-2.5-flash"


@pytest_asyncio.fixture(autouse=True)
async def db_setup():
    maker = get_sessionmaker()
    tenants = ["local", OTHER_TENANT]
    async with maker() as session:
        for model in (DocumentExtraction, DocumentPage, Document, CaseFact, Contradiction):
            await session.execute(delete(model).where(model.tenant_id.in_(tenants)))
        await session.execute(delete(CaseMember).where(CaseMember.tenant_id.in_(tenants)))
        await session.execute(delete(Case).where(Case.tenant_id.in_(tenants)))
        await session.execute(delete(AuditEvent).where(AuditEvent.tenant_id.in_(tenants)))
        await session.execute(delete(User).where(User.id.in_(["local-user", OTHER_USER])))
        await session.execute(delete(Tenant).where(Tenant.id.in_(tenants)))
        await session.flush()
        session.add(Tenant(id="local", name="Local", slug="local-docai", status="active"))
        session.add(Tenant(id=OTHER_TENANT, name="Other", slug="other-docai", status="active"))
        session.add(User(id="local-user", tenant_id="local", email_normalized="docai@local",
                         display_name="L", status="active", role="lawyer"))
        session.add(User(id=OTHER_USER, tenant_id=OTHER_TENANT, email_normalized="docai@other",
                         display_name="O", status="active", role="lawyer"))
        await session.commit()
    yield
    async with maker() as session:
        for model in (DocumentExtraction, DocumentPage, Document, CaseFact, Contradiction):
            await session.execute(delete(model).where(model.tenant_id.in_(tenants)))
        await session.execute(delete(CaseMember).where(CaseMember.tenant_id.in_(tenants)))
        await session.execute(delete(Case).where(Case.tenant_id.in_(tenants)))
        await session.execute(delete(AuditEvent).where(AuditEvent.tenant_id.in_(tenants)))
        await session.execute(delete(User).where(User.id.in_(["local-user", OTHER_USER])))
        await session.execute(delete(Tenant).where(Tenant.id.in_(tenants)))
        await session.commit()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def ocr_provider(monkeypatch: pytest.MonkeyPatch) -> _GeminiLikeProvider:
    provider = _GeminiLikeProvider(_ocr_result())
    monkeypatch.setattr(pipeline_routes, "_document_intelligence_provider", lambda: provider)
    return provider


def make_pdf(text: str = "") -> bytes:
    document = fitz.open()
    page = document.new_page()
    if text:
        page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


async def _make_case(client: AsyncClient, title: str = "DocAI Case") -> str:
    r = await client.post("/api/v1/cases", json={"title": title})
    assert r.status_code == 201
    return r.json()["id"]


def _upload(client, case_id, name, content, mime):
    return client.post(f"/api/v1/cases/{case_id}/documents", files={"file": (name, content, mime)})


@pytest.mark.asyncio
async def test_native_text_pdf_never_calls_ai(client: AsyncClient, ocr_provider):
    case_id = await _make_case(client)
    r = await _upload(client, case_id, "karar.pdf",
                      make_pdf("Esas No: 2023/456 Karar metni burada."), "application/pdf")
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "awaiting_confirmation"
    assert ocr_provider.call_count == 0
    analysis = (await client.get(
        f"/api/v1/cases/{case_id}/documents/{r.json()['id']}/analysis")).json()
    assert all(e["provider_name"] == "deterministic" for e in analysis["extractions"])
    assert all(e["analysis_run_id"] for e in analysis["extractions"])


@pytest.mark.asyncio
async def test_png_upload_runs_ocr_with_real_page_order(client: AsyncClient, ocr_provider):
    case_id = await _make_case(client)
    r = await _upload(client, case_id, "foto.png", PNG_BYTES, "image/png")
    assert r.status_code == 201, r.text
    data = r.json()
    assert ocr_provider.call_count == 1
    assert data["status"] == "awaiting_confirmation"
    assert data["analysis_status"] == "analyzed"
    assert data["page_count"] == 2
    assert data["extracted_text_available"] is True
    assert data["document_type"] == "fatura"
    assert data["document_type_source"] == "ai_suggested"

    pages = (await client.get(f"/api/v1/cases/{case_id}/documents/{data['id']}/pages")).json()
    assert [p["page_number"] for p in pages] == [1, 2]
    assert pages[0]["text"] == OCR_PAGE_1
    assert pages[1]["text"] == OCR_PAGE_2

    analysis = (await client.get(f"/api/v1/cases/{case_id}/documents/{data['id']}/analysis")).json()
    extractions = analysis["extractions"]
    assert len(extractions) == 2
    assert all(e["verification_status"] == "detected" for e in extractions)
    assert all(e["provider_name"] == "gemini" for e in extractions)
    assert all(e["provider_model"] == "gemini-2.5-flash" for e in extractions)
    run_ids = {e["analysis_run_id"] for e in extractions}
    assert len(run_ids) == 1 and all(run_ids)

    # No CaseFact is auto-created from AI findings.
    mem = await client.get(f"/api/v1/cases/{case_id}/memory")
    assert mem.json()["counts"]["facts"] == 0


@pytest.mark.asyncio
async def test_scanned_pdf_without_text_layer_falls_back_to_ai(client: AsyncClient, ocr_provider):
    case_id = await _make_case(client)
    r = await _upload(client, case_id, "tarama.pdf", make_pdf(""), "application/pdf")
    assert r.status_code == 201, r.text
    assert ocr_provider.call_count == 1
    assert r.json()["status"] == "awaiting_confirmation"


@pytest.mark.asyncio
async def test_image_without_provider_keeps_honest_unsupported(client: AsyncClient):
    # Default configuration: no document intelligence provider -> no AI call.
    case_id = await _make_case(client)
    r = await _upload(client, case_id, "foto.png", PNG_BYTES, "image/png")
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "unsupported"
    assert r.json()["failure_code"] == "DOC-OCR-07"


@pytest.mark.asyncio
async def test_provider_hard_failure_fails_document_closed(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    provider = _FailingProvider("gemini_timeout")
    monkeypatch.setattr(pipeline_routes, "_document_intelligence_provider", lambda: provider)
    case_id = await _make_case(client)
    r = await _upload(client, case_id, "foto.png", PNG_BYTES, "image/png")
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "failed"
    assert r.json()["analysis_status"] == "ai_failed"
    assert r.json()["failure_code"] == "gemini_timeout"


@pytest.mark.asyncio
async def test_confirm_gemini_extraction_creates_document_verified_fact(
    client: AsyncClient, ocr_provider
):
    case_id = await _make_case(client)
    doc = (await _upload(client, case_id, "foto.png", PNG_BYTES, "image/png")).json()
    extractions = (await client.get(
        f"/api/v1/cases/{case_id}/documents/{doc['id']}/analysis")).json()["extractions"]
    amount = next(e for e in extractions if e["field_key"] == "amount")

    confirm = await client.post(
        f"/api/v1/cases/{case_id}/documents/{doc['id']}/extractions/{amount['id']}/confirm")
    assert confirm.status_code == 200
    assert confirm.json()["verification_status"] == "user_confirmed"
    assert confirm.json()["memory_fact_id"]
    mem = await client.get(f"/api/v1/cases/{case_id}/memory")
    facts = mem.json()["facts"]
    assert any(f["verification_status"] == "document_verified" for f in facts)


@pytest.mark.asyncio
async def test_reject_gemini_extraction_creates_no_fact(client: AsyncClient, ocr_provider):
    case_id = await _make_case(client)
    doc = (await _upload(client, case_id, "foto.png", PNG_BYTES, "image/png")).json()
    extraction = (await client.get(
        f"/api/v1/cases/{case_id}/documents/{doc['id']}/analysis")).json()["extractions"][0]
    r = await client.post(
        f"/api/v1/cases/{case_id}/documents/{doc['id']}/extractions/{extraction['id']}/reject")
    assert r.status_code == 200
    assert r.json()["verification_status"] == "rejected"
    mem = await client.get(f"/api/v1/cases/{case_id}/memory")
    assert mem.json()["counts"]["facts"] == 0


@pytest.mark.asyncio
async def test_rerun_is_idempotent_no_duplicate_pages_or_extractions(
    client: AsyncClient, ocr_provider
):
    case_id = await _make_case(client)
    doc = (await _upload(client, case_id, "foto.png", PNG_BYTES, "image/png")).json()
    retry = await client.post(f"/api/v1/cases/{case_id}/documents/{doc['id']}/retry")
    assert retry.status_code == 200
    assert ocr_provider.call_count == 2

    pages = (await client.get(f"/api/v1/cases/{case_id}/documents/{doc['id']}/pages")).json()
    assert [p["page_number"] for p in pages] == [1, 2]
    extractions = (await client.get(
        f"/api/v1/cases/{case_id}/documents/{doc['id']}/analysis")).json()["extractions"]
    keys = [(e["field_key"], e["value"]) for e in extractions]
    assert len(keys) == len(set(keys)) == 2


@pytest.mark.asyncio
async def test_quarantined_document_is_never_processed(
    client: AsyncClient, ocr_provider
):
    case_id = await _make_case(client)
    doc = (await _upload(client, case_id, "foto.png", PNG_BYTES, "image/png")).json()
    maker = get_sessionmaker()
    async with maker() as session:
        row = (await session.execute(select(Document).where(Document.id == doc["id"]))).scalar_one()
        row.status = "quarantined"
        await session.commit()
    calls_before = ocr_provider.call_count
    retry = await client.post(f"/api/v1/cases/{case_id}/documents/{doc['id']}/retry")
    assert retry.status_code == 409
    assert ocr_provider.call_count == calls_before


@pytest.mark.asyncio
async def test_deleted_document_cannot_be_reanalyzed(client: AsyncClient, ocr_provider):
    case_id = await _make_case(client)
    doc = (await _upload(client, case_id, "foto.png", PNG_BYTES, "image/png")).json()
    assert (await client.delete(f"/api/v1/cases/{case_id}/documents/{doc['id']}")).status_code == 204
    calls_before = ocr_provider.call_count
    retry = await client.post(f"/api/v1/cases/{case_id}/documents/{doc['id']}/retry")
    assert retry.status_code == 404
    assert ocr_provider.call_count == calls_before


@pytest.mark.asyncio
async def test_foreign_case_upload_404_even_with_provider(client: AsyncClient, ocr_provider):
    maker = get_sessionmaker()
    async with maker() as session:
        session.add(Case(id="foreign-docai-case", tenant_id=OTHER_TENANT,
                         owner_user_id=OTHER_USER, title="Foreign", legal_topic="x",
                         status="active", version=1))
        await session.commit()
    r = await _upload(client, "foreign-docai-case", "foto.png", PNG_BYTES, "image/png")
    assert r.status_code == 404
    assert ocr_provider.call_count == 0


@pytest.mark.asyncio
async def test_raw_gemini_response_is_never_stored_or_logged(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, caplog
):
    caplog.set_level(logging.DEBUG)
    provider = _provider(
        lambda _req: httpx.Response(200, json=_gemini_http_response(_ocr_result())))
    monkeypatch.setattr(pipeline_routes, "_document_intelligence_provider", lambda: provider)
    case_id = await _make_case(client)
    doc = (await _upload(client, case_id, "foto.png", PNG_BYTES, "image/png")).json()
    assert doc["status"] == "awaiting_confirmation"

    raw_markers = ("finishReason", "usageMetadata", "candidatesTokenCount", "text_blocks")
    maker = get_sessionmaker()
    async with maker() as session:
        page_rows = (await session.execute(
            select(DocumentPage).where(DocumentPage.document_id == doc["id"]))).scalars().all()
        extraction_rows = (await session.execute(
            select(DocumentExtraction).where(DocumentExtraction.document_id == doc["id"]))).scalars().all()
        audit_rows = (await session.execute(
            select(AuditEvent).where(AuditEvent.case_id == case_id))).scalars().all()
    stored = [p.text for p in page_rows]
    stored += [f"{e.value}|{e.normalized_value}|{e.source_quote}" for e in extraction_rows]
    stored += [str(a.safe_metadata) for a in audit_rows]
    for blob in stored:
        for marker in raw_markers:
            assert marker not in blob
    assert sorted(p.text for p in page_rows) == sorted([OCR_PAGE_1, OCR_PAGE_2])

    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "gm-test-key" not in logs
    assert OCR_PAGE_1 not in logs and OCR_PAGE_2 not in logs
    assert "12.500 TL" not in logs
