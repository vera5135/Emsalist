from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.ai_models import WorkflowReviewRequest
from app.services.case_session_service import CaseSessionService
from app.services import case_session_service as case_session_module
from app.services.review_workflow_service import review_workflow_service


def _make_request(case_id: str, request_id: str = "test-req-1"):
    return {
        "case_id": case_id,
        "request_id": request_id,
        "case_text": "Müvekkil ikinci el aracı galeriden satın aldı motor arızası çıktı satıcıya bildirildi sözleşmeden dönme ve bedel iadesi talep edilmektedir",
        "practice_area": "auto",
        "max_yargitay_results": 2,
        "use_ai": False,
        "use_legal_brain": False,
    }


MOCK_YARGITAY_RESULT = {
    "top_decisions": [],
    "final_precedents": [],
    "live_yargitay_results": [],
    "fallback_precedents": [],
    "final_precedent_count": 0,
    "final_live_result_count": 0,
    "source_summary": {"used_fallback": False},
    "errors": [],
    "case_analysis": {"legal_topic": "test"},
    "queries": [],
}


class WorkflowReviewEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.cases = CaseSessionService(Path(self.temporary.name) / "workflow-cases")
        self.patches = [
            patch("app.routes.workflow_routes.case_session_service", self.cases),
            patch("app.services.review_workflow_service.case_session_service", self.cases),
        ]
        for item in self.patches:
            item.start()
        self.client = TestClient(app)
        self.case_a = self.cases.new_case()["case_id"]
        self.case_b = self.cases.new_case()["case_id"]

    def tearDown(self) -> None:
        self.client.close()
        for item in reversed(self.patches):
            item.stop()
        self.temporary.cleanup()

    def test_missing_case_id_returns_422(self) -> None:
        response = self.client.post("/workflow/review", json={
            "request_id": "r1",
            "case_text": "valid case text with enough length for validation",
        })
        self.assertEqual(response.status_code, 422)

    def test_unknown_case_id_returns_404(self) -> None:
        response = self.client.post("/workflow/review", json=_make_request("bilinmeyen-dosya-99999", "r2"))
        self.assertEqual(response.status_code, 404)

    def test_valid_request_completes(self) -> None:
        with patch("app.services.review_workflow_service.research_service.research_yargitay", new_callable=AsyncMock) as mock_yargitay:
            mock_yargitay.return_value = dict(MOCK_YARGITAY_RESULT)
            response = self.client.post("/workflow/review", json=_make_request(self.case_a, "wf-complete-3"))
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIn(data["status"], ("completed", "partial_success"))

    def test_valid_request_includes_analysis_and_enrichment(self) -> None:
        with patch("app.services.review_workflow_service.research_service.research_yargitay", new_callable=AsyncMock) as mock_yargitay:
            mock_yargitay.return_value = dict(MOCK_YARGITAY_RESULT)
            response = self.client.post("/workflow/review", json=_make_request(self.case_a, "wf-full-3"))
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertIn("legal_topic", data.get("analysis", {}))
            self.assertIn("detected_case_type", data.get("enrichment", {}))

    def test_use_ai_false_runs_deterministic(self) -> None:
        with patch("app.services.review_workflow_service.research_service.research_yargitay", new_callable=AsyncMock) as mock_yargitay:
            mock_yargitay.return_value = dict(MOCK_YARGITAY_RESULT)
            response = self.client.post("/workflow/review", json=_make_request(self.case_a, "wf-det-3"))
            self.assertEqual(response.status_code, 200)

    def test_same_request_id_with_same_fingerprint_returns_cached(self) -> None:
        rid = "wf-cache-test-3"
        with patch("app.services.review_workflow_service.research_service.research_yargitay", new_callable=AsyncMock) as mock_yargitay:
            mock_yargitay.return_value = dict(MOCK_YARGITAY_RESULT)
            first = self.client.post("/workflow/review", json=_make_request(self.case_a, rid))
            self.assertEqual(first.status_code, 200)

            second = self.client.post("/workflow/review", json=_make_request(self.case_a, rid))
            self.assertEqual(second.status_code, 200)
            self.assertTrue(second.json().get("cached", False))
            self.assertEqual(mock_yargitay.call_count, 1)

    def test_same_request_id_different_case_text_returns_409(self) -> None:
        rid = "wf-conflict-3"
        with patch("app.services.review_workflow_service.research_service.research_yargitay", new_callable=AsyncMock) as mock_yargitay:
            mock_yargitay.return_value = dict(MOCK_YARGITAY_RESULT)
            body = _make_request(self.case_a, rid)
            self.client.post("/workflow/review", json=body)

            body["case_text"] = "tamamen farklı bir dava metni kiracı kira bedelini ödemiyor ve evden çıkmıyor ihtar çekildi tahliye talep ediliyor"
            response = self.client.post("/workflow/review", json=body)
            self.assertEqual(response.status_code, 409)

    def test_yargitay_failure_produces_partial_success(self) -> None:
        with patch("app.services.review_workflow_service.research_service.research_yargitay", new_callable=AsyncMock) as mock_yargitay:
            mock_yargitay.side_effect = Exception("yargitay down")
            response = self.client.post("/workflow/review", json=_make_request(self.case_a, "wf-yarg-3"))
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["status"], "partial_success")

    def test_issue_graph_stored_in_session(self) -> None:
        with patch("app.services.review_workflow_service.research_service.research_yargitay", new_callable=AsyncMock) as mock_yargitay:
            mock_yargitay.return_value = dict(MOCK_YARGITAY_RESULT)
            response = self.client.post("/workflow/review", json=_make_request(self.case_a, "wf-graph-3"))
            self.assertEqual(response.status_code, 200)
            state = self.cases.get_case_state(self.case_a)
            self.assertIn("legal_issue_graph", state)

    def test_workflow_result_stored_only_under_correct_case(self) -> None:
        with patch("app.services.review_workflow_service.research_service.research_yargitay", new_callable=AsyncMock) as mock_yargitay:
            mock_yargitay.return_value = dict(MOCK_YARGITAY_RESULT)
            self.client.post("/workflow/review", json=_make_request(self.case_a, "wf-iso-3"))
        state_b = self.cases.get_case_state(self.case_b)
        enrichment_b = state_b.get("case_enrichment", {})
        self.assertFalse(
            enrichment_b.get("detected_case_type") or enrichment_b.get("legal_theory"),
            "case_b should not have enrichment data from case_a",
        )

    def test_workflow_persists_one_canonical_graph_snapshot(self) -> None:
        with patch("app.services.review_workflow_service.research_service.research_yargitay", new_callable=AsyncMock) as mock_yargitay:
            mock_yargitay.return_value = dict(MOCK_YARGITAY_RESULT)
            response = self.client.post("/workflow/review", json=_make_request(self.case_a, "wf-canonical-p03"))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        stored = self.cases.get_case_state(self.case_a)
        graph = data["issue_graph"]

        self.assertTrue(graph["canonical"])
        self.assertEqual(graph, stored["legal_issue_graph"])
        self.assertEqual(graph, stored["case_state"]["legal_issue_graph"])
        self.assertEqual(data["summary"]["risk_count"], len(graph["global_risks"]))
        self.assertEqual(data["summary"]["question_count"], len(graph["next_best_questions"]))
        self.assertEqual(data["better_searches"]["canonical_research_plan"], graph["research_plan"])

    def test_same_workflow_request_is_stable_across_three_calls(self) -> None:
        request_id = "stable-three-calls"
        with patch("app.services.review_workflow_service.research_service.research_yargitay", new_callable=AsyncMock) as mock_yargitay:
            mock_yargitay.return_value = dict(MOCK_YARGITAY_RESULT)
            responses = [
                self.client.post("/workflow/review", json=_make_request(self.case_a, request_id))
                for _ in range(3)
            ]

        self.assertTrue(all(response.status_code == 200 for response in responses))
        payloads = [response.json() for response in responses]
        self.assertEqual([item["status"] for item in payloads], [payloads[0]["status"]] * 3)
        self.assertEqual([item["cached"] for item in payloads], [False, True, True])
        self.assertEqual(payloads[0]["issue_graph"], payloads[1]["issue_graph"])
        self.assertEqual(payloads[1]["issue_graph"], payloads[2]["issue_graph"])
        self.assertEqual(mock_yargitay.call_count, 1)

    def test_completed_request_id_from_another_service_is_not_a_cache_hit(self) -> None:
        request_id = "isolated-completed-request"
        with patch("app.services.review_workflow_service.research_service.research_yargitay", new_callable=AsyncMock) as mock_yargitay:
            mock_yargitay.return_value = dict(MOCK_YARGITAY_RESULT)
            first = self.client.post("/workflow/review", json=_make_request(self.case_a, request_id))
        self.assertEqual(first.status_code, 200)

        with tempfile.TemporaryDirectory() as directory:
            other_cases = CaseSessionService(Path(directory) / "other-cases")
            other_case_id = other_cases.new_case()["case_id"]
            with (
                patch("app.routes.workflow_routes.case_session_service", other_cases),
                patch("app.services.review_workflow_service.case_session_service", other_cases),
                patch("app.services.review_workflow_service.research_service.research_yargitay", new_callable=AsyncMock) as other_yargitay,
            ):
                other_yargitay.return_value = dict(MOCK_YARGITAY_RESULT)
                with TestClient(app) as other_client:
                    second = other_client.post("/workflow/review", json=_make_request(other_case_id, request_id))

        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()["cached"])
        self.assertEqual(other_yargitay.call_count, 1)

    def test_workflow_service_uses_non_production_state_path(self) -> None:
        production_path = Path(case_session_module.__file__).resolve().parents[1] / "case_store"
        self.assertNotEqual(self.cases.storage_dir.resolve(), production_path.resolve())

    def test_cache_fingerprint_covers_validation_context(self) -> None:
        request = WorkflowReviewRequest(**_make_request(self.case_a, "fingerprint-context"))
        base = review_workflow_service._fingerprint(
            request,
            graph_source_fingerprint="graph-a",
            normalized_citations=["TBK:m.219"],
            profile_id="defective_vehicle",
        )
        changed_graph = review_workflow_service._fingerprint(
            request,
            graph_source_fingerprint="graph-b",
            normalized_citations=["TBK:m.219"],
            profile_id="defective_vehicle",
        )
        changed_citation = review_workflow_service._fingerprint(
            request,
            graph_source_fingerprint="graph-a",
            normalized_citations=["TBK:m.223"],
            profile_id="defective_vehicle",
        )
        changed_event_date = review_workflow_service._fingerprint(
            request.model_copy(update={"event_date": "2026-07-04"}),
            graph_source_fingerprint="graph-a",
            normalized_citations=["TBK:m.219"],
            profile_id="defective_vehicle",
        )
        changed_profile = review_workflow_service._fingerprint(
            request,
            graph_source_fingerprint="graph-a",
            normalized_citations=["TBK:m.219"],
            profile_id="generic",
        )
        with patch("app.services.review_workflow_service.legal_ground_validator_service.REGISTRY_VERSION", "next-registry"):
            changed_registry = review_workflow_service._fingerprint(
                request,
                graph_source_fingerprint="graph-a",
                normalized_citations=["TBK:m.219"],
                profile_id="defective_vehicle",
            )

        self.assertEqual(len({base, changed_graph, changed_citation, changed_event_date, changed_profile, changed_registry}), 6)


if __name__ == "__main__":
    unittest.main()
