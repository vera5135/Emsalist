"""Shared precedent analysis heuristics for research and petition drafting."""

from __future__ import annotations

from typing import Any, Literal

from app.models.petition_models import PrecedentAnalysis
from app.services.petition_profile_service import get_petition_profile


VerificationStatus = Literal[
    "verified_supportive_precedent",
    "verification_required_precedent_candidate",
    "weak_or_partial_precedent",
    "adverse_or_distinguishable_precedent",
]


PROFILE_SIGNALS: dict[str, dict[str, list[tuple[tuple[str, ...], str]] | dict[str, str]]] = {
    "defective_vehicle": {
        "facts": [
            (("araç", "ikinci el", "satış"), "İkinci el araç satışı"),
            (("gizli ayıp", "ayıp", "arıza", "hasar"), "Gizli ayıp / teknik arıza"),
            (("servis", "ekspertiz"), "Servis ve ekspertiz tespiti"),
            (("ihbar", "bildirim", "ihtar", "whatsapp", "sms"), "Ayıp ihbarı ve bildirim"),
            (("bedel", "değer", "indirim"), "Bedel ve değer farkı"),
            (("tramer", "hasar"), "TRAMER / hasar kaydı"),
        ],
        "issues": [
            (("tbk 219", "ayıba karşı tekeffül", "tekeffül"), "TBK 219 ayıba karşı tekeffül"),
            (("tbk 223", "inceleme", "bildirim", "ihbar"), "Ayıp incelemesi ve ihbar yükü"),
            (("tbk 227", "seçimlik", "sözleşmeden dönme", "bedel indirimi", "onarım"), "Seçimlik haklar"),
            (("bilirkişi", "bilirkişi incelemesi", "ekspertiz"), "Bilirkişi ve teknik inceleme"),
            (("6502", "tüketici", "tkhk"), "Tüketici işlemi niteliği"),
        ],
        "arguments": [
            (("sözleşmeden dönme", "dönme"), "Sözleşmeden dönme hakkı"),
            (("bedel indirimi", "indirim"), "Ayıp oranında bedel indirimi"),
            (("onarım", "servis"), "Onarım ve servis giderlerinin tazmini"),
            (("değer", "fark"), "Değer farkı ve bedel uyarlaması"),
            (("ihbar", "bildirim"), "İhbarın süresinde yapıldığı savı"),
        ],
        "evidence": [
            (("servis", "rapor"), "Servis raporu ayıbın teslim anına uzanan niteliğini göstermek için kullanılmalı."),
            (("ekspertiz",), "Ekspertiz raporu, gizli ayıp ve değer farkını somutlaştırmak için kullanılmalı."),
            (("tramer", "hasar"), "TRAMER / hasar kaydı, geçmiş hasar ve gizli ayıp bağlantısını destekler."),
            (("whatsapp", "sms", "ihtar"), "Mesajlaşma ve ihtar kayıtları, ayıp ihbarını ve süreyi doğrular."),
            (("dekont", "ödeme"), "Ödeme dekontları, satış bedelini ve iade talebini somutlaştırır."),
        ],
        "risks": [
            (("satıştan sonra", "sonradan", "yeni arıza"), "Ayıbın satıştan sonra oluştuğu savı ayrıştırılmalıdır."),
            (("süre", "geç", "gecik", "ihbar"), "Ayıp ihbarının süresinde yapıldığı ayrıca ispatlanmalıdır."),
            (("görev", "yetki"), "Görevli mahkeme ve tüketici işlemi niteliği ayrıca kontrol edilmelidir."),
        ],
        "recommendations": {
            "verified_supportive_precedent": "Karar, karar kimliği ve teknik delil bağlantısı birlikte verilerek doğrudan destekleyici emsal olarak kullanılabilir.",
            "verification_required_precedent_candidate": "Karar, doğrulanması gereken aday emsal olarak gösterilmeli; tam metin kontrolü sonrası kullanılmalıdır.",
            "weak_or_partial_precedent": "Karar yalnızca kavramsal benzerlik için sınırlı atıf olarak kullanılmalı, ana dayanak yapılmamalıdır.",
            "adverse_or_distinguishable_precedent": "Karar aleyhe veya ayırt edilebilir nitelikte; yalnızca karşı savunmaya cevap ve ayrıştırma için kullanılmalıdır.",
        },
    },
    "eviction_need": {
        "facts": [
            (("kira", "kiralanan"), "Kira ilişkisi"),
            (("ihtiyaç", "gereksinim"), "Gerçek, samimi ve zorunlu ihtiyaç"),
            (("başka", "alternatif", "uygun"), "Alternatif taşınmaz yokluğu"),
            (("ihtar", "bildirim"), "İhtar ve bildirim süreci"),
            (("dönem", "süre", "tarih"), "Dönem ve dava süresi"),
        ],
        "issues": [
            (("tbk 350", "ihtiyaç nedeniyle tahliye"), "TBK 350 ihtiyaca dayalı tahliye"),
            (("tbk 351", "bildirim", "süre"), "Bildirim ve süre şartı"),
            (("gerçek", "samimi", "zorunlu"), "İhtiyacın gerçek, samimi ve zorunlu niteliği"),
        ],
        "arguments": [
            (("ihtiyaç",), "Gerçek ve zorunlu konut / işyeri ihtiyacı"),
            (("başka", "uygun"), "Aynı bölgede uygun taşınmaz bulunmaması"),
            (("bildirim", "ihtar"), "Süre ve bildirim şartlarının tamamlanması"),
        ],
        "evidence": [
            (("tapu", "kira", "sözleşme"), "Kira sözleşmesi ve tapu kaydı birlikte sunulmalı."),
            (("nüfus", "ikamet"), "Nüfus ve ikamet kayıtları ihtiyaç bağlamını güçlendirir."),
            (("ihtar", "tebliğ"), "İhtarname ve tebliğ şerhi, usul ve süreyi ispatlar."),
        ],
        "risks": [
            (("soyut", "tercih"), "İhtiyaç soyut tercih düzeyinde kalıyorsa talep zayıflar."),
            (("başka", "konut", "taşınmaz"), "Alternatif taşınmaz bulunması savı ayrıştırılmalıdır."),
        ],
        "recommendations": {
            "verified_supportive_precedent": "İhtiyacın gerçekliği ve süre unsuru ile birlikte doğrudan kullanılabilir.",
            "verification_required_precedent_candidate": "Doğrulama sonrası destekleyici emsal olarak eklenmeli.",
            "weak_or_partial_precedent": "Sınırlı ve yardımcı atıf olarak kullanılmalı.",
            "adverse_or_distinguishable_precedent": "Aleyhe görünen noktalar ayrıştırılmadan kullanılmamalı.",
        },
    },
    "poverty_alimony": {
        "facts": [
            (("nafaka",), "Nafaka ilişkisi"),
            (("gelir", "maaş"), "Gelir değişikliği"),
            (("gider", "kira", "sağlık"), "Güncel gider tablosu"),
            (("çalış", "çalıştığı"), "Karşı tarafın gelir elde etmesi"),
        ],
        "issues": [
            (("tmk 176", "nafakanın kaldırılması", "indirilmesi"), "Nafakanın kaldırılması / indirilmesi"),
            (("hakkaniyet",), "Hakkaniyet değerlendirmesi"),
            (("sosyal", "ekonomik"), "Sosyal ve ekonomik durum değişikliği"),
        ],
        "arguments": [
            (("gelir", "değişiklik"), "Gelir ve gider dengesinde esaslı değişiklik"),
            (("hakkaniyet",), "Hakkaniyet gereği kaldırma veya indirim"),
            (("çalış", "gelir"), "Karşı tarafın gelir elde etmesi"),
        ],
        "evidence": [
            (("maaş", "bordro", "banka"), "Banka ve bordro kayıtları güncel ekonomik durumu gösterir."),
            (("sgk", "tapu", "araç"), "SGK, tapu ve araç kayıtları gelir ve malvarlığı incelemesini destekler."),
        ],
        "risks": [
            (("somut", "delil"), "Esaslı değişiklik somut belgelerle ispatlanmalıdır."),
            (("indirim", "kaldırma"), "Mahkeme kaldırma yerine indirim yoluna gidebilir."),
        ],
        "recommendations": {
            "verified_supportive_precedent": "Gelir değişikliği ve hakkaniyetle birlikte doğrudan kullanılabilir.",
            "verification_required_precedent_candidate": "Tam metin doğrulandıktan sonra destekleyici emsal olarak eklenmeli.",
            "weak_or_partial_precedent": "Sınırlı kullanıma uygundur.",
            "adverse_or_distinguishable_precedent": "Aleyhe yönleri açıklanmadan kullanılmamalıdır.",
        },
    },
    "labor_receivable": {
        "facts": [
            (("işçi", "işçilik"), "İşçilik alacağı ilişkisi"),
            (("ücret", "bordro"), "Ücret ve bordro ilişkisi"),
            (("fazla mesai", "vardiya", "puantaj"), "Fazla çalışma düzeni"),
            (("fesih",), "Fesih ve çıkış süreci"),
        ],
        "issues": [
            (("kıdem", "ihbar", "fazla mesai"), "İşçilik alacakları"),
            (("arabuluculuk",), "Arabuluculuk dava şartı"),
            (("ispat", "tanık", "kayıt"), "İspat ve kayıt düzeni"),
        ],
        "arguments": [
            (("işçilik", "alacak"), "İşçilik alacaklarının tahsili"),
            (("fazla mesai",), "Fazla mesai ispatı"),
            (("arabuluculuk",), "Arabuluculuk şartının tamamlanması"),
        ],
        "evidence": [
            (("sgk",), "SGK kaydı çalışma süresini doğrular."),
            (("banka", "bordro"), "Banka ve bordro kayıtları ücret miktarını destekler."),
        ],
        "risks": [
            (("bordro", "imzalı"), "İmzalı bordro savunması ayrıca ele alınmalıdır."),
            (("arabuluculuk",), "Arabuluculuk kapsamı eksikse dava şartı riski doğar."),
        ],
        "recommendations": {
            "verified_supportive_precedent": "Çalışma süresi ve ücret bağlantısı ile birlikte kullanılabilir.",
            "verification_required_precedent_candidate": "Doğrulandıktan sonra örnek emsal olarak eklenmeli.",
            "weak_or_partial_precedent": "Yardımcı atıf olarak kullanılmalı.",
            "adverse_or_distinguishable_precedent": "Aleyhe yönleri ayıklanmadan kullanılmamalıdır.",
        },
    },
    "enforcement_objection": {
        "facts": [
            (("icra", "takip"), "İcra takibi"),
            (("itiraz", "ödeme emri"), "İtiraz süreci"),
            (("fatura", "sözleşme", "senet"), "Takibin dayanağı"),
            (("likit", "likitlik"), "Likit alacak tartışması"),
        ],
        "issues": [
            (("itirazın iptali", "takibin devamı"), "İtirazın iptali ve takibin devamı"),
            (("icra inkar tazminatı", "inkar"), "İcra inkar tazminatı"),
            (("yetki", "zamanaşımı"), "Yetki ve zamanaşımı denetimi"),
        ],
        "arguments": [
            (("likit",), "Alacağın likit olduğu savı"),
            (("itiraz",), "İtirazın haksız olduğu savı"),
            (("icra inkar tazminatı",), "İcra inkar tazminatı koşulları"),
        ],
        "evidence": [
            (("sözleşme", "fatura", "dekont"), "Dayanak belgeler alacağın varlığını somutlaştırır."),
            (("icra", "dosya"), "Takip dosyası ve itiraz dilekçesi birlikte değerlendirilmeli."),
        ],
        "risks": [
            (("yetki",), "Yetki itirazı ayrıca kontrol edilmelidir."),
            (("likit",), "Likitlik açık değilse tazminat riski doğar."),
        ],
        "recommendations": {
            "verified_supportive_precedent": "Takip ve likitlik bağlantısı ile doğrudan kullanılabilir.",
            "verification_required_precedent_candidate": "Belge doğrulaması sonrası destekleyici emsal olarak eklenmeli.",
            "weak_or_partial_precedent": "Sınırlı atıf yeterlidir.",
            "adverse_or_distinguishable_precedent": "Kararın usul veya yetki yönleri ayrıştırılmadan kullanılmamalıdır.",
        },
    },
    "generic": {
        "facts": [
            (("taraf", "rol"), "Taraf sıfatı"),
            (("delil", "belge"), "Delil ilişkisi"),
            (("süre", "tarih"), "Kritik tarih ve süre"),
            (("ispat", "kanıt"), "İspat ilişkisi"),
        ],
        "issues": [
            (("hukuki", "neden"), "Hukuki nedenlerin kurulması"),
            (("ispat",), "İspat yükü"),
            (("delil",), "Delil bağlantısı"),
        ],
        "arguments": [
            (("ispat",), "İspat yükü ve delil bağlantısı"),
            (("hukuki",), "Hukuki nitelendirme"),
        ],
        "evidence": [
            (("belge",), "Belge ve kayıtlar kararın olay örüntüsünü destekler."),
            (("tanık",), "Tanık anlatımları olay akışını güçlendirir."),
        ],
        "risks": [
            (("farklı", "ayrılan"), "Olay farkları ayrıştırılmalıdır."),
            (("eksik",), "Eksik delil varsa karar yalnızca yardımcı atıf olmalıdır."),
        ],
        "recommendations": {
            "verified_supportive_precedent": "Benzer olay örgüsü varsa doğrudan kullanılabilir.",
            "verification_required_precedent_candidate": "Önce tam metin doğrulanmalı, sonra emsal olarak eklenmeli.",
            "weak_or_partial_precedent": "Yardımcı açıklama olarak sınırlı kullanılmalı.",
            "adverse_or_distinguishable_precedent": "Ayrıştırılmadan kullanımı önerilmez.",
        },
    },
}


class PrecedentAnalysisService:
    """Convert raw decision cards into structured precedent analysis cards."""

    def analyze(self, *, case_text: str, decision: dict[str, Any]) -> PrecedentAnalysis:
        profile = get_petition_profile(case_text)
        decision_map = self._normalize_decision(decision)
        decision_text = self._decision_text(decision_map)
        case_plain = self._plain(case_text)
        decision_plain = self._plain(decision_text)
        score = self._int_value(decision_map.get("similarity_score"), default=0)

        shared_facts = self._shared_labels(profile.key, "facts", case_plain, decision_plain)
        shared_legal_issues = self._shared_labels(profile.key, "issues", case_plain, decision_plain)
        supported_arguments = self._supported_arguments(profile.key, decision_plain, shared_legal_issues)
        evidence_connection = self._evidence_connection(profile.key, decision_plain, shared_facts, shared_legal_issues)
        distinguishing_risks = self._distinguishing_risks(profile.key, decision_plain)
        verification_status = self._verification_status(
            score=score,
            decision_map=decision_map,
            shared_facts=shared_facts,
            shared_legal_issues=shared_legal_issues,
        )
        similarity_reasons = self._similarity_reasons(
            profile.key,
            score=score,
            shared_facts=shared_facts,
            shared_legal_issues=shared_legal_issues,
            decision_map=decision_map,
        )
        confidence_score = self._confidence_score(
            score=score,
            verification_status=verification_status,
            shared_facts=shared_facts,
            shared_legal_issues=shared_legal_issues,
            decision_map=decision_map,
        )
        recommended_use = self._recommended_use(profile.key, verification_status)

        return PrecedentAnalysis(
            precedent_id=self._precedent_id(decision_map),
            citation=self._citation(decision_map),
            verification_status=verification_status,
            similarity_reasons=similarity_reasons,
            shared_facts=shared_facts,
            shared_legal_issues=shared_legal_issues,
            supported_arguments=supported_arguments,
            evidence_connection=evidence_connection,
            distinguishing_risks=distinguishing_risks,
            recommended_use=recommended_use,
            confidence_score=confidence_score,
        )

    def analyze_many(self, *, case_text: str, decisions: list[dict[str, Any]]) -> list[PrecedentAnalysis]:
        result: list[PrecedentAnalysis] = []
        seen: set[str] = set()
        for decision in decisions:
            analysis = self.analyze(case_text=case_text, decision=decision)
            key = self._plain(analysis.precedent_id)
            if key in seen:
                continue
            seen.add(key)
            result.append(analysis)
        return result

    def _verification_status(
        self,
        *,
        score: int,
        decision_map: dict[str, Any],
        shared_facts: list[str],
        shared_legal_issues: list[str],
    ) -> VerificationStatus:
        alignment = self._plain(
            " ".join(
                [
                    str(decision_map.get("lehe_aleyhe") or ""),
                    str(decision_map.get("usefulness_score") or ""),
                    str(decision_map.get("petition_paragraph") or ""),
                ]
            )
        )
        if any(marker in alignment for marker in ("aleyhe", "riskli", "redd", "olumsuz")):
            return "adverse_or_distinguishable_precedent"

        detail_text = self._decision_text(decision_map)
        has_full_citation = all(
            str(decision_map.get(field) or "").strip()
            for field in ("court", "esas_no", "karar_no", "date")
        )
        has_substance = len(shared_facts) + len(shared_legal_issues) >= 2
        has_decision_text = len(self._plain(detail_text)) >= 80

        if score >= 68 and has_full_citation and has_substance and has_decision_text:
            return "verified_supportive_precedent"
        if score >= 42 and has_substance:
            return "verification_required_precedent_candidate"
        return "weak_or_partial_precedent"

    def _similarity_reasons(
        self,
        profile_key: str,
        *,
        score: int,
        shared_facts: list[str],
        shared_legal_issues: list[str],
        decision_map: dict[str, Any],
    ) -> list[str]:
        reasons: list[str] = []
        if shared_facts:
            reasons.append(f"Somut vakıa düzeyinde örtüşen başlıklar: {', '.join(shared_facts[:3])}.")
        if shared_legal_issues:
            reasons.append(f"Aynı hukuki sorun hattı: {', '.join(shared_legal_issues[:3])}.")
        if decision_map.get("title"):
            reasons.append(f"Karar başlığı ve özeti, {self._profile_label(profile_key)} eksenini destekliyor.")
        if score:
            reasons.append(f"Benzerlik puanı {score} ve üzerindeki kavramsal eşleşmelerle oluştu.")
        if not reasons:
            reasons.append("Karar kimliği mevcut, ancak olay ve hukuk benzerliği sınırlı görünüyor.")
        return reasons[:4]

    def _supported_arguments(
        self,
        profile_key: str,
        decision_plain: str,
        shared_legal_issues: list[str],
    ) -> list[str]:
        templates = self._profile_signals(profile_key).get("arguments", [])
        result: list[str] = []
        for patterns, label in templates:  # type: ignore[assignment]
            if self._matches_any(decision_plain, patterns):
                result.append(label)
        if not result:
            result.extend(shared_legal_issues[:3])
        if not result:
            result.append("Hukuki ilke ve delil bağlantısı sınırlı şekilde kurulabilir.")
        return result[:4]

    def _evidence_connection(
        self,
        profile_key: str,
        decision_plain: str,
        shared_facts: list[str],
        shared_legal_issues: list[str],
    ) -> list[str]:
        templates = self._profile_signals(profile_key).get("evidence", [])
        result: list[str] = []
        for patterns, label in templates:  # type: ignore[assignment]
            if self._matches_any(decision_plain, patterns):
                result.append(label)
        if not result and shared_facts:
            result.append(f"{shared_facts[0]} ile ilgili deliller, kararın olay örgüsünü somutlaştırmak için kullanılmalı.")
        if not result and shared_legal_issues:
            result.append(f"{shared_legal_issues[0]} yönünden delil bağlantısı kurulmalı.")
        if not result:
            result.append("Karar ile delil seti arasında açık bağlantı kurmak için tam metin doğrulaması gerekir.")
        return result[:4]

    def _distinguishing_risks(self, profile_key: str, decision_plain: str) -> list[str]:
        templates = self._profile_signals(profile_key).get("risks", [])
        result: list[str] = []
        for patterns, label in templates:  # type: ignore[assignment]
            if self._matches_any(decision_plain, patterns):
                result.append(label)
        if not result:
            result.append("Kararın olay farkları tam metinle doğrulanmadan destekleyici emsal gibi sunulmamalı.")
        return result[:4]

    def _recommended_use(self, profile_key: str, verification_status: VerificationStatus) -> str:
        recommendations = self._profile_signals(profile_key).get("recommendations", {})
        text = str(recommendations.get(verification_status) or "").strip()
        if text:
            return text
        if verification_status == "verified_supportive_precedent":
            return "Karar doğrulanmış destekleyici emsal olarak kullanılabilir."
        if verification_status == "verification_required_precedent_candidate":
            return "Karar aday emsal olarak sunulmalı; tam metin doğrulanmadan doğrudan emsal denmemelidir."
        if verification_status == "weak_or_partial_precedent":
            return "Karar yalnızca yardımcı atıf olarak kullanılmalıdır."
        return "Karar aleyhe veya ayırt edilebilir olduğundan yalnızca karşı argümana cevap için kullanılmalıdır."

    def _confidence_score(
        self,
        *,
        score: int,
        verification_status: VerificationStatus,
        shared_facts: list[str],
        shared_legal_issues: list[str],
        decision_map: dict[str, Any],
    ) -> int:
        bonus = 0
        if verification_status == "verified_supportive_precedent":
            bonus += 15
        elif verification_status == "verification_required_precedent_candidate":
            bonus += 5
        elif verification_status == "weak_or_partial_precedent":
            bonus -= 10
        else:
            bonus -= 20
        if shared_facts:
            bonus += min(len(shared_facts) * 4, 12)
        if shared_legal_issues:
            bonus += min(len(shared_legal_issues) * 5, 15)
        if str(decision_map.get("detail_url") or "").strip():
            bonus += 4
        if str(decision_map.get("clean_text_preview") or "").strip():
            bonus += 4
        return max(0, min(100, score + bonus))

    @staticmethod
    def _normalize_decision(decision: dict[str, Any]) -> dict[str, Any]:
        return {str(key): value for key, value in (decision or {}).items()}

    @staticmethod
    def _precedent_id(decision_map: dict[str, Any]) -> str:
        identity = " ".join(
            part
            for part in (
                str(decision_map.get("court") or "").strip(),
                f"E. {str(decision_map.get('esas_no') or '').strip()}" if decision_map.get("esas_no") else "",
                f"K. {str(decision_map.get('karar_no') or '').strip()}" if decision_map.get("karar_no") else "",
                f"T. {str(decision_map.get('date') or '').strip()}" if decision_map.get("date") else "",
            )
            if part
        ).strip()
        return identity or str(decision_map.get("title") or "karar")

    @staticmethod
    def _citation(decision_map: dict[str, Any]) -> str:
        identity = PrecedentAnalysisService._precedent_id(decision_map)
        source = str(decision_map.get("source") or "").strip()
        title = str(decision_map.get("title") or "").strip()
        parts = [part for part in (source, title, identity) if part]
        return " | ".join(parts) if parts else identity

    def _decision_text(self, decision_map: dict[str, Any]) -> str:
        parts = [
            str(decision_map.get("title") or ""),
            str(decision_map.get("short_summary") or ""),
            str(decision_map.get("legal_principle") or ""),
            str(decision_map.get("why_relevant") or ""),
            str(decision_map.get("petition_paragraph") or ""),
            str(decision_map.get("clean_text_preview") or ""),
        ]
        return " ".join(part for part in parts if part).strip()

    def _shared_labels(self, profile_key: str, bucket: str, case_plain: str, decision_plain: str) -> list[str]:
        templates = self._profile_signals(profile_key).get(bucket, [])
        result: list[str] = []
        for patterns, label in templates:  # type: ignore[assignment]
            if self._matches_any(case_plain, patterns) and self._matches_any(decision_plain, patterns):
                result.append(label)
        if not result and bucket == "facts":
            generic = self._profile_signals("generic").get("facts", [])
            for patterns, label in generic:  # type: ignore[assignment]
                if self._matches_any(case_plain, patterns) and self._matches_any(decision_plain, patterns):
                    result.append(label)
        if not result and bucket == "issues":
            generic = self._profile_signals("generic").get("issues", [])
            for patterns, label in generic:  # type: ignore[assignment]
                if self._matches_any(case_plain, patterns) and self._matches_any(decision_plain, patterns):
                    result.append(label)
        return result[:4]

    @staticmethod
    def _profile_label(profile_key: str) -> str:
        labels = {
            "defective_vehicle": "gizli ayıp ve ayıba karşı tekeffül",
            "eviction_need": "ihtiyaç nedeniyle tahliye",
            "poverty_alimony": "nafakanın kaldırılması / indirimi",
            "labor_receivable": "işçilik alacakları",
            "enforcement_objection": "itirazın iptali ve takip",
        }
        return labels.get(profile_key, "somut uyuşmazlık")

    def _profile_signals(self, profile_key: str) -> dict[str, Any]:
        return PROFILE_SIGNALS.get(profile_key, PROFILE_SIGNALS["generic"])

    @staticmethod
    def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
        plain = PrecedentAnalysisService._plain(text)
        return any(PrecedentAnalysisService._plain(pattern) in plain for pattern in patterns)

    @staticmethod
    def _int_value(value: Any, *, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _plain(text: str) -> str:
        plain = str(text or "").casefold()
        plain = (
            plain.replace("ç", "c")
            .replace("ğ", "g")
            .replace("ı", "i")
            .replace("ö", "o")
            .replace("ş", "s")
            .replace("ü", "u")
        )
        return " ".join(plain.split())


precedent_analysis_service = PrecedentAnalysisService()
