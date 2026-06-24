"""Generate case-specific legal questions for the petition sidebar."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.models.ai_models import LegalQuestionItem, LegalQuestionResponse
from app.services.ai_output_validator import ai_output_validator
from app.services.case_enrichment_agent import case_enrichment_agent
from app.services.gemini_client import gemini_client


class LegalQuestionAgent:
    def generate(
        self,
        *,
        case_text: str,
        case_enrichment: dict[str, Any] | None = None,
        use_gemini: bool = True,
    ) -> LegalQuestionResponse:
        enrichment = case_enrichment or case_enrichment_agent.enrich(
            case_text=case_text,
            practice_area="auto",
            use_gemini=False,
        ).model_dump()
        fallback = self._fallback(case_text=case_text, enrichment=enrichment)
        gemini_result = gemini_client.generate_json(
            system_instruction=(
                "Sen dava türüne özel eksik bilgi soruları üreten bir hukuk asistanısın. "
                "Sorular genel değil, avukatın dilekçeyi güçlendirmek için kullanacağı hedef sorular olmalı. "
                "Sadece JSON döndür."
            ),
            prompt=(
                "Aşağıdaki olay ve zenginleştirmeye göre questions listesi üret. "
                "Her soru id, question, why_needed, suggested_answers alanlarını içersin.\n"
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
            questions = [
                LegalQuestionItem(
                    id=str(item.get("id") or f"question_{index}"),
                    question=" ".join(str(item.get("question") or "").split()),
                    why_needed=" ".join(str(item.get("why_needed") or "").split()),
                    suggested_answers=ai_output_validator.clean_ai_list(item.get("suggested_answers"), max_items=8),
                )
                for index, item in enumerate(gemini_result.data.get("questions") or [], start=1)
                if isinstance(item, dict) and str(item.get("question") or "").strip()
            ]
            if not questions:
                raise ValueError("empty questions")
            return LegalQuestionResponse(ai_used=True, questions=questions[:12], warnings=gemini_result.warnings)
        except (ValidationError, TypeError, ValueError):
            fallback.warnings.append("Gemini soru çıktısı validator’dan geçmedi; fallback kullanıldı.")
            return fallback

    def _fallback(self, *, case_text: str, enrichment: dict[str, Any]) -> LegalQuestionResponse:
        if ai_output_validator.is_vehicle_case(" ".join([case_text, json.dumps(enrichment, ensure_ascii=False)])):
            questions = [
                self._item("seller_status", "Satıcı galeri/şirket/tacir mi, gerçek kişi mi?", "Görevli mahkeme ve tüketici işlemi değerlendirmesi için gereklidir.", ["Galeri/şirket satıcı", "Gerçek kişi", "Tacir", "Tüketici işlemi"]),
                self._item("vehicle_identity", "Aracın marka-modeli, plaka/şasi bilgisi, satış tarihi ve satış bedeli nedir?", "Araç kimliği, bedel iadesi ve değer farkı hesabı için gereklidir.", ["Noter satış sözleşmesi var", "Plaka/şasi belli", "Satış bedeli ödendi"]),
                self._item("seller_representations", "Satış sırasında kazasızlık, ağır hasarsızlık, kilometre veya mekanik durum hakkında hangi beyanlar verildi?", "Satıcının beyanı ayıba karşı sorumluluğun kapsamını etkiler.", ["Kazasız beyan edildi", "Ağır hasarsız denildi", "İlan görüntüsü var", "Mesaj yazışması var"]),
                self._item("defect_detection", "Motor arızası, gizli onarım, TRAMER/hasar kaydı veya ekspertiz bulgusu hangi belgeyle tespit edildi?", "Ayıbın varlığı ve satıştan önce mevcut olup olmadığı teknik delille ispatlanmalıdır.", ["Servis raporu", "Ekspertiz raporu", "TRAMER kaydı", "Bilirkişi gerekecek"]),
                self._item("hidden_defect", "Ayıp olağan gözden geçirme ile fark edilebilir miydi, yoksa gizli ayıp niteliğinde mi?", "TBK ayıp ihbarı ve seçimlik hak değerlendirmesi için ayıbın niteliği önemlidir.", ["Gizli ayıp", "Teslimden kısa süre sonra çıktı", "Olağan muayeneyle anlaşılamaz"]),
                self._item("notification", "Ayıp hangi tarihte öğrenildi, satıcıya hangi tarihte ve hangi yolla bildirildi?", "Ayıp ihbarının süresinde yapıldığını göstermek gerekir.", ["WhatsApp bildirimi", "Noter ihtarı", "Bildirim tarihi belli"]),
                self._item("remedies", "Öncelikli seçimlik hak sözleşmeden dönme mi, bedel indirimi mi; terditli talep kurulacak mı?", "Sonuç ve istemin avukatça ve terditli kurulması için gereklidir.", ["Öncelikle sözleşmeden dönme", "Aksi halde bedel indirimi", "Zarar kalemleri tahsil"]),
                self._item("damages", "Onarım, ekspertiz, servis, ihtarname, değer kaybı ve diğer zarar kalemleri nelerdir?", "Tazmin ve feri taleplerin ayrıştırılması için gereklidir.", ["Servis gideri", "Ekspertiz masrafı", "İhtarname gideri", "Değer kaybı"]),
            ]
            return LegalQuestionResponse(ai_used=False, questions=questions, warnings=[])

        questions = [
            self._item("parties", "Tarafların sıfatı ve uyuşmazlıktaki rolleri nelerdir?", "Görev, husumet ve talep sonucunu netleştirmek için gereklidir.", []),
            self._item("claim", "Somut talep ve dava türü nedir?", "Dilekçe konusu ve sonuç istemi buna göre kurulacaktır.", []),
            self._item("evidence", "Talebi destekleyen belge, kayıt, tanık veya diğer deliller nelerdir?", "Vakıa-delil bağlantısı için gereklidir.", []),
            self._item("risks", "Karşı tarafın muhtemel savunması veya riskli nokta nedir?", "Dilekçede peşinen karşılanacak savunmaları belirler.", []),
        ]
        return LegalQuestionResponse(ai_used=False, questions=questions, warnings=[])

    @staticmethod
    def _item(id_: str, question: str, why_needed: str, suggested_answers: list[str]) -> LegalQuestionItem:
        return LegalQuestionItem(id=id_, question=question, why_needed=why_needed, suggested_answers=suggested_answers)


legal_question_agent = LegalQuestionAgent()
