from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from app.models.yargitay_models import YargitaySearchResponse
from app.services.research_service import ResearchService
from app.services.yargitay_search_service import (
    build_vehicle_yargitay_queries,
    build_yargitay_query,
    sanitize_yargitay_query,
)


VEHICLE_ATTEMPTED_PREFIX = list(build_vehicle_yargitay_queries())[:4]


class YargitayQueryBuilderTests(unittest.TestCase):
    def test_build_all_mode(self) -> None:
        self.assertEqual(
            build_yargitay_query(["ayıplı araç", "gizli ayıp"], mode="all"),
            '+"ayıplı araç" +"gizli ayıp"',
        )

    def test_build_all_mode_with_single_word_phrase(self) -> None:
        self.assertEqual(
            build_yargitay_query(["gizli ayıp", "araç"], mode="all"),
            '+"gizli ayıp" +"araç"',
        )

    def test_build_any_mode(self) -> None:
        self.assertEqual(
            build_yargitay_query(["ayıplı araç", "gizli ayıp"], mode="any"),
            '"ayıplı araç" "gizli ayıp"',
        )

    def test_build_broad_mode(self) -> None:
        self.assertEqual(
            build_yargitay_query(["ayıplı araç", "gizli ayıp"], mode="broad"),
            "ayıplı araç gizli ayıp",
        )

    def test_sanitize_outer_quotes(self) -> None:
        self.assertEqual(
            sanitize_yargitay_query('\'"ayıplı araç" "gizli ayıp"\''),
            '"ayıplı araç" "gizli ayıp"',
        )

    def test_sanitize_escaped_quotes(self) -> None:
        self.assertEqual(
            sanitize_yargitay_query('\\"ayıplı araç\\" \\"gizli ayıp\\"'),
            '"ayıplı araç" "gizli ayıp"',
        )

    def test_vehicle_queries_do_not_contain_broken_wrappers(self) -> None:
        queries = build_vehicle_yargitay_queries()
        joined = " ".join(queries)
        self.assertNotIn('\'"', joined)
        self.assertNotIn('\\"', joined)
        self.assertNotIn("'''", joined)

    def test_vehicle_queries_include_expected_primary_forms(self) -> None:
        queries = build_vehicle_yargitay_queries()
        self.assertIn('+"gizli ayıp" +"araç"', queries)
        self.assertIn('+"ayıplı araç" +"gizli ayıp"', queries)

    def test_vehicle_research_queries_prioritize_yargitay_syntax(self) -> None:
        service = ResearchService()
        queries = service._research_queries(
            case_text="Müvekkil ikinci el araç aldı, gizli ayıp çıktı.",
            legal_topic="Ayıplı araç",
            legal_keywords=["gizli ayıp", "araç"],
            generated_queries=['"ayıplı araç" "gizli ayıp"'],
            preferred_queries=[],
        )
        self.assertEqual(queries[0], '+"gizli ayıp" +"araç"')
        self.assertIn("gizli ayıp araç", queries)

    def test_fallback_keeps_broad_query_available(self) -> None:
        queries = build_vehicle_yargitay_queries()
        self.assertIn("gizli ayıp araç", queries)
        self.assertIn("ayıplı araç", queries)

    def test_vehicle_generated_queries_filter_out_labor_leakage(self) -> None:
        service = ResearchService()
        filtered = service._filter_generated_queries(
            generated_queries=[
                "işçilik alacakları kıdem ihbar fazla mesai",
                '"ayıplı araç" "gizli ayıp"',
                '"ekspertiz raporu" "ayıplı araç"',
            ],
            is_vehicle_case=True,
        )
        self.assertEqual(
            filtered,
            ['"ayıplı araç" "gizli ayıp"', '"ekspertiz raporu" "ayıplı araç"'],
        )

    def test_research_response_exposes_attempted_queries_and_rate_limit_fallback(self) -> None:
        class FakeAnalyzer:
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

        class FakeQueryBuilder:
            def build(self, _: object) -> SimpleNamespace:
                return SimpleNamespace(
                    queries=[
                        "işçilik alacakları kıdem ihbar fazla mesai",
                        '"ayıplı araç" "gizli ayıp"',
                    ]
                )

        class FakeScraper:
            async def search(self, queries: list[str], max_results: int) -> YargitaySearchResponse:
                self.last_queries = list(queries)
                self.last_max_results = max_results
                return YargitaySearchResponse(
                    results=[],
                    errors=["Yargıtay hız sınırı uyguladı; mevcut sonuçlarla devam edildi."],
                    attempted_queries=queries[:4],
                    skipped_due_to_rate_limit=True,
                )

        service = ResearchService(
            analyzer=FakeAnalyzer(),
            query_builder=FakeQueryBuilder(),
            scraper=FakeScraper(),
            ranker=None,
            summarizer=None,
            precedent_analyzer=None,
        )

        response = asyncio.run(
            service.research_yargitay(
                case_text="Müvekkil ikinci el araç aldı, gizli ayıp ortaya çıktı.",
                max_results=5,
            )
        )

        self.assertEqual(response["queries"][0], '+"gizli ayıp" +"araç"')
        self.assertEqual(response["generated_queries"], ['"ayıplı araç" "gizli ayıp"'])
        self.assertEqual(response["attempted_queries"], VEHICLE_ATTEMPTED_PREFIX)
        self.assertEqual(response["fallback_queries"], ["gizli ayıp araç"])
        self.assertTrue(response["fallback_query_used"])
        self.assertTrue(response["skipped_due_to_rate_limit"])
        self.assertIn("hız sınırı", response["user_message"])


if __name__ == "__main__":
    unittest.main()
