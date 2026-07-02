"""Deterministic legal issue extraction without Gemini."""

from __future__ import annotations

import re


SAFE_SOURCE_DOMAINS = [
    "mevzuat.gov.tr",
    "karararama.yargitay.gov.tr",
    "emsal.uyap.gov.tr",
    "resmigazete.gov.tr",
]


class DynamicLegalReasonerService:
    def reason(
        self,
        *,
        event_text: str,
        document_facts: list[str] | None = None,
        question_answers: dict[str, str] | None = None,
    ) -> dict[str, list[str]]:
        return self.analyze(
            event_text=event_text,
            document_facts=document_facts,
            question_answers=question_answers,
        )

    def analyze(
        self,
        *,
        event_text: str,
        document_facts: list[str] | None = None,
        question_answers: dict[str, str] | None = None,
    ) -> dict[str, list[str]]:
        facts = document_facts or []
        answers = question_answers or {}
        combined = " ".join([event_text, *facts, *answers.keys(), *answers.values()])
        plain = self._plain(combined)
        is_vehicle = any(term in plain for term in ("ayip", "arac", "tramer", "ekspertiz", "motor ariz", "noter satis"))

        if is_vehicle:
            return {
                "legal_area_candidates": ["Tüketici Hukuku", "Borçlar Hukuku"],
                "case_type_candidates": ["gizli ayıplı ikinci el araç satışı"],
                "legal_issues": [
                    "satış ilişkisi",
                    "gizli ayıp",
                    "ayıp ihbarı",
                    "ayıbın satıştan önce mevcut olması",
                    "seçimlik haklar",
                    "satıcı sıfatı / görevli mahkeme",
                ],
                "research_queries": [
                    "ikinci el araç gizli ayıp Yargıtay",
                    "TBK 219 ayıba karşı tekeffül araç",
                    "TBK 223 ayıp ihbarı araç satışı",
                    "TBK 227 sözleşmeden dönme bedel indirimi",
                    "motor arızası gizli ayıp bilirkişi",
                ],
                "question_plan": [
                    "Servis/ekspertiz raporu mevcut mu?",
                    "Ayıp ihbarı hangi tarihte ve hangi yöntemle yapıldı?",
                    "Satıcı galeri/tacir/şirket mi?",
                    "TRAMER veya ağır hasar kaydı araştırıldı mı?",
                    "Zarar kalemlerine ilişkin fatura/makbuz var mı?",
                ],
                "evidence_plan": self._dedupe([
                    "Noter satış sözleşmesi dosyaya alınmalı.",
                    "Servis veya ekspertiz raporu teknik ayıbı desteklemeli.",
                    "TRAMER/hasar kaydı güvenli resmi kayıtlarla doğrulanmalı.",
                    "Mesajlaşma, ihtarname ve ödeme kayıtları birlikte sunulmalı.",
                ]),
                "risk_plan": self._dedupe([
                    "Ayıbın satıştan sonra oluştuğu savunmasına karşı teknik bağ kurulmalı.",
                    "Ayıp ihbarının süresi ve yöntemi ispatlanmalı.",
                    "Satıcının sıfatına göre görevli mahkeme ayrıca kontrol edilmeli.",
                ]),
            }

        return {
            "legal_area_candidates": [],
            "case_type_candidates": [],
            "legal_issues": self._generic_items(plain, limit=4),
            "research_queries": self._generic_queries(event_text),
            "question_plan": [
                "Somut talep nedir?",
                "Talebi destekleyen temel belgeler nelerdir?",
                "Karşı tarafın beklenen savunması nedir?",
            ],
            "evidence_plan": ["Belge, kayıt ve tanık planı somutlaştırılmalı."],
            "risk_plan": ["Eksik tarih, taraf sıfatı ve delil bağlantıları tamamlanmalı."],
        }

    @staticmethod
    def _plain(value: str) -> str:
        return (
            str(value or "")
            .casefold()
            .replace("ı", "i")
            .replace("ğ", "g")
            .replace("ü", "u")
            .replace("ş", "s")
            .replace("ö", "o")
            .replace("ç", "c")
        )

    def _generic_queries(self, event_text: str) -> list[str]:
        words = re.findall(r"[a-zçğıöşü]{4,}", self._plain(event_text))
        selected = self._dedupe(words)[:5]
        return [" ".join(selected)] if selected else []

    def _generic_items(self, plain: str, *, limit: int) -> list[str]:
        items: list[str] = []
        if "sozlesme" in plain:
            items.append("sözleşme ilişkisi")
        if "bildir" in plain or "ihtar" in plain:
            items.append("bildirim süreci")
        if "delil" in plain or "belge" in plain:
            items.append("delil bağlantısı")
        if "zarar" in plain:
            items.append("zarar kalemleri")
        return items[:limit]

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = " ".join(str(value).split())
            key = cleaned.casefold()
            if cleaned and key not in seen:
                seen.add(key)
                result.append(cleaned)
        return result


dynamic_legal_reasoner_service = DynamicLegalReasonerService()
