"""P1.1 — AI run tracking tests."""

from __future__ import annotations

import unittest

from app.models.ai_models import estimate_cost
from app.services.ai_run_service import AIRunService


class CostEstimateTests(unittest.TestCase):

    def test_known_model_cost(self) -> None:
        cost = estimate_cost("deepseek-chat", 3000, 2000)
        self.assertIsNotNone(cost)
        self.assertGreater(cost, 0)

    def test_unknown_model_null(self) -> None:
        cost = estimate_cost("unknown-model", 1000, 500)
        self.assertIsNone(cost)

    def test_null_tokens_null_cost(self) -> None:
        cost = estimate_cost("deepseek-chat", None, 500)
        self.assertIsNone(cost)


class AIRunServiceTests(unittest.TestCase):

    def setUp(self) -> None:
        import tempfile
        self.temp = tempfile.TemporaryDirectory()
        self.service = AIRunService(store_path=f"{self.temp.name}/ai_runs.json")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_start_and_complete_run(self) -> None:
        rid = self.service.start_run(case_id="test-1", operation="case_enrichment")
        self.service.complete_run(rid, input_tokens=100, output_tokens=50)
        record = self.service.get_run(rid)
        self.assertIsNotNone(record)
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["total_tokens"], 150)

    def test_start_and_fail_run(self) -> None:
        rid = self.service.start_run(case_id="test-2", operation="legal_questions")
        self.service.fail_run(rid, error_code="AI_TIMEOUT")
        record = self.service.get_run(rid)
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["error_code"], "AI_TIMEOUT")

    def test_fallback_status_recorded(self) -> None:
        rid = self.service.start_run(case_id="test-3", operation="petition_refine")
        self.service.mark_fallback(rid, fallback_type="local_template")
        record = self.service.get_run(rid)
        self.assertEqual(record["status"], "fallback")
        self.assertTrue(record["fallback_used"])

    def test_list_runs_filters_by_case(self) -> None:
        self.service.start_run(case_id="case-a", operation="case_enrichment")
        self.service.start_run(case_id="case-b", operation="case_enrichment")
        records_a, _ = self.service.list_case_runs("case-a")
        records_b, _ = self.service.list_case_runs("case-b")
        self.assertEqual(len(records_a), 1)
        self.assertEqual(len(records_b), 1)

    def test_summary_counts(self) -> None:
        rid1 = self.service.start_run(case_id="test-4", operation="case_enrichment")
        rid2 = self.service.start_run(case_id="test-4", operation="legal_questions")
        self.service.complete_run(rid1, input_tokens=100, output_tokens=50)
        self.service.fail_run(rid2, error_code="AI_TIMEOUT")
        summary = self.service.summarize_case("test-4")
        self.assertEqual(summary.total_runs, 2)
        self.assertEqual(summary.completed, 1)
        self.assertEqual(summary.failed, 1)

    def test_purge_case(self) -> None:
        self.service.start_run(case_id="test-5", operation="case_enrichment")
        self.service.purge_case("test-5")
        records, _ = self.service.list_case_runs("test-5")
        self.assertEqual(len(records), 0)

    def test_no_raw_prompt_stored(self) -> None:
        rid = self.service.start_run(case_id="test-6", operation="case_enrichment", prompt_preview="Müvekkil TC 12345")
        record = self.service.get_run(rid)
        self.assertNotIn("Müvekkil TC", str(record))
        self.assertNotIn("12345", str(record))

    def test_run_id_unique(self) -> None:
        rid1 = self.service.start_run(case_id="test-7", operation="generic")
        rid2 = self.service.start_run(case_id="test-7", operation="generic")
        self.assertNotEqual(rid1, rid2)


class AIRunEndpointTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        from fastapi.testclient import TestClient
        from app.main import app
        from app.services.case_session_service import case_session_service
        from app.services.ai_run_service import ai_run_service
        cls.client = TestClient(app)
        cls.case_id = case_session_service.new_case()["case_id"]
        rid = ai_run_service.start_run(case_id=cls.case_id, operation="case_enrichment", model="deepseek-chat")
        ai_run_service.complete_run(rid, input_tokens=100, output_tokens=50)

    def test_list_runs_returns_data(self) -> None:
        response = self.client.get(f"/ai-runs/cases/{self.case_id}")
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.json()["total"], 0)

    def test_summary_endpoint(self) -> None:
        response = self.client.get(f"/ai-runs/cases/{self.case_id}/summary")
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.json().get("total_runs", 0), 0)

    def test_unknown_case_404(self) -> None:
        response = self.client.get("/ai-runs/cases/unknown-case")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
