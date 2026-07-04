"""P0.5 — Precedent authority tests."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.main import app
from app.services.case_session_service import case_session_service
from app.services.precedent_authority_service import (
    build_canonical_key,
    precedent_authority_service,
    _normalize_docket,
    _normalize_decision,
    _normalize_date,
)


class CanonicalKeyTests(unittest.TestCase):

    def test_same_decision_same_key(self) -> None:
        k1 = build_canonical_key(court="Yargıtay", chamber="3. Hukuk Dairesi", docket_number="2023/1234", decision_number="2024/5678", decision_date="16.05.2024")
        k2 = build_canonical_key(court="Yargıtay", chamber="3. Hukuk Dairesi", docket_number="2023/1234", decision_number="2024/5678", decision_date="2024-05-16")
        self.assertEqual(k1, k2)

    def test_different_decisions_different_keys(self) -> None:
        k1 = build_canonical_key(docket_number="2023/100", decision_number="2024/200")
        k2 = build_canonical_key(docket_number="2023/101", decision_number="2024/201")
        self.assertNotEqual(k1, k2)

    def test_docket_formats_normalize(self) -> None:
        self.assertEqual(_normalize_docket("E. 2023/1234"), "2023/1234")
        self.assertEqual(_normalize_docket("2023/1234 E."), "2023/1234")
        self.assertEqual(_normalize_docket("Esas No: 2023/5678"), "2023/5678")

    def test_decision_formats_normalize(self) -> None:
        self.assertEqual(_normalize_decision("K. 2024/5678"), "2024/5678")
        self.assertEqual(_normalize_decision("Karar No: 2024/5678"), "2024/5678")

    def test_date_formats_normalize(self) -> None:
        self.assertEqual(_normalize_date("16.05.2024"), "2024-05-16")
        self.assertEqual(_normalize_date("2024-05-16"), "2024-05-16")
        self.assertEqual(_normalize_date("16/05/2024"), "2024-05-16")


class PrecedentAuthorityServiceTests(unittest.TestCase):

    def test_live_results_become_accepted_verified(self) -> None:
        live = [{"court": "Yargıtay 3. HD", "chamber": "3. Hukuk Dairesi", "esas_no": "2023/1234", "karar_no": "2024/5678", "date": "16.05.2024", "title": "Test karar"}]
        authority = precedent_authority_service.build_authority(case_id="test-1", live_results=live, brain_results=[])
        self.assertEqual(len(authority.records), 1)
        self.assertEqual(authority.records[0].verification_status, "verified")
        self.assertEqual(authority.records[0].authority_status, "authoritative")
        self.assertEqual(authority.records[0].selection_status, "accepted")

    def test_brain_results_unverified(self) -> None:
        brain = [{"title": "Legal Brain karar", "court": "Yargıtay"}]
        authority = precedent_authority_service.build_authority(case_id="test-2", live_results=[], brain_results=brain)
        self.assertEqual(len(authority.records), 1)
        self.assertEqual(authority.records[0].verification_status, "unverified")

    def test_duplicate_detection(self) -> None:
        live = [
            {"court": "Yargıtay", "chamber": "3. HD", "esas_no": "2023/100", "karar_no": "2024/200", "date": "01.01.2024"},
            {"court": "Yargıtay", "chamber": "3. HD", "esas_no": "2023/100", "karar_no": "2024/200", "date": "01.01.2024"},
        ]
        authority = precedent_authority_service.build_authority(case_id="test-3", live_results=live, brain_results=[])
        self.assertEqual(len(authority.records), 1)

    def test_fallback_not_authoritative(self) -> None:
        brain = [{"title": "fallback", "court": ""}]
        authority = precedent_authority_service.build_authority(case_id="test-4", live_results=[], brain_results=brain)
        self.assertNotEqual(authority.records[0].authority_status, "authoritative")

    def test_select_precedent(self) -> None:
        live = [{"court": "Yargıtay", "esas_no": "2023/999", "karar_no": "2024/888", "date": "01.01.2024"}]
        authority = precedent_authority_service.build_authority(case_id="test-5", live_results=live, brain_results=[])
        authority_data = authority.model_dump(mode="json")
        pid = authority_data["records"][0]["precedent_id"]
        updated = precedent_authority_service.select_precedent(authority=authority_data, precedent_id=pid, selected=False, reason="test")
        self.assertEqual(updated["records"][0]["selection_status"], "rejected")
        self.assertIn(pid, updated["rejected_ids"])

    def test_unknown_precedent_raises(self) -> None:
        with self.assertRaises(KeyError):
            precedent_authority_service.select_precedent(authority={"records": []}, precedent_id="nonexistent", selected=True)

    def test_rejected_in_existing_stays_rejected(self) -> None:
        live = [{"court": "Yargıtay", "esas_no": "2023/777", "karar_no": "2024/666", "date": "01.01.2024"}]
        authority1 = precedent_authority_service.build_authority(case_id="test-6", live_results=live, brain_results=[])
        data1 = authority1.model_dump(mode="json")
        pid = data1["records"][0]["precedent_id"]
        precedent_authority_service.select_precedent(authority=data1, precedent_id=pid, selected=False)
        authority2 = precedent_authority_service.build_authority(case_id="test-6", live_results=live, brain_results=[], existing=data1)
        self.assertEqual(authority2.records[0].selection_status, "rejected")


class PrecedentEndpointTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        cls.case_id = case_session_service.new_case()["case_id"]
        live = [{"court": "Yargıtay 3. HD", "esas_no": "2023/5000", "karar_no": "2024/4000", "date": "01.01.2024"}]
        authority = precedent_authority_service.build_authority(case_id=cls.case_id, live_results=live, brain_results=[])
        case_session_service.update_case(cls.case_id, precedent_authority=authority.model_dump(mode="json"))

    def test_get_authority_returns_records(self) -> None:
        response = self.client.get(f"/precedents/authority/{self.case_id}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data.get("authority", {}).get("records", [])), 0)

    def test_get_unknown_case_returns_404(self) -> None:
        response = self.client.get("/precedents/authority/bilinmeyen-dosya")
        self.assertEqual(response.status_code, 404)

    def test_select_unknown_precedent_returns_404(self) -> None:
        response = self.client.post("/precedents/select", json={
            "case_id": self.case_id,
            "precedent_id": "nonexistent",
            "selected": False,
        })
        self.assertEqual(response.status_code, 404)

    def test_select_valid_precedent(self) -> None:
        authority = case_session_service.get_case_state(self.case_id).get("precedent_authority", {})
        pid = authority.get("records", [{}])[0].get("precedent_id", "")
        response = self.client.post("/precedents/select", json={
            "case_id": self.case_id,
            "precedent_id": pid,
            "selected": False,
            "reason": "test rejection",
        })
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
