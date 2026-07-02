"""Tests for LegalIssueGraphService v1."""

from __future__ import annotations

import unittest

from app.services.legal_issue_graph_service import legal_issue_graph_service


class LegalIssueGraphServiceTests(unittest.TestCase):
    """Test the graph builds correct issues, risks, queries for defective vehicle."""

    def _vehicle_case_state(self, **overrides: str) -> dict:
        """Build a minimal vehicle case_state dict."""
        base = {
            "case_id": "test_vehicle_001",
            "area": "Borçlar hukuku",
            "case_type": "ayıplı araç",
            "event_text": (
                "Müvekkil aracı satıcının sorunsuz olduğu beyanına güvenerek satın aldı. "
                "Satıştan kısa süre sonra araçta motor arızası ortaya çıktı."
            ),
            "document_facts": [
                "parties: Alıcı: Mehmet Demir; Satıcı: Ahmet Yılmaz",
                "sale_date: 12.04.2024",
                "sale_price: 500.000 TL",
                "vehicle_make_model: Volkswagen Golf 1.6 TDI",
                "vehicle_plate: 35 ABC 123",
                "vehicle_vin: WVWZZZ123456789",
                "notary_info: İzmir 5. Noterliği",
            ],
            "question_answers": {},
        }
        base.update(overrides)
        return base

    def test_build_returns_required_issues(self) -> None:
        """Test 1: Graph produces at least the 7 required legal issues."""
        state = self._vehicle_case_state()
        graph = legal_issue_graph_service.build(state)

        issue_titles = [i.title for i in graph.issues]
        required = [
            "Satış ilişkisi ve taraflar",
            "Ayıbın varlığı",
            "Ayıbın gizli niteliği",
            "Ayıp ihbarı",
            "Seçimlik hak ve talep",
            "Görevli mahkeme / tüketici-ticari ayrımı",
        ]
        for title in required:
            self.assertIn(title, issue_titles, f"Missing issue: {title}")

    def test_facts_map_to_sale_relationship_issue(self) -> None:
        """Test 2: NOTER._TEST facts appear in sale_relationship confirmed_facts."""
        state = self._vehicle_case_state()
        graph = legal_issue_graph_service.build(state)

        sale_issue = next(i for i in graph.issues if i.issue_id == "sale_relationship")
        confirmed = " ".join(sale_issue.confirmed_facts)
        self.assertIn("sale_date: 12.04.2024", confirmed)
        self.assertIn("sale_price: 500.000 TL", confirmed)
        self.assertIn("vehicle_plate: 35 ABC 123", confirmed)

    def test_missing_report_raises_risk_not_low(self) -> None:
        """Test 3: No report date/number → defect_existence risk is not low + missing_evidence."""
        state = self._vehicle_case_state(
            document_facts=[
                "parties: Alıcı: Mehmet Demir; Satıcı: Ahmet Yılmaz",
                "sale_date: 12.04.2024",
                "sale_price: 500.000 TL",
            ]
        )
        graph = legal_issue_graph_service.build(state)

        defect_issue = next(i for i in graph.issues if i.issue_id == "defect_existence")
        self.assertIn(defect_issue.risk_level, ("high", "medium"),
                       "Risk should not be low when report date/number missing")
        self.assertTrue(
            any("servis raporu" in e for e in defect_issue.missing_evidence),
            "servis raporu should be in missing_evidence"
        )

    def test_missing_notice_raises_high_risk(self) -> None:
        """Test 4: No notice date → defect_notice risk is high."""
        state = self._vehicle_case_state(
            document_facts=[
                "parties: Alıcı: Mehmet Demir; Satıcı: Ahmet Yılmaz",
            ],
            question_answers={},
        )
        graph = legal_issue_graph_service.build(state)

        notice_issue = next(i for i in graph.issues if i.issue_id == "defect_notice")
        self.assertEqual(notice_issue.risk_level, "high")

    def test_research_plan_vehicle_only(self) -> None:
        """Test 5: research_plan contains vehicle queries, not labour/family/rent/foreclosure."""
        state = self._vehicle_case_state()
        graph = legal_issue_graph_service.build(state)

        all_queries = " ".join(graph.research_plan).lower()
        # Should contain vehicle terms
        self.assertIn("gizli ayıplı araç", all_queries)
        self.assertIn("ikinci el araç", all_queries)

        # Should NOT contain irrelevant terms
        irrelevant = ["işçilik", "kıdem", "nafaka", "kira", "icra"]
        for term in irrelevant:
            self.assertNotIn(term, all_queries, f"Irrelevant query term found: {term}")

    def test_next_best_questions_prioritise_notice_and_report(self) -> None:
        """Test 6: next_best_questions includes notice and report questions first."""
        state = self._vehicle_case_state(
            document_facts=[
                "parties: Alıcı: Mehmet Demir; Satıcı: Ahmet Yılmaz",
                "sale_date: 12.04.2024",
            ]
        )
        graph = legal_issue_graph_service.build(state)

        questions = " ".join(graph.next_best_questions).lower()
        self.assertTrue(
            any("ihbar" in q for q in graph.next_best_questions),
            "Should contain notice question"
        )
        self.assertTrue(
            any("servis" in q or "rapor" in q for q in graph.next_best_questions),
            "Should contain report question"
        )

    def test_graph_case_id_matches_input(self) -> None:
        """Test 7: Graph carries the same case_id as input case_state."""
        state = self._vehicle_case_state()
        graph = legal_issue_graph_service.build(state)
        self.assertEqual(graph.case_id, "test_vehicle_001")

    def test_global_risks_are_generated(self) -> None:
        """Test 3b: Missing evidence generates global risk entries."""
        state = self._vehicle_case_state(
            document_facts=[
                "parties: Alıcı: Mehmet Demir; Satıcı: Ahmet Yılmaz",
            ]
        )
        graph = legal_issue_graph_service.build(state)
        self.assertTrue(len(graph.global_risks) > 0)

    def test_drafting_plan_is_clean(self) -> None:
        """Test drafting_plan has items with section and argument, no technical fields."""
        state = self._vehicle_case_state()
        graph = legal_issue_graph_service.build(state)
        self.assertTrue(len(graph.drafting_plan) > 0)
        for item in graph.drafting_plan:
            self.assertTrue(item.section)
            self.assertTrue(item.argument)
            # No technical fields
            self.assertNotIn("issue_id", item.model_dump())

    def test_issue_id_not_in_research_plan(self) -> None:
        """Ensure research_plan does not leak technical issue_id values."""
        state = self._vehicle_case_state()
        graph = legal_issue_graph_service.build(state)
        all_plan = " ".join(graph.research_plan)
        self.assertNotIn("sale_relationship", all_plan)
        self.assertNotIn("defect_existence", all_plan)


if __name__ == "__main__":
    unittest.main()