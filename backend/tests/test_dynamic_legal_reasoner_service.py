from __future__ import annotations

import unittest

from app.services.dynamic_legal_reasoner_service import dynamic_legal_reasoner_service


class DynamicLegalReasonerServiceTests(unittest.TestCase):
    def test_vehicle_reasoning_returns_structured_plans(self) -> None:
        reasoning = dynamic_legal_reasoner_service.analyze(
            event_text=(
                "Davacı ikinci el araç satın aldı. Satıştan kısa süre sonra motor arızası çıktı "
                "ve araçta gizli ayıp olduğu değerlendirildi."
            ),
            document_facts=["sale_date: 12.04.2024", "vehicle_plate: 35 ABC 123"],
            question_answers={"Satıcı galeri/tacir/şirket mi?": "Bilmiyorum"},
        )

        self.assertIn("gizli ayıplı ikinci el araç satışı", reasoning["case_type_candidates"])
        self.assertGreaterEqual(len(reasoning["legal_issues"]), 6)
        self.assertEqual(reasoning["legal_issues"][0]["issue_key"], "sale_relationship")
        self.assertIn("required_evidence", reasoning["legal_issues"][0])
        self.assertEqual(reasoning["evidence_plan"][0]["evidence_key"], "notary_sale_contract")
        self.assertIn("risk_if_missing", reasoning["evidence_plan"][0])
        self.assertEqual(reasoning["risk_plan"][0]["risk_key"], "preexisting_defect_proof")
        self.assertTrue(reasoning["question_plan"])
        self.assertIn("seller_status", [item["related_issue_key"] for item in reasoning["question_plan"]])
        self.assertTrue(reasoning["precedent_query_context"]["positive_terms"])
        self.assertTrue(reasoning["research_queries"])

    def test_generic_reasoning_keeps_structured_shape(self) -> None:
        reasoning = dynamic_legal_reasoner_service.analyze(
            event_text="Davacı kiralananın tahliyesini ve kira alacağının tahsilini talep etmektedir.",
            document_facts=["lease_start_date: 01.01.2024"],
            question_answers={"İhtarname mevcut mu?": "Bilmiyorum"},
        )

        self.assertIsInstance(reasoning["legal_area_candidates"], list)
        self.assertTrue(reasoning["legal_issues"])
        self.assertTrue(reasoning["evidence_plan"])
        self.assertTrue(reasoning["risk_plan"])
        self.assertTrue(reasoning["question_plan"])


if __name__ == "__main__":
    unittest.main()
