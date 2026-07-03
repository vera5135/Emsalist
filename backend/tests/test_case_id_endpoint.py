from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.services.case_session_service import case_session_service


class CaseIdEndpointEnforcementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        cls.case_a = case_session_service.new_case()["case_id"]
        cls.case_b = case_session_service.new_case()["case_id"]

    def test_ai_enrich_missing_case_id_returns_422(self) -> None:
        response = self.client.post(
            "/ai/enrich-case",
            json={"case_text": "kira davasi metni", "use_ai": False},
        )
        self.assertEqual(response.status_code, 422)

    def test_ai_enrich_empty_case_id_returns_422(self) -> None:
        response = self.client.post(
            "/ai/enrich-case",
            json={"case_id": "", "case_text": "kira davasi metni", "use_ai": False},
        )
        self.assertEqual(response.status_code, 422)

    def test_ai_enrich_unknown_case_id_returns_404(self) -> None:
        response = self.client.post(
            "/ai/enrich-case",
            json={
                "case_id": "bilinmeyen-dosya-99999",
                "case_text": "valid case text with enough length to pass validation",
                "use_ai": False,
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_ai_enrich_valid_case_id_succeeds(self) -> None:
        response = self.client.post(
            "/ai/enrich-case",
            json={
                "case_id": self.case_a,
                "case_text": "kira davasi metni",
                "use_ai": False,
            },
        )
        self.assertEqual(response.status_code, 200)

    def test_petition_draft_missing_case_id_returns_422(self) -> None:
        response = self.client.post(
            "/petition/draft",
            json={
                "case_text": "valid case text with enough length to pass validation check",
                "request_type": "talep",
                "answers": {},
                "selected_decisions": [],
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_petition_draft_unknown_case_id_returns_404(self) -> None:
        response = self.client.post(
            "/petition/draft",
            json={
                "case_id": "bilinmeyen-dosya-99999",
                "case_text": "valid case text with enough length to pass validation check",
                "request_type": "talep",
                "answers": {},
                "selected_decisions": [],
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_legal_brain_search_missing_case_id_returns_422(self) -> None:
        response = self.client.post(
            "/legal-brain/search",
            json={"query": "test query", "max_results": 3},
        )
        self.assertEqual(response.status_code, 422)

    def test_research_unknown_case_id_returns_404(self) -> None:
        response = self.client.post(
            "/research/yargitay",
            json={
                "case_id": "bilinmeyen-dosya-99999",
                "case_text": "valid case text with enough length to pass validation check",
                "max_results": 1,
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_strategy_missing_case_id_returns_422(self) -> None:
        response = self.client.post(
            "/petition/strategy",
            json={"case_text": "kira davasi acmak istiyoruz"},
        )
        self.assertEqual(response.status_code, 422)

    def test_enrichment_from_case_a_not_written_to_case_b(self) -> None:
        self.client.post(
            "/ai/enrich-case",
            json={
                "case_id": self.case_a,
                "case_text": "A dosyasi kira metni",
                "use_ai": False,
            },
        )
        state_a = case_session_service.get_case_state(self.case_a)
        state_b = case_session_service.get_case_state(self.case_b)
        self.assertEqual(state_a.get("event_text"), "A dosyasi kira metni")
        self.assertNotEqual(state_a.get("event_text"), state_b.get("event_text"))


if __name__ == "__main__":
    unittest.main()
