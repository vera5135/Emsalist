from __future__ import annotations

import asyncio
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


def _source(index: int, raw_text: str | None = None):
    return {
        "source_record_id": f"sr-{index}",
        "source_version_id": f"sv-{index}",
        "source_paragraph_id": f"sp-{index}",
        "court": "Yargıtay",
        "chamber": f"{index}. HD",
        "case_number": f"2024/{index}",
        "decision_number": f"2024/{100 + index}",
        "decision_date": "2024-01-02",
        "article_number": "",
        "paragraph_index": 0,
        "text_hash": f"hash-{index}",
        "text": raw_text or (f"Emsal karar {index} paragraf metni. " * 40),
    }


def _payload(source_count: int = 1, raw_text: str | None = None):
    return {
        "case_scope": {"tenant_id": "t1", "case_id": "c1"},
        "case_memory": {
            "facts": [{"id": "f1", "type": "defect", "value": "motor arızası"}],
            "missing_information": [],
        },
        "legal_sources": {
            "content_boundary": "UNTRUSTED_LEGAL_CONTENT",
            "items": [_source(index, raw_text=raw_text) for index in range(1, source_count + 1)],
        },
    }


def _case_content(**overrides):
    value = {
        "fact_summary": ["Araçta gizli ayıp iddiası var."],
        "chronology": ["Satıştan sonra arıza çıktı."],
        "legal_issues": [{
            "issue_code": "defective_vehicle",
            "title": "Ayıplı araç",
            "description": "Gizli ayıp ve satıcının sorumluluğu.",
            "status": "proposed",
        }],
        "claims": ["Bedel iadesi"],
        "defenses": ["Kullanıcı hatası savunması"],
        "burdens_of_proof": ["Ayıbın teslim anında varlığı ispatlanmalı."],
        "evidence_gaps": ["Servis raporu eksik."],
        "risks": ["İspat riski"],
        "missing_facts": ["İhbar tarihi"],
        "confidence": 0.82,
        "needs_review": True,
    }
    value.update(overrides)
    return value


def _precedent_entry(index: int, **overrides):
    value = {
        "source_record_id": f"sr-{index}",
        "source_version_id": f"sv-{index}",
        "source_paragraph_id": f"sp-{index}",
        "similarities": [f"Benzerlik {index}"],
        "differences": [f"Fark {index}"],
        "favorable_use": [f"Lehe kullanım {index}"],
        "adverse_use": [f"Aleyhe kullanım {index}"],
        "confidence": 0.8,
        "needs_review": False,
    }
    value.update(overrides)
    return value


_USAGE = {
    "prompt_tokens": 12,
    "completion_tokens": 34,
    "total_tokens": 46,
    "prompt_cache_hit_tokens": 2,
    "prompt_cache_miss_tokens": 10,
    "completion_tokens_details": {"reasoning_tokens": 5},
}


def _chat_response(content, usage=None, finish_reason="stop"):
    return {
        "choices": [{"finish_reason": finish_reason, "message": {"content": content}}],
        "usage": usage or dict(_USAGE),
    }


def _prompt_of(request: httpx.Request) -> dict:
    body = json.loads(request.content)
    return json.loads(body["messages"][1]["content"])


def _default_handler(request: httpx.Request) -> httpx.Response:
    prompt = _prompt_of(request)
    if prompt["task"] == "case_analysis":
        return httpx.Response(200, json=_chat_response(json.dumps(_case_content(), ensure_ascii=False)))
    entries = [
        _precedent_entry(int(item["source_record_id"].split("-")[1]))
        for item in prompt["precedents"]
    ]
    return httpx.Response(200, json=_chat_response(json.dumps({"precedents": entries}, ensure_ascii=False)))


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def _noop_sleep(_seconds: float) -> None:
    return None


def test_provider_selection(monkeypatch: pytest.MonkeyPatch):
    import app.config as app_config

    monkeypatch.setattr(app_config, "_load_env_file", lambda: None)
    for key in ("DEEPSEEK_MAX_TOKENS", "DEEPSEEK_PRECEDENT_BATCH_SIZE",
                "DEEPSEEK_BATCH_CONCURRENCY", "DEEPSEEK_MAX_PARAGRAPHS_PER_SOURCE",
                "DEEPSEEK_MAX_SOURCE_CHARS"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AI_REASONING_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.deepseek_max_tokens == 8192
    assert settings.deepseek_precedent_batch_size == 2
    assert settings.deepseek_batch_concurrency == 2
    assert settings.deepseek_max_paragraphs_per_source == 3
    assert settings.deepseek_max_source_chars == 6000
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
async def test_case_and_precedent_calls_are_split_and_compact():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _default_handler(request)

    provider = DeepSeekReasoningProvider(
        api_key="ds-secret",
        max_source_chars=120,
        http_client=_client(handler),
    )
    result = await provider.analyze(_payload())

    assert len(requests) == 2
    case_body = json.loads(requests[0].content)
    case_prompt = _prompt_of(requests[0])
    assert case_prompt["task"] == "case_analysis"
    assert "precedents" not in case_prompt
    assert "legal_sources" not in case_prompt
    raw_text = _payload()["legal_sources"]["items"][0]["text"]
    assert raw_text[:120] not in json.dumps(case_prompt, ensure_ascii=False)
    assert case_body["temperature"] == 0
    assert case_body["response_format"] == {"type": "json_object"}
    assert case_body["model"] == "deepseek-v4-pro"
    assert case_body["thinking"] == {"type": "enabled"}
    assert case_body["reasoning_effort"] == "high"
    assert case_body["stream"] is False
    assert case_body["max_tokens"] == 8192
    assert requests[0].headers["authorization"] == "Bearer ds-secret"

    precedent_body = json.loads(requests[1].content)
    precedent_prompt = _prompt_of(requests[1])
    assert precedent_prompt["task"] == "precedent_analysis"
    assert precedent_body["temperature"] == 0
    assert len(precedent_prompt["precedents"]) == 1
    compact = precedent_prompt["precedents"][0]
    assert compact["source_record_id"] == "sr-1"
    assert compact["text_hash"] == "hash-1"
    assert compact["case_number"] == "2024/1"
    assert compact["decision_number"] == "2024/101"
    assert compact["chamber"] == "1. HD"
    assert compact["decision_date"] == "2024-01-02"
    assert "text" not in compact
    assert compact["paragraph_excerpt"] == raw_text[:120]
    request_text = requests[1].content.decode("utf-8")
    assert request_text.count(json.dumps(compact["paragraph_excerpt"], ensure_ascii=False)[1:-1]) == 1

    assert result["issues"][0]["issue_code"] == "defective_vehicle"
    assert result["counterarguments"]
    summary = result["safe_summary"]
    assert summary["paragraph_references"] == [{
        "source_record_id": "sr-1", "source_version_id": "sv-1", "source_paragraph_id": "sp-1",
    }]
    assert summary["provider_metrics"]["request_count"] == 2


@pytest.mark.asyncio
async def test_eight_sources_batch_size_two_yields_five_bounded_calls():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _default_handler(request)

    provider = DeepSeekReasoningProvider(
        api_key="x",
        precedent_batch_size=2,
        batch_concurrency=2,
        http_client=_client(handler),
    )
    result = await provider.analyze(_payload(source_count=8))

    assert len(requests) == 5
    tasks = [_prompt_of(request)["task"] for request in requests]
    assert tasks.count("case_analysis") == 1
    assert tasks.count("precedent_analysis") == 4
    batch_ids = [
        [item["source_record_id"] for item in _prompt_of(request)["precedents"]]
        for request in requests if _prompt_of(request)["task"] == "precedent_analysis"
    ]
    assert sorted(batch_ids) == [
        ["sr-1", "sr-2"], ["sr-3", "sr-4"], ["sr-5", "sr-6"], ["sr-7", "sr-8"],
    ]

    summary = result["safe_summary"]
    metrics = summary["provider_metrics"]
    assert metrics["request_count"] == 5
    assert len(metrics["calls"]) == 5
    assert metrics["calls"][0]["call_type"] == "case_analysis"
    assert [call["batch_index"] for call in metrics["calls"][1:]] == [0, 1, 2, 3]
    assert metrics["finish_reasons"] == ["stop"] * 5
    assert metrics["prompt_tokens"] == 12 * 5
    assert metrics["completion_tokens"] == 34 * 5
    assert metrics["total_tokens"] == 46 * 5
    assert metrics["reasoning_tokens"] == 5 * 5
    assert metrics["prompt_cache_hit_tokens"] == 2 * 5
    assert metrics["prompt_cache_miss_tokens"] == 10 * 5
    assert metrics["max_tokens_per_request"] == 8192
    for call in metrics["calls"]:
        assert call["finish_reason"] == "stop"
        assert call["request_count"] == 1

    refs = summary["paragraph_references"]
    assert [ref["source_record_id"] for ref in refs] == [f"sr-{i}" for i in range(1, 9)]
    assert len({(r["source_record_id"], r["source_version_id"], r["source_paragraph_id"]) for r in refs}) == 8

    structured = summary["deepseek_structured"]
    similarity_refs = [
        entry["paragraph_references"][0]["source_record_id"]
        for entry in structured["precedent_similarities"]
    ]
    assert similarity_refs == [f"sr-{i}" for i in range(1, 9)]
    assert [entry["text"] for entry in structured["precedent_similarities"]] == [
        f"Benzerlik {i}" for i in range(1, 9)
    ]
    assert len(structured["adverse_use"]) == 8


@pytest.mark.asyncio
async def test_precedent_batch_concurrency_is_bounded():
    state = {"active": 0, "max_active": 0, "case_done": False, "case_first": True}

    async def handler(request: httpx.Request) -> httpx.Response:
        prompt = _prompt_of(request)
        if prompt["task"] == "case_analysis":
            await asyncio.sleep(0.01)
            state["case_done"] = True
            return _default_handler(request)
        if not state["case_done"]:
            state["case_first"] = False
        state["active"] += 1
        state["max_active"] = max(state["max_active"], state["active"])
        await asyncio.sleep(0.02)
        state["active"] -= 1
        return _default_handler(request)

    provider = DeepSeekReasoningProvider(
        api_key="x",
        precedent_batch_size=2,
        batch_concurrency=2,
        http_client=_client(handler),
    )
    await provider.analyze(_payload(source_count=8))
    assert state["case_first"] is True
    assert state["max_active"] <= 2
    assert state["max_active"] >= 1


@pytest.mark.asyncio
async def test_truncated_batch_fails_whole_analysis_closed():
    def handler(request: httpx.Request) -> httpx.Response:
        prompt = _prompt_of(request)
        if prompt["task"] == "precedent_analysis" and any(
            item["source_record_id"] == "sr-3" for item in prompt["precedents"]
        ):
            return httpx.Response(200, json=_chat_response("{}", finish_reason="length"))
        return _default_handler(request)

    provider = DeepSeekReasoningProvider(
        api_key="x",
        precedent_batch_size=2,
        batch_concurrency=2,
        http_client=_client(handler),
    )
    with pytest.raises(DeepSeekReasoningError, match="deepseek_output_truncated"):
        await provider.analyze(_payload(source_count=8))


@pytest.mark.asyncio
async def test_output_count_and_char_limits_are_enforced():
    long_text = "Ç" * 1000

    def handler(request: httpx.Request) -> httpx.Response:
        prompt = _prompt_of(request)
        if prompt["task"] == "case_analysis":
            content = _case_content(
                chronology=[f"{long_text} {i}" for i in range(10)],
                claims=[f"talep {i} {long_text}" for i in range(8)],
                defenses=[f"savunma {i}" for i in range(9)],
                missing_facts=[f"eksik {i}" for i in range(11)],
                legal_issues=[{
                    "issue_code": f"issue_{i}",
                    "title": f"Sorun {i}",
                    "description": long_text,
                    "status": "proposed",
                } for i in range(7)],
            )
            return httpx.Response(200, json=_chat_response(json.dumps(content, ensure_ascii=False)))
        entries = [
            _precedent_entry(
                int(item["source_record_id"].split("-")[1]),
                similarities=[f"benzer {i} {long_text}" for i in range(5)],
                differences=[f"fark {i}" for i in range(4)],
                favorable_use=[f"lehe {i}" for i in range(3)],
                adverse_use=[f"aleyhe {i}" for i in range(3)],
            )
            for item in prompt["precedents"]
        ]
        return httpx.Response(200, json=_chat_response(json.dumps({"precedents": entries}, ensure_ascii=False)))

    provider = DeepSeekReasoningProvider(api_key="x", http_client=_client(handler))
    result = await provider.analyze(_payload(source_count=2))
    structured = result["safe_summary"]["deepseek_structured"]

    assert len(structured["legal_issues"]) == 6
    assert len(structured["chronology"]) == 8
    assert len(structured["claims"]) == 6
    assert len(structured["defenses"]) == 6
    assert len(structured["missing_facts"]) == 8
    assert len(structured["precedent_similarities"]) == 3 * 2
    assert len(structured["precedent_differences"]) == 3 * 2
    assert len(structured["favorable_use"]) == 2 * 2
    assert len(structured["adverse_use"]) == 2 * 2
    for issue in structured["legal_issues"]:
        assert len(issue["description"]) <= 400
    for key in ("fact_summary", "chronology", "claims", "defenses",
                "burdens_of_proof", "evidence_gaps", "risks", "missing_facts"):
        assert all(len(item) <= 400 for item in structured[key])
    for key in ("precedent_similarities", "precedent_differences", "favorable_use", "adverse_use"):
        assert all(len(entry["text"]) <= 400 for entry in structured[key])


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

    def bad_batch_handler(request: httpx.Request) -> httpx.Response:
        prompt = _prompt_of(request)
        if prompt["task"] == "case_analysis":
            return _default_handler(request)
        return httpx.Response(200, json=_chat_response(json.dumps({"precedents": [{"unexpected": True}]})))

    invalid_batch = DeepSeekReasoningProvider(api_key="x", http_client=_client(bad_batch_handler))
    with pytest.raises(DeepSeekReasoningError, match="deepseek_invalid_schema"):
        await invalid_batch.analyze(_payload())


@pytest.mark.asyncio
async def test_finish_reason_failures_are_safe_codes():
    truncated = DeepSeekReasoningProvider(
        api_key="x",
        http_client=_client(lambda _request: httpx.Response(
            200,
            json=_chat_response(json.dumps(_case_content()), finish_reason="length"),
        )),
    )
    with pytest.raises(DeepSeekReasoningError, match="deepseek_output_truncated"):
        await truncated.analyze(_payload())

    filtered = DeepSeekReasoningProvider(
        api_key="x",
        http_client=_client(lambda _request: httpx.Response(
            200,
            json=_chat_response(json.dumps(_case_content()), finish_reason="content_filter"),
        )),
    )
    with pytest.raises(DeepSeekReasoningError, match="deepseek_content_filtered"):
        await filtered.analyze(_payload())


@pytest.mark.asyncio
async def test_empty_content_fails_closed():
    empty = DeepSeekReasoningProvider(
        api_key="x",
        http_client=_client(lambda _request: httpx.Response(200, json=_chat_response(""))),
    )
    with pytest.raises(DeepSeekReasoningError, match="deepseek_empty_response"):
        await empty.analyze(_payload())

    null_content = DeepSeekReasoningProvider(
        api_key="x",
        http_client=_client(lambda _request: httpx.Response(200, json=_chat_response(None))),
    )
    with pytest.raises(DeepSeekReasoningError, match="deepseek_empty_response"):
        await null_content.analyze(_payload())


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

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(500, json={"error": "server"})
        return _default_handler(request)

    provider = DeepSeekReasoningProvider(
        api_key="x",
        max_retries=1,
        sleeper=_noop_sleep,
        http_client=_client(handler),
    )
    result = await provider.analyze(_payload())
    metrics = result["safe_summary"]["provider_metrics"]
    assert metrics["request_count"] == 3
    assert metrics["calls"][0]["request_count"] == 2
    assert metrics["calls"][1]["request_count"] == 1
    assert calls == 3


@pytest.mark.asyncio
async def test_unknown_or_hallucinated_or_incomplete_precedents_are_rejected():
    def unknown_handler(request: httpx.Request) -> httpx.Response:
        prompt = _prompt_of(request)
        if prompt["task"] == "case_analysis":
            return _default_handler(request)
        entry = _precedent_entry(1, source_record_id="sr-missing")
        return httpx.Response(200, json=_chat_response(json.dumps({"precedents": [entry]})))

    provider = DeepSeekReasoningProvider(api_key="x", http_client=_client(unknown_handler))
    with pytest.raises(DeepSeekReasoningError, match="deepseek_unknown_source_provenance"):
        await provider.analyze(_payload())

    def hallucinated_handler(request: httpx.Request) -> httpx.Response:
        prompt = _prompt_of(request)
        if prompt["task"] == "case_analysis":
            return _default_handler(request)
        entry = _precedent_entry(1, decision_number="2024/999")
        return httpx.Response(200, json=_chat_response(json.dumps({"precedents": [entry]})))

    provider = DeepSeekReasoningProvider(api_key="x", http_client=_client(hallucinated_handler))
    with pytest.raises(DeepSeekReasoningError, match="deepseek_hallucinated_source_metadata"):
        await provider.analyze(_payload())

    def missing_handler(request: httpx.Request) -> httpx.Response:
        prompt = _prompt_of(request)
        if prompt["task"] == "case_analysis":
            return _default_handler(request)
        return httpx.Response(200, json=_chat_response(json.dumps({"precedents": [_precedent_entry(1)]})))

    provider = DeepSeekReasoningProvider(
        api_key="x", precedent_batch_size=2, http_client=_client(missing_handler),
    )
    with pytest.raises(DeepSeekReasoningError, match="deepseek_missing_precedent_analysis"):
        await provider.analyze(_payload(source_count=2))

    def duplicate_handler(request: httpx.Request) -> httpx.Response:
        prompt = _prompt_of(request)
        if prompt["task"] == "case_analysis":
            return _default_handler(request)
        return httpx.Response(200, json=_chat_response(json.dumps(
            {"precedents": [_precedent_entry(1), _precedent_entry(1)]}
        )))

    provider = DeepSeekReasoningProvider(
        api_key="x", precedent_batch_size=2, http_client=_client(duplicate_handler),
    )
    with pytest.raises(DeepSeekReasoningError, match="deepseek_duplicate_precedent_analysis"):
        await provider.analyze(_payload(source_count=2))


@pytest.mark.asyncio
async def test_reasoning_content_is_never_saved_or_returned():
    def handler(request: httpx.Request) -> httpx.Response:
        prompt = _prompt_of(request)
        if prompt["task"] == "case_analysis":
            content = json.dumps(_case_content(), ensure_ascii=False)
        else:
            entries = [
                _precedent_entry(int(item["source_record_id"].split("-")[1]))
                for item in prompt["precedents"]
            ]
            content = json.dumps({"precedents": entries}, ensure_ascii=False)
        response = _chat_response(content)
        response["choices"][0]["message"]["reasoning_content"] = "HIDDEN-CHAIN-OF-THOUGHT"
        return httpx.Response(200, json=response)

    provider = DeepSeekReasoningProvider(api_key="x", http_client=_client(handler))
    result = await provider.analyze(_payload())
    serialized = json.dumps(result, ensure_ascii=False)
    assert "reasoning_content" not in serialized
    assert "HIDDEN-CHAIN-OF-THOUGHT" not in serialized
    assert "reasoning_content" not in json.dumps(provider.last_metrics)


@pytest.mark.asyncio
async def test_no_secret_or_raw_content_logging(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.DEBUG)
    raw_text = "MÜVEKKİLİN RAW HUKUKİ METNİ LOGLANMAMALI"
    provider = DeepSeekReasoningProvider(
        api_key="ds-secret-not-logged",
        http_client=_client(_default_handler),
    )
    await provider.analyze(_payload(raw_text=raw_text))
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "ds-secret-not-logged" not in logs
    assert raw_text not in logs
