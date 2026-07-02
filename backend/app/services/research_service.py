"""High-level research workflow that connects analysis, search and ranking."""

from __future__ import annotations

import re
import logging
from typing import Any

from pydantic import ValidationError

from app.models.case_models import SearchBuildRequest
from app.models.decision_models import DecisionInput
from app.models.yargitay_models import YargitayDecision
from app.services.case_analyzer import case_analyzer
from app.services.decision_ranker import decision_ranker
from app.services.legal_summary_service import legal_summary_service
from app.services.precedent_analysis_service import precedent_analysis_service
from app.services.search_builder import search_builder
from app.services.yargitay_search_service import build_vehicle_yargitay_queries, sanitize_yargitay_query
from app.services.yargitay_scraper import yargitay_scraper


RESEARCH_QUERY_LIMIT = 8
RESEARCH_MAX_RESULTS_CAP = 10
logger = logging.getLogger(__name__)

VEHICLE_YARGITAY_FALLBACK_QUERIES = (
    '"ayıplı araç" "gizli ayıp"',
    '"ikinci el araç" "gizli ayıp"',
    '"ayıplı araç" "sözleşmeden dönme"',
    '"araç satışı" "bedel indirimi"',
    '"ayıplı araç" "servis raporu"',
    '"gizli ayıp" "ayıp ihbarı"',
)
VEHICLE_YARGITAY_QUERY_PLAN = tuple(build_vehicle_yargitay_queries())

POVERTY_ALIMONY_PRIORITY_QUERIES = (
    '"yoksulluk nafakası" "nafakanın kaldırılması"',
    '"yoksulluk nafakası" "nafaka indirimi"',
    '"yoksulluk nafakası" "ekonomik durum"',
    '"yoksulluk nafakası" "emekli maaşı"',
    '"yoksulluk nafakası" "yeniden evlenme"',
)


class ResearchService:
    """Run the complete Yargıtay research pipeline for a case summary."""

    def __init__(
        self,
        *,
        analyzer=case_analyzer,
        query_builder=search_builder,
        scraper=yargitay_scraper,
        ranker=decision_ranker,
        summarizer=legal_summary_service,
        precedent_analyzer=precedent_analysis_service,
    ) -> None:
        self.analyzer = analyzer
        self.query_builder = query_builder
        self.scraper = scraper
        self.ranker = ranker
        self.summarizer = summarizer
        self.precedent_analyzer = precedent_analyzer

    async def research_yargitay(
        self,
        *,
        case_text: str,
        max_results: int,
        yargitay_query_templates: list[str] | None = None,
        case_enrichment: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        effective_max_results = min(max(max_results, 1), RESEARCH_MAX_RESULTS_CAP)
        case_enrichment = case_enrichment or {}
        case_analysis = self.analyzer.analyze(case_text)
        is_vehicle_case = self._is_vehicle_case(
            case_text=case_text,
            legal_topic=case_analysis.legal_topic,
            legal_keywords=case_analysis.legal_keywords,
        )
        query_response = self.query_builder.build(
            SearchBuildRequest(
                case_text=case_text,
                legal_topic=case_analysis.legal_topic,
                legal_keywords=case_analysis.legal_keywords,
            )
        )
        logger.info("generated_queries=%s", query_response.queries)
        generated_queries_filtered = self._filter_generated_queries(
            generated_queries=query_response.queries,
            is_vehicle_case=is_vehicle_case,
        )
        logger.info("generated_queries_filtered=%s", generated_queries_filtered)
        queries = self._research_queries(
            case_text=case_text,
            legal_topic=case_analysis.legal_topic,
            legal_keywords=case_analysis.legal_keywords,
            generated_queries=generated_queries_filtered,
            preferred_queries=yargitay_query_templates or [],
        )
        logger.info("yargitay_queries_final=%s", queries)
        logger.info("yargitay_live_attempt_started=%s", True)

        scraper_response = await self.scraper.search(
            queries=queries,
            max_results=effective_max_results,
        )
        errors = list(scraper_response.errors)
        attempted_queries = list(scraper_response.attempted_queries or queries)
        attempted_query_count = len(attempted_queries)
        fallback_queries = [
            query for query in attempted_queries if query in VEHICLE_YARGITAY_QUERY_PLAN[3:]
        ]
        fallback_query_used = bool(is_vehicle_case and fallback_queries)
        skipped_due_to_rate_limit = bool(
            scraper_response.skipped_due_to_rate_limit or any(self._is_rate_limit_error(error) for error in errors)
        )
        raw_live_result_count = int(scraper_response.raw_live_result_count or 0)
        parsed_live_result_count = int(scraper_response.parsed_live_result_count or len(scraper_response.results))
        logger.info(
            "yargitay_search_started attempted_queries=%s fallback_query_used=%s skipped_due_to_rate_limit=%s",
            attempted_queries,
            fallback_query_used,
            skipped_due_to_rate_limit,
        )
        logger.info("raw_live_result_count=%s", raw_live_result_count)
        logger.info("parsed_live_result_count=%s", parsed_live_result_count)
        logger.info("yargitay_result_count=%s", len(scraper_response.results))
        if errors:
            logger.warning("yargitay_error=%s", errors)

        rankable_decisions = self._dedupe_rankable_decisions(self._to_rankable_decisions(scraper_response.results, errors))
        ranked_items = (
            self.ranker.rank(
                case_text=case_text,
                decisions=[item["rank_input"] for item in rankable_decisions],
                limit=len(rankable_decisions),
            )
            if rankable_decisions
            else []
        )

        decisions_by_identity: dict[str, list[YargitayDecision]] = {}
        for item in rankable_decisions:
            decisions_by_identity.setdefault(item["identity"], []).append(item["decision"])

        live_yargitay_results: list[dict[str, Any]] = []
        for ranked_item in ranked_items:
            matching_decisions = decisions_by_identity.get(ranked_item.decision_identity) or []
            if not matching_decisions:
                continue

            decision = matching_decisions.pop(0)
            summary = self.summarizer.summarize(
                case_text=case_text,
                decision=decision,
                base_similarity_score=ranked_item.similarity_score,
            )
            final_score = max(
                0,
                min(100, ranked_item.similarity_score + summary.relevance_bonus - summary.rank_penalty),
            )
            analysis = self.precedent_analyzer.analyze(
                case_text=case_text,
                decision={
                    "source": decision.source,
                    "title": decision.title,
                    "detail_url": decision.detail_url,
                    "court": decision.court,
                    "esas_no": decision.esas_no,
                    "karar_no": decision.karar_no,
                    "date": decision.date,
                    "similarity_score": final_score,
                    "usefulness_score": self.summarizer.usefulness_label(
                        score=final_score,
                        lehe_aleyhe=summary.lehe_aleyhe,
                        is_procedural=summary.is_procedural,
                    ),
                    "short_summary": summary.short_summary,
                    "legal_principle": summary.legal_principle,
                    "why_relevant": summary.why_relevant,
                    "lehe_aleyhe": summary.lehe_aleyhe,
                    "petition_paragraph": summary.petition_paragraph,
                    "clean_text_preview": summary.clean_text_preview,
                },
            )

            live_yargitay_results.append(
                {
                    "similarity_score": final_score,
                    "usefulness_score": self.summarizer.usefulness_label(
                        score=final_score,
                        lehe_aleyhe=summary.lehe_aleyhe,
                        is_procedural=summary.is_procedural,
                    ),
                    "source": decision.source,
                    "court": decision.court,
                    "esas_no": decision.esas_no,
                    "karar_no": decision.karar_no,
                    "date": decision.date,
                    "title": decision.title,
                    "detail_url": decision.detail_url,
                    "short_summary": summary.short_summary,
                    "legal_principle": summary.legal_principle,
                    "why_relevant": summary.why_relevant,
                    "lehe_aleyhe": summary.lehe_aleyhe,
                    "petition_paragraph": summary.petition_paragraph,
                    "clean_text_preview": summary.clean_text_preview,
                    "precedent_id": analysis.precedent_id,
                    "citation": analysis.citation,
                    "verification_status": analysis.verification_status,
                    "source_type": "yargitay_live",
                    "official_verification_status": "verified_live",
                    "similarity_reasons": analysis.similarity_reasons,
                    "shared_facts": analysis.shared_facts,
                    "shared_legal_issues": analysis.shared_legal_issues,
                    "supported_arguments": analysis.supported_arguments,
                    "evidence_connection": analysis.evidence_connection,
                    "distinguishing_risks": analysis.distinguishing_risks,
                    "recommended_use": analysis.recommended_use,
                    "confidence_score": analysis.confidence_score,
                    "use_class": analysis.precedent_use_class,
                    "petition_use_summary": analysis.petition_use_summary,
                }
            )

        live_yargitay_results.sort(key=lambda item: item["similarity_score"], reverse=True)
        live_yargitay_results = self._dedupe_top_decisions(live_yargitay_results)

        if scraper_response.results and not live_yargitay_results:
            errors.append("Sıralama için yeterli karar metni bulunamadı.")

        final_live_result_count = len(live_yargitay_results[:5])
        failure_reason = str(scraper_response.failure_reason or "")
        if not failure_reason:
            if skipped_due_to_rate_limit:
                failure_reason = "rate_limited"
            elif raw_live_result_count > 0 and parsed_live_result_count == 0:
                failure_reason = "parser_failed"
            elif scraper_response.official_yargitay_reached and raw_live_result_count == 0:
                failure_reason = "no_results"
        if parsed_live_result_count > 0 and final_live_result_count == 0:
            failure_reason = "filtered_all"
        fallback_precedents, fallback_source = self._fallback_precedents(
            case_enrichment=case_enrichment,
            use_fallback=final_live_result_count == 0,
        )
        if final_live_result_count == 0 and fallback_precedents and not failure_reason:
            failure_reason = "no_results"
        final_precedents = live_yargitay_results[:5] if final_live_result_count else fallback_precedents[:5]
        source_summary = {
            "live_yargitay_count": final_live_result_count,
            "legal_brain_fallback_count": len([item for item in fallback_precedents if item.get("source_type") == "legal_brain"]),
            "local_seed_count": len([item for item in fallback_precedents if item.get("source_type") == "local_seed"]),
            "official_yargitay_reached": bool(scraper_response.official_yargitay_reached),
            "official_yargitay_returned_results": bool(scraper_response.official_yargitay_returned_results),
            "used_fallback": bool(final_live_result_count == 0 and fallback_precedents),
        }
        user_message = self._build_user_message(
            skipped_due_to_rate_limit=skipped_due_to_rate_limit,
            has_errors=bool(errors),
            final_precedent_count=len(final_precedents),
            used_fallback=source_summary["used_fallback"],
            source_summary=source_summary,
        )
        logger.info("final_live_result_count=%s", final_live_result_count)
        logger.info("failure_reason=%s", failure_reason)
        logger.info("used_fallback=%s", source_summary["used_fallback"])
        logger.info("fallback_source=%s", fallback_source)
        return {
            "case_analysis": case_analysis.model_dump(),
            "queries": queries,
            "generated_queries": generated_queries_filtered,
            "attempted_queries": attempted_queries,
            "fallback_queries": fallback_queries,
            "attempted_query_count": attempted_query_count,
            "yargitay_search_started": True,
            "yargitay_result_count": parsed_live_result_count,
            "raw_live_result_count": raw_live_result_count,
            "parsed_live_result_count": parsed_live_result_count,
            "final_live_result_count": final_live_result_count,
            "fallback_query_used": fallback_query_used,
            "skipped_due_to_rate_limit": skipped_due_to_rate_limit,
            "failure_reason": failure_reason,
            "user_message": user_message,
            "final_precedent_count": len(final_precedents),
            "live_yargitay_results": live_yargitay_results[:5],
            "fallback_precedents": fallback_precedents[:5],
            "final_precedents": final_precedents,
            "source_summary": source_summary,
            "debug_source_summary": {
                "failure_reason": failure_reason,
                "fallback_source": fallback_source,
                "raw_live_result_count": raw_live_result_count,
                "parsed_live_result_count": parsed_live_result_count,
                "final_live_result_count": final_live_result_count,
            },
            "top_decisions": final_precedents,
            "errors": errors,
        }

    def _research_queries(
        self,
        *,
        case_text: str,
        legal_topic: str,
        legal_keywords: list[str],
        generated_queries: list[str],
        preferred_queries: list[str],
    ) -> list[str]:
        is_vehicle_case = self._is_vehicle_case(
            case_text=case_text,
            legal_topic=legal_topic,
            legal_keywords=legal_keywords,
        )

        if preferred_queries:
            queries = [sanitize_yargitay_query(query) for query in preferred_queries]
            queries.extend(sanitize_yargitay_query(query) for query in generated_queries)
            if is_vehicle_case:
                queries.extend(VEHICLE_YARGITAY_QUERY_PLAN)
            return self._dedupe_queries(queries)[:RESEARCH_QUERY_LIMIT]

        if self._is_poverty_alimony_case(
            case_text=case_text,
            legal_topic=legal_topic,
            legal_keywords=legal_keywords,
        ):
            queries = list(POVERTY_ALIMONY_PRIORITY_QUERIES)
            queries.extend(
                query
                for query in generated_queries
                if not self._contains_participation_or_tmk331(query)
            )
            return self._dedupe_queries(queries)[:RESEARCH_QUERY_LIMIT]

        if is_vehicle_case:
            queries = list(VEHICLE_YARGITAY_QUERY_PLAN)
            queries.extend(sanitize_yargitay_query(query) for query in generated_queries)
            return self._dedupe_queries(queries)[:5]

        return self._dedupe_queries([sanitize_yargitay_query(query) for query in generated_queries])[:RESEARCH_QUERY_LIMIT]

    def _to_rankable_decisions(
        self,
        decisions: list[YargitayDecision],
        errors: list[str],
    ) -> list[dict[str, Any]]:
        rankable: list[dict[str, Any]] = []
        for decision in decisions:
            text = " ".join((decision.clean_text or decision.raw_text).split())
            if len(text) < 10:
                errors.append(f"Karar metni sıralama için çok kısa: {decision.detail_url}")
                continue

            try:
                rank_input = DecisionInput(
                    source=decision.source or "Yargıtay",
                    court=decision.court or "Bilinmeyen Daire",
                    esas_no=decision.esas_no or "Esas no yok",
                    karar_no=decision.karar_no or "Karar no yok",
                    date=decision.date or "Tarih yok",
                    raw_text=text,
                )
            except ValidationError as exc:
                errors.append(f"Karar sıralama girdisine dönüştürülemedi: {self._short_error(exc)}")
                continue

            rankable.append(
                {
                    "decision": decision,
                    "rank_input": rank_input,
                    "identity": self._rank_identity(rank_input),
                }
            )
        return rankable

    @staticmethod
    def _dedupe_rankable_decisions(rankable: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in rankable:
            key = ResearchService._plain(str(item.get("identity") or ""))
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    @staticmethod
    def _dedupe_top_decisions(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for decision in decisions:
            key = ResearchService._plain(
                " ".join(
                    str(decision.get(part) or "")
                    for part in ("court", "esas_no", "karar_no", "date")
                )
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(decision)
        return result

    @staticmethod
    def _rank_identity(decision: DecisionInput) -> str:
        return f"{decision.court}, E. {decision.esas_no}, K. {decision.karar_no}, T. {decision.date}"

    @staticmethod
    def _short_error(error: Exception) -> str:
        message = " ".join(str(error).split())
        return message[:300] or error.__class__.__name__

    def _is_poverty_alimony_case(
        self,
        *,
        case_text: str,
        legal_topic: str,
        legal_keywords: list[str],
    ) -> bool:
        combined = " ".join([case_text, legal_topic, *legal_keywords])
        normalized = self._plain(combined)
        return "yoksulluk nafakasi" in normalized or (
            "yoksulluk" in normalized and "nafaka" in normalized
        )

    def _contains_participation_or_tmk331(self, query: str) -> bool:
        normalized = self._plain(query)
        return "tmk 331" in normalized or "istirak nafakasi" in normalized or "istirak" in normalized

    def _filter_generated_queries(
        self,
        *,
        generated_queries: list[str],
        is_vehicle_case: bool,
    ) -> list[str]:
        sanitized = [sanitize_yargitay_query(query) for query in generated_queries]
        sanitized = [query for query in sanitized if query]
        if not is_vehicle_case:
            return self._dedupe_queries(sanitized)
        filtered = [query for query in sanitized if self._is_vehicle_query(query)]
        return self._dedupe_queries(filtered)

    def _is_vehicle_case(
        self,
        *,
        case_text: str,
        legal_topic: str,
        legal_keywords: list[str],
    ) -> bool:
        combined = self._plain(" ".join([case_text, legal_topic, *legal_keywords]))
        return any(
            term in combined
            for term in (
                "ayipli arac",
                "gizli ayip",
                "ikinci el arac",
                "arac satisi",
                "motor arizasi",
                "tramer",
                "servis raporu",
                "ekspertiz",
                "bedel indirimi",
                "sozlesmeden donme",
            )
        )

    def _is_vehicle_query(self, query: str) -> bool:
        normalized = self._plain(query)
        if any(
            marker in normalized
            for marker in (
                "iscilik",
                "isci",
                "kidem",
                "ihbar",
                "fazla mesai",
                "nafaka",
                "kira",
                "kiraci",
                "icra",
                "odeme emri",
            )
        ):
            return False
        return any(
            marker in normalized
            for marker in (
                "arac",
                "ayip",
                "gizli ayip",
                "ikinci el",
                "tramer",
                "ekspertiz",
                "motor arizasi",
                "servis raporu",
                "bedel indirimi",
                "noter satis",
            )
        )

    @staticmethod
    def _is_rate_limit_error(error: str) -> bool:
        normalized = ResearchService._plain(error)
        return "hiz siniri" in normalized or "rate limit" in normalized or "http 429" in normalized

    def _fallback_precedents(
        self,
        *,
        case_enrichment: dict[str, Any],
        use_fallback: bool,
    ) -> tuple[list[dict[str, Any]], str]:
        if not use_fallback:
            return [], "none"
        candidates = list(case_enrichment.get("fallback_precedent_candidates") or [])
        if not candidates:
            return [], "none"
        result: list[dict[str, Any]] = []
        for index, item in enumerate(candidates, start=1):
            title = str(item.get("title") or item.get("citation_label") or item.get("source_id") or f"Yerel kaynak adayı {index}").strip()
            paragraph = str(
                item.get("usable_argument")
                or item.get("doctrine_principle")
                or item.get("chunk_preview")
                or item.get("summary")
                or "Canlı Yargıtay doğrulaması yapılamayan yerel kaynak adayı."
            ).strip()
            result.append(
                {
                    "similarity_score": 20,
                    "usefulness_score": "Düşük",
                    "source": "Legal Brain",
                    "source_type": "legal_brain",
                    "official_verification_status": "not_verified",
                    "court": str(item.get("court") or "Legal Brain yerel kaynak"),
                    "esas_no": str(item.get("esas_no") or "-"),
                    "karar_no": str(item.get("karar_no") or "-"),
                    "date": str(item.get("date") or item.get("decision_date") or "-"),
                    "title": title,
                    "detail_url": str(item.get("detail_url") or item.get("url") or ""),
                    "short_summary": paragraph,
                    "legal_principle": paragraph,
                    "why_relevant": str(item.get("relevance_reason") or "Canlı Yargıtay doğrulaması yapılamadı; yerel kaynak adayı olarak ayrıldı."),
                    "lehe_aleyhe": "Nötr",
                    "petition_paragraph": paragraph,
                    "clean_text_preview": paragraph,
                    "precedent_id": str(item.get("source_id") or title),
                    "citation": str(item.get("citation_label") or title),
                    "verification_status": "verification_required_precedent_candidate",
                    "similarity_reasons": [],
                    "shared_facts": [],
                    "shared_legal_issues": [],
                    "supported_arguments": [],
                    "evidence_connection": [],
                    "distinguishing_risks": ["Canlı Yargıtay doğrulaması yapılamadı."],
                    "recommended_use": "Resmi doğrulama yapılmadan kesin emsal gibi kullanılmamalıdır.",
                    "confidence_score": 20,
                    "use_class": "exclude_from_petition",
                    "petition_use_summary": "Canlı Yargıtay doğrulaması yapılmadığından ana emsal listesine alınmamalıdır.",
                }
            )
        return result[:5], "legal_brain"

    @staticmethod
    def _build_user_message(
        *,
        skipped_due_to_rate_limit: bool,
        has_errors: bool,
        final_precedent_count: int,
        used_fallback: bool,
        source_summary: dict[str, Any],
    ) -> str:
        if skipped_due_to_rate_limit:
            return "Yargıtay geçici hız sınırı uyguladı; mevcut yerel analizle devam edildi."
        if source_summary.get("live_yargitay_count", 0) == 0 and used_fallback:
            return "Canlı Yargıtay araması sonuç döndürmedi. Legal Brain yerel kaynak adaylarıyla devam edildi."
        if has_errors and final_precedent_count == 0:
            return "Yargıtay canlı araması sonuç döndürmedi; yerel hukuki analizle devam edildi."
        return ""

    @staticmethod
    def _dedupe_queries(queries: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for query in queries:
            cleaned = sanitize_yargitay_query(query)
            key = cleaned.casefold()
            if cleaned and key not in seen:
                seen.add(key)
                result.append(cleaned)
        return result

    @staticmethod
    def _plain(text: str) -> str:
        translation = str.maketrans(
            {
                "ç": "c",
                "Ç": "c",
                "ğ": "g",
                "Ğ": "g",
                "ı": "i",
                "I": "i",
                "İ": "i",
                "ö": "o",
                "Ö": "o",
                "ş": "s",
                "Ş": "s",
                "ü": "u",
                "Ü": "u",
            }
        )
        simplified = text.translate(translation).casefold()
        simplified = re.sub(r"\s+", " ", simplified)
        return simplified.strip()


research_service = ResearchService()
