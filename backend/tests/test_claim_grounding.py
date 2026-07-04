"""P0.6 — Claim grounding tests."""

from __future__ import annotations

import unittest

from app.services.claim_grounding_service import claim_grounding_service, _classify_claim_type


class ClaimGroundingServiceTests(unittest.TestCase):

    def test_factual_claim_detected(self) -> None:
        self.assertEqual(_classify_claim_type("Müvekkil aracı satın almıştır."), "factual")

    def test_legal_claim_detected(self) -> None:
        self.assertEqual(_classify_claim_type("TBK m.219 uyarınca satıcı sorumludur."), "legal")

    def test_precedent_claim_detected(self) -> None:
        self.assertEqual(_classify_claim_type("Yargıtay Hukuk Genel Kurulu E. 2018/436 K. 2021/1717 sayılı kararı emsal alınmıştır"), "precedent")

    def test_relief_claim_detected(self) -> None:
        self.assertEqual(_classify_claim_type("Davanın kabulüne karar verilmesini talep ederiz saygıyla arz olunur"), "relief")

    def test_parse_produces_claims(self) -> None:
        state = {"case_enrichment": {"confirmed_facts": ["Müvekkil aracı satın almıştır"]}}
        result = claim_grounding_service.analyze(
            case_id="test-1",
            petition_text="Müvekkil aracı satın almıştır. TBK m.219 uyarınca satıcı sorumludur. Davanın kabulüne karar verilmesini talep ederiz.",
            case_state=state,
        )
        self.assertGreater(len(result.claims), 0)

    def test_grounding_with_verified_sources(self) -> None:
        state = {"case_enrichment": {"confirmed_facts": ["Müvekkil aracı satın almıştır"]}}
        result = claim_grounding_service.analyze(
            case_id="test-2",
            petition_text="Müvekkil aracı satın almıştır.",
            case_state=state,
        )
        grounded = [c for c in result.claims if c.status == "grounded"]
        self.assertGreater(len(grounded), 0)

    def test_empty_petition_produces_no_claims(self) -> None:
        result = claim_grounding_service.analyze(
            case_id="test-3",
            petition_text="Kısa.",
        )
        self.assertEqual(len(result.claims), 0)

    def test_summary_counts(self) -> None:
        result = claim_grounding_service.analyze(
            case_id="test-4",
            petition_text="Müvekkil aracı satın almıştır. Motor arızası çıkmıştır.",
        )
        self.assertIn("total", result.summary)

    def test_fingerprint_cache_hit(self) -> None:
        text = "Müvekkil aracı satın almıştır."
        state = {"case_enrichment": {"confirmed_facts": ["Müvekkil aracı satın almıştır"]}}
        r1 = claim_grounding_service.analyze(case_id="test-5", petition_text=text, case_state=state)
        r2 = claim_grounding_service.analyze(case_id="test-5", petition_text=text, case_state=state, existing=r1.model_dump(mode="json"))
        self.assertEqual(r1.grounding_ready, r2.grounding_ready)

    def test_cross_case_sources_not_matched(self) -> None:
        state = {"case_enrichment": {"confirmed_facts": ["B davası metni"]}}
        result = claim_grounding_service.analyze(
            case_id="test-A",
            petition_text="A davasına ait metin burada yazılıdır.",
            case_state=state,
        )
        for claim in result.claims:
            for src in claim.source_refs:
                self.assertEqual(src.case_id, "test-A")

    def test_unsupported_claim_detected(self) -> None:
        result = claim_grounding_service.analyze(
            case_id="test-6",
            petition_text="Tamamen kaynaksız bir iddia metni buraya yazılmıştır.",
        )
        unsupported = [c for c in result.claims if c.status == "unsupported"]
        self.assertGreater(len(unsupported), 0)

    def test_grounding_ready_when_no_contradictions(self) -> None:
        state = {"case_enrichment": {"confirmed_facts": ["Müvekkil aracı satın almıştır"]}}
        result = claim_grounding_service.analyze(
            case_id="test-7",
            petition_text="Müvekkil aracı satın almıştır.",
            case_state=state,
        )
        self.assertTrue(result.grounding_ready)


class GroundingEndpointTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        from fastapi.testclient import TestClient
        from app.main import app
        from app.services.case_session_service import case_session_service
        cls.client = TestClient(app)
        cls.case_id = case_session_service.new_case()["case_id"]

    def test_missing_case_id_returns_422(self) -> None:
        response = self.client.post("/grounding/analyze", json={"petition_text": "Müvekkil aracı satın almıştır."})
        self.assertEqual(response.status_code, 422)

    def test_unknown_case_id_returns_404(self) -> None:
        response = self.client.post("/grounding/analyze", json={"case_id": "nonexistent", "petition_text": "Müvekkil aracı satın almıştır."})
        self.assertEqual(response.status_code, 404)

    def test_valid_request_returns_grounding(self) -> None:
        response = self.client.post("/grounding/analyze", json={"case_id": self.case_id, "petition_text": "Müvekkil aracı satın almıştır."})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("grounding", data)
        self.assertIn("summary", data)

    def test_get_grounding_returns_stored(self) -> None:
        self.client.post("/grounding/analyze", json={"case_id": self.case_id, "petition_text": "Müvekkil aracı satın almıştır."})
        response = self.client.get(f"/grounding/{self.case_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("grounding", data)


if __name__ == "__main__":
    unittest.main()
