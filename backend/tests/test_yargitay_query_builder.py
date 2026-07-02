from __future__ import annotations

import unittest

from app.services.research_service import ResearchService
from app.services.yargitay_search_service import (
    build_vehicle_yargitay_queries,
    build_yargitay_query,
    sanitize_yargitay_query,
)


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


if __name__ == "__main__":
    unittest.main()
