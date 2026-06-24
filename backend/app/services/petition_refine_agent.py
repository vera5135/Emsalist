"""Refine a generated petition without inventing facts, sources or citations."""

from __future__ import annotations

import json
from typing import Any

from app.models.ai_models import DraftRefineResponse
from app.services.ai_output_validator import ai_output_validator
from app.services.gemini_client import gemini_client
from app.services.petition_quality_agent import petition_quality_agent


class PetitionRefineAgent:
    def refine(
        self,
        *,
        draft_text: str,
        case_text: str = "",
        case_enrichment: dict[str, Any] | None = None,
        selected_decisions: list[dict[str, Any]] | None = None,
        use_gemini: bool = True,
    ) -> DraftRefineResponse:
        fallback_text = self._fallback_cleanup(draft_text)
        fallback = DraftRefineResponse(
            ai_used=False,
            refined_draft=fallback_text,
            accepted=True,
            validator_warnings=ai_output_validator.validate_refined_draft(
                original_draft=draft_text,
                refined_draft=fallback_text,
                case_text=case_text,
            ),
            quality_score=0,
            warnings=["Gemini kapalıysa yalnızca kural tabanlı temizlik yapılır."],
        )
        audit = petition_quality_agent.audit(
            draft_text=fallback_text,
            case_text=case_text,
            case_enrichment=case_enrichment or {},
            selected_decisions=selected_decisions or [],
            use_gemini=False,
        )
        fallback.quality_score = audit.quality_score
        if fallback.validator_warnings:
            fallback.accepted = False

        gemini_result = gemini_client.generate_json(
            system_instruction=(
                "Sen Emsalist dilekçesini usta avukat diliyle redakte eden hukuk editörüsün. "
                "Sadece verilen olay, mevcut taslak ve mevcut kaynaklarla çalış. Yeni vakıa, yeni kanun maddesi, "
                "yeni esas/karar numarası, yeni kaynak veya sayfa uydurma. Riskli kararı lehe gibi sunma. "
                "Sadece JSON döndür: refined_draft, warnings."
            ),
            prompt=(
                "Aşağıdaki taslağı güçlendir; olay, delil, hukuk ve talep bağlantısını kuvvetlendir; tekrarları temizle. "
                "Araç gizli ayıp dosyasında nafaka/TMK/aile hukuku karıştırma.\n"
                f"Olay: {case_text}\n"
                f"Zenginleştirme: {json.dumps(case_enrichment or {}, ensure_ascii=False)}\n"
                f"Seçilmiş kararlar: {json.dumps(selected_decisions or [], ensure_ascii=False)}\n"
                f"Taslak: {draft_text[:28000]}"
            ),
            fallback=fallback.model_dump(),
            use_gemini=use_gemini,
        )
        if not gemini_result.ai_used:
            fallback.warnings.extend(gemini_result.warnings)
            return fallback

        refined = str(gemini_result.data.get("refined_draft") or "").replace("\\n", "\n").strip()
        if not refined:
            fallback.warnings.append("Gemini redaksiyon metni boş döndü; fallback kullanıldı.")
            return fallback

        validator_warnings = ai_output_validator.validate_refined_draft(
            original_draft=draft_text,
            refined_draft=refined,
            case_text=case_text,
        )
        audit = petition_quality_agent.audit(
            draft_text=refined,
            case_text=case_text,
            case_enrichment=case_enrichment or {},
            selected_decisions=selected_decisions or [],
            use_gemini=False,
        )
        if validator_warnings:
            return DraftRefineResponse(
                ai_used=True,
                refined_draft=fallback.refined_draft,
                accepted=False,
                validator_warnings=validator_warnings,
                quality_score=audit.quality_score,
                warnings=["Gemini redaksiyonu validator’dan geçmedi; final metne alınmadı.", *gemini_result.warnings],
            )
        return DraftRefineResponse(
            ai_used=True,
            refined_draft=refined,
            accepted=True,
            validator_warnings=[],
            quality_score=audit.quality_score,
            warnings=ai_output_validator.clean_ai_list(gemini_result.data.get("warnings"), max_items=20) + gemini_result.warnings,
        )

    @staticmethod
    def _fallback_cleanup(draft_text: str) -> str:
        replacements = {
            "Talebimizin kabulü talebimizin kabulüne": "Davanın kabulüne",
            "Talebimizin kabulü talebimiz ile": "Talebimiz",
            "içtihat sinyalleri": "içtihat değerlendirmesi",
            "içtihat sinyali": "içtihat değerlendirmesi",
            "alıcının, aracın, araç": "alıcının ve aracın somut durumu",
            "aracın, araç, araçtaki": "aracın ve araçtaki ayıbın",
        }
        cleaned = draft_text
        for old, new in replacements.items():
            cleaned = cleaned.replace(old, new)
        return cleaned


petition_refine_agent = PetitionRefineAgent()
