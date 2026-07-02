"""Legal Issue Graph v1 — builds a structured hukuki analiz zinciri for a case.

For each active case, the graph produces:
  hukuki mesele → required facts → confirmed facts → missing facts →
  available evidence → missing evidence → risk → client questions →
  research queries → petition argument

This is a v1 skeleton. It is optimised for defective vehicle / hidden defect
cases and does NOT replace the existing dynamic_legal_reasoner_service.
"""

from __future__ import annotations

import re
from typing import Any

from app.models.legal_issue_graph_models import (
    DraftingPlanItem,
    LegalIssue,
    LegalIssueGraph,
)

# ── helpers ──────────────────────────────────────────────────────────────

_ASCII = str.maketrans(
    {
        "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g",
        "ı": "i", "I": "i", "İ": "i",
        "ö": "o", "Ö": "o", "ş": "s", "Ş": "s",
        "ü": "u", "Ü": "u",
    }
)


def _plain(text: str) -> str:
    return text.translate(_ASCII).casefold().strip()


def _fact_map(document_facts: list[str]) -> dict[str, str]:
    """Convert ['key: value', …] into a dict."""
    result: dict[str, str] = {}
    for line in document_facts:
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip()
    return result


def _answer_map(question_answers: dict[str, str]) -> dict[str, str]:
    """Normalise question-answer keys to plain text."""
    return {_plain(k): v for k, v in (question_answers or {}).items()}


def _has_answer(answers: dict[str, str], *terms: str) -> bool:
    """Check if any answer contains one of the given terms."""
    for value in answers.values():
        pv = _plain(value)
        if any(t in pv for t in terms):
            return True
    return False


def _answer_value(answers: dict[str, str], *question_terms: str) -> str:
    """Return the first answer whose question contains one of the terms."""
    for q, v in answers.items():
        if any(t in q for t in question_terms):
            return v
    return ""


# ── issue definitions ────────────────────────────────────────────────────

_ISSUE_DEFS: list[dict[str, Any]] = [
    {
        "issue_id": "sale_relationship",
        "title": "Satış ilişkisi ve taraflar",
        "issue_type": "factual",
        "legal_basis": ["TBK m. 207", "TBK m. 209"],
        "required_facts": [
            "satıcı",
            "alıcı",
            "satış tarihi",
            "satış bedeli",
            "araç marka/model",
            "plaka",
            "şasi",
            "noter satış sözleşmesi",
        ],
        "evidence_labels": ["noter satış sözleşmesi", "ruhsat", "ödeme dekontu"],
        "fact_keys": ["parties", "sale_date", "sale_price", "vehicle_make_model", "vehicle_plate", "vehicle_vin", "notary_info"],
        "drafting_priority": 1,
    },
    {
        "issue_id": "defect_existence",
        "title": "Ayıbın varlığı",
        "issue_type": "factual",
        "legal_basis": ["TBK m. 219", "TBK m. 223"],
        "required_facts": [
            "arıza türü",
            "arıza tarihi",
            "arızadan teslimden ne kadar sonra çıktığı",
            "servis/ekspertiz tespiti",
        ],
        "evidence_labels": ["servis raporu", "ekspertiz raporu", "bilirkişi", "fotoğraf/video"],
        "fact_keys": ["technical_findings", "report_date", "report_number"],
        "drafting_priority": 2,
    },
    {
        "issue_id": "hidden_defect",
        "title": "Ayıbın gizli niteliği",
        "issue_type": "legal_analysis",
        "legal_basis": ["TBK m. 219/2", "TBK m. 223/2"],
        "required_facts": [
            "ayıp olağan kontrolde fark edilebilir miydi?",
            "teknik inceleme gerektiriyor mu?",
            "satış öncesi mevcut olma ihtimali var mı?",
        ],
        "evidence_labels": ["bilirkişi raporu", "servis teknik açıklaması", "ekspertiz"],
        "fact_keys": ["technical_findings"],
        "drafting_priority": 3,
    },
    {
        "issue_id": "seller_statements",
        "title": "Satıcının beyanları ve sorumluluk",
        "issue_type": "factual",
        "legal_basis": ["TBK m. 36", "TBK m. 219"],
        "required_facts": [
            "satıcının sorunsuz beyanı",
            "motor/mekanik problem yok beyanı",
            "günlük kullanıma uygun beyanı",
            "varsa ilan/yazışma",
        ],
        "evidence_labels": ["ilan metni", "WhatsApp mesajları", "tanık"],
        "fact_keys": [],
        "drafting_priority": 4,
    },
    {
        "issue_id": "defect_notice",
        "title": "Ayıp ihbarı",
        "issue_type": "procedural",
        "legal_basis": ["TBK m. 223"],
        "required_facts": [
            "ayıbın öğrenildiği tarih",
            "ihbar tarihi",
            "ihbar yöntemi",
            "ihbar içeriği",
        ],
        "evidence_labels": ["ihtarname", "WhatsApp/SMS", "e-posta", "arama kayıtları"],
        "fact_keys": ["notice_date"],
        "drafting_priority": 5,
    },
    {
        "issue_id": "elective_rights",
        "title": "Seçimlik hak ve talep",
        "issue_type": "legal_analysis",
        "legal_basis": ["TBK m. 227", "TBK m. 229"],
        "required_facts": [
            "sözleşmeden dönme talebi",
            "bedel indirimi talebi",
            "servis/ekspertiz/onarım zararları",
        ],
        "evidence_labels": ["ödeme belgesi", "servis faturası", "ekspertiz faturası", "ihtarname"],
        "fact_keys": ["claim_result", "payment_info"],
        "drafting_priority": 6,
    },
    {
        "issue_id": "court_jurisdiction",
        "title": "Görevli mahkeme / tüketici-ticari ayrımı",
        "issue_type": "procedural",
        "legal_basis": ["6502 sayılı TKHK m. 3", "6502 sayılı TKHK m. 73", "HMK m. 1"],
        "required_facts": [
            "satıcı gerçek kişi mi?",
            "satıcı galeri/tacir mi?",
            "alıcı tüketici mi?",
            "araç kişisel kullanım için mi alındı?",
        ],
        "evidence_labels": [],
        "fact_keys": [],
        "drafting_priority": 7,
    },
]

# ── vehicle research queries (no labour/family/rent/foreclosure) ─────────

_VEHICLE_RESEARCH_QUERIES = [
    "gizli ayıplı araç satış bedeli iadesi",
    "ikinci el araç gizli ayıp sözleşmeden dönme",
    "ayıplı araç bedel indirimi ekspertiz raporu",
    "araç gizli ayıp ayıp ihbarı süresi",
    "pert kayıtlı araç ayıp bedel indirimi",
    "ayıplı araç tüketici mahkemesi görev",
    "gizli ayıp ispat yükü bilirkişi",
    "ikinci el araç satışında ayıptan sorumluluk süresi",
]

_IRRELEVANT_TERMS = {
    "işçilik", "işçi", "kıdem", "ihbar tazminatı", "fazla mesai",
    "nafaka", "kira", "kiracı", "icra", "ödeme emri", "tahliye",
    "boşanma", "velayet", "kat mülkiyeti", "kamulaştırma",
}


def _is_vehicle_query_safe(query: str) -> bool:
    pq = _plain(query)
    return not any(t in pq for t in _IRRELEVANT_TERMS)


# ── service ──────────────────────────────────────────────────────────────


class LegalIssueGraphService:
    """Build a Legal Issue Graph for a given case_state."""

    def build(self, case_state: dict[str, Any]) -> LegalIssueGraph:
        case_id = str(case_state.get("case_id") or "")
        legal_area = str(case_state.get("area") or "")
        case_type = str(case_state.get("case_type") or "")
        document_facts: list[str] = list(case_state.get("document_facts") or [])
        question_answers: dict[str, str] = dict(case_state.get("question_answers") or {})
        event_text: str = str(case_state.get("event_text") or "")

        fm = _fact_map(document_facts)
        am = _answer_map(question_answers)
        plain_event = _plain(event_text)

        issues: list[LegalIssue] = []
        global_risks: list[str] = []
        all_missing_evidence: list[str] = []
        all_client_questions: list[str] = []
        all_research_queries: list[str] = []
        drafting_plan: list[DraftingPlanItem] = []

        for idx, issue_def in enumerate(_ISSUE_DEFS):
            issue = self._build_issue(
                issue_def=issue_def,
                fact_map=fm,
                answer_map=am,
                plain_event=plain_event,
                index=idx,
            )
            issues.append(issue)
            all_missing_evidence.extend(issue.missing_evidence)
            all_client_questions.extend(issue.client_questions)
            all_research_queries.extend(issue.research_queries)

            if issue.risk_level in ("high", "medium"):
                global_risks.append(f"[{issue.risk_level.upper()}] {issue.title}: {issue.risk_reason}")

            if issue.petition_argument:
                drafting_plan.append(
                    DraftingPlanItem(
                        section=issue.title,
                        use_facts=issue.confirmed_facts[:5],
                        argument=issue.petition_argument,
                    )
                )

        # ── next_best_questions (prioritised) ────────────────────────
        next_best_questions = self._prioritise_questions(issues, am)

        # ── research_plan (filtered, vehicle-safe) ───────────────────
        research_plan = [
            q for q in _VEHICLE_RESEARCH_QUERIES
            if _is_vehicle_query_safe(q)
        ]
        # Add issue-specific queries
        for issue in issues:
            for q in issue.research_queries:
                if _is_vehicle_query_safe(q) and q not in research_plan:
                    research_plan.append(q)

        # ── drafting_plan (final) ────────────────────────────────────
        if not drafting_plan:
            drafting_plan = self._default_drafting_plan(issues)

        return LegalIssueGraph(
            case_id=case_id,
            legal_area=legal_area,
            case_type=case_type,
            issues=issues,
            global_risks=global_risks,
            next_best_questions=next_best_questions,
            research_plan=research_plan,
            drafting_plan=drafting_plan,
        )

    # ── per-issue builder ────────────────────────────────────────────

    def _build_issue(
        self,
        *,
        issue_def: dict[str, Any],
        fact_map: dict[str, str],
        answer_map: dict[str, str],
        plain_event: str,
        index: int,
    ) -> LegalIssue:
        issue_id = issue_def["issue_id"]
        title = issue_def["title"]
        required_facts = list(issue_def["required_facts"])
        evidence_labels = list(issue_def.get("evidence_labels", []))
        fact_keys = list(issue_def.get("fact_keys", []))

        # ── confirmed_facts from document_facts ──────────────────────
        confirmed_facts: list[str] = []
        uncertain_facts: list[str] = []
        missing_facts: list[str] = []
        available_evidence: list[str] = []
        missing_evidence: list[str] = []

        for fk in fact_keys:
            if fk in fact_map:
                confirmed_facts.append(f"{fk}: {fact_map[fk]}")

        # Check required facts against document facts
        for rf in required_facts:
            rf_plain = _plain(rf)
            found = False
            for fk, fv in fact_map.items():
                if rf_plain in _plain(fk) or rf_plain in _plain(fv):
                    found = True
                    break
            if not found:
                # Check if it's in event text
                if rf_plain in plain_event:
                    uncertain_facts.append(f"{rf} (olay metninde geçiyor, belgeyle doğrulanmamış)")
                else:
                    missing_facts.append(rf)

        # Evidence mapping
        for el in evidence_labels:
            el_plain = _plain(el)
            found = False
            for fk, fv in fact_map.items():
                if el_plain in _plain(fk) or el_plain in _plain(fv):
                    found = True
                    break
            if el_plain in plain_event:
                uncertain_facts.append(f"{el} (olay metninde geçiyor, belgeyle doğrulanmamış)")
                found = True
            if found:
                available_evidence.append(el)
            else:
                missing_evidence.append(el)

        # ── risk assessment ──────────────────────────────────────────
        risk_level, risk_reason = self._assess_risk(
            issue_id=issue_id,
            fact_map=fact_map,
            answer_map=answer_map,
            missing_evidence=missing_evidence,
            missing_facts=missing_facts,
            plain_event=plain_event,
        )

        # ── client questions ─────────────────────────────────────────
        client_questions = self._client_questions(
            issue_id=issue_id,
            fact_map=fact_map,
            answer_map=answer_map,
            missing_facts=missing_facts,
            missing_evidence=missing_evidence,
        )

        # ── research queries ─────────────────────────────────────────
        research_queries = self._research_queries(
            issue_id=issue_id,
            fact_map=fact_map,
            missing_evidence=missing_evidence,
        )

        # ── petition argument ────────────────────────────────────────
        petition_argument = self._petition_argument(
            issue_id=issue_id,
            title=title,
            fact_map=fact_map,
            confirmed_facts=confirmed_facts,
            missing_evidence=missing_evidence,
        )

        return LegalIssue(
            issue_id=issue_id,
            title=title,
            issue_type=issue_def["issue_type"],
            legal_basis=list(issue_def["legal_basis"]),
            required_facts=required_facts,
            confirmed_facts=confirmed_facts,
            uncertain_facts=uncertain_facts,
            missing_facts=missing_facts,
            available_evidence=available_evidence,
            missing_evidence=missing_evidence,
            risk_level=risk_level,
            risk_reason=risk_reason,
            client_questions=client_questions,
            research_queries=research_queries,
            petition_argument=petition_argument,
            drafting_priority=issue_def["drafting_priority"],
        )

    # ── risk assessment ──────────────────────────────────────────────

    def _assess_risk(
        self,
        *,
        issue_id: str,
        fact_map: dict[str, str],
        answer_map: dict[str, str],
        missing_evidence: list[str],
        missing_facts: list[str],
        plain_event: str,
    ) -> tuple[str, str]:
        """Return (risk_level, risk_reason)."""

        # Issue-specific risk rules
        if issue_id == "defect_existence":
            if not fact_map.get("report_date") and not fact_map.get("report_number"):
                return (
                    "high",
                    "Servis/ekspertiz raporu tarihi/numarası yok. Ayıbın varlığını ispat güçleşir.",
                )
            if not fact_map.get("technical_findings"):
                return (
                    "medium",
                    "Teknik tespit belirtilmemiş. Bilirkişi incelemesi gerekebilir.",
                )
            return ("low", "Ayıbın varlığına dair yeterli teknik tespit mevcut.")

        if issue_id == "hidden_defect":
            if not fact_map.get("technical_findings"):
                return (
                    "high",
                    "Ayıbın satıştan önce mevcut olduğunu destekleyen teknik delil yok.",
                )
            return ("medium", "Teknik tespit var ancak gizli ayıp niteliği bilirkişiyle netleşmelidir.")

        if issue_id == "defect_notice":
            if not fact_map.get("notice_date") and not _has_answer(answer_map, "whatsapp", "sms", "ihtar", "bildirim"):
                return (
                    "high",
                    "Ayıp ihbar tarihi/yöntemi yok. TBK m. 223 yönünden hak kaybı riski.",
                )
            if not fact_map.get("notice_date"):
                return (
                    "medium",
                    "Ayıp ihbar tarihi belgesiz. İhbarın süresinde yapıldığı ispatlanmalıdır.",
                )
            return ("low", "Ayıp ihbarı belgelenmiş görünüyor.")

        if issue_id == "court_jurisdiction":
            if not _has_answer(answer_map, "galeri", "sirket", "tacir", "tuketici"):
                return (
                    "medium",
                    "Satıcının tacir/galeri olup olmadığı belirsiz. Görevli mahkeme net değil.",
                )
            return ("low", "Taraf sıfatı belirlenmiş.")

        if issue_id == "seller_statements":
            if not any(t in plain_event for t in ("sorunsuz", "kazasiz", "hasarsiz", "ilan")):
                return (
                    "medium",
                    "Satıcının satış öncesi beyanlarına dair somut delil yok.",
                )
            return ("low", "Satıcı beyanlarına dair bilgi mevcut.")

        if issue_id == "elective_rights":
            if not fact_map.get("claim_result") and not _has_answer(answer_map, "bedel iadesi", "sozlesmeden donme", "bedel indirimi"):
                return (
                    "medium",
                    "Talep sonucu netleştirilmemiş. Seçimlik hak kullanımı belirsiz.",
                )
            return ("low", "Talep stratejisi belirlenmiş.")

        if issue_id == "sale_relationship":
            missing_core = [rf for rf in ["satış tarihi", "satış bedeli", "plaka", "şasi"] if rf not in " ".join(fact_map.values())]
            if missing_core:
                return (
                    "medium",
                    f"Temel satış bilgileri eksik: {', '.join(missing_core)}.",
                )
            return ("low", "Satış ilişkisi temel bilgileri mevcut.")

        return ("low", "")

    # ── client questions ─────────────────────────────────────────────

    def _client_questions(
        self,
        *,
        issue_id: str,
        fact_map: dict[str, str],
        answer_map: dict[str, str],
        missing_facts: list[str],
        missing_evidence: list[str],
    ) -> list[str]:
        questions: list[str] = []

        if issue_id == "defect_notice":
            if not fact_map.get("notice_date"):
                questions.append("Ayıbı ne zaman öğrendiniz ve satıcıya ne zaman, nasıl bildirdiniz?")
            if "ihtarname" in missing_evidence:
                questions.append("Noter ihtarnamesi gönderildi mi? Varsa tarihi ve tebliğ bilgisi nedir?")

        if issue_id == "defect_existence":
            if not fact_map.get("report_date"):
                questions.append("Servis veya ekspertiz raporu var mı? Rapor tarihi ve numarası nedir?")
            if not fact_map.get("technical_findings"):
                questions.append("Arızanın ilk ortaya çıkış tarihi ve arızanın türü nedir?")

        if issue_id == "seller_statements":
            questions.append("Satıcının size aracın durumuyla ilgili yazılı/sözlü beyanı var mı? İlan metni veya mesaj kaydı mevcut mu?")

        if issue_id == "court_jurisdiction":
            if not _has_answer(answer_map, "galeri", "sirket", "tacir", "tuketici"):
                questions.append("Satıcı galeri, şirket, tacir mi yoksa gerçek kişi mi? Araç kişisel kullanım için mi alındı?")

        if issue_id == "elective_rights":
            if not _has_answer(answer_map, "bedel iadesi", "sozlesmeden donme", "bedel indirimi"):
                questions.append("Öncelikli talebiniz nedir: sözleşmeden dönme/bedel iadesi mi, yoksa bedel indirimi mi?")
            questions.append("Servis, ekspertiz, onarım gibi masraf kalemleriniz var mı? Toplam tutarı nedir?")

        if issue_id == "hidden_defect":
            if not fact_map.get("technical_findings"):
                questions.append("Servis/ekspertiz raporunda arızanın satış öncesi mevcut olduğuna dair tespit var mı?")

        return questions

    # ── research queries ─────────────────────────────────────────────

    def _research_queries(
        self,
        *,
        issue_id: str,
        fact_map: dict[str, str],
        missing_evidence: list[str],
    ) -> list[str]:
        queries: list[str] = []

        if issue_id == "defect_existence":
            queries.append("gizli ayıp ispatı servis raporu")
            queries.append("ayıplı araç bilirkişi delil değerlendirmesi")

        if issue_id == "hidden_defect":
            queries.append("gizli ayıp niteliği tespit kriterleri")
            queries.append("ikinci el araç satış öncesi mevcut ayıp ispatı")

        if issue_id == "defect_notice":
            queries.append("ayıp ihbarı süresi TBK 223")
            queries.append("ayıp ihbarı yöntemi geçerlilik")

        if issue_id == "court_jurisdiction":
            queries.append("ayıplı araç tüketici mahkemesi görev")
            queries.append("galeri satıcı tacir sıfatı tüketici mahkemesi")

        if issue_id == "elective_rights":
            queries.append("ayıplı araç sözleşmeden dönme şartları")
            queries.append("ayıplı araç bedel indirimi hesaplama")

        return queries

    # ── petition argument ────────────────────────────────────────────

    def _petition_argument(
        self,
        *,
        issue_id: str,
        title: str,
        fact_map: dict[str, str],
        confirmed_facts: list[str],
        missing_evidence: list[str],
    ) -> str:
        if issue_id == "sale_relationship":
            if fact_map.get("sale_date") and fact_map.get("sale_price"):
                return (
                    f"Noter satış sözleşmesiyle satış ilişkisi ve bedel sabittir. "
                    f"Satış tarihi {fact_map.get('sale_date', 'belirtilen tarih')}, "
                    f"bedel {fact_map.get('sale_price', 'belirtilen bedel')}'dir."
                )
            return "Noter satış sözleşmesiyle satış ilişkisi ve bedel sabittir."

        if issue_id == "defect_existence":
            if fact_map.get("technical_findings"):
                return (
                    f"Teknik tespitlere göre araçta {fact_map.get('technical_findings', 'arıza')} "
                    f"bulunduğu belirlenmiştir."
                )
            return (
                "Arızanın varlığı ve niteliği servis/ekspertiz raporu ve bilirkişi "
                "incelemesiyle ortaya konulacaktır."
            )

        if issue_id == "hidden_defect":
            return (
                "Arızanın teslimden kısa süre sonra ortaya çıkması ve teknik inceleme "
                "gerektirmesi gizli ayıp iddiasını destekler."
            )

        if issue_id == "seller_statements":
            return (
                "Satıcının satış öncesinde aracın sorunsuz/kazasız olduğu yönündeki "
                "beyanları, ayıptan sorumluluğunu artırmaktadır."
            )

        if issue_id == "defect_notice":
            if fact_map.get("notice_date"):
                return (
                    f"Ayıp, öğrenildiği tarihte ({fact_map.get('notice_date', 'belirtilen tarih')}) "
                    f"satıcıya bildirilmiştir."
                )
            return (
                "Ayıp ihbarının tarihi ve yöntemi sunulacak yazışma/ihtar kayıtları "
                "üzerinden belirlenecektir."
            )

        if issue_id == "elective_rights":
            return (
                "Öncelikle sözleşmeden dönülerek satış bedelinin iadesi, "
                "aksi halde ayıp oranında bedel indirimi ile kanıtlanan zararların "
                "tahsili talep edilmektedir."
            )

        if issue_id == "court_jurisdiction":
            return (
                "Satıcının sıfatına göre görevli mahkeme belirlenecektir. "
                "Tüketici işlemi niteliğinde ise Tüketici Mahkemesi görevlidir."
            )

        return ""

    # ── question prioritisation ──────────────────────────────────────

    def _prioritise_questions(
        self,
        issues: list[LegalIssue],
        answer_map: dict[str, str],
    ) -> list[str]:
        """Return prioritised next-best questions."""
        ordered: list[str] = []

        priority_map: dict[str, list[str]] = {
            "defect_notice": [
                "Ayıp ihbarı tarihi ve yöntemi nedir?",
                "Noter ihtarnamesi gönderildi mi? Tebliğ tarihi nedir?",
            ],
            "defect_existence": [
                "Servis/ekspertiz raporu tarihi ve içeriği nedir?",
                "Arızanın ilk ortaya çıkış tarihi nedir?",
            ],
            "seller_statements": [
                "Satıcının beyanlarının yazılı delili (ilan, mesaj) var mı?",
            ],
            "court_jurisdiction": [
                "Satıcının sıfatı (galeri/tacir/gerçek kişi) nedir?",
            ],
            "elective_rights": [
                "Talep tercihiniz nedir (sözleşmeden dönme/bedel indirimi)?",
                "Masraf kalemleriniz ve tutarları nedir?",
            ],
            "hidden_defect": [
                "Servis raporunda arızanın satış öncesi mevcut olduğuna dair tespit var mı?",
            ],
        }

        for issue in issues:
            if issue.risk_level in ("high", "medium"):
                for q in priority_map.get(issue.issue_id, []):
                    q_plain = _plain(q)
                    if not any(q_plain in _plain(a) for a in answer_map.values()):
                        ordered.append(q)

        return ordered[:10]

    # ── default drafting plan ────────────────────────────────────────

    @staticmethod
    def _default_drafting_plan(issues: list[LegalIssue]) -> list[DraftingPlanItem]:
        plan: list[DraftingPlanItem] = []
        for issue in issues:
            if issue.petition_argument:
                plan.append(
                    DraftingPlanItem(
                        section=issue.title,
                        use_facts=issue.confirmed_facts[:5],
                        argument=issue.petition_argument,
                    )
                )
        if not plan:
            plan.append(
                DraftingPlanItem(
                    section="Genel",
                    argument="Dosya kapsamındaki bilgi ve belgelere göre dava açılmıştır.",
                )
            )
        return plan


legal_issue_graph_service = LegalIssueGraphService()