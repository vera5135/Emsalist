from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.case_session_service import CaseSessionService
from app.services.document_intake_service import DocumentIntakeService


FIXTURE = Path(__file__).parent / "fixtures" / "NOTER._TEST.txt"


class CaseIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.docs = DocumentIntakeService(Path(self.temporary.name) / "documents")
        self.cases = CaseSessionService(Path(self.temporary.name) / "cases")
        self.client = TestClient(app)
        self.patches = [
            patch("app.routes.case_routes.case_session_service", self.cases),
            patch("app.routes.document_routes.case_session_service", self.cases),
            patch("app.routes.document_routes.document_intake_service", self.docs),
            patch("app.routes.petition_routes.case_session_service", self.cases),
            patch("app.routes.petition_routes.document_intake_service", self.docs),
            patch("app.routes.ai_routes.case_session_service", self.cases),
            patch("app.routes.legal_brain_routes.case_session_service", self.cases),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.temporary.cleanup()

    def _new_case(self) -> str:
        response = self.client.post("/case/new")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["case_id"]

    def test_new_case_returns_unique_ids_and_starts_empty(self) -> None:
        case_a = self._new_case()
        case_b = self._new_case()

        self.assertNotEqual(case_a, case_b)

        state_b = self.client.get(f"/case/state?case_id={case_b}")
        self.assertEqual(state_b.status_code, 200, state_b.text)
        payload = state_b.json()
        self.assertEqual(payload["case_id"], case_b)
        self.assertEqual(payload["documents"], [])
        self.assertEqual(payload["document_facts"], [])
        self.assertEqual(payload["question_answers"], {})
        self.assertEqual(payload["final_precedents"], [])

    def test_case_b_does_not_see_case_a_document_or_fact(self) -> None:
        case_a = self._new_case()
        upload = self.client.post(
            "/documents/upload",
            files={"file": (FIXTURE.name, FIXTURE.read_bytes(), "text/plain")},
            data={"case_id": case_a},
        )
        self.assertEqual(upload.status_code, 200, upload.text)
        analyzed = self.client.post("/documents/analyze", json={"case_id": case_a})
        self.assertEqual(analyzed.status_code, 200, analyzed.text)

        case_b = self._new_case()
        documents_b = self.client.get(f"/documents?case_id={case_b}")
        self.assertEqual(documents_b.status_code, 200, documents_b.text)
        self.assertEqual(documents_b.json(), [])

        state_b = self.client.get(f"/case/state?case_id={case_b}")
        self.assertEqual(state_b.status_code, 200, state_b.text)
        self.assertEqual(state_b.json()["document_facts"], [])

    def test_question_answers_are_isolated_per_case(self) -> None:
        case_a = self._new_case()
        response_a = self.client.post(
            "/case/state",
            json={
                "case_id": case_a,
                "event_text": "AyÄ±plÄ± araÃ§ satÄ±ÅŸÄ± nedeniyle bedel iadesi talep ediliyor.",
                "question_answers": {"SatÄ±cÄ± galeri/tacir/ÅŸirket mi?": "Galeri/ÅŸirket"},
            },
        )
        self.assertEqual(response_a.status_code, 200, response_a.text)

        case_b = self._new_case()
        response_b = self.client.get(f"/case/state?case_id={case_b}")
        self.assertEqual(response_b.status_code, 200, response_b.text)
        self.assertEqual(response_b.json()["question_answers"], {})

    def test_final_draft_does_not_pull_precedent_from_another_case(self) -> None:
        case_a = self._new_case()
        self.cases.update_case(
            case_a,
            final_precedents=[
                {
                    "court": "YargÄ±tay 19. Hukuk Dairesi",
                    "esas_no": "2013/17670",
                    "karar_no": "2014/508",
                    "date": "15.01.2014",
                    "summary": "Case A emsali",
                    "petition_paragraph": "Case A emsali",
                    "source_type": "yargitay_live",
                    "official_verification_status": "verified_live",
                    "use_class": "direct_support",
                }
            ],
        )

        case_b = self._new_case()
        response = self.client.post(
            "/petition/final-draft",
            json={
                "case_id": case_b,
                "case_text": "KiracÄ±nÄ±n tahliyesi talep edilmektedir.",
                "request_type": "Tahliye",
                "writer_mode": "local",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        package = response.json()["drafting_package"]
        self.assertEqual(package["precedent_for_petition"], [])

    def test_final_draft_uses_only_its_case_facts(self) -> None:
        case_a = self._new_case()
        upload = self.client.post(
            "/documents/upload",
            files={"file": (FIXTURE.name, FIXTURE.read_bytes(), "text/plain")},
            data={"case_id": case_a},
        )
        document_id = upload.json()["document_id"]
        response_a = self.client.post(
            "/petition/final-draft",
            json={
                "case_id": case_a,
                "case_text": "AyÄ±plÄ± araÃ§ satÄ±ÅŸÄ± nedeniyle bedel iadesi isteniyor.",
                "request_type": "SatÄ±ÅŸ bedelinin iadesi",
                "document_ids": [document_id],
                "writer_mode": "local",
            },
        )
        self.assertEqual(response_a.status_code, 200, response_a.text)
        self.assertIn("Mehmet Demir", response_a.json()["petition_text"])

        case_b = self._new_case()
        response_b = self.client.post(
            "/petition/final-draft",
            json={
                "case_id": case_b,
                "case_text": "Kiraya verenin ihtiyaÃ§ nedeniyle tahliye talebi bulunuyor.",
                "request_type": "Tahliye",
                "writer_mode": "local",
            },
        )
        self.assertEqual(response_b.status_code, 200, response_b.text)
        self.assertNotIn("Mehmet Demir", response_b.json()["petition_text"])
        self.assertNotIn("Volkswagen Golf", response_b.json()["petition_text"])

    def test_missing_case_id_creates_or_uses_a_controlled_active_case(self) -> None:
        current = self.client.get("/case/current")
        self.assertEqual(current.status_code, 200, current.text)
        case_id = current.json()["case_id"]
        self.assertTrue(case_id.startswith("case_"))

        upload = self.client.post(
            "/documents/upload",
            files={"file": ("notes.txt", "SatÄ±ÅŸ bedeli: 100.000 TL".encode("utf-8"), "text/plain")},
        )
        self.assertEqual(upload.status_code, 200, upload.text)
        self.assertEqual(upload.json()["case_id"], case_id)


if __name__ == "__main__":
    unittest.main()
