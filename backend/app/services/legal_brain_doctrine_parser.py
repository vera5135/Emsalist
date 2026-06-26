"""Parse Turkish legal doctrine sources into structured knowledge cards."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LEGAL_BRAIN_ROOT = Path(__file__).resolve().parents[1] / "legal_brain"

CONCEPT_KEYWORDS = {
    "dava şartı": ["dava şartı", "dava sarti", "şartlı", "dava açma şartı"],
    "görev": ["görev", "gorev", "yetkili makam", "yetki"],
    "süre": ["süre", "sure", "zamanaşımı", "zamanasimi", "hak düşürücü süre"],
    "ispat yükü": ["ispat yükü", "ispat yuku", "ispat", "ispât"],
    "delil": ["delil", "deliller", "ispat vasıtaları", "ispat vasitalari"],
    "tanık": ["tanık", "tanik", "tanıklar", "taniklar", "şahit"],
    "bilirkişi": ["bilirkişi", "bilirkisi", "uzman", "bilir kişi"],
    "ihtar": ["ihtar", "tebliğ", "teblig", "tebligat"],
    "arabuluculuk": ["arabuluculuk", "arabulucu", "uyuşmazlık danışmanı"],
    "talep sonucu": ["talep sonucu", "sonuç istemi", "sonuc istemi"],
    "terditli talep": ["terditli talep", "terdit", "terditten"],
    "seçimlik hak": ["seçimlik hak", "secimlik hak", "seçim", "secim"],
    "tazminat": ["tazminat", "tazminatlar", "maddi tazminat", "manevi tazminat"],
    "müdahalenin men'i": ["müdahalenin men'i", "mudahalenin meni", "müdahale", "mudahale"],
    "tahliye": ["tahliye", "tahliye davası", "tahliyesi"],
    "alacak": ["alacak", "alacaklar", "tahsil", "tahsili"],
    "itirazın iptali": ["itirazın iptali", "itirazin iptali", "itiraz iptali"],
    "iptal davası": ["iptal davası", "iptal"],
    "yürütmenin durdurulması": ["yürütmenin durdurulması", "yurutmenin durdurulmasi"],
}

CASE_TYPE_MAP = {
    "alacak": "alacak davası",
    "tazminat": "tazminat davası",
    "müdahale": "müdahalenin men'i",
    "gürültü": "müdahalenin men'i",
    "komşu": "müdahalenin men'i",
    "tahliye": "kira tahliyesi",
    "kira": "kira tahliyesi",
    "nafaka": "nafaka davası",
    "boşanma": "boşanma davası",
    "işçi": "işçi alacağı",
    "işveren": "işçi alacağı",
    "icra": "icra itirazı",
    "itiraz": "icra itirazı",
    "miras": "miras hukuku",
    "idare": "idare hukuku",
    "ceza": "ceza hukuku",
    "ticaret": "ticaret hukuku",
    "sözleşme": "sözleşmeler hukuku",
}


class LegalBrainDoctrineParser:
    """Parse doctrinal sources into structured knowledge cards."""

    def parse(self, text: str, source_file: str = "", source_reliability: str = "medium") -> dict[str, Any]:
        plain_text = self._plain(text)
        area, area_terms = self._detect_area(plain_text)
        case_type = self._detect_case_type(plain_text)
        summary = self._build_summary(text)
        legal_rules = self._extract_rules(text)
        required_facts = self._extract_facts(area, case_type)
        required_evidence = self._extract_evidence(area, case_type)
        procedural = self._extract_procedural(plain_text)
        defenses = self._extract_defenses(area, case_type)
        risks = self._extract_risks(area, case_type)
        patterns = self._extract_language_patterns(text)
        questions = self._generate_questions(area, case_type, plain_text)

        return {
            "card_type": "doctrine",
            "legal_area": area,
            "case_type": case_type,
            "doctrine_summary": summary,
            "legal_rules": legal_rules,
            "required_facts": required_facts,
            "required_evidence": required_evidence,
            "procedural_requirements": procedural,
            "limitation_or_deadline_risks": risks,
            "common_defenses": defenses,
            "petition_language_patterns": patterns,
            "question_suggestions": questions,
            "source_file": source_file,
            "source_reliability": source_reliability,
            "warnings": [],
        }

    def _detect_area(self, plain_text: str) -> tuple[str, list[str]]:
        scores: dict[str, int] = {}
        for term, area in [
            ("kira", "kira hukuku"),
            ("kiracı", "kira hukuku"),
            ("tüketici", "tüketici hukuku"),
            ("ayıp", "tüketici hukuku"),
            ("araç", "ayıplı araç / gizli ayıp"),
            ("gizli ayıp", "ayıplı araç / gizli ayıp"),
            ("işçi", "iş hukuku"),
            ("işveren", "iş hukuku"),
            ("nafaka", "aile hukuku"),
            ("boşanma", "aile hukuku"),
            ("velayet", "aile hukuku"),
            ("icra", "icra hukuku"),
            ("itiraz", "icra hukuku"),
            ("miras", "miras hukuku"),
            ("idare", "idare hukuku"),
            ("belediye", "idare hukuku"),
            ("ceza", "ceza hukuku"),
            ("suç", "ceza hukuku"),
            ("kat mülkiyeti", "kat mülkiyeti / komşuluk hukuku"),
            ("apartman", "kat mülkiyeti / komşuluk hukuku"),
            ("gürültü", "kat mülkiyeti / komşuluk hukuku"),
            ("komşu", "kat mülkiyeti / komşuluk hukuku"),
            ("tazminat", "tazminat hukuku"),
            ("zarar", "tazminat hukuku"),
            ("sözleşme", "sözleşmeler hukuku"),
            ("ticaret", "ticaret hukuku"),
            ("şirket", "ticaret hukuku"),
            ("vergi", "vergi hukuku"),
            ("vergi dairesi", "vergi hukuku"),
        ]:
            if term in plain_text:
                scores[area] = scores.get(area, 0) + 1
        if scores:
            return max(scores.items(), key=lambda kv: kv[1])[0], list(scores.keys())[:4]
        return "belirsiz", ["belirsiz"]

    def _detect_case_type(self, plain_text: str) -> str:
        for term, case_type in CASE_TYPE_MAP.items():
            if term in plain_text:
                return case_type
        return "bilinmeyen"

    def _build_summary(self, text: str, max_chars: int = 500) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", " ".join(str(text or "").split()))
        parts: list[str] = []
        length = 0
        for sentence in sentences:
            if length + len(sentence) <= max_chars:
                parts.append(sentence)
                length += len(sentence) + 1
            else:
                break
        return " ".join(parts)[:max_chars] or text[:max_chars]

    def _extract_rules(self, text: str) -> list[str]:
        rules: list[str] = []
        plain = self._plain(text)
        rule_triggers = ["gerekir", "kural", "ilke", "esastır", "esas", "hüküm", "hukum", "uygulanır", "kapsar", "kapsamı"]
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            if any(t in self._plain(sentence) for t in rule_triggers):
                rules.append(self._clean(sentence))
        return rules[:10]

    def _extract_facts(self, area: str, case_type: str) -> list[str]:
        facts: list[str] = []
        if area in ("kira hukuku",) or case_type == "kira tahliyesi":
            facts = ["Kira ilişkisinin varlığı ve türü", "Kira bedeli ve süresi", "Temerrüt tarihi"]
        elif area in ("aile hukuku",) or case_type == "nafaka davası":
            facts = ["Tarafların gelir ve gider durumu", "Evlatların durumu", "Nafaka miktarı"]
        elif case_type == "işçi alacağı":
            facts = ["İşe giriş tarihi", "Ücret tutarı", "Fazla mesai süresi"]
        elif area in ("icra hukuku",):
            facts = ["İcra dosya numarası", "Alacak miktarı", "İtiraz tarihi"]
        elif case_type in ("tazminat davası",):
            facts = ["Zarar türü ve miktarı", "Kusur durumu", "Zarar-tazminat ilişkisi"]
        if not facts:
            facts = ["Tarafların kimliği", "Uyuşmazlığın konusu", "Talep edilen sonuç"]
        return facts[:10]

    def _extract_evidence(self, area: str, case_type: str) -> list[str]:
        evidence: list[str] = []
        if area in ("kira hukuku",) or case_type == "kira tahliyesi":
            evidence = ["Kira sözleşmesi", "Banka dekontları", "İhtarname", "Arabuluculuk tutanağı"]
        elif case_type == "işçi alacağı":
            evidence = ["SGK hizmet dökümü", "Bordro örnekleri", "İşten çıkış bildirimi"]
        elif case_type == "tazminat davası":
            evidence = ["Hasar tespit raporu", "Sağlık raporu", "Bilirkişi raporu"]
        elif area in ("tüketici hukuku", "ayıplı araç / gizli ayıp"):
            evidence = ["Satış sözleşmesi", "Servis/ekspertiz raporu", "TRAMER kaydı"]
        if not evidence:
            evidence = ["Belgeler", "Tanık beyanları", "Resmi kayıtlar", "Bilirkişi incelemesi"]
        return evidence[:10]

    def _extract_procedural(self, plain_text: str) -> list[str]:
        rules: list[str] = []
        concept_map = {
            "dava şartı": "Dava şartları kontrol edilmelidir",
            "görev": "Görevli makam yetkilisi",
            "yetki": "Yetki alanı doğrulanmalıdır",
            "süre": "Usuli süre takibi yapılmalıdır",
            "zamanaşımı": "Zamanaşımı süreleri kontrol edilmelidir",
            "hak düşürücü süre": "Hak düşürücü süreler dikkate alınmalıdır",
            "arabuluculuk": "Arabuluculuk süreci tamamlanmalıdır",
            "ihtar": "İhtar tebliği usulüne uygun yapılmalıdır",
        }
        for concept, rule in concept_map.items():
            if concept in plain_text:
                rules.append(rule)
        if not rules:
            rules = ["Dava şartları ve yetki usulüne uygun kontrol edilmelidir"]
        return rules[:6]

    def _extract_defenses(self, area: str, case_type: str) -> list[str]:
        defenses: list[str] = []
        if case_type in ("kira tahliyesi",):
            defenses = ["Temerrüt oluşmadı", "İhtar usulüne uygun değil", "İhtiyaç niteliği yok"]
        elif case_type == "tazminat davası":
            defenses = ["Zarar davacıya bağlı", "Kusur yok", "Zarar-Tazminat ilişkisi yok"]
        elif case_type == "işçi alacağı":
            defenses = ["Ücret ödenmiş", "Fazla mesai yok", "Fesih haklı"]
        elif case_type in ("icra itirazı",):
            defenses = ["Alacak ödenmiş", "Yetki yok", "İmza sahte"]
        if not defenses:
            defenses = ["İspat yükü davacıdadır", "Zamanaşımı itirazı", "Vakıalar yanlış"]
        return defenses[:6]

    def _extract_risks(self, area: str, case_type: str) -> list[str]:
        risks: list[str] = []
        if case_type in ("kira tahliyesi",):
            risks = ["Tahliye davası süresi", "Temerrüt tebellüğü süresi"]
        elif case_type == "nafaka davası":
            risks = ["Nafaka zamanaşımı süresi"]
        elif case_type == "işçi alacağı":
            risks = ["İşçi alacakları zamanaşımı süresi", "Kıdem tazminatı süresi"]
        elif case_type in ("icra itirazı",):
            risks = ["İtiraz süresi", "İcra inkar tazminatı riski"]
        if not risks:
            risks = ["Genel zamanaşımı süreleri", "Dava şartları"]
        return risks[:4]

    def _extract_language_patterns(self, text: str) -> list[str]:
        patterns: list[str] = []
        plain = self._plain(text)
        if "mahkeme" in plain and "yürütmenin durdurulması" in plain:
            patterns.append("... yürütmenin durdurulması talebiyle dava açılmıştır.")
        if "bilirkişi" in plain and "inceleme" in plain:
            patterns.append("... bilirkişi marifetiyle tespit edilmesi gerekmektedir.")
        if "tazminat" in plain and "zarar" in plain:
            patterns.append("... zararının tazmini ve feri taleplerin ayrıştırılması gerekir.")
        if "delil" in plain and "ispat" in plain:
            patterns.append("... ispat yükü dava türüne göre değerlendirilmelidir.")
        if "süre" in plain and "zamanaşımı" in plain:
            patterns.append("... süre ve zamanaşımı unsurları dosya özelinde kontrol edilmelidir.")
        return patterns[:8]

    def _generate_questions(self, area: str, case_type: str, plain_text: str) -> list[dict[str, Any]]:
        questions: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(qid: str, question: str, category: str, options: list[str], reason: str) -> None:
            if qid not in seen:
                seen.add(qid)
                questions.append({
                    "id": qid,
                    "question": question,
                    "category": category,
                    "answer_type": "single_choice",
                    "options": options,
                    "reason": reason,
                })

        generic_opts = ["Evet", "Hayır", "Bilinmiyor"]
        if area in ("kira hukuku",) or case_type == "kira tahliyesi":
            add("rent_basis", "Kira ilişkisi nasıl kurulmuştur?", "hukuki_ilişki", ["Yazılı sözleşme", "Sözlü ilişki", "Ödeme kayıtları"], "Kira ilişkisinin türü hukuki sonuçları etkiler.")
            add("unpaid_period", "Temerrüt dönemi ne kadardır?", "miktar", ["3 ay altı", "3-6 ay", "6 ay üzeri", "Düzensiz"], "Temerrüt süresi faiz ve tahliye kararını etkiler.")
        elif case_type == "işçi alacağı":
            add("emp_duration", "İş ilişkisi ne kadar sürmüştür?", "taraf", ["1 yıl altı", "1-5 yıl", "5 yıl üzeri", "Bilinmiyor"], "Kıdem ve ihbar tazminatı hesaplamasında esas alınır.")
            add("salary_proof", "Ücret ispatı nasıldır?", "delil", ["Bordro", "Banka dekontu", "Tanık beyanı", "Bilinmiyor"], "Ücret kanıtı alacak hesaplanması için gereklidir.")
        elif case_type == "nafaka davası":
            add("income_change", "Nafaka değişikliği nedeni nedir?", "talep_sonucu", ["Gelir artışı", "Gelir azalması", "Gider değişikliği", "Hakkaniyet değişimi"], "Esaslı değişiklik iddiasının dayanağıdır.")
        elif case_type == "tazminat davası":
            add("damage_type", "Zarar türü nedir?", "maddi_vakia", ["Maddi zarar", "Manevi zarar", "Her ikisi", "Bilinmiyor"], "Tazminat türü talep ve ispat stratejisini belirler.")
        elif area in ("icra hukuku",):
            add("enforcement_file", "İcra dosya no ve takip türü nedir?", "taraf", ["İlamsız takip", "İlamlı takip", "Tutuklama", "Bilinmiyor"], "İcra türü itirazın değerlendirilmesini etkiler.")

        if not questions:
            add("parties", "Tarafların sıfatı ve rolleri nelerdir?", "taraf", ["Davacı", "Davalı", "Üçüncü kişi", "Vekil"], "Dava konusu ve sorumluluk nispeti için gereklidir.")
        return questions[:8]

    @staticmethod
    def _clean(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip().rstrip(".")

    @staticmethod
    def _plain(text: str) -> str:
        import unicodedata
        normalized = str(text or "").casefold().translate(
            str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
                          "Ç": "c", "Ğ": "g", "İ": "i", "Ö": "o", "Ş": "s", "Ü": "u"})
        )
        decomposed = unicodedata.normalize("NFKD", normalized)
        return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


legal_brain_doctrine_parser = LegalBrainDoctrineParser()