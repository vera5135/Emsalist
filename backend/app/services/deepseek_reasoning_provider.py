"""DeepSeek-backed implementation of the existing LegalReasoningProvider."""
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.services.legal_reasoning_service import ReasoningProviderUnavailable


class DeepSeekReasoningError(ReasoningProviderUnavailable):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class DeepSeekReasoningProvider:
    provider_name = "deepseek"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-v4-pro",
        reasoning_effort: str = "high",
        timeout_seconds: int = 60,
        max_retries: int = 2,
        http_client: httpx.AsyncClient | None = None,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
    ):
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self.model_version = model.strip() or "deepseek-v4-pro"
        self._reasoning_effort = reasoning_effort if reasoning_effort in {"high", "max"} else "high"
        self._timeout_seconds = max(1, int(timeout_seconds))
        self._max_retries = max(0, int(max_retries))
        self._http_client = http_client
        self._sleeper = sleeper or asyncio.sleep
        self.last_metrics: dict[str, Any] = {}

    async def analyze(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._api_key:
            raise DeepSeekReasoningError("deepseek_api_key_missing")
        source_index = _source_index(payload)
        started = time.perf_counter()
        attempts = 0
        response_json: dict[str, Any] | None = None
        last_code = "deepseek_request_failed"
        for attempt in range(self._max_retries + 1):
            attempts += 1
            try:
                response_json = await self._post(payload)
                last_code = ""
                break
            except DeepSeekReasoningError as exc:
                last_code = exc.code
                if exc.code not in {"deepseek_timeout", "deepseek_rate_limited", "deepseek_server_error", "deepseek_connection_error"}:
                    raise
                if attempt >= self._max_retries:
                    raise
                await self._sleeper(min(2 ** attempt, 5))
        if response_json is None:
            raise DeepSeekReasoningError(last_code)
        candidate, usage = _extract_candidate(response_json)
        normalized = normalize_deepseek_reasoning(candidate, source_index)
        self.last_metrics = {
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "request_count": attempts,
            "token_usage": usage,
        }
        normalized.setdefault("safe_summary", {})["provider_metrics"] = self.last_metrics
        return normalized

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = {
            "model": self.model_version,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(_prompt_payload(payload), ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
            "thinking": "enabled",
            "reasoning_effort": self._reasoning_effort,
        }
        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        owns_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(timeout=self._timeout_seconds)
        try:
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers=headers,
                json=body,
                timeout=self._timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise DeepSeekReasoningError("deepseek_timeout") from exc
        except httpx.RequestError as exc:
            raise DeepSeekReasoningError("deepseek_connection_error") from exc
        finally:
            if owns_client:
                await client.aclose()
        if response.status_code == 429:
            raise DeepSeekReasoningError("deepseek_rate_limited")
        if response.status_code >= 500:
            raise DeepSeekReasoningError("deepseek_server_error")
        if response.status_code >= 400:
            raise DeepSeekReasoningError("deepseek_http_error")
        try:
            return response.json()
        except ValueError as exc:
            raise DeepSeekReasoningError("deepseek_invalid_json") from exc


_SYSTEM_PROMPT = (
    "Return only JSON. Do not include chain-of-thought, hidden reasoning, markdown, "
    "or raw legal text. Use only provided source identifiers and metadata."
)

_REQUIRED_TOP_LEVEL = {
    "fact_summary",
    "chronology",
    "legal_issues",
    "claims",
    "defenses",
    "burdens_of_proof",
    "evidence_gaps",
    "precedent_similarities",
    "precedent_differences",
    "favorable_use",
    "adverse_use",
    "risks",
    "missing_facts",
    "paragraph_references",
    "confidence",
    "needs_review",
}

_TEXT_KEYS = {
    "fact_summary", "chronology", "claims", "defenses", "burdens_of_proof",
    "evidence_gaps", "precedent_similarities", "precedent_differences",
    "favorable_use", "adverse_use", "risks", "missing_facts",
}


def _prompt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_scope": payload.get("case_scope", {}),
        "case_memory": payload.get("case_memory", {}),
        "legal_sources": payload.get("legal_sources", {}),
        "required_json_keys": sorted(_REQUIRED_TOP_LEVEL),
    }


def _extract_candidate(response_json: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        content = response_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DeepSeekReasoningError("deepseek_invalid_response") from exc
    if not isinstance(content, str):
        raise DeepSeekReasoningError("deepseek_invalid_response")
    try:
        candidate = json.loads(content)
    except ValueError as exc:
        raise DeepSeekReasoningError("deepseek_invalid_json") from exc
    if not isinstance(candidate, dict):
        raise DeepSeekReasoningError("deepseek_invalid_schema")
    usage = response_json.get("usage", {})
    return candidate, usage if isinstance(usage, dict) else {}


def _source_index(payload: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    items = payload.get("legal_sources", {}).get("items", [])
    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    if not isinstance(items, list):
        return result
    for item in items:
        if not isinstance(item, dict):
            continue
        key = (
            str(item.get("source_record_id", "")),
            str(item.get("source_version_id", "")),
            str(item.get("source_paragraph_id", "")),
        )
        if all(key):
            result[key] = item
    return result


def normalize_deepseek_reasoning(
    candidate: dict[str, Any],
    source_index: dict[tuple[str, str, str], dict[str, Any]],
) -> dict[str, Any]:
    if set(candidate) - _REQUIRED_TOP_LEVEL:
        raise DeepSeekReasoningError("deepseek_invalid_schema")
    if not _REQUIRED_TOP_LEVEL <= set(candidate):
        raise DeepSeekReasoningError("deepseek_invalid_schema")
    if not isinstance(candidate["confidence"], (int, float)):
        raise DeepSeekReasoningError("deepseek_invalid_schema")
    if not isinstance(candidate["needs_review"], bool):
        raise DeepSeekReasoningError("deepseek_invalid_schema")
    for key in _TEXT_KEYS:
        if not isinstance(candidate[key], list):
            raise DeepSeekReasoningError("deepseek_invalid_schema")
    legal_issues = candidate["legal_issues"]
    if not isinstance(legal_issues, list) or not legal_issues:
        raise DeepSeekReasoningError("deepseek_invalid_schema")
    _validate_references(candidate, source_index)
    issues = []
    for index, item in enumerate(legal_issues):
        if not isinstance(item, dict):
            raise DeepSeekReasoningError("deepseek_invalid_schema")
        title = _required_text(item, "title")
        code = _safe_code(item.get("issue_code") or title)
        issues.append({
            "issue_code": code,
            "title": title,
            "description": _required_text(item, "description"),
            "status": item.get("status") if item.get("status") in {"proposed", "needs_review"} else "needs_review",
            "parent_code": None if index == 0 else _safe_code(legal_issues[0].get("issue_code") or legal_issues[0].get("title")),
        })
    counterarguments = []
    for idx, item in enumerate(candidate["adverse_use"]):
        text = _coerce_text(item)
        if text:
            counterarguments.append({
                "issue_code": issues[0]["issue_code"],
                "category": "adverse_precedent_use",
                "title": f"Aleyhe kullanım {idx + 1}",
                "rationale": text,
                "basis": "DeepSeek structured output; exact paragraph provenance is in safe_summary.paragraph_references.",
            })
    return {
        "issues": issues,
        "counterarguments": counterarguments,
        "safe_summary": {
            "deepseek_structured": candidate,
            "paragraph_references": candidate["paragraph_references"],
        },
    }


def _validate_references(candidate: dict[str, Any], source_index: dict[tuple[str, str, str], dict[str, Any]]) -> None:
    refs = list(candidate["paragraph_references"])
    if not refs:
        raise DeepSeekReasoningError("deepseek_missing_provenance")
    for item in candidate.values():
        if isinstance(item, list):
            for entry in item:
                if isinstance(entry, dict) and "paragraph_references" in entry:
                    nested = entry["paragraph_references"]
                    if not isinstance(nested, list):
                        raise DeepSeekReasoningError("deepseek_invalid_schema")
                    refs.extend(nested)
    for ref in refs:
        if not isinstance(ref, dict):
            raise DeepSeekReasoningError("deepseek_invalid_schema")
        key = (
            _required_text(ref, "source_record_id"),
            _required_text(ref, "source_version_id"),
            _required_text(ref, "source_paragraph_id"),
        )
        source = source_index.get(key)
        if source is None:
            raise DeepSeekReasoningError("deepseek_unknown_source_provenance")
        for field in ("court", "chamber", "case_number", "decision_number", "decision_date", "article_number"):
            if field in ref and ref[field] not in ("", None) and str(ref[field]) != str(source.get(field, "")):
                raise DeepSeekReasoningError("deepseek_hallucinated_source_metadata")


def _required_text(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DeepSeekReasoningError("deepseek_invalid_schema")
    return value.strip()


def _coerce_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("text", "summary", "rationale"):
            if isinstance(value.get(key), str) and value[key].strip():
                return value[key].strip()
    return ""


def _safe_code(value: Any) -> str:
    raw = str(value or "issue").lower()
    chars = [ch if ch.isalnum() else "_" for ch in raw]
    code = "".join(chars).strip("_")
    return code[:60] or "issue"
