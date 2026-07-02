"""Safe Gemini JSON client used by optional AI agents."""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeminiJSONResult:
    ai_used: bool
    data: dict[str, Any]
    warnings: list[str]


class GeminiClient:
    """Small wrapper around google-genai with JSON cleanup and graceful fallback."""

    def generate_json(
        self,
        *,
        system_instruction: str,
        prompt: str,
        fallback: dict[str, Any],
        use_gemini: bool = True,
        respect_enabled_flag: bool = True,
    ) -> GeminiJSONResult:
        settings = get_settings()
        if not use_gemini:
            return GeminiJSONResult(ai_used=False, data=fallback, warnings=["Gemini isteği kullanıcı tercihiyle kapalı."])
        if respect_enabled_flag and not settings.gemini_enabled:
            return GeminiJSONResult(ai_used=False, data=fallback, warnings=["Gemini kapalı; kural tabanlı fallback kullanıldı."])
        if not settings.gemini_api_key:
            return GeminiJSONResult(ai_used=False, data=fallback, warnings=["GEMINI_API_KEY tanımlı değil; fallback kullanıldı."])

        try:
            raw_text = self._call_gemini(
                api_key=settings.gemini_api_key,
                model=settings.gemini_model,
                timeout_seconds=settings.gemini_timeout_seconds,
                system_instruction=system_instruction,
                prompt=prompt,
            )
            parsed = self._parse_json(raw_text)
            if not isinstance(parsed, dict):
                return GeminiJSONResult(ai_used=False, data=fallback, warnings=["Gemini JSON nesnesi döndürmedi; fallback kullanıldı."])
            return GeminiJSONResult(ai_used=True, data=parsed, warnings=[])
        except TimeoutError:
            return GeminiJSONResult(ai_used=False, data=fallback, warnings=["Gemini zaman aşımına uğradı; fallback kullanıldı."])
        except Exception as exc:  # noqa: BLE001 - API integration must not break local flow.
            logger.warning("Gemini call failed without exposing credentials: %s", exc.__class__.__name__)
            return GeminiJSONResult(ai_used=False, data=fallback, warnings=[f"Gemini hatası nedeniyle fallback kullanıldı: {exc.__class__.__name__}"])

    def _call_gemini(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: int,
        system_instruction: str,
        prompt: str,
    ) -> str:
        def run() -> str:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )
            return str(getattr(response, "text", "") or "")

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run)
            return future.result(timeout=max(timeout_seconds, 1))

    @staticmethod
    def _parse_json(raw_text: str) -> Any:
        cleaned = GeminiClient._strip_json_markdown(raw_text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            candidate = GeminiClient._extract_first_json_object(cleaned)
            return json.loads(candidate)

    @staticmethod
    def _strip_json_markdown(raw_text: str) -> str:
        text = str(raw_text or "").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        return text.strip()

    @staticmethod
    def _extract_first_json_object(text: str) -> str:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise json.JSONDecodeError("No JSON object found", text, 0)
        return text[start : end + 1]


gemini_client = GeminiClient()
