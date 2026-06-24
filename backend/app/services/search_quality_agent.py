"""AI-assisted search query builder with deterministic legal fallback."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.models.ai_models import SearchQualityResponse
from app.services.ai_output_validator import ai_output_validator
from app.services.case_enrichment_agent import (
    VEHICLE_BLOCKED_TOPICS,
    VEHICLE_LEGAL_BRAIN_QUERY,
    VEHICLE_SEARCH_KEYWORDS,
    VEHICLE_YARGITAY_QUERIES,
    case_enrichment_agent,
)
from app.services.gemini_client import gemini_client


class SearchQualityAgent:
    def build(
        self,
        *,
        case_text: str,
        case_enrichment: dict[str, Any] | None = None,
        use_gemini: bool = True,
    ) -> SearchQualityResponse:
        enrichment = case_enrichment or case_enrichment_agent.enrich(
            case_text=case_text,
            practice_area="auto",
            use_gemini=False,
        ).model_dump()
        fallback = self._fallback(case_text=case_text, enrichment=enrichment)
        gemini_result = gemini_client.generate_json(
            system_instruction=(
                "Sen Yargıtay ve Legal Brain için dar, hukuki ve özel arama sorguları üreten ajansın. "
                "Genel kelimelerle puan şişirme yapma. Sadece JSON döndür."
            ),
            prompt=(
                "Aşağıdaki olaya göre yargitay_queries, legal_brain_query, must_include_terms, "
                "should_include_terms, blocked_terms, ranking_boost_terms alanlarını üret.\n"
                f"Olay: {case_text}\n"
                f"Zenginleştirme: {json.dumps(enrichment, ensure_ascii=False)}"
            ),
            fallback=fallback.model_dump(),
            use_gemini=use_gemini,
        )
        if not gemini_result.ai_used:
            fallback.warnings.extend(gemini_result.warnings)
            return fallback
        try:
            response = SearchQualityResponse(
                ai_used=True,
                yargitay_queries=ai_output_validator.clean_ai_list(gemini_result.data.get("yargitay_queries"), max_items=12),
                legal_brain_query=" ".join(str(gemini_result.data.get("legal_brain_query") or fallback.legal_brain_query).split()),
                must_include_terms=ai_output_validator.clean_ai_list(gemini_result.data.get("must_include_terms"), max_items=20),
                should_include_terms=ai_output_validator.clean_ai_list(gemini_result.data.get("should_include_terms"), max_items=20),
                blocked_terms=ai_output_validator.clean_ai_list(gemini_result.data.get("blocked_terms"), max_items=20),
                ranking_boost_terms=ai_output_validator.clean_ai_list(gemini_result.data.get("ranking_boost_terms"), max_items=20),
                warnings=gemini_result.warnings,
            )
            if not response.yargitay_queries:
                response.yargitay_queries = fallback.yargitay_queries
            return response
        except (ValidationError, TypeError, ValueError):
            fallback.warnings.append("Gemini arama sorgusu çıktısı validator’dan geçmedi; fallback kullanıldı.")
            return fallback

    def _fallback(self, *, case_text: str, enrichment: dict[str, Any]) -> SearchQualityResponse:
        if ai_output_validator.is_vehicle_case(" ".join([case_text, json.dumps(enrichment, ensure_ascii=False)])):
            return SearchQualityResponse(
                ai_used=False,
                yargitay_queries=VEHICLE_YARGITAY_QUERIES,
                legal_brain_query=VEHICLE_LEGAL_BRAIN_QUERY,
                must_include_terms=["ayıplı araç", "gizli ayıp", "sözleşmeden dönme", "bedel indirimi"],
                should_include_terms=["TRAMER", "ekspertiz", "motor arızası", "ayıp ihbarı", "noter satış sözleşmesi"],
                blocked_terms=VEHICLE_BLOCKED_TOPICS + ["dava", "edildi", "edilebilir", "gibi", "ilişkin", "taraf", "mahkeme"],
                ranking_boost_terms=VEHICLE_SEARCH_KEYWORDS,
                warnings=[],
            )

        queries = enrichment.get("yargitay_query_templates") or []
        return SearchQualityResponse(
            ai_used=False,
            yargitay_queries=ai_output_validator.clean_ai_list(queries, max_items=10),
            legal_brain_query=str(enrichment.get("legal_brain_query") or case_text),
            must_include_terms=ai_output_validator.clean_ai_list(enrichment.get("search_keywords"), max_items=8),
            should_include_terms=[],
            blocked_terms=["dava", "edildi", "edilebilir", "gibi", "ilişkin", "taraf", "mahkeme"],
            ranking_boost_terms=ai_output_validator.clean_ai_list(enrichment.get("search_keywords"), max_items=12),
            warnings=[],
        )


search_quality_agent = SearchQualityAgent()
