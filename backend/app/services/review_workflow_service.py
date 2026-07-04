"""P0.2 — Backend review workflow orchestrator.

Orchestrates the full review pipeline in a single backend call
instead of 8 sequential frontend API calls.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from app.models.ai_models import (
    WorkflowReviewRequest,
    WorkflowReviewResponse,
    WorkflowReviewSummary,
    WorkflowStepResult,
)
from app.services.case_analyzer import case_analyzer
from app.services.case_enrichment_agent import case_enrichment_agent
from app.services.case_session_service import case_session_service
from app.services.case_state_service import case_state_service
from app.services.dynamic_legal_reasoner_service import dynamic_legal_reasoner_service
from app.services.legal_brain_service import legal_brain_service
from app.services import legal_ground_validator_service
from app.services.legal_issue_graph_service import legal_issue_graph_service
from app.services.legal_question_agent import legal_question_agent
from app.services.precedent_quality_agent import precedent_quality_agent
from app.services.research_service import research_service
from app.services.search_quality_agent import search_quality_agent
from app.services.source_relevance_agent import source_relevance_agent
from app.services.petition_profile_service import get_petition_profile

WORKFLOW_VERSION = "p0.4.1"


class ReviewWorkflowService:

    async def execute(self, request: WorkflowReviewRequest) -> WorkflowReviewResponse:
        case_id = request.case_id
        profile = get_petition_profile(request.case_text)
        fingerprint = self._fingerprint(request, profile_id=profile.key)
        now = self._now()
        workflow_id = f"wf_{case_id}_{request.request_id}"

        cached = self._check_cache(case_id, request.request_id, fingerprint)
        if cached:
            return cached

        self._mark_running(case_id, request.request_id, fingerprint, now)

        steps: list[WorkflowStepResult] = []
        warnings: list[str] = []
        step_results: dict[str, Any] = {}

        # ── A. Case analysis (CRITICAL) ──
        result = self._run_step("analyze", steps, lambda: self._run_analyze(case_id, request.case_text))
        if result is None:
            response = self._build_response(case_id, request.request_id, workflow_id, "failed", steps, warnings, {}, {}, {})
            self._cache_result(case_id, request.request_id, fingerprint, response, now)
            return response
        analysis, dynamic_reasoning = result
        step_results["analysis"] = analysis
        step_results["dynamic_reasoning"] = dynamic_reasoning
        warnings.extend(analysis.get("warnings", []))

        # ── B. AI enrichment (CRITICAL) ──
        result = self._run_step("enrich", steps, lambda: self._run_enrich(case_id, request))
        if result is None:
            response = self._build_response(case_id, request.request_id, workflow_id, "failed", steps, warnings, analysis, {}, {})
            self._cache_result(case_id, request.request_id, fingerprint, response, now)
            return response
        enrichment = result
        step_results["enrichment"] = enrichment
        warnings.extend(enrichment.get("warnings", []))

        # ── C. Legal Issue Graph (IMPORTANT) ──
        issue_graph: dict[str, Any] = {}
        try:
            stored = case_session_service.get_case_state(case_id)
            previous = dict(stored.get("case_state") or {})
            canonical_state = case_state_service.build(
                case_id=case_id,
                event_text=request.case_text,
                area=str(enrichment.get("detected_practice_area") or analysis.get("legal_topic") or ""),
                case_type=profile.key,
                document_facts=list(stored.get("document_facts") or []),
                question_answers=dict(stored.get("question_answers") or {}),
                legal_sources=list(dynamic_reasoning.get("research_queries") or []),
                precedent_candidates=list(stored.get("final_precedents") or []),
                drafting_package=dict(stored.get("drafting_package") or {}),
                analysis_context={
                    "documents": list(stored.get("documents") or []),
                    "warnings": [
                        *list(previous.get("warnings") or []),
                        *list(enrichment.get("warnings") or []),
                    ],
                },
            )
            issue_graph = dict(canonical_state["legal_issue_graph"])
            case_session_service.update_case_state(case_id, canonical_state)
            steps.append(WorkflowStepResult(
                name="issue_graph", status="completed",
                started_at=now, completed_at=now,
            ))
        except Exception:
            warnings.append("Legal Issue Graph oluşturulamadı; strateji ve risk analizi sınırlı olabilir.")
            steps.append(WorkflowStepResult(
                name="issue_graph", status="fallback",
                started_at=now, completed_at=now, fallback_used=True,
                safe_error_message="graph_build_failed",
            ))
        step_results["issue_graph"] = issue_graph

        # ── C2. Legal ground validation ──
        legal_ground_validation: dict[str, Any] = {}
        validation_context = self._validation_context(
            request,
            issue_graph=issue_graph,
            enrichment=enrichment,
            profile_id=profile.key,
        )
        all_raw_grounds = validation_context["raw_citations"]
        fingerprint = self._fingerprint(
            request,
            graph_source_fingerprint=validation_context["graph_source_fingerprint"],
            normalized_citations=validation_context["normalized_citations"],
            profile_id=profile.key,
        )
        if all_raw_grounds:
            try:
                validation_response = legal_ground_validator_service.legal_ground_validator.validate_response(
                    case_id=case_id,
                    raw_grounds=all_raw_grounds,
                    case_type=profile.key,
                    event_date=request.event_date,
                )
                legal_ground_validation = validation_response.model_dump(mode="json")
                case_session_service.update_case(case_id, legal_ground_validation=legal_ground_validation)
                steps.append(WorkflowStepResult(name="legal_grounds", status="completed", started_at=now, completed_at=now))
                warnings.extend(legal_ground_validation.get("warnings", []))
            except Exception:
                steps.append(WorkflowStepResult(
                    name="legal_grounds", status="fallback", started_at=now, completed_at=now, fallback_used=True,
                    safe_error_message="legal_ground_validation_failed",
                ))
        else:
            steps.append(WorkflowStepResult(
                name="legal_grounds", status="skipped", started_at=now, completed_at=now,
                safe_error_message="no_grounds_to_validate",
            ))
        step_results["legal_ground_validation"] = legal_ground_validation

        # ── D. Questions + Searches ──
        questions: dict[str, Any] = {}
        try:
            enrichment_for_questions = {k: v for k, v in enrichment.items() if k != "warnings"}
            q_response = legal_question_agent.generate(
                case_text=request.case_text,
                case_enrichment=enrichment_for_questions,
                use_gemini=request.use_ai,
            )
            questions = q_response.model_dump(mode="json")
            questions["canonical_questions"] = list(issue_graph.get("next_best_questions") or [])
            case_session_service.update_case(case_id, generated_questions=questions)
            steps.append(WorkflowStepResult(name="questions", status="completed", started_at=now, completed_at=now))
            warnings.extend(questions.get("warnings", []))
        except Exception:
            questions = {
                "canonical_questions": list(issue_graph.get("next_best_questions") or []),
            }
            steps.append(WorkflowStepResult(
                name="questions", status="fallback", started_at=now, completed_at=now, fallback_used=True,
                safe_error_message="question_generation_failed",
            ))
        step_results["questions"] = questions

        better_searches: dict[str, Any] = {}
        try:
            enrichment_for_search = {k: v for k, v in enrichment.items() if k != "warnings"}
            s_response = search_quality_agent.build(
                case_text=request.case_text,
                case_enrichment=enrichment_for_search,
                use_gemini=request.use_ai,
            )
            better_searches = s_response.model_dump(mode="json")
            canonical_queries = list(issue_graph.get("research_plan") or [])
            better_searches["canonical_research_plan"] = canonical_queries
            better_searches["yargitay_queries"] = self._dedupe_strings([
                *canonical_queries,
                *list(better_searches.get("yargitay_queries") or []),
            ])
            if not better_searches.get("legal_brain_query") and canonical_queries:
                better_searches["legal_brain_query"] = " ".join(canonical_queries[:3])
            case_session_service.update_case(case_id, better_searches=better_searches)
            steps.append(WorkflowStepResult(name="searches", status="completed", started_at=now, completed_at=now))
        except Exception:
            better_searches = {
                "canonical_research_plan": list(issue_graph.get("research_plan") or []),
                "yargitay_queries": list(issue_graph.get("research_plan") or []),
            }
            steps.append(WorkflowStepResult(
                name="searches", status="fallback", started_at=now, completed_at=now, fallback_used=True,
                safe_error_message="search_build_failed",
            ))
        step_results["better_searches"] = better_searches

        # ── E. Legal Brain (OPTIONAL) ──
        brain_results: list[dict[str, Any]] = []
        if request.use_legal_brain:
            result = self._run_step("legal_brain", steps, lambda: self._run_brain(case_id, request, better_searches, enrichment))
            if result is not None:
                brain_results, source_audit = result
                step_results["legal_brain_results"] = brain_results
                step_results["source_audit"] = source_audit

        if not brain_results:
            step_results["legal_brain_results"] = []
            step_results["source_audit"] = {}
            if request.use_legal_brain:
                steps.append(WorkflowStepResult(
                    name="legal_brain", status="skipped", started_at=now, completed_at=now,
                    safe_error_message="brain_search_returned_empty",
                ))

        # ── G. Yargıtay (CRITICAL) ──
        yargitay_used_fallback = False
        result = await self._run_step_async("yargitay", steps, self._run_yargitay(case_id, request, better_searches, enrichment))
        if result is None:
            warnings.append("Yargıtay araştırması başarısız; emsal havuzu boş.")
            yargitay_used_fallback = True
            step_results["yargitay_results"] = {}
        else:
            yargitay_results = result
            step_results["yargitay_results"] = yargitay_results
            yargitay_used_fallback = yargitay_results.get("source_summary", {}).get("used_fallback", False)
            warnings.extend(yargitay_results.get("errors", []))

        # ── H. Canonical precedent ingestion (P0.5) ──
        live_decisions = step_results.get("yargitay_results", {}).get("live_yargitay_results", [])
        brain_decisions = brain_results or []
        try:
            from app.services.precedent_authority_service import precedent_authority_service
            stored_authority = case_session_service.get_case_state(case_id).get("precedent_authority")
            authority = precedent_authority_service.build_authority(
                case_id=case_id,
                live_results=live_decisions,
                brain_results=brain_decisions,
                existing=stored_authority,
            )
            case_session_service.update_case(case_id, precedent_authority=authority.model_dump(mode="json"))
            step_results["precedent_authority"] = authority.model_dump(mode="json")
            steps.append(WorkflowStepResult(name="precedent_authority", status="completed", started_at=now, completed_at=now))
        except Exception:
            steps.append(WorkflowStepResult(
                name="precedent_authority", status="fallback", started_at=now, completed_at=now, fallback_used=True,
                safe_error_message="precedent_authority_failed",
            ))
            step_results["precedent_authority"] = {}

        # ── I. Precedent audit (IMPORTANT) ──
        final_precedents = step_results.get("yargitay_results", {}).get("final_precedents", [])
        if final_precedents:
            result = self._run_step("precedent_audit", steps, lambda: self._run_audit_precedents(case_id, request, enrichment, final_precedents))
            if result is not None:
                step_results["precedent_audit"] = result
            else:
                step_results["precedent_audit"] = {}
        else:
            steps.append(WorkflowStepResult(
                name="precedent_audit", status="skipped", started_at=now, completed_at=now,
                safe_error_message="no_precedents_to_audit",
            ))
            step_results["precedent_audit"] = {}

        # ── Determine overall status ──
        if yargitay_used_fallback:
            overall_status = "partial_success"
        else:
            overall_status = "completed"

        # ── Build summary ──
        summary = WorkflowReviewSummary(
            case_type=enrichment.get("detected_case_type", ""),
            practice_area=enrichment.get("detected_practice_area", ""),
            source_count=len(brain_results),
            precedent_count=len(final_precedents),
            live_precedent_count=step_results.get("yargitay_results", {}).get("final_live_result_count", 0),
            risk_count=len(issue_graph.get("global_risks", [])),
            question_count=len(issue_graph.get("next_best_questions", [])),
        )

        response = WorkflowReviewResponse(
            case_id=case_id,
            request_id=request.request_id,
            workflow_id=workflow_id,
            status=overall_status,
            cached=False,
            steps=steps,
            warnings=warnings,
            summary=summary,
            analysis=analysis,
            enrichment=enrichment,
            issue_graph=issue_graph,
            legal_ground_validation=legal_ground_validation,
            questions=questions,
            better_searches=better_searches,
            legal_brain_results=brain_results,
            source_audit=step_results.get("source_audit", {}),
            yargitay_results=step_results.get("yargitay_results", {}),
            precedent_audit=step_results.get("precedent_audit", {}),
            precedent_authority=step_results.get("precedent_authority", {}),
        )

        self._cache_result(case_id, request.request_id, fingerprint, response, now)
        return response

    # ── Step runners ──

    def _run_step(self, name: str, steps: list[WorkflowStepResult], fn):
        started = self._now()
        try:
            result = fn()
            steps.append(WorkflowStepResult(
                name=name, status="completed",
                started_at=started, completed_at=self._now(),
            ))
            return result
        except Exception:
            steps.append(WorkflowStepResult(
                name=name, status="failed",
                started_at=started, completed_at=self._now(),
                safe_error_message=f"{name}_failed",
            ))
            return None

    async def _run_step_async(self, name: str, steps: list[WorkflowStepResult], coro):
        started = self._now()
        try:
            result = await coro
            steps.append(WorkflowStepResult(
                name=name, status="completed",
                started_at=started, completed_at=self._now(),
            ))
            return result
        except Exception:
            steps.append(WorkflowStepResult(
                name=name, status="failed",
                started_at=started, completed_at=self._now(),
                safe_error_message=f"{name}_failed",
            ))
            return None

    def _run_analyze(self, case_id: str, case_text: str):
        analysis_result = case_analyzer.analyze(case_text)
        dynamic_reasoning = dynamic_legal_reasoner_service.analyze(
            event_text=case_text, document_facts=[], question_answers={}
        )
        analysis_dict = {
            "legal_topic": analysis_result.legal_topic,
            "legal_keywords": analysis_result.legal_keywords,
            "case_facts": analysis_result.case_facts,
        }
        reasoning_dict = dict(dynamic_reasoning)

        profile = get_petition_profile(case_text)
        case_state = case_state_service.build(
            event_text=case_text,
            question_answers={},
            document_facts=[],
            area=analysis_result.legal_topic,
            case_type=profile.key,
            legal_sources=list(reasoning_dict.get("research_queries", [])),
        )

        case_session_service.update_case_state(
            case_id,
            case_state,
            event_text=case_text,
            title=analysis_result.legal_topic or "Yeni dava",
            legal_topic=analysis_result.legal_topic,
            dynamic_reasoning=reasoning_dict,
        )
        return analysis_dict, reasoning_dict

    def _run_enrich(self, case_id: str, request: WorkflowReviewRequest):
        response = case_enrichment_agent.enrich(
            case_text=request.case_text,
            practice_area=request.practice_area,
            use_gemini=request.use_ai,
        )
        enrichment_dict = response.model_dump(mode="json")
        case_session_service.update_case(
            case_id,
            event_text=request.case_text,
            case_enrichment=enrichment_dict,
        )
        return enrichment_dict

    def _run_brain(self, case_id: str, request: WorkflowReviewRequest, better_searches: dict, enrichment: dict):
        brain_query = (
            better_searches.get("legal_brain_query")
            or enrichment.get("legal_brain_query")
            or f"{request.case_text} {request.practice_area}"
        )
        practice_area = enrichment.get("detected_practice_area") or request.practice_area or "Genel hukuk"

        brain_response = legal_brain_service.search(
            query=brain_query,
            practice_area=practice_area,
            max_results=request.max_yargitay_results,
        )
        brain_results = [item.model_dump(mode="json") for item in brain_response.results]
        case_session_service.update_case(case_id, legal_brain_results=brain_results)

        source_audit_dict: dict[str, Any] = {}
        if brain_results:
            try:
                enrichment_for_audit = {k: v for k, v in enrichment.items() if k != "warnings"}
                audit_response = source_relevance_agent.audit(
                    case_enrichment=enrichment_for_audit,
                    sources=brain_results,
                    use_gemini=request.use_ai,
                )
                source_audit_dict = audit_response.model_dump(mode="json")
                case_session_service.update_case(case_id, source_audit=source_audit_dict)
            except Exception:
                source_audit_dict = {}

        return brain_results, source_audit_dict

    async def _run_yargitay(self, case_id: str, request: WorkflowReviewRequest, better_searches: dict, enrichment: dict):
        yargitay_queries = (
            better_searches.get("yargitay_queries")
            or enrichment.get("yargitay_query_templates")
            or []
        )
        enrichment_for_yargitay = {k: v for k, v in enrichment.items() if k != "warnings"}

        yargitay_response = await research_service.research_yargitay(
            case_text=request.case_text,
            max_results=request.max_yargitay_results,
            yargitay_query_templates=yargitay_queries,
            case_enrichment=enrichment_for_yargitay,
        )
        yargitay_dict = dict(yargitay_response)

        case_session_service.update_case(
            case_id,
            live_yargitay_results=yargitay_dict.get("live_yargitay_results", []),
            fallback_precedents=yargitay_dict.get("fallback_precedents", []),
            final_precedents=yargitay_dict.get("final_precedents", []),
        )
        return yargitay_dict

    def _run_audit_precedents(self, case_id: str, request: WorkflowReviewRequest, enrichment: dict, final_precedents: list):
        enrichment_for_audit = {k: v for k, v in enrichment.items() if k != "warnings"}
        audit_response = precedent_quality_agent.audit(
            case_text=request.case_text,
            case_enrichment=enrichment_for_audit,
            precedents=final_precedents,
            use_gemini=request.use_ai,
        )
        audit_dict = audit_response.model_dump(mode="json")
        case_session_service.update_case(case_id, precedent_audit=audit_dict)
        return audit_dict

    @staticmethod
    def _dedupe_strings(values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            clean = " ".join(str(value or "").split())
            key = clean.casefold()
            if clean and key not in seen:
                seen.add(key)
                result.append(clean)
        return result

    # ── Cache / Idempotency ──

    @classmethod
    def _fingerprint(
        cls,
        request: WorkflowReviewRequest,
        *,
        graph_source_fingerprint: str = "",
        normalized_citations: list[str] | None = None,
        profile_id: str = "",
    ) -> str:
        if not graph_source_fingerprint or normalized_citations is None or not profile_id:
            context = cls._validation_context(request, profile_id=profile_id)
            graph_source_fingerprint = graph_source_fingerprint or context["graph_source_fingerprint"]
            normalized_citations = normalized_citations if normalized_citations is not None else context["normalized_citations"]
            profile_id = profile_id or context["profile_id"]
        components = [
            WORKFLOW_VERSION,
            legal_ground_validator_service.REGISTRY_VERSION,
            request.case_id,
            request.case_text,
            request.event_date,
            profile_id,
            graph_source_fingerprint,
            "|".join(normalized_citations or []),
            request.practice_area,
            str(request.max_yargitay_results),
            str(request.use_ai),
            str(request.use_legal_brain),
        ]
        joined = "|".join(components)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _validation_context(
        request: WorkflowReviewRequest,
        *,
        issue_graph: dict[str, Any] | None = None,
        enrichment: dict[str, Any] | None = None,
        profile_id: str = "",
    ) -> dict[str, Any]:
        profile = get_petition_profile(request.case_text)
        resolved_profile_id = profile_id or profile.key
        try:
            stored = case_session_service.get_case_state(request.case_id)
        except KeyError:
            stored = {}
        same_event = str(stored.get("event_text") or "").strip() == request.case_text.strip()
        stored_graph = dict(stored.get("legal_issue_graph") or {}) if same_event else {}
        graph = dict(issue_graph or stored_graph)
        if not graph:
            preview = legal_issue_graph_service.build({
                "case_id": request.case_id,
                "event_text": request.case_text,
                "area": request.practice_area,
                "case_type": resolved_profile_id,
                "document_facts": list(stored.get("document_facts") or []),
                "question_answers": dict(stored.get("question_answers") or {}),
            })
            graph = preview.model_dump(mode="json")

        stored_enrichment = dict(stored.get("case_enrichment") or {}) if same_event else {}
        effective_enrichment = dict(enrichment or stored_enrichment)
        analysis = case_analyzer.analyze(request.case_text)
        graph_citations = [
            str(citation)
            for issue in graph.get("issues", [])
            if isinstance(issue, dict)
            for citation in issue.get("legal_basis", [])
        ]
        raw_citations = ReviewWorkflowService._dedupe_strings([
            *list(profile.legal_basis),
            *list(analysis.legal_keywords),
            *list(effective_enrichment.get("relevant_articles") or []),
            *graph_citations,
        ])
        normalized = legal_ground_validator_service.legal_ground_validator.normalized_citations(raw_citations)
        return {
            "profile_id": resolved_profile_id,
            "graph_source_fingerprint": str(graph.get("source_fingerprint") or ""),
            "raw_citations": raw_citations,
            "normalized_citations": normalized,
        }

    def _check_cache(self, case_id: str, request_id: str, fingerprint: str) -> WorkflowReviewResponse | None:
        runs = case_session_service._state.get("cases", {}).get(case_id, {}).get("workflow_runs", {})
        if not isinstance(runs, dict):
            return None
        existing = runs.get(request_id)
        if not isinstance(existing, dict):
            return None
        if existing.get("fingerprint") != fingerprint:
            return None
        if existing.get("status") == "completed":
            cached_response = existing.get("response")
            if isinstance(cached_response, dict):
                result = WorkflowReviewResponse(**cached_response)
                result.cached = True
                return result
        return None

    def _mark_running(self, case_id: str, request_id: str, fingerprint: str, now: str) -> None:
        case = case_session_service._state.get("cases", {}).get(case_id)
        if case is None:
            case = case_session_service.get_case(case_id)
            case_session_service._state["cases"][case_id] = case
        runs = case_session_service._state["cases"][case_id].setdefault("workflow_runs", {})
        runs[request_id] = {
            "request_id": request_id,
            "fingerprint": fingerprint,
            "status": "running",
            "created_at": now,
            "updated_at": now,
        }
        case_session_service._persist()

    def _cache_result(self, case_id: str, request_id: str, fingerprint: str, response: WorkflowReviewResponse, now: str) -> None:
        case = case_session_service._state.get("cases", {}).get(case_id)
        if case is None:
            case = case_session_service.get_case(case_id)
            case_session_service._state["cases"][case_id] = case
        runs = case_session_service._state["cases"][case_id].setdefault("workflow_runs", {})
        runs[request_id] = {
            "request_id": request_id,
            "fingerprint": fingerprint,
            "status": response.status,
            "response": response.model_dump(mode="json"),
            "created_at": runs.get(request_id, {}).get("created_at", now),
            "updated_at": now,
        }
        case_session_service._persist()

    @staticmethod
    def _build_response(
        case_id: str, request_id: str, workflow_id: str, status: str,
        steps: list[WorkflowStepResult], warnings: list[str],
        analysis: dict, enrichment: dict, issue_graph: dict,
    ) -> WorkflowReviewResponse:
        return WorkflowReviewResponse(
            case_id=case_id,
            request_id=request_id,
            workflow_id=workflow_id,
            status=status,
            steps=steps,
            warnings=warnings,
            summary=WorkflowReviewSummary(),
            analysis=analysis,
            enrichment=enrichment,
            issue_graph=issue_graph,
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()


review_workflow_service = ReviewWorkflowService()
