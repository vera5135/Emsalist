"""Build a safe, provider-ready legal search profile from a case narrative.

This module deliberately exposes only structured, user-facing rationale. It does
not persist the raw narrative, generate hidden chain-of-thought, or claim that a
legal hypothesis is verified law. The deterministic provider is the first
product-value slice; a model-backed provider can implement the same interface
later without changing the API contract.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Protocol

from app.models.case_models import (
    CaseSearchProfileEvent,
    CaseSearchProfileRequest,
    CaseSearchProfileResponse,
)

_DATE_RE = re.compile(r"\b(?:[0-3]?\d[./-][01]?\d[./-](?:19|20)\d{2}|(?:19|20)\d{2})\b")
_AMOUNT_RE = re.compile(
    r"\b\d{1,3}(?:[.\s]\d{3})*(?:,\d{1,2})?\s*(?:TL|₺|lira)\b",
    re.IGNORECASE,
)
_PLATE_RE = re.compile(r"\b\d{2}\s?[A-ZÇĞİÖŞÜ]{1,3}\s?\d{2,4}\b", re.IGNORECASE)
_VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b", re.IGNORECASE)


class CaseSearchProfileProvider(Protocol):
    def build(self, request: CaseSearchProfileRequest) -> CaseSearchProfileResponse:
        """Return a bounded, provider-ready legal search profile."""


def _contains(text: str, *terms: str) -> bool:
    return any(term.casefold() in text for term in terms)


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = " ".join(str(value).split())
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def _matched_phrases(text: str, mapping: tuple[tuple[tuple[str, ...], str], ...]) -> list[str]:
    return [label for terms, label in mapping if _contains(text, *terms)]


def _extract_explicit_facts(case_text: str) -> list[str]:
    facts: list[str] = []
    for date_text in _DATE_RE.findall(case_text):
        facts.append(f"Metinde tarih bilgisi geçiyor: {date_text}")
    for amount in _AMOUNT_RE.findall(case_text):
        facts.append(f"Metinde parasal tutar geçiyor: {amount}")
    for plate in _PLATE_RE.findall(case_text.upper()):
        facts.append(f"Araç plakası belirtilmiş: {' '.join(plate.split())}")
    for vin in _VIN_RE.findall(case_text.upper()):
        facts.append(f"Şasi/VIN bilgisi belirtilmiş: {vin}")
    return _unique(facts)


def _extract_chronology(case_text: str) -> list[CaseSearchProfileEvent]:
    events: list[CaseSearchProfileEvent] = []
    sentences = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", case_text) if segment.strip()]
    for sentence in sentences:
        dates = _DATE_RE.findall(sentence)
        if dates:
            events.append(
                CaseSearchProfileEvent(
                    date_text=dates[0],
                    description=sentence[:500],
                    certainty="explicit",
                )
            )
    return events[:10]


_VEHICLE_TERMS = (
    "ayıplı araç",
    "ikinci el araç",
    "araç satışı",
    "gizli ayıp",
    "motor arız",
    "şanzıman",
    "ekspertiz",
    "tramer",
    "ağır hasar",
    "kilometre düşür",
)


class DeterministicCaseSearchProfileProvider:
    """Conservative first-pass legal understanding for provider discovery.

    The first accepted pilot is defective second-hand vehicle disputes. Other
    legal areas receive a smaller, explicit fallback profile instead of a false
    high-confidence classification.
    """

    provider_name = "deterministic_v1"

    def build(self, request: CaseSearchProfileRequest) -> CaseSearchProfileResponse:
        text = request.case_text
        folded = text.casefold()
        if _contains(folded, *_VEHICLE_TERMS):
            return self._build_defective_vehicle(request, folded)
        return self._build_fallback(request, folded)

    def _build_defective_vehicle(
        self,
        request: CaseSearchProfileRequest,
        folded: str,
    ) -> CaseSearchProfileResponse:
        party_roles = _matched_phrases(
            folded,
            (
                (("alıcı", "müvekkil satın aldı", "satın aldım"), "Alıcı"),
                (("satıcı", "satandan", "galeri", "bayi"), "Satıcı"),
                (("galeri", "bayi", "tacir", "şirket"), "Ticari satıcı ihtimali"),
                (("özel kişi", "şahıstan", "bireysel satıcı"), "Özel kişi satıcı ihtimali"),
                (("ekspertiz", "eksper"), "Ekspertiz kuruluşu"),
                (("servis", "usta"), "Servis/teknik inceleme tarafı"),
            ),
        )
        if not party_roles:
            party_roles = ["Alıcı", "Satıcı"]

        material_facts = _extract_explicit_facts(request.case_text)
        material_facts.extend(
            _matched_phrases(
                folded,
                (
                    (("ikinci el",), "Satışın ikinci el araca ilişkin olduğu belirtilmiş."),
                    (("motor arız",), "Motor arızası ileri sürülmüş."),
                    (("şanzıman",), "Şanzıman arızası ileri sürülmüş."),
                    (("ağır hasar", "pert"), "Ağır hasar/pert geçmişi uyuşmazlık konusu."),
                    (("tramer",), "TRAMER kaydı uyuşmazlıkta önem taşıyor."),
                    (("kilometre düşür",), "Kilometre düşürülmesi iddiası bulunuyor."),
                    (("ekspertiz",), "Satış öncesi veya sonrası ekspertiz raporu mevcut olabilir."),
                    (("servis",), "Servis incelemesi veya onarım kaydı mevcut olabilir."),
                    (("kısa süre", "hemen sonra", "ertesi gün"), "Arızanın satıştan kısa süre sonra ortaya çıktığı ileri sürülmüş."),
                ),
            )
        )

        claims = _matched_phrases(
            folded,
            (
                (("sözleşmeden dön", "bedel iades", "aracı iade"), "Sözleşmeden dönme ve satış bedelinin iadesi"),
                (("bedel indir",), "Satış bedelinden indirim"),
                (("ücretsiz onarım", "tamir masraf"), "Ücretsiz onarım veya onarım gideri"),
                (("ayıpsız misli", "değişim"), "Ayıpsız misliyle değişim"),
                (("tazminat", "zarar", "masraf"), "Maddi zarar ve yan giderlerin tazmini"),
            ),
        )
        claims.extend(request.preferred_relief)
        if not claims:
            claims = ["Ayıplı mal seçimlik haklarından uygun olanının belirlenmesi"]

        legal_issues = [
            "Araçta hukuken ayıp bulunup bulunmadığı",
            "Ayıbın gizli/açık niteliği ve alıcının bilip bilmediği",
            "Ayıbın teslim tarihinde mevcut olup olmadığı",
            "Satıcının tüketici işlemi veya genel satış hükümleri kapsamındaki sıfatı",
            "Ayıp bildiriminin zamanı ve içeriği",
            "Talep edilen seçimlik hakkın koşulları",
            "Ayıp ile zarar arasında illiyet bağı",
        ]
        if _contains(folded, "ekspertiz", "eksper"):
            legal_issues.append("Ekspertiz raporunun ayıbı ve tarafların bilgi durumunu ispat gücü")
        if _contains(folded, "tramer", "ağır hasar", "pert"):
            legal_issues.append("Hasar geçmişinin açıklanması ve gizlenmesinin hukuki etkisi")
        if _contains(folded, "kilometre düşür"):
            legal_issues.append("Kilometre bilgisindeki müdahalenin ayıp ve hile bakımından etkisi")

        evidence_issues = [
            "Noter satış sözleşmesi ve teslim tarihi",
            "Arızanın niteliğini ve teslimde varlığını inceleyen teknik bilirkişi raporu",
            "Servis kayıtları, arıza kodları, onarım faturaları ve parça geçmişi",
            "Ayıp ihbarı, mesajlar, ihtarname ve satıcının cevapları",
        ]
        if _contains(folded, "ekspertiz", "eksper"):
            evidence_issues.append("Ekspertiz raporunun tarihi, kapsamı ve kontrol edilmeyen parçaları")
        if _contains(folded, "tramer", "ağır hasar", "pert"):
            evidence_issues.append("TRAMER/SBM kayıtları ve önceki hasar-onarım belgeleri")

        possible_defenses = [
            "Arızanın teslimden sonra kullanım veya bakım hatasıyla oluştuğu savunması",
            "Alıcının ayıbı satış sırasında bildiği veya makul incelemeyle bilebileceği savunması",
            "Ayıp ihbarının geç veya belirsiz yapıldığı savunması",
            "Talep edilen seçimlik hakkın ölçüsüz olduğu savunması",
        ]
        if _contains(folded, "ekspertiz", "eksper"):
            possible_defenses.append("Olumlu ekspertiz raporuna güvenildiği ve satıcının ayıbı bilmediği savunması")

        missing_information = _unique(
            item
            for condition, item in (
                (not bool(_DATE_RE.search(request.case_text)), "Satış ve teslim tarihi"),
                (not bool(_AMOUNT_RE.search(request.case_text)), "Satış bedeli"),
                (not _contains(folded, "galeri", "bayi", "tacir", "şirket", "özel kişi", "şahıstan"), "Satıcının tacir/mesleki satıcı mı yoksa özel kişi mi olduğu"),
                (not _contains(folded, "ihbar", "ihtar", "bildir", "mesaj att"), "Ayıp ihbarının tarihi, yöntemi ve içeriği"),
                (not _contains(folded, "rapor", "ekspertiz", "bilirkişi", "servis"), "Teknik raporun tarihi, düzenleyeni ve temel bulguları"),
                (not _contains(folded, "motor", "şanzıman", "hasar", "kilometre", "arıza"), "Ayıbın teknik niteliği ve ortaya çıkış biçimi"),
                (not claims or claims == ["Ayıplı mal seçimlik haklarından uygun olanının belirlenmesi"], "Müvekkilin öncelikli seçimlik hakkı ve zarar kalemleri"),
            )
            if condition
        )

        legislation = [
            "6502 sayılı Tüketicinin Korunması Hakkında Kanun m. 8-12 (uygulanabilirlik satıcının sıfatına bağlıdır)",
            "Türk Borçlar Kanunu m. 219 ve devamı (satıcının ayıptan sorumluluğu)",
            "HMK m. 266 ve devamı (teknik bilirkişi incelemesi ihtimali)",
        ]

        queries = [
            "ikinci el araç gizli ayıp teslim tarihinde mevcut motor arızası",
            "ayıplı araç ekspertiz raporu satıcının sorumluluğu",
            "6502 ayıplı mal seçimlik haklar ikinci el araç",
            "TBK 219 gizli ayıp araç satışı ayıp ihbarı",
        ]
        if _contains(folded, "tramer", "ağır hasar", "pert"):
            queries.append("ikinci el araç ağır hasar TRAMER gizli ayıp bedel iadesi")
        if _contains(folded, "kilometre düşür"):
            queries.append("ikinci el araç kilometre düşürülmesi gizli ayıp hile")
        elif _contains(folded, "şanzıman"):
            queries.append("ikinci el araç şanzıman arızası gizli ayıp bilirkişi")
        elif _contains(folded, "motor"):
            queries.append("ikinci el araç motor arızası gizli ayıp bilirkişi")
        if any("dönme" in claim.casefold() or "iade" in claim.casefold() for claim in claims):
            queries.append("ayıplı araç sözleşmeden dönme kullanım bedeli satış bedeli iadesi")
        elif any("indirim" in claim.casefold() for claim in claims):
            queries.append("ayıplı araç bedel indirimi değer farkı bilirkişi")

        return CaseSearchProfileResponse(
            case_id=request.case_id,
            legal_area="Tüketici Hukuku / Satış Hukuku",
            dispute_type="Ayıplı ikinci el araç satışı",
            party_roles=_unique(party_roles),
            material_facts=_unique(material_facts),
            chronology=_extract_chronology(request.case_text),
            claims=_unique(claims),
            possible_defenses=_unique(possible_defenses),
            legal_issues=_unique(legal_issues),
            evidence_issues=_unique(evidence_issues),
            legislation_hypotheses=legislation,
            missing_information=missing_information,
            yargitay_queries=_unique(queries)[: request.max_queries],
            extraction_mode="deterministic_v1",
            confidence=0.9,
        )

    def _build_fallback(
        self,
        request: CaseSearchProfileRequest,
        folded: str,
    ) -> CaseSearchProfileResponse:
        area, dispute, queries = self._fallback_classification(folded)
        material_facts = _extract_explicit_facts(request.case_text)
        if not material_facts:
            material_facts = [request.case_text[:500]]
        claims = request.preferred_relief or ["Talep türü henüz netleştirilmedi"]
        generic_queries = _unique([*queries, *claims, dispute])
        while len(generic_queries) < 3:
            generic_queries.append(f"{dispute} ispat yükü")
            generic_queries = _unique(generic_queries)
            if len(generic_queries) < 3:
                generic_queries.append(f"{dispute} Yargıtay")
        return CaseSearchProfileResponse(
            case_id=request.case_id,
            legal_area=area,
            dispute_type=dispute,
            party_roles=[],
            material_facts=material_facts,
            chronology=_extract_chronology(request.case_text),
            claims=_unique(claims),
            possible_defenses=["Karşı tarafın temel savunmaları için ek olay bilgisi gerekli"],
            legal_issues=["Uyuşmazlığın hukuki sebebi ve talep sonucu kesinleştirilmeli"],
            evidence_issues=["İddiaları destekleyen belge ve deliller sınıflandırılmalı"],
            legislation_hypotheses=[],
            missing_information=[
                "Tarafların hukuki sıfatları",
                "Talep sonucu",
                "Kritik tarihler",
                "Mevcut belge ve deliller",
            ],
            yargitay_queries=generic_queries[: request.max_queries],
            extraction_mode="deterministic_v1",
            confidence=0.45,
        )

    @staticmethod
    def _fallback_classification(folded: str) -> tuple[str, str, list[str]]:
        if _contains(folded, "kira", "kiracı", "tahliye", "kiralanan"):
            return (
                "Kira Hukuku",
                "Kira sözleşmesinden doğan uyuşmazlık",
                [
                    "kira sözleşmesi tahliye Yargıtay",
                    "kiracı kiraya veren ispat yükü",
                    "TBK kira uyuşmazlığı",
                ],
            )
        if _contains(folded, "işçi", "kıdem", "ihbar", "fazla mesai", "işçilik"):
            return (
                "İş Hukuku",
                "İşçilik alacağı veya fesih uyuşmazlığı",
                [
                    "işçilik alacağı kıdem ihbar ispat",
                    "fazla çalışma bordro tanık Yargıtay",
                    "iş sözleşmesi fesih haklı neden",
                ],
            )
        if _contains(folded, "icra", "takip", "ödeme emri", "itirazın iptali"):
            return (
                "İcra ve İflas Hukuku",
                "İcra takibi ve alacak uyuşmazlığı",
                [
                    "itirazın iptali alacağın ispatı Yargıtay",
                    "İİK 67 icra inkar tazminatı",
                    "ilamsız icra borca itiraz",
                ],
            )
        if _contains(folded, "nafaka", "boşanma", "velayet"):
            return (
                "Aile Hukuku",
                "Aile hukukundan doğan uyuşmazlık",
                [
                    "nafaka velayet boşanma Yargıtay",
                    "TMK aile hukuku değişen koşullar",
                    "aile mahkemesi ispat değerlendirmesi",
                ],
            )
        return (
            "Henüz sınıflandırılmadı",
            "Genel hukuki uyuşmazlık",
            [
                "hukuki uyuşmazlık olay benzerliği Yargıtay",
                "talep ispat yükü Yargıtay",
                "usul ve maddi hukuk değerlendirmesi",
            ],
        )


case_search_profile_provider: CaseSearchProfileProvider = DeterministicCaseSearchProfileProvider()
