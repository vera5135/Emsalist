from __future__ import annotations

import json
import logging

import httpx
import pytest

from app.config import get_settings
from app.services.deepseek_reasoning_provider import (
    DeepSeekReasoningError,
    DeepSeekReasoningProvider,
)
from app.services.legal_reasoning_service import (
    create_configured_legal_reasoning_provider,
)


def _payload(raw_text: str = "Ayıplı araç paragraf metni."):
    return {
        "case_scope": {"tenant_id": "t1", "case_id": "c1"},
        "case_memory": {
            "facts": [{"id": "f1", "type": "defect", "value": "motor arızası"}],
            "missing_information": [],
        },
        "legal_sources": {
            "content_boundary": "UNTRUSTED_LEGAL_CONTENT",
            "items": [{
                "source_record_id": "sr-1",
                "source_version_id": "sv-1",
                "source_paragraph_id": "sp-1",
                "court": "Yargıtay",
                "chamber": "13. HD",
                "case_number": "2024/1",
                "decision_number": "2024/2",
                "decision_date": "2024-01-02",
                "article_number": "",
                "text_hash": "hash-1",
                "text": raw_text,
            }],
        },
    }


def _structured(**overrides):
    ref = {
        "source_record_id": "sr-1",
        "source_version_id": "sv-1",
        "source_paragraph_id": "sp-1",
        "court": "Yargıtay",
        "chamber": "13. HD",
        "case_number": "2024/1",
        "decision_number": "2024/2",
        "decision_date": "2024-01-02",
    }
    value = {
        "fact_summary": ["Araçta gizli ayıp iddiası var."],
        "chronology": ["Satıştan sonra arıza çıktı."],
        "legal_issues": [{
            "issue_code": "defective_vehicle",
            "title": "Ayıplı araç",
            "description": "Gizli ayıp ve satıcının sorumluluğu.",
            "status": "proposed",
            "paragraph_references": [ref],
        }],
        "claims": ["Bedel iadesi"],
        "defenses": ["Kullanıcı hatası savunması"],
        "burdens_of_proof": ["Ayıbın teslim anında varlığı ispatlanmalı."],
        "evidence_gaps": ["Servis raporu eksik."],
        "precedent_similarities": [{"text": "Motor arızası benzer.", "paragraph_references": [ref]}],
        "precedent_differences": [{"text": "Ekspertiz kapsamı farklı.", "paragraph_references": [ref]}],
        "favorable_use": [{"text": "Gizli ayıp yönünden lehe.", "paragraph_references": [ref]}],
        "adverse_use": [{"text": "İhbar süresi aleyhe tartışılabilir.", "paragraph_references": [ref]}],
        "risks": ["İspat riski"],
        "missing_facts": ["İhbar tarihi"],
        "paragraph_references": [ref],
        "confidence": 0.82,
        "needs_review": True,
    }
    value.update(overrides)
    return value


def _chat_response(content, usage=None):
    return {
        "choices": [{"message": {"content": content}}],
        "usage": usage or {"prompt_tokens": 12, "completion_tokens": 34},
    }


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def _noop_sleep(_seconds: float) -> None:
    return None


def test_provider_selection(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AI_REASONING_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    get_settings.cache_clear()
    provider = create_configured_legal_reasoning_provider()
    assert isinstance(provider, DeepSeekReasoningProvider)
    assert provider.model_version == "deepseek-v4-pro"
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_missing_api_key_fails_closed():
    provider = DeepSeekReasoningProvider(api_key="")
    with pytest.raises(DeepSeekReasoningError, match="deepseek_api_key_missing"):
        await provider.analyze(_payload())


@pytest.mark.asyncio
async def test_valid_structured_response_records_metrics_and_provenance():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=_chat_response(json.dumps(_structured(), ensure_ascii=False)),
        )

    provider = DeepSeekReasoningProvider(api_key="ds-secret", http_client=_client(handler))
    result = await provider.analyze(_payload())

    assert result["issues"][0]["issue_code"] == "defective_vehicle"
    assert result["counterarguments"]
    summary = result["safe_summary"]
    assert summary["paragraph_references"][0]["source_paragraph_id"] == "sp-1"
    assert summary["provider_metrics"]["request_count"] == 1
    assert summary["provider_metrics"]["token_usage"]["prompt_tokens"] == 12
    assert requests[0].headers["authorization"] == "Bearer ds-secret"
    body = json.loads(requests[0].content)
    assert body["response_format"] == {"type": "json_object"}
    assert body["model"] == "deepseek-v4-pro"
    assert body["reasoning_effort"] == "high"


@pytest.mark.asyncio
async def test_invalid_json_and_schema_fail_closed():
    invalid_json = DeepSeekReasoningProvider(
        api_key="x",
        http_client=_client(lambda _request: httpx.Response(200, json=_chat_response("{"))),
    )
    with pytest.raises(DeepSeekReasoningError, match="deepseek_invalid_json"):
        await invalid_json.analyze(_payload())

    invalid_schema = DeepSeekReasoningProvider(
        api_key="x",
        http_client=_client(lambda _request: httpx.Response(200, json=_chat_response(json.dumps({"legal_issues": []})))),
    )
    with pytest.raises(DeepSeekReasoningError, match="deepseek_invalid_schema"):
        await invalid_schema.analyze(_payload())


@pytest.mark.asyncio
async def test_timeout_and_429_are_safe_codes():
    timeout_provider = DeepSeekReasoningProvider(
        api_key="x",
        max_retries=0,
        http_client=_client(lambda _request: (_ for _ in ()).throw(httpx.TimeoutException("raw timeout"))),
    )
    with pytest.raises(DeepSeekReasoningError, match="deepseek_timeout"):
        await timeout_provider.analyze(_payload())

    rate_limited = DeepSeekReasoningProvider(
        api_key="x",
        max_retries=0,
        http_client=_client(lambda _request: httpx.Response(429, json={"error": "too fast"})),
    )
    with pytest.raises(DeepSeekReasoningError, match="deepseek_rate_limited"):
        await rate_limited.analyze(_payload())


@pytest.mark.asyncio
async def test_safe_retry_only_for_idempotent_provider_errors():
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500, json={"error": "server"})
        return httpx.Response(200, json=_chat_response(json.dumps(_structured(), ensure_ascii=False)))

    provider = DeepSeekReasoningProvider(
        api_key="x",
        max_retries=1,
        sleeper=_noop_sleep,
        http_client=_client(handler),
    )
    result = await provider.analyze(_payload())
    assert result["safe_summary"]["provider_metrics"]["request_count"] == 2
    assert calls == 2


@pytest.mark.asyncio
async def test_unknown_or_hallucinated_source_is_rejected():
    unknown = _structured(paragraph_references=[{
        "source_record_id": "sr-missing",
        "source_version_id": "sv-1",
        "source_paragraph_id": "sp-1",
    }])
    provider = DeepSeekReasoningProvider(
        api_key="x",
        http_client=_client(lambda _request: httpx.Response(200, json=_chat_response(json.dumps(unknown)))),
    )
    with pytest.raises(DeepSeekReasoningError, match="deepseek_unknown_source_provenance"):
        await provider.analyze(_payload())

    hallucinated = _structured()
    hallucinated["paragraph_references"][0]["decision_number"] = "2024/999"
    provider = DeepSeekReasoningProvider(
        api_key="x",
        http_client=_client(lambda _request: httpx.Response(200, json=_chat_response(json.dumps(hallucinated)))),
    )
    with pytest.raises(DeepSeekReasoningError, match="deepseek_hallucinated_source_metadata"):
        await provider.analyze(_payload())


@pytest.mark.asyncio
async def test_no_secret_or_raw_content_logging(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.DEBUG)
    raw_text = "MÜVEKKİLİN RAW HUKUKİ METNİ LOGLANMAMALI"
    provider = DeepSeekReasoningProvider(
        api_key="ds-secret-not-logged",
        http_client=_client(lambda _request: httpx.Response(200, json=_chat_response(json.dumps(_structured())))),
    )
    await provider.analyze(_payload(raw_text=raw_text))
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "ds-secret-not-logged" not in logs
    assert raw_text not in logs
