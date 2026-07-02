"""Deterministic legal issue extraction without Gemini."""

from __future__ import annotations

import re
from typing import Any


SAFE_SOURCE_DOMAINS = [
    "mevzuat.gov.tr",
    "karararama.yargitay.gov.tr",
    "emsal.uyap.gov.tr",
    "resmigazete.gov.tr",
]

VEHICLE_SAFE_ANSWER_OPTIONS = [
    "Belge mevcut",
    "Bilmiyorum",
    "Sonra tamamlanacak",
    "Servis raporu mevcut",
    "Ekspertiz raporu mevcut",
    "Noter ihtarnamesi mevcut",
    "Mesaj yazışması mevcut",
    "TRAMER kaydı araştırılacak",
    "Bilirkişi incelemesi talep edilecek",
]

VEHICLE_NEGATIVE_TERMS = [
    "iş hukuku",
    "kıdem tazminatı",
    "ihbar tazminatı",
    "fazla mesai",
    "SGK",
    "bordro",
    "işçi",
    "işveren",
    "nafaka",
    "boşanma",
    "kira",
    "tahliye",
    "ceza",
    "icra",
]


class DynamicLegalReasonerService:
    def reason(
        self,
        *,
        event_text: str,
        document_facts: list[str] | None = None,
        question_answers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
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
    ) -> dict[str, Any]:
        facts = self._clean_list(document_facts or [])
        answers = {
            " ".join(str(key).split()): " ".join(str(value).split())
            for key, value in (question_answers or {}).items()
            if str(key).strip() and str(value).strip()
        }
        combined = " ".join([event_text, *facts, *answers.keys(), *answers.values()])
        plain = self._plain(combined)
        if self._is_vehicle_case(plain):
            return self._vehicle_reasoning(
                event_text=event_text,
                facts=facts,
                answers=answers,
                plain=plain,
            )
        return self._generic_reasoning(event_text=event_text, facts=facts, answers=answers, plain=plain)

    def _vehicle_reasoning(
        self,
        *,
        event_text: str,
        facts: list[str],
        answers: dict[str, str],
        plain: str,
    ) -> dict[str, Any]:
        known = self._known_vehicle_facts(event_text=event_text, facts=facts, answers=answers, plain=plain)
        issues = [
            self._issue(
                issue_key="sale_relationship",
                title="Satış ilişkisi",
                description="Taraflar arasında ikinci el araç satış ilişkisinin kurulduğu ve temel satış bilgilerinin somutlaştırılması gerekir.",
                legal_basis=["TBK m. 219"],
                required_facts=["Taraflar", "Satış tarihi", "Satış bedeli", "Araç kimliği", "Noter satış sözleşmesi"],
                known_facts=self._take_known(known, ["Taraflar", "Satış tarihi", "Satış bedeli", "Araç kimliği", "Noter satış sözleşmesi"]),
                missing_facts=self._missing(known, ["Taraflar", "Satış tarihi", "Satış bedeli", "Araç kimliği", "Noter satış sözleşmesi"]),
                required_evidence=["Noter satış sözleşmesi", "Ruhsat/tescil kayıtları"],
                risk_level="medium",
                risk_reason="Satış ilişkisinin temel unsurları eksikse dava iskeleti zayıflar.",
                questions=[
                    "Noter satış sözleşmesi mevcut mu?",
                    "Araç plaka ve şasi bilgileri tam mı?",
                ],
                research_queries=[
                    "ikinci el araç gizli ayıp Yargıtay",
                ],
            ),
            self._issue(
                issue_key="hidden_defect",
                title="Gizli ayıp",
                description="Ayıbın olağan incelemeyle fark edilemeyen nitelikte olması ve satış konusu araçla bağlantısı kurulmalıdır.",
                legal_basis=["TBK m. 219"],
                required_facts=["Arıza/ayıp türü", "Gizli ayıp niteliği", "Satıcı beyanı"],
                known_facts=self._take_known(known, ["Arıza/ayıp türü", "Gizli ayıp niteliği", "Satıcı beyanı"]),
                missing_facts=self._missing(known, ["Arıza/ayıp türü", "Gizli ayıp niteliği", "Satıcı beyanı"]),
                required_evidence=["Servis/ekspertiz raporu", "İlan ve mesaj kayıtları"],
                risk_level="medium",
                risk_reason="Ayıbın gizli niteliği teknik belge ve satış öncesi beyanlarla desteklenmezse savunma güçlenir.",
                questions=[
                    "Satıcı satış öncesinde hangi beyanda bulundu?",
                    "Ayıp olağan muayene ile anlaşılabilir miydi?",
                ],
                research_queries=[
                    "araç satışında gizli ayıp servis raporu Yargıtay",
                ],
            ),
            self._issue(
                issue_key="preexisting_defect",
                title="Ayıbın satıştan önce mevcut olması",
                description="Ayıbın teslim sonrası değil, satış anında mevcut olduğunun teknik bağla ispatlanması gerekir.",
                legal_basis=["TBK m. 219", "HMK m. 190", "HMK m. 266"],
                required_facts=["Arızanın ortaya çıkış zamanı", "Teknik tespit", "Satış öncesi mevcut olma olgusu"],
                known_facts=self._take_known(known, ["Arızanın ortaya çıkış zamanı", "Teknik tespit"]),
                missing_facts=self._missing(known, ["Satış öncesi mevcut olma olgusu", "Teknik tespit"]),
                required_evidence=["Servis/ekspertiz raporu", "Bilirkişi incelemesi"],
                risk_level="high",
                risk_reason="Satış öncesi mevcut olma bağı kurulamazsa talebin ana omurgası zayıflar.",
                questions=[
                    "Servis/ekspertiz raporu mevcut mu?",
                    "Ayıp teslimden ne kadar süre sonra ortaya çıktı?",
                ],
                research_queries=[
                    "motor arızası gizli ayıp bilirkişi",
                    "araç satışında gizli ayıp servis raporu Yargıtay",
                ],
            ),
            self._issue(
                issue_key="notice",
                title="Ayıp ihbarı",
                description="Ayıbın öğrenilmesinden sonra uygun sürede ve somut biçimde bildirim yapılıp yapılmadığı önemlidir.",
                legal_basis=["TBK m. 223"],
                required_facts=["Ayıbın öğrenilme tarihi", "Bildirim tarihi", "Bildirim yöntemi"],
                known_facts=self._take_known(known, ["Bildirim tarihi", "Bildirim yöntemi"]),
                missing_facts=self._missing(known, ["Ayıbın öğrenilme tarihi", "Bildirim tarihi", "Bildirim yöntemi"]),
                required_evidence=["Mesaj yazışmaları", "Noter ihtarnamesi"],
                risk_level="high",
                risk_reason="İhbar tarihi ve yöntemi belirsiz kalırsa TBK m. 223 yönünden güçlü risk doğar.",
                questions=[
                    "Ayıp ihbarı hangi tarihte ve hangi yöntemle yapıldı?",
                ],
                research_queries=[
                    "TBK 223 ayıp ihbarı araç satışı",
                ],
            ),
            self._issue(
                issue_key="remedies",
                title="Seçimlik haklar",
                description="Sözleşmeden dönme, bedel indirimi ve zarar kalemleri arasında açık talep kurgusu kurulmalıdır.",
                legal_basis=["TBK m. 227"],
                required_facts=["Asli talep", "Terditli talep", "Talep edilen zarar kalemleri"],
                known_facts=self._take_known(known, ["Asli talep", "Terditli talep", "Talep edilen zarar kalemleri"]),
                missing_facts=self._missing(known, ["Asli talep", "Terditli talep"]),
                required_evidence=["Satış bedeli kaydı", "Masraf faturaları/makbuzları"],
                risk_level="medium",
                risk_reason="Talep kurgusu belirsiz kalırsa hüküm sonucu zayıflayabilir.",
                questions=[
                    "Öncelikli seçimlik hak sözleşmeden dönme mi?",
                    "Terditli bedel indirimi ve zarar kalemleri istenecek mi?",
                ],
                research_queries=[
                    "TBK 227 sözleşmeden dönme bedel indirimi",
                ],
            ),
            self._issue(
                issue_key="seller_status",
                title="Satıcı sıfatı / görevli mahkeme",
                description="Satıcının tacir, galeri veya şirket olup olmadığı görevli mahkeme bakımından önemlidir.",
                legal_basis=["6502 sayılı Kanun", "HMK m. 114"],
                required_facts=["Satıcı sıfatı"],
                known_facts=self._take_known(known, ["Satıcı sıfatı"]),
                missing_facts=self._missing(known, ["Satıcı sıfatı"]),
                required_evidence=["Ticaret sicili / işletme bilgisi", "İlan bilgileri"],
                risk_level="medium",
                risk_reason="Tacir/galeri sıfatı netleşmezse görevli mahkeme değerlendirmesi güvenli bırakılmalıdır.",
                questions=[
                    "Satıcı galeri/tacir/şirket mi?",
                ],
                research_queries=[
                    "ayıplı araç tüketici mahkemesi galeri satıcı",
                ],
            ),
            self._issue(
                issue_key="damages",
                title="Zarar kalemleri",
                description="Satış bedeli dışındaki servis, ekspertiz, onarım ve sair zararların dayanağı toplanmalıdır.",
                legal_basis=["TBK m. 227"],
                required_facts=["Masraf kalemleri", "Fatura/makbuz"],
                known_facts=self._take_known(known, ["Masraf kalemleri", "Fatura/makbuz"]),
                missing_facts=self._missing(known, ["Masraf kalemleri", "Fatura/makbuz"]),
                required_evidence=["Fatura/makbuz", "Servis/ekspertiz gider belgesi"],
                risk_level="medium",
                risk_reason="Masraf kalemleri belgesiz kalırsa yalnızca ana talep yönünden ilerleme sağlanabilir.",
                questions=[
                    "Zarar kalemlerine ilişkin fatura/makbuz var mı?",
                ],
                research_queries=[
                    "ayıplı araç TRAMER ağır hasar bedel indirimi",
                ],
            ),
        ]

        evidence_plan = [
            self._evidence(
                evidence_key="notary_sale_contract",
                title="Noter satış sözleşmesi",
                proves=["sale_relationship", "remedies"],
                status="available" if "Noter satış sözleşmesi" in known else "unknown",
                source="Belge / noter satış sözleşmesi",
                risk_if_missing="Satış ilişkisi ve temel satış bilgileri eksik kalır.",
            ),
            self._evidence(
                evidence_key="vehicle_registration",
                title="Ruhsat/tescil kayıtları",
                proves=["sale_relationship"],
                status="to_be_requested" if "Araç kimliği" not in known else "unknown",
                source="Tescil kayıtları",
                risk_if_missing="Araç kimliği ve malik zinciri tam kurulamaz.",
            ),
            self._evidence(
                evidence_key="technical_report",
                title="Servis/ekspertiz raporu",
                proves=["hidden_defect", "preexisting_defect"],
                status="available" if "Teknik tespit" in known else "missing",
                source="Servis/ekspertiz belgesi",
                risk_if_missing="Ayıbın niteliği ve satıştan önce mevcut olduğu savı zayıflar.",
            ),
            self._evidence(
                evidence_key="notice_records",
                title="Ayıp ihbarı mesajları/ihtarname",
                proves=["notice"],
                status="available" if "Bildirim yöntemi" in known else "unknown",
                source="Mesaj kayıtları / ihtarname",
                risk_if_missing="TBK m. 223 ihbar riski yükselir.",
            ),
            self._evidence(
                evidence_key="tramer_record",
                title="TRAMER kaydı",
                proves=["hidden_defect", "preexisting_defect"],
                status="to_be_requested" if "TRAMER kaydı" not in known else "unknown",
                source="TRAMER / resmi kayıt",
                risk_if_missing="Ağır hasar veya gizli onarım savı somutlaşmaz.",
            ),
            self._evidence(
                evidence_key="expert_examination",
                title="Bilirkişi incelemesi",
                proves=["preexisting_defect", "damages"],
                status="to_be_requested",
                source="Mahkeme bilirkişisi",
                risk_if_missing="Teknik ve değer farkı bağlantısı yetersiz kalır.",
            ),
        ]

        risk_plan = [
            self._risk(
                risk_key="preexisting_defect_proof",
                title="Ayıbın satıştan önce mevcut olduğunun ispatı",
                level="high",
                reason="Teknik rapor veya bilirkişi bağlantısı olmadan gizli ayıp savı zayıflar.",
                related_issue_keys=["preexisting_defect", "hidden_defect"],
                mitigation="Servis/ekspertiz raporu ve bilirkişi incelemesiyle teknik bağ kurulmalıdır.",
                needed_evidence=["Servis/ekspertiz raporu", "Bilirkişi incelemesi"],
            ),
            self._risk(
                risk_key="notice_timing",
                title="Ayıp ihbarının süresi/yöntemi",
                level="high",
                reason="Bildirim tarihi ve yöntemi somut değilse TBK m. 223 yönünden savunma güçlenir.",
                related_issue_keys=["notice"],
                mitigation="Mesaj kayıtları ve ihtarname ile ihbar tarihi/yöntemi netleştirilmelidir.",
                needed_evidence=["Ayıp ihbarı mesajları/ihtarname"],
            ),
            self._risk(
                risk_key="seller_status_uncertain",
                title="Satıcının tacir/galeri sıfatı ve görevli mahkeme",
                level="medium",
                reason="Satıcı sıfatı kesinleşmeden görevli mahkeme güvenli başlıkla bırakılmalıdır.",
                related_issue_keys=["seller_status"],
                mitigation="Ticari sıfatı gösteren kayıtlar ve ilan verileri toplanmalıdır.",
                needed_evidence=["Ticaret sicili / işletme bilgisi", "İlan bilgileri"],
            ),
            self._risk(
                risk_key="missing_technical_report",
                title="Servis/ekspertiz raporu eksikliği",
                level="high",
                reason="Ayıbın niteliği ve satış öncesi mevcudiyeti teknik belge olmadan zayıf kalır.",
                related_issue_keys=["preexisting_defect", "hidden_defect"],
                mitigation="Servis/ekspertiz kaydı sunulmalı veya bilirkişi talebi öne çıkarılmalıdır.",
                needed_evidence=["Servis/ekspertiz raporu", "Bilirkişi incelemesi"],
            ),
            self._risk(
                risk_key="tramer_uncertainty",
                title="TRAMER/gizli onarım bilgisinin belirsizliği",
                level="medium",
                reason="Ağır hasar veya gizli onarım savı resmi kayıtla desteklenmezse iddia daralır.",
                related_issue_keys=["hidden_defect", "damages"],
                mitigation="TRAMER kaydı ve resmi kayıtların celbi talep edilmelidir.",
                needed_evidence=["TRAMER kaydı"],
            ),
        ]

        question_plan = [
            self._question(
                "Servis/ekspertiz raporu mevcut mu?",
                reason="Ayıbın niteliği ve satış öncesi mevcut olma bağlantısı için gereklidir.",
                related_issue_key="preexisting_defect",
            ),
            self._question(
                "Ayıp ihbarı hangi tarihte ve hangi yöntemle yapıldı?",
                reason="TBK m. 223 yönünden bildirim süresini ve yöntemini netleştirmek için sorulur.",
                related_issue_key="notice",
            ),
            self._question(
                "Satıcı galeri/tacir/şirket mi?",
                reason="Görevli mahkeme ve tüketici işlemi değerlendirmesi için gereklidir.",
                related_issue_key="seller_status",
            ),
            self._question(
                "TRAMER veya ağır hasar kaydı araştırıldı mı?",
                reason="Gizli ayıp ve gizli onarım savını desteklemek için sorulur.",
                related_issue_key="hidden_defect",
            ),
            self._question(
                "Zarar kalemlerine ilişkin fatura/makbuz var mı?",
                reason="Zarar kalemlerinin tahsili için belge ihtiyacını netleştirir.",
                related_issue_key="damages",
            ),
        ]

        research_queries = self._clean_list(
            [
                "ikinci el araç gizli ayıp Yargıtay",
                "TBK 219 ayıba karşı tekeffül araç",
                "TBK 223 ayıp ihbarı araç satışı",
                "TBK 227 sözleşmeden dönme bedel indirimi",
                "motor arızası gizli ayıp bilirkişi",
                "araç satışında gizli ayıp servis raporu Yargıtay",
                "ayıplı araç TRAMER ağır hasar bedel indirimi",
                *[query for issue in issues for query in issue["research_queries"]],
            ]
        )

        return {
            "legal_area_candidates": self._clean_list(
                [
                    "Borçlar Hukuku",
                    "Tüketici Hukuku" if self._seller_professional(answers, plain) else "",
                ]
            ),
            "case_type_candidates": self._clean_list(
                [
                    "gizli ayıplı ikinci el araç satışı",
                    "ayıba karşı tekeffül",
                    "ayıplı mal / seçimlik haklar",
                ]
            ),
            "legal_issues": issues,
            "research_queries": research_queries,
            "question_plan": question_plan,
            "evidence_plan": evidence_plan,
            "risk_plan": risk_plan,
            "precedent_query_context": {
                "positive_terms": [
                    "gizli ayıp",
                    "ikinci el araç",
                    "ayıp ihbarı",
                    "sözleşmeden dönme",
                    "bedel indirimi",
                    "servis raporu",
                    "TRAMER",
                ],
                "negative_terms": ["konu dışı karar", "işçilik uyuşmazlığı", "kira uyuşmazlığı"],
                "issue_tags": [issue["issue_key"] for issue in issues],
                "must_not_include": VEHICLE_NEGATIVE_TERMS,
            },
            "warnings": self._clean_list(
                [
                    "Satıcının sıfatı netleşmeden görevli mahkeme güvenli başlıkla korunmalıdır." if not self._seller_professional(answers, plain) else "",
                    "Servis/ekspertiz raporu bulunmadıkça satış öncesi mevcut olma bağı ihtiyatla kurulmalıdır." if "Teknik tespit" not in known else "",
                ]
            ),
        }

    def _generic_reasoning(
        self,
        *,
        event_text: str,
        facts: list[str],
        answers: dict[str, str],
        plain: str,
    ) -> dict[str, Any]:
        issue = self._issue(
            issue_key="generic_case_map",
            title="Somut olay haritası",
            description="Olay, talep, delil ve risk bağlantısının genel çerçevede kurulması gerekir.",
            legal_basis=[],
            required_facts=["Somut talep", "Taraf sıfatları", "Temel deliller"],
            known_facts=self._clean_list(
                [
                    "Somut talep" if "talep" in plain or "dava" in plain else "",
                    "Taraf sıfatları" if any(term in plain for term in ("davaci", "davali", "muvekkil")) else "",
                    "Temel deliller" if any(term in plain for term in ("belge", "delil", "tanik")) else "",
                ]
            ),
            missing_facts=[],
            required_evidence=["Belge ve kayıt planı"],
            risk_level="medium",
            risk_reason="Somut veri eksikse dava stratejisi dağınık kalabilir.",
            questions=["Somut talep nedir?"],
            research_queries=self._generic_queries(event_text),
        )
        return {
            "legal_area_candidates": [],
            "case_type_candidates": [],
            "legal_issues": [issue],
            "research_queries": issue["research_queries"],
            "question_plan": [
                self._question("Somut talep nedir?", reason="Dava kurgusunu netleştirmek için sorulur.", related_issue_key=issue["issue_key"]),
                self._question("Talebi destekleyen temel belgeler nelerdir?", reason="Delil planı için sorulur.", related_issue_key=issue["issue_key"]),
                self._question("Karşı tarafın beklenen savunması nedir?", reason="Risk planı için sorulur.", related_issue_key=issue["issue_key"]),
            ],
            "evidence_plan": [
                self._evidence(
                    evidence_key="generic_documents",
                    title="Belge ve kayıt planı",
                    proves=[issue["issue_key"]],
                    status="unknown",
                    source="Dosya içeriği",
                    risk_if_missing="Vak’a-delil bağlantısı zayıf kalır.",
                )
            ],
            "risk_plan": [
                self._risk(
                    risk_key="generic_missing_facts",
                    title="Eksik somutlaştırma riski",
                    level="medium",
                    reason="Talep, taraf ve delil başlıkları eksik kalırsa dava iskeleti zayıflar.",
                    related_issue_keys=[issue["issue_key"]],
                    mitigation="Temel olay, talep ve deliller net cümlelerle tamamlanmalıdır.",
                    needed_evidence=["Belge ve kayıt planı"],
                )
            ],
            "precedent_query_context": {
                "positive_terms": self._generic_queries(event_text),
                "negative_terms": [],
                "issue_tags": [issue["issue_key"]],
                "must_not_include": [],
            },
            "warnings": [],
        }

    @staticmethod
    def _issue(
        *,
        issue_key: str,
        title: str,
        description: str,
        legal_basis: list[str],
        required_facts: list[str],
        known_facts: list[str],
        missing_facts: list[str],
        required_evidence: list[str],
        risk_level: str,
        risk_reason: str,
        questions: list[str],
        research_queries: list[str],
    ) -> dict[str, Any]:
        return {
            "issue_key": issue_key,
            "title": title,
            "description": description,
            "legal_basis": legal_basis,
            "required_facts": required_facts,
            "known_facts": known_facts,
            "missing_facts": missing_facts,
            "required_evidence": required_evidence,
            "risk_level": risk_level,
            "risk_reason": risk_reason,
            "questions": questions,
            "research_queries": research_queries,
        }

    @staticmethod
    def _evidence(
        evidence_key: str,
        title: str,
        proves: list[str],
        status: str,
        source: str,
        risk_if_missing: str,
    ) -> dict[str, Any]:
        return {
            "evidence_key": evidence_key,
            "title": title,
            "proves": proves,
            "status": status,
            "source": source,
            "risk_if_missing": risk_if_missing,
        }

    @staticmethod
    def _risk(
        *,
        risk_key: str,
        title: str,
        level: str,
        reason: str,
        related_issue_keys: list[str],
        mitigation: str,
        needed_evidence: list[str],
    ) -> dict[str, Any]:
        return {
            "risk_key": risk_key,
            "title": title,
            "level": level,
            "reason": reason,
            "related_issue_keys": related_issue_keys,
            "mitigation": mitigation,
            "needed_evidence": needed_evidence,
        }

    @staticmethod
    def _question(question: str, *, reason: str, related_issue_key: str) -> dict[str, Any]:
        return {
            "question": question,
            "reason": reason,
            "related_issue_key": related_issue_key,
            "answer_options": list(VEHICLE_SAFE_ANSWER_OPTIONS),
        }

    def _known_vehicle_facts(
        self,
        *,
        event_text: str,
        facts: list[str],
        answers: dict[str, str],
        plain: str,
    ) -> set[str]:
        joined = " ".join([event_text, *facts, *answers.keys(), *answers.values()])
        known: set[str] = set()
        if any(term in plain for term in ("noter satis", "satis sozles")):
            known.add("Noter satış sözleşmesi")
        if any(term in plain for term in ("plaka", "sasi", "marka", "model")):
            known.add("Araç kimliği")
        if re.search(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b", joined):
            known.add("Satış tarihi")
            known.add("Arızanın ortaya çıkış zamanı")
        if re.search(r"(₺|tl|\b\d{4,}\b)", joined, re.IGNORECASE):
            known.add("Satış bedeli")
        if any(term in plain for term in ("motor ariz", "gizli ayip", "agir hasar", "tramer")):
            known.add("Arıza/ayıp türü")
        if any(term in plain for term in ("gizli ayip", "olagan muayene", "anlasilamaz")):
            known.add("Gizli ayıp niteliği")
        if any(term in plain for term in ("sorunsuz", "kazasiz", "hasarsiz", "ilan", "mesaj")):
            known.add("Satıcı beyanı")
        if any(term in plain for term in ("servis raporu", "ekspertiz raporu", "teknik tespit")):
            known.add("Teknik tespit")
        if any(term in plain for term in ("whatsapp", "sms", "ihtar", "bildirim", "ihbar")):
            known.add("Bildirim yöntemi")
        if any(term in plain for term in ("galeri", "sirket", "tacir", "gercek kisi")):
            known.add("Satıcı sıfatı")
        if any(term in plain for term in ("bedel iadesi", "sozlesmeden donme")):
            known.add("Asli talep")
        if "bedel indirimi" in plain:
            known.add("Terditli talep")
        if any(term in plain for term in ("masraf", "onarim gideri", "ekspertiz masrafi", "fatura", "makbuz")):
            known.add("Talep edilen zarar kalemleri")
            if any(term in plain for term in ("fatura", "makbuz")):
                known.add("Fatura/makbuz")
        if any(term in plain for term in ("tramer", "agir hasar")):
            known.add("TRAMER kaydı")
        if any(term in plain for term in ("davaci", "davali", "muvekkil", "satici", "alici")) or any("parties:" in self._plain(item) for item in facts):
            known.add("Taraflar")
        return known

    @staticmethod
    def _seller_professional(answers: dict[str, str], plain: str) -> bool:
        answer_text = " ".join(answers.values()).casefold()
        return any(term in answer_text for term in ("galeri", "şirket", "sirket", "tacir")) or any(
            term in plain for term in ("galeri", "şirket", "sirket", "tacir")
        )

    @staticmethod
    def _take_known(known: set[str], expected: list[str]) -> list[str]:
        return [item for item in expected if item in known]

    @staticmethod
    def _missing(known: set[str], expected: list[str]) -> list[str]:
        return [item for item in expected if item not in known]

    def _generic_queries(self, event_text: str) -> list[str]:
        words = re.findall(r"[a-zçğıöşü]{4,}", self._plain(event_text))
        selected = self._clean_list(words)[:5]
        return [" ".join(selected)] if selected else []

    @staticmethod
    def _is_vehicle_case(plain: str) -> bool:
        return any(
            term in plain
            for term in (
                "ayip",
                "arac",
                "ikinci el",
                "plaka",
                "sasi",
                "motor ariz",
                "gizli ayip",
                "tramer",
                "ekspertiz",
                "noter satis",
                "ayipli mal",
                "volkswagen",
                "satis bedeli",
            )
        )

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

    @staticmethod
    def _clean_list(values: list[str]) -> list[str]:
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
