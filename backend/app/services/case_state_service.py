"""Central case_state builder used across local drafting flows."""

from __future__ import annotations

import hashlib
from typing import Any

from app.services.dynamic_legal_reasoner_service import dynamic_legal_reasoner_service
from app.services.legal_issue_graph_service import legal_issue_graph_service


class CaseStateService:
    def build(
        self,
        *,
        case_id: str | None = None,
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
        resolved_case_id = case_id or self._case_id(clean_event_text, document_facts, answers)
        graph = legal_issue_graph_service.build({
            "case_id": resolved_case_id,
            "event_text": clean_event_text,
            "area": " ".join(str(area or context.get("area") or "").split()),
            "case_type": " ".join(str(case_type or context.get("case_type") or "").split()),
            "document_facts": document_facts,
            "question_answers": answers,
            "documents": list(context.get("documents", [])),
        })
        graph_dict = graph.model_dump(mode="json")
        graph_views = legal_issue_graph_service.project(graph)
        graph_legal_sources = self._clean_list([
            basis
            for issue in graph.issues
            for basis in issue.legal_basis
        ])
        return {
            "case_id": resolved_case_id,
            "canonical_model": "legal_issue_graph",
            "graph_source_fingerprint": graph.source_fingerprint,
            "legal_issue_graph": graph_dict,
            "event_text": clean_event_text,
            "area": graph.legal_area,
            "case_type": graph.case_type,
            "legal_area_candidates": self._clean_list(reasoning.get("legal_area_candidates", [])),
            "case_type_candidates": self._clean_list(reasoning.get("case_type_candidates", [])),
            "legal_issues": graph_views["legal_issues"],
            "documents": list(context.get("documents", [])),
            "document_facts": document_facts,
            "question_answers": [
                {"question": question, "answer": answer}
                for question, answer in answers.items()
            ],
            "evidence_items": graph_views["evidence_items"],
            "risk_items": graph_views["risk_items"],
            "legal_sources": self._clean_list([*(legal_sources or []), *graph_legal_sources]),
            "precedent_candidates": precedent_candidates,
            "usable_precedents": usable_precedents,
            "research_queries": graph_views["research_queries"],
            "question_plan": graph_views["question_plan"],
            "evidence_plan": graph_views["evidence_plan"],
            "risk_plan": graph_views["risk_plan"],
            "drafting_plan": graph_views["drafting_plan"],
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
