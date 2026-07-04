"""P0.5.1 — Precedent authority regression tests."""

from __future__ import annotations

import unittest

from app.services.precedent_authority_service import (
    PrecedentAuthorityService,
    precedent_authority_service,
)


def _live_docket(esas, karar, court="Yargitay 3. HD", chamber="3. Hukuk Dairesi", date="01.01.2024"):
    return {"court": court, "chamber": chamber, "esas_no": esas, "karar_no": karar, "date": date, "title": f"Karar {esas}/{karar}"}


class PrecedentPetitionFilterTests(unittest.TestCase):

    def test_rejected_not_in_accepted_list(self) -> None:
        live = [_live_docket("2023/100", "2024/200")]
        authority = precedent_authority_service.build_authority(case_id="test-r1", live_results=live, brain_results=[])
        data = authority.model_dump(mode="json")
        pid = data["records"][0]["precedent_id"]
        precedent_authority_service.select_precedent(authority=data, precedent_id=pid, selected=False)
        accepted = [r for r in data["records"] if r.get("selection_status") == "accepted"]
        self.assertEqual(len(accepted), 0)

    def test_fallback_not_in_accepted(self) -> None:
        brain = [{"title": "Fallback", "court": ""}]
        authority = precedent_authority_service.build_authority(case_id="test-r2", live_results=[], brain_results=brain)
        accepted = [r for r in authority.records if r.selection_status == "accepted"]
        self.assertEqual(len(accepted), 0)

    def test_rejected_persists_across_rebuilds(self) -> None:
        live = [_live_docket("2023/300", "2024/400")]
        a1 = precedent_authority_service.build_authority(case_id="test-r3", live_results=live, brain_results=[])
        d1 = a1.model_dump(mode="json")
        pid = d1["records"][0]["precedent_id"]
        precedent_authority_service.select_precedent(authority=d1, precedent_id=pid, selected=False)
        a2 = precedent_authority_service.build_authority(case_id="test-r3", live_results=live, brain_results=[], existing=d1)
        self.assertEqual(a2.records[0].selection_status, "rejected")

    def test_accepted_verified_has_authoritative(self) -> None:
        live = [_live_docket("2023/500", "2024/600")]
        authority = precedent_authority_service.build_authority(case_id="test-r4", live_results=live, brain_results=[])
        self.assertEqual(authority.records[0].verification_status, "verified")
        self.assertEqual(authority.records[0].authority_status, "authoritative")

    def test_no_source_not_fallback_only(self) -> None:
        brain = [{"title": "LR", "court": "Yargitay 3. HD", "esas_no": "2023/700", "karar_no": "2024/800", "date": "01.01.2024", "detail_url": "https://example.com/karar"}]
        authority = precedent_authority_service.build_authority(case_id="test-r5", live_results=[], brain_results=brain)
        self.assertNotEqual(authority.records[0].authority_status, "fallback_only")

    def test_ai_cannot_set_authoritative(self) -> None:
        ai_rec = {"court": "Yargitay", "title": "AI onerisi", "source_type": "ai_suggested"}
        brain = [ai_rec]
        authority = precedent_authority_service.build_authority(case_id="test-r6", live_results=[], brain_results=brain)
        self.assertNotEqual(authority.records[0].authority_status, "authoritative")

    def test_canonical_key_unique_per_decision(self) -> None:
        from app.services.precedent_authority_service import build_canonical_key
        k1 = build_canonical_key(docket_number="2023/900", decision_number="2024/1000", decision_date="15.06.2024")
        k2 = build_canonical_key(docket_number="2023/900", decision_number="2024/1000", decision_date="15.06.2024")
        self.assertEqual(k1, k2)

    def test_case_isolation(self) -> None:
        from app.services.case_session_service import case_session_service
        case_a = case_session_service.new_case()["case_id"]
        case_b = case_session_service.new_case()["case_id"]
        live_a = [_live_docket("2023/aa1", "2024/aa1")]
        live_b = [_live_docket("2023/bb1", "2024/bb1")]
        authority_a = precedent_authority_service.build_authority(case_id=case_a, live_results=live_a, brain_results=[])
        authority_b = precedent_authority_service.build_authority(case_id=case_b, live_results=live_b, brain_results=[])
        case_session_service.update_case(case_a, precedent_authority=authority_a.model_dump(mode="json"))
        case_session_service.update_case(case_b, precedent_authority=authority_b.model_dump(mode="json"))
        state_b = case_session_service.get_case_state(case_b)
        records_b = state_b.get("precedent_authority", {}).get("records", [])
        dockets_b = [r.get("docket_number", "") for r in records_b]
        self.assertIn("2023/bb1", dockets_b)
        self.assertNotIn("2023/aa1", dockets_b)


if __name__ == "__main__":
    unittest.main()
