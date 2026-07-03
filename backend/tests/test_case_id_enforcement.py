from __future__ import annotations

import unittest

from fastapi import HTTPException

from app.services.case_session_service import case_session_service


class CaseIdEnforcementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case_id = case_session_service.new_case()["case_id"]

    def test_require_existing_accepts_known_id(self) -> None:
        self.assertEqual(
            case_session_service.require_existing_case(self.case_id),
            self.case_id,
        )

    def test_require_existing_rejects_unknown_id_with_404(self) -> None:
        with self.assertRaises(HTTPException) as context:
            case_session_service.require_existing_case("nonexistent-case-99999")
        self.assertEqual(context.exception.status_code, 404)

    def test_resolve_without_requirement_can_create_unknown_id(self) -> None:
        fake_id = "fresh-auto-created-case"
        self.assertEqual(
            case_session_service.resolve_case_id(fake_id, require_existing=False),
            fake_id,
        )

    def test_cross_case_data_isolation(self) -> None:
        case_a = case_session_service.new_case()["case_id"]
        case_b = case_session_service.new_case()["case_id"]

        case_session_service.update_case(
            case_a,
            event_text="kira davasi",
            legal_topic="kira",
        )
        case_session_service.update_case(
            case_b,
            event_text="isci davasi",
            legal_topic="iscilik",
        )

        state_a = case_session_service.get_case_state(case_a)
        state_b = case_session_service.get_case_state(case_b)

        self.assertEqual(state_a.get("legal_topic"), "kira")
        self.assertEqual(state_b.get("legal_topic"), "iscilik")
        self.assertNotEqual(state_a.get("event_text"), state_b.get("event_text"))

    def test_resolve_existing_case_sets_active_for_legacy_flows(self) -> None:
        case_x = case_session_service.new_case()["case_id"]
        case_session_service.resolve_case_id(case_x, require_existing=True)
        self.assertEqual(case_session_service.resolve_case_id(None), case_x)


if __name__ == "__main__":
    unittest.main()
