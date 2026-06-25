"""Audit generated petitions for legal drafting quality."""

from __future__ import annotations

import json
from typing import Any

from app.models.ai_models import DraftAuditResponse
from app.services.ai_output_validator import ai_output_validator
from app.services.gemini_client import gemini_client


class PetitionQualityAgent:
    def audit(
        self,
        *,
        draft_text: str,
        case_text: str = "",
        case_enrichment: dict[str, Any] | None = None,
        selected_decisions: list[dict[str, Any]] | None = None,
        use_gemini: bool = True,
    ) -> DraftAuditResponse:
        fallback = self._fallback(
            draft_text=draft_text,
            case_text=case_text,
            case_enrichment=case_enrichment or {},
            selected_decisions=selected_decisions or [],
        )
        gemini_result = gemini_client.generate_json(
            system_instruction=(
                "Sen dilekçe taslağını kalite, kaynak, emsal ve dil bakımından denetleyen kıdemli hukuk editörüsün. "
                "Yeni vakıa veya kaynak ekleme. Sadece JSON döndür."
            ),
            prompt=(
                "Aşağıdaki dilekçeyi denetle. quality_score, critical_issues, major_issues, minor_issues, missing_facts, "
                "source_problems, precedent_problems, petition_language_problems, recommended_actions, "
                "ready_for_lawyer_review ve can_refine alanlarını döndür.\n"
                f"Olay: {case_text}\n"
                f"Zenginleştirme: {json.dumps(case_enrichment or {}, ensure_ascii=False)}\n"
                f"Dilekçe: {draft_text[:24000]}"
            ),
            fallback=fallback.model_dump(),
            use_gemini=use_gemini,
        )
        if not gemini_result.ai_used:
            fallback.warnings.extend(gemini_result.warnings)
            return fallback
        response = self._response_from_ai(data=gemini_result.data, fallback=fallback)
        response.ai_used = True
        response.warnings.extend(gemini_result.warnings)
        return self._merge_validator(response=response, draft_text=draft_text, case_text=case_text, selected_decisions=selected_decisions or [])

    def _fallback(
        self,
        *,
        draft_text: str,
        case_text: str,
        case_enrichment: dict[str, Any],
        selected_decisions: list[dict[str, Any]],
    ) -> DraftAuditResponse:
        response = DraftAuditResponse(
            ai_used=False,
            quality_score=82,
            critical_issues=[],
            major_issues=[],
            minor_issues=[],
            missing_facts=ai_output_validator.clean_ai_list(case_enrichment.get("missing_facts"), max_items=12),
            source_problems=[],
            precedent_problems=[],
            petition_language_problems=[],
            recommended_actions=[],
            ready_for_lawyer_review=True,
            can_refine=True,
            warnings=[],
        )
        return self._merge_validator(response=response, draft_text=draft_text, case_text=case_text, selected_decisions=selected_decisions)

    def _merge_validator(
        self,
        *,
        response: DraftAuditResponse,
        draft_text: str,
        case_text: str,
        selected_decisions: list[dict[str, Any]],
    ) -> DraftAuditResponse:
        audit = ai_output_validator.audit_draft(
            draft_text=draft_text,
            case_text=case_text,
            selected_decisions=selected_decisions,
        )
        response.critical_issues = ai_output_validator.dedupe(response.critical_issues + audit["critical"])
        response.major_issues = ai_output_validator.dedupe(response.major_issues + audit["major"])
        response.source_problems = ai_output_validator.dedupe(response.source_problems + audit["source_problems"])
        response.precedent_problems = ai_output_validator.dedupe(response.precedent_problems + audit["precedent_problems"])
        response.petition_language_problems = ai_output_validator.dedupe(response.petition_language_problems + audit["language_problems"])

        penalty = (
            len(response.critical_issues) * 25
            + len(response.major_issues) * 12
            + len(response.precedent_problems) * 8
            + len(response.petition_language_problems) * 8
            + len(response.source_problems) * 6
        )
        response.quality_score = max(0, min(100, response.quality_score - penalty))
        response.ready_for_lawyer_review = response.quality_score >= 70 and not response.critical_issues
        response.can_refine = bool(response.critical_issues or response.major_issues or response.petition_language_problems or response.precedent_problems)
        if response.can_refine and not response.recommended_actions:
            response.recommended_actions = ["Dilekçeyi validator uyarılarına göre redakte et.", "KONU, emsal ve sonuç istem bölümlerini son kez kontrol et."]
        return response

    @staticmethod
    def _response_from_ai(*, data: dict[str, Any], fallback: DraftAuditResponse) -> DraftAuditResponse:
        def list_field(name: str) -> list[str]:
            return ai_output_validator.clean_ai_list(data.get(name), max_items=30)

        return DraftAuditResponse(
            ai_used=False,
            quality_score=max(0, min(100, int(data.get("quality_score") or fallback.quality_score))),
            critical_issues=list_field("critical_issues"),
            major_issues=list_field("major_issues"),
            minor_issues=list_field("minor_issues"),
            missing_facts=list_field("missing_facts"),
            source_problems=list_field("source_problems"),
            precedent_problems=list_field("precedent_problems"),
            petition_language_problems=list_field("petition_language_problems"),
            recommended_actions=list_field("recommended_actions"),
            ready_for_lawyer_review=bool(data.get("ready_for_lawyer_review")),
            can_refine=bool(data.get("can_refine", True)),
            warnings=ai_output_validator.clean_ai_list(data.get("warnings"), max_items=20),
        )


petition_quality_agent = PetitionQualityAgent()
