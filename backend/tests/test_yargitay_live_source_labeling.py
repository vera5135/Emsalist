from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from app.models.yargitay_models import YargitayDecision, YargitaySearchResponse
from app.services.research_service import ResearchService


class _FakeAnalyzer:
    def analyze(self, _: str) -> SimpleNamespace:
        return SimpleNamespace(
            legal_topic="Ayıplı araç",
            legal_keywords=["gizli ayıp", "araç"],
            model_dump=lambda: {
                "legal_topic": "Ayıplı araç",
                "case_facts": [],
                "legal_keywords": ["gizli ayıp", "araç"],
                "case_state": {},
                "dynamic_reasoning": {},
            },
        )


class _FakeQueryBuilder:
    def build(self, _: object) -> SimpleNamespace:
        return SimpleNamespace(queries=['"ayıplı araç" "gizli ayıp"'])


class _FakeRanker:
    def rank(self, *, case_text: str, decisions: list[object], limit: int) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                decision_identity=f"{decision.court}, E. {decision.esas_no}, K. {decision.karar_no}, T. {decision.date}",
                similarity_score=70,
            )
            for decision in decisions[:limit]
        ]


class _FakeSummarizer:
    def summarize(self, *, case_text: str, decision: YargitayDecision, base_similarity_score: int) -> SimpleNamespace:
        return SimpleNamespace(
            relevance_bonus=0,
            rank_penalty=0,
            lehe_aleyhe="Lehe",
            is_procedural=False,
            short_summary="Özet",
            legal_principle="İlke",
            why_relevant="Bağlantı",
            petition_paragraph="Paragraf",
            clean_text_preview="Önizleme",
        )

    def usefulness_label(self, *, score: int, lehe_aleyhe: str, is_procedural: bool) -> str:
        return "Orta"


class _FakePrecedentAnalyzer:
    def analyze(self, *, case_text: str, decision: dict[str, object]) -> SimpleNamespace:
        return SimpleNamespace(
            precedent_id="P-1",
            citation="Yargıtay 3. HD",
            verification_status="verified_supportive_precedent",
            similarity_reasons=[],
            shared_facts=[],
            shared_legal_issues=[],
            supported_arguments=[],
            evidence_connection=[],
            distinguishing_risks=[],
            recommended_use="Kullanılabilir",
            confidence_score=80,
        )


class YargitayLiveSourceLabelingTests(unittest.TestCase):
    def _service(self, scraper: object) -> ResearchService:
        return ResearchService(
            analyzer=_FakeAnalyzer(),
            query_builder=_FakeQueryBuilder(),
            scraper=scraper,
            ranker=_FakeRanker(),
            summarizer=_FakeSummarizer(),
            precedent_analyzer=_FakePrecedentAnalyzer(),
        )

    def test_empty_live_results_with_legal_brain_fallback_are_labeled(self) -> None:
        class FakeScraper:
            async def search(self, queries: list[str], max_results: int) -> YargitaySearchResponse:
                return YargitaySearchResponse(
                    results=[],
                    errors=[],
                    attempted_queries=queries,
                    raw_live_result_count=0,
                    parsed_live_result_count=0,
                    official_yargitay_reached=True,
                    official_yargitay_returned_results=False,
                    failure_reason="no_results",
                )

        response = asyncio.run(
            self._service(FakeScraper()).research_yargitay(
                case_text="Müvekkil ikinci el araç aldı, gizli ayıp çıktı.",
                max_results=5,
                case_enrichment={
                    "fallback_precedent_candidates": [
                        {"source_id": f"lb-{index}", "title": f"LB {index}", "usable_argument": "Yerel argüman"}
                        for index in range(1, 6)
                    ]
                },
            )
        )

        self.assertEqual(response["source_summary"]["live_yargitay_count"], 0)
        self.assertEqual(response["source_summary"]["legal_brain_fallback_count"], 5)
        self.assertTrue(response["source_summary"]["used_fallback"])
        self.assertTrue(all(item["source_type"] == "legal_brain" for item in response["fallback_precedents"]))
        self.assertTrue(all(item["source_type"] != "yargitay_live" for item in response["fallback_precedents"]))

    def test_live_results_are_marked_as_verified_live(self) -> None:
        class FakeScraper:
            async def search(self, queries: list[str], max_results: int) -> YargitaySearchResponse:
                return YargitaySearchResponse(
                    results=[
                        YargitayDecision(
                            query=queries[0],
                            court="Yargıtay 3. HD",
                            esas_no=f"2020/{index}",
                            karar_no=f"2021/{index}",
                            date="09.02.2021",
                            title=f"Karar {index}",
                            detail_url=f"https://example.com/{index}",
                            raw_text="Karar metni yeterince uzundur.",
                            clean_text="Karar metni yeterince uzundur.",
                        )
                        for index in range(1, 4)
                    ],
                    errors=[],
                    attempted_queries=queries,
                    raw_live_result_count=3,
                    parsed_live_result_count=3,
                    official_yargitay_reached=True,
                    official_yargitay_returned_results=True,
                )

        response = asyncio.run(
            self._service(FakeScraper()).research_yargitay(
                case_text="Müvekkil ikinci el araç aldı, gizli ayıp çıktı.",
                max_results=5,
            )
        )

        self.assertEqual(response["source_summary"]["live_yargitay_count"], 3)
        self.assertFalse(response["source_summary"]["used_fallback"])
        self.assertTrue(all(item["source_type"] == "yargitay_live" for item in response["live_yargitay_results"]))
        self.assertTrue(all(item["official_verification_status"] == "verified_live" for item in response["live_yargitay_results"]))

    def test_runtime_exception_is_sanitized(self) -> None:
        class FakeScraper:
            async def search(self, queries: list[str], max_results: int) -> YargitaySearchResponse:
                return YargitaySearchResponse(
                    results=[],
                    errors=["Runtime exception:{0}:Hata Oluştu!"],
                    attempted_queries=queries,
                    official_yargitay_reached=True,
                    failure_reason="runtime_exception",
                )

        response = asyncio.run(
            self._service(FakeScraper()).research_yargitay(
                case_text="Müvekkil ikinci el araç aldı, gizli ayıp çıktı.",
                max_results=5,
            )
        )

        self.assertEqual(response["failure_reason"], "runtime_exception")
        self.assertNotIn("Runtime exception", response["user_message"])
        self.assertNotIn("Traceback", response["user_message"])

    def test_parser_failed_is_preserved_when_raw_exists_but_parsed_is_zero(self) -> None:
        class FakeScraper:
            async def search(self, queries: list[str], max_results: int) -> YargitaySearchResponse:
                return YargitaySearchResponse(
                    results=[],
                    errors=["Karar listesi okunamadı."],
                    attempted_queries=queries,
                    raw_live_result_count=4,
                    parsed_live_result_count=0,
                    official_yargitay_reached=True,
                    official_yargitay_returned_results=True,
                    failure_reason="selector_changed",
                )

        response = asyncio.run(
            self._service(FakeScraper()).research_yargitay(
                case_text="Müvekkil ikinci el araç aldı, gizli ayıp çıktı.",
                max_results=5,
            )
        )

        self.assertIn(response["failure_reason"], {"parser_failed", "selector_changed"})


if __name__ == "__main__":
    unittest.main()
