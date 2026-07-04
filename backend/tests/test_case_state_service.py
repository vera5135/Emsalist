from __future__ import annotations

import unittest

from app.services.case_state_service import case_state_service


class CaseStateServiceTests(unittest.TestCase):
    def test_build_returns_structured_vehicle_case_state(self) -> None:
        state = case_state_service.build(
            event_text=(
                "Müvekkil aracı satıcının sorunsuz olduğu beyanına güvenerek satın aldı. "
                "Satıştan kısa süre sonra motor arızası ortaya çıktı."
            ),
            area="Satış bedelinin iadesi",
            case_type="ayıplı araç",
            document_facts=[
                "sale_date: 12.04.2024",
                "sale_price: 500.000 TL",
                "vehicle_plate: 35 ABC 123",
            ],
            question_answers={
                "Satıcı galeri/tacir/şirket mi?": "Bilmiyorum",
                "Servis/ekspertiz raporu mevcut mu?": "Servis raporu mevcut",
            },
            legal_sources=["TBK m. 219", "TBK m. 223", "TBK m. 219"],
            precedent_candidates=[
                {"citation": "Yargıtay 1", "use_in_petition": True},
                {"citation": "Yargıtay 2", "excluded_reason": "Konu dışı"},
            ],
            analysis_context={
                "documents": [{"document_type": "noter_satis_sozlesmesi"}],
                "warnings": ["TRAMER kaydı araştırılacak"],
            },
        )

        self.assertRegex(state["case_id"], r"^[0-9a-f]{12}$")
        self.assertEqual(state["area"], "Satış bedelinin iadesi")
        self.assertEqual(state["case_type"], "ayıplı araç")
        self.assertEqual(state["documents"], [{"document_type": "noter_satis_sozlesmesi"}])
        self.assertEqual(len(state["usable_precedents"]), 1)
        self.assertIn("question_plan", state)
        self.assertIn("evidence_plan", state)
        self.assertIn("risk_plan", state)
        self.assertIn("reasoner_output", state)
        self.assertIn("precedent_query_context", state)
        self.assertIn("TRAMER kaydı araştırılacak", state["warnings"])
        self.assertIn("Servis/ekspertiz raporu", state["evidence_items"])
        graph = state["legal_issue_graph"]
        self.assertEqual(state["canonical_model"], "legal_issue_graph")
        self.assertTrue(graph["canonical"])
        self.assertEqual(state["graph_source_fingerprint"], graph["source_fingerprint"])
        self.assertEqual(state["research_queries"], graph["research_plan"])
        self.assertEqual(state["risk_items"], graph["global_risks"])
        self.assertEqual(state["drafting_plan"], graph["drafting_plan"])
        self.assertEqual(
            [item["title"] for item in state["legal_issues"]],
            [item["title"] for item in graph["issues"]],
        )


if __name__ == "__main__":
    unittest.main()
