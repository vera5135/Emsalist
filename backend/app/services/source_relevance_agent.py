"""Audit Legal Brain sources before they are used in a petition."""

from __future__ import annotations

import json
from typing import Any

from app.models.ai_models import AuditedSource, SourceAuditResponse
from app.services.ai_output_validator import VEHICLE_BLOCKED_TOPICS, ai_output_validator
from app.services.gemini_client import gemini_client


class SourceRelevanceAgent:
    def audit(
        self,
        *,
        case_enrichment: dict[str, Any],
        sources: list[dict[str, Any]],
        use_gemini: bool = True,
    ) -> SourceAuditResponse:
        fallback = self._fallback(case_enrichment=case_enrichment, sources=sources)
        gemini_result = gemini_client.generate_json(
            system_instruction=(
                "Sen Legal Brain kaynaklarını somut uyuşmazlıkla doğrudan bağlantı açısından denetleyen hukuk ajanısın. "
                "Alakasız TMK/nafaka/aile hukuku kaynaklarını araç ayıp dosyasında reddet. Sadece JSON döndür."
            ),
            prompt=(
                "case_enrichment ve sources listesine göre audited_sources üret. "
                "Her kaynak source_id, is_directly_relevant, use_in_petition, relevance_score, reason, source_rejected_reason içersin.\n"
                f"case_enrichment: {json.dumps(case_enrichment, ensure_ascii=False)}\n"
                f"sources: {json.dumps(sources[:20], ensure_ascii=False)}"
            ),
            fallback=fallback.model_dump(),
            use_gemini=use_gemini,
        )
        if not gemini_result.ai_used:
            fallback.warnings.extend(gemini_result.warnings)
            return fallback

        audited = []
        for item in gemini_result.data.get("audited_sources") or []:
            if not isinstance(item, dict):
                continue
            audited.append(
                AuditedSource(
                    source_id=str(item.get("source_id") or ""),
                    is_directly_relevant=bool(item.get("is_directly_relevant")),
                    use_in_petition=bool(item.get("use_in_petition")),
                    relevance_score=max(0, min(100, int(item.get("relevance_score") or 0))),
                    reason=" ".join(str(item.get("reason") or "").split()),
                    source_rejected_reason=" ".join(str(item.get("source_rejected_reason") or "").split()),
                )
            )
        if not audited:
            fallback.warnings.append("Gemini kaynak denetimi boş döndü; fallback kullanıldı.")
            return fallback
        response = SourceAuditResponse(ai_used=True, audited_sources=audited, warnings=gemini_result.warnings)
        return self._apply_hard_rejections(response=response, case_enrichment=case_enrichment, sources=sources)

    def _fallback(self, *, case_enrichment: dict[str, Any], sources: list[dict[str, Any]]) -> SourceAuditResponse:
        is_vehicle = ai_output_validator.is_vehicle_case(json.dumps(case_enrichment, ensure_ascii=False))
        audited: list[AuditedSource] = []
        for index, source in enumerate(sources):
            source_id = self._source_id(source, index)
            haystack = ai_output_validator.plain(json.dumps(source, ensure_ascii=False))
            rejected_reason = ""
            directly_relevant = bool(source.get("is_directly_relevant"))
            score = int(source.get("relevance_score") or 0)
            if is_vehicle:
                if any(topic in haystack for topic in VEHICLE_BLOCKED_TOPICS):
                    directly_relevant = False
                    score = min(score, 20)
                    rejected_reason = "Araç gizli ayıp dosyasında TMK/nafaka/aile hukuku kaynağı konu dışıdır."
                elif not self._has_vehicle_source_core(haystack):
                    directly_relevant = False
                    score = min(score, 45)
                    rejected_reason = "Kaynak yalnızca genel kelime benzerliği taşıyor; araç, satım, ayıp, TBK/TKHK veya seçimlik hak bağlantısı zayıf."
                else:
                    directly_relevant = True
                    score = max(score, 75)
            audited.append(
                AuditedSource(
                    source_id=source_id,
                    is_directly_relevant=directly_relevant,
                    use_in_petition=directly_relevant,
                    relevance_score=max(0, min(100, score)),
                    reason="Doğrudan araç ayıp bağlantısı denetlendi." if directly_relevant else "Kaynak denetlendi ancak doğrudan kullanım uygun değil.",
                    source_rejected_reason=rejected_reason,
                )
            )
        return SourceAuditResponse(ai_used=False, audited_sources=audited, warnings=[])

    def _apply_hard_rejections(
        self,
        *,
        response: SourceAuditResponse,
        case_enrichment: dict[str, Any],
        sources: list[dict[str, Any]],
    ) -> SourceAuditResponse:
        if not ai_output_validator.is_vehicle_case(json.dumps(case_enrichment, ensure_ascii=False)):
            return response
        source_by_id = {self._source_id(source, index): source for index, source in enumerate(sources)}
        audited = []
        for item in response.audited_sources:
            source = source_by_id.get(item.source_id, {})
            haystack = ai_output_validator.plain(json.dumps(source, ensure_ascii=False))
            if any(topic in haystack for topic in VEHICLE_BLOCKED_TOPICS) or not self._has_vehicle_source_core(haystack):
                item.is_directly_relevant = False
                item.use_in_petition = False
                item.relevance_score = min(item.relevance_score, 45)
                item.source_rejected_reason = item.source_rejected_reason or "Validator kaynağı araç gizli ayıp dosyası için konu dışı buldu."
            audited.append(item)
        response.audited_sources = audited
        return response

    @staticmethod
    def _has_vehicle_source_core(haystack: str) -> bool:
        strong_terms = (
            "ayipli arac",
            "gizli ayip",
            "arac satisi",
            "ikinci el arac",
            "satim sozlesmesi",
            "ayiba karsi",
            "tbk 219",
            "tbk 223",
            "tbk 227",
            "tbk 229",
            "tkhk",
            "tuketici",
            "sozlesmeden donme",
            "bedel indirimi",
            "tramer",
            "hasar kaydi",
            "noter satis",
        )
        weak_terms = ("ekspertiz", "bilirkisi", "bilir kisi", "servis raporu")
        has_strong_link = any(term in haystack for term in strong_terms)
        if any(term in haystack for term in weak_terms) and not has_strong_link:
            return False
        return has_strong_link
        core_terms = (
            "ayipli arac",
            "gizli ayip",
            "arac satisi",
            "satim",
            "ayiba karsi",
            "tbk 219",
            "tbk 223",
            "tbk 227",
            "tbk 229",
            "tkhk",
            "tuketici",
            "sozlesmeden donme",
            "bedel indirimi",
            "tramer",
            "ekspertiz raporu",
            "servis raporu",
        )
        return any(term in haystack for term in core_terms)

    @staticmethod
    def _source_id(source: dict[str, Any], index: int) -> str:
        return str(source.get("source_id") or source.get("citation_label") or source.get("title") or f"source_{index + 1}")


source_relevance_agent = SourceRelevanceAgent()
