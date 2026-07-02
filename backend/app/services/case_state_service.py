"""Central case_state builder used across local drafting flows."""

from __future__ import annotations

from app.services.dynamic_legal_reasoner_service import dynamic_legal_reasoner_service


class CaseStateService:
    def build(
        self,
        *,
        event_text: str,
        area: str = "",
        case_type: str = "",
        document_facts: list[str] | None = None,
        question_answers: dict[str, str] | None = None,
        legal_sources: list[str] | None = None,
        precedent_candidates: list[dict] | None = None,
        drafting_package: dict | None = None,
    ) -> dict:
        document_facts = self._dedupe(document_facts or [])
        question_answers = {
            " ".join(str(key).split()): " ".join(str(value).split())
            for key, value in (question_answers or {}).items()
            if str(key).strip() and str(value).strip()
        }
        reasoning = dynamic_legal_reasoner_service.analyze(
            event_text=event_text,
            document_facts=document_facts,
            question_answers=question_answers,
        )
        evidence_items = self._dedupe([*document_facts, *reasoning.get("evidence_plan", [])])
        risk_items = self._dedupe(reasoning.get("risk_plan", []))
        legal_issue_items = self._dedupe(reasoning.get("legal_issues", []))
        return {
            "event_text": " ".join(str(event_text or "").split()),
            "area": " ".join(str(area or "").split()),
            "case_type": " ".join(str(case_type or "").split()),
            "legal_issues": legal_issue_items,
            "documents": [],
            "document_facts": document_facts,
            "question_answers": [
                {"question": question, "answer": answer}
                for question, answer in question_answers.items()
            ],
            "evidence_items": evidence_items,
            "risk_items": risk_items,
            "legal_sources": self._dedupe(legal_sources or []),
            "precedent_candidates": list(precedent_candidates or []),
            "drafting_package": drafting_package or {},
        }

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


case_state_service = CaseStateService()
