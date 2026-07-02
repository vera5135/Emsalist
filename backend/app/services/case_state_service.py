"""Central case_state builder used across local drafting flows."""

from __future__ import annotations

import hashlib
from typing import Any

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
        precedent_candidates: list[dict[str, Any]] | None = None,
        drafting_package: dict[str, Any] | None = None,
        analysis_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_event_text = " ".join(str(event_text or "").split())
        document_facts = self._clean_list(document_facts or [])
        answers = {
            " ".join(str(key).split()): " ".join(str(value).split())
            for key, value in (question_answers or {}).items()
            if str(key).strip() and str(value).strip()
        }
        reasoning = dynamic_legal_reasoner_service.analyze(
            event_text=clean_event_text,
            document_facts=document_facts,
            question_answers=answers,
        )
        precedent_candidates = list(precedent_candidates or [])
        usable_precedents = [
            item for item in precedent_candidates
            if item.get("use_in_petition", True) is not False and not item.get("excluded_reason")
        ]
        context = analysis_context or {}
        warnings = self._clean_list(
            [
                *list(reasoning.get("warnings", [])),
                *list(context.get("warnings", [])),
            ]
        )
        return {
            "case_id": self._case_id(clean_event_text, document_facts, answers),
            "event_text": clean_event_text,
            "area": " ".join(str(area or context.get("area") or "").split()),
            "case_type": " ".join(str(case_type or context.get("case_type") or "").split()),
            "legal_area_candidates": self._clean_list(reasoning.get("legal_area_candidates", [])),
            "case_type_candidates": self._clean_list(reasoning.get("case_type_candidates", [])),
            "legal_issues": list(reasoning.get("legal_issues", [])),
            "documents": list(context.get("documents", [])),
            "document_facts": document_facts,
            "question_answers": [
                {"question": question, "answer": answer}
                for question, answer in answers.items()
            ],
            "evidence_items": self._clean_list([item.get("title", "") for item in reasoning.get("evidence_plan", [])]),
            "risk_items": self._clean_list([item.get("title", "") for item in reasoning.get("risk_plan", [])]),
            "legal_sources": self._clean_list(legal_sources or []),
            "precedent_candidates": precedent_candidates,
            "usable_precedents": usable_precedents,
            "research_queries": self._clean_list(reasoning.get("research_queries", [])),
            "question_plan": list(reasoning.get("question_plan", [])),
            "evidence_plan": list(reasoning.get("evidence_plan", [])),
            "risk_plan": list(reasoning.get("risk_plan", [])),
            "drafting_package": drafting_package or {},
            "warnings": warnings,
            "reasoner_output": reasoning,
            "precedent_query_context": dict(reasoning.get("precedent_query_context", {})),
        }

    @staticmethod
    def _case_id(event_text: str, document_facts: list[str], answers: dict[str, str]) -> str:
        payload = "|".join([event_text, *document_facts, *[f"{k}:{v}" for k, v in answers.items()]])
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]

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


case_state_service = CaseStateService()
