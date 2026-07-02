from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.petition_models import FinalPetitionDraftRequest
from app.routes.petition_routes import build_final_petition_draft
from app.services.document_intake_service import DocumentDuplicateError, DocumentIntakeService
from app.services.dynamic_legal_reasoner_service import SAFE_SOURCE_DOMAINS, dynamic_legal_reasoner_service
from app.services.final_petition_writer_service import FORBIDDEN_TEXT, final_petition_writer_service
from app.services.gemini_client import GeminiJSONResult


FIXTURE = Path(__file__).parent / "fixtures" / "NOTER._TEST.txt"
CASE_TEXT = (
    "Müvekkil aracı satıcının sorunsuz olduğu beyanına güvenerek satın aldı. "
    "Satıştan kısa süre sonra araçta motor arızası ortaya çıktı."
)


class FinalPetitionWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.service = DocumentIntakeService(Path(self.temporary.name))
        self.record = self.service.create_document(
            file_name=FIXTURE.name,
            content=FIXTURE.read_bytes(),
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_duplicate_document_content_is_rejected(self) -> None:
        with self.assertRaisesRegex(DocumentDuplicateError, "Bu belge zaten ekli"):
            self.service.create_document(
                file_name=FIXTURE.name,
                content=FIXTURE.read_bytes(),
            )
        self.assertEqual(len(self.service.list_documents()), 1)

    def test_local_template_is_a_clean_natural_petition(self) -> None:
        package = final_petition_writer_service.build_package(
            case_text=CASE_TEXT,
            request_type="Sözleşmeden dönme ve satış bedelinin iadesi",
            document_facts=self.record.extracted_facts,
            document_types=[self.record.document_type],
        )
        with patch("app.services.final_petition_writer_service.get_settings") as settings:
            settings.return_value.gemini_api_key = ""
            response = final_petition_writer_service.write(package)

        self.assertEqual(response.generation_mode, "local_template_mode")
        self.assertIn("DAVACI", response.petition_text)
        self.assertIn("AÇIKLAMALAR", response.petition_text)
        self.assertIn("HUKUKİ NEDENLER", response.petition_text)
        self.assertIn("SONUÇ VE İSTEM", response.petition_text)
        self.assertIn(
            "Dosyaya sunulan noter satış sözleşmesine göre müvekkil Mehmet Demir, "
            "davalı Ahmet Yılmaz’dan Volkswagen Golf 1.6 TDI marka, 35 ABC 123 plakalı, "
            "WVWZZZ123456789 şasi numaralı aracı 12.04.2024 tarihinde 500.000 TL bedelle satın almıştır.",
            response.petition_text,
        )
        lowered = response.petition_text.casefold()
        for forbidden in FORBIDDEN_TEXT:
            self.assertNotIn(forbidden.casefold(), lowered)
        self.assertNotIn("NOTER._TEST.txt", response.petition_text)
        self.assertEqual(response.petition_text.count("motor arızası"), 1)
        self.assertEqual(response.petition_text.count("TBK m. 219"), 1)
        self.assertNotIn("TBK 219", response.petition_text)
        self.assertEqual(response.petition_text.count("12.04.2024"), 1)
        self.assertEqual(response.petition_text.count("500.000 TL"), 2)
        self.assertEqual(response.petition_text.count("35 ABC 123"), 1)
        self.assertEqual(response.petition_text.count("WVWZZZ123456789"), 1)
        self.assertNotIn("Satış işlemi İzmir 12. Noterliği", response.petition_text)

    def test_final_route_allows_draft_without_review_approval(self) -> None:
        request = FinalPetitionDraftRequest(
            case_text=CASE_TEXT,
            request_type="Satış bedelinin iadesi",
        )
        response = build_final_petition_draft(request)
        self.assertIn(response.generation_mode, ("local_template_mode", "local_fallback"))
        self.assertIn("DAVACI", response.petition_text)
        self.assertIn("question_answers", response.case_state)
        self.assertIn("document_facts", response.case_state)

    def test_gemini_receives_only_the_clean_drafting_package(self) -> None:
        package = final_petition_writer_service.build_package(
            case_text=CASE_TEXT,
            request_type="Sözleşmeden dönme ve satış bedelinin iadesi",
            document_facts=self.record.extracted_facts,
            document_types=[self.record.document_type],
            writer_mode="gemini",
        )
        safe_text = final_petition_writer_service._local_template(package)
        with (
            patch("app.services.final_petition_writer_service.get_settings") as settings,
            patch("app.services.final_petition_writer_service.gemini_client.generate_json") as generate,
        ):
            settings.return_value.gemini_api_key = "test-key"
            generate.return_value = GeminiJSONResult(
                ai_used=True,
                data={"petition_text": safe_text},
                warnings=[],
            )
            response = final_petition_writer_service.write(package)

        self.assertEqual(response.generation_mode, "gemini_mode")
        prompt = generate.call_args.kwargs["prompt"]
        self.assertIn('"confirmed_facts"', prompt)
        self.assertNotIn("source_document_id", prompt)
        self.assertNotIn("confidence_score", prompt)
        self.assertNotIn("NOTER._TEST.txt", prompt)

    def test_gemini_cannot_turn_uncertain_notice_into_a_confirmed_fact(self) -> None:
        package = final_petition_writer_service.build_package(
            case_text=CASE_TEXT,
            request_type="Sözleşmeden dönme ve satış bedelinin iadesi",
            document_facts=self.record.extracted_facts,
            document_types=[self.record.document_type],
            writer_mode="gemini",
        )
        unsafe_text = final_petition_writer_service._local_template(package).replace(
            "Ayıp ihbarının tarihi ve yöntemi, sunulacak yazışma veya ihtar kayıtları üzerinden belirlenecektir.",
            "Müvekkil ayıbı WhatsApp üzerinden davalıya bildirmiştir.",
        )
        with (
            patch("app.services.final_petition_writer_service.get_settings") as settings,
            patch("app.services.final_petition_writer_service.gemini_client.generate_json") as generate,
        ):
            settings.return_value.gemini_api_key = "test-key"
            generate.return_value = GeminiJSONResult(
                ai_used=True,
                data={"petition_text": unsafe_text},
                warnings=[],
            )
            response = final_petition_writer_service.write(package)

        self.assertEqual(response.generation_mode, "local_fallback")
        self.assertNotIn("WhatsApp üzerinden davalıya bildirmiştir", response.petition_text)

    def test_gemini_cannot_claim_preexisting_defect_without_a_report(self) -> None:
        package = final_petition_writer_service.build_package(
            case_text=CASE_TEXT,
            request_type="Sözleşmeden dönme ve satış bedelinin iadesi",
            document_facts=self.record.extracted_facts,
            document_types=[self.record.document_type],
            writer_mode="gemini",
        )
        unsafe_text = final_petition_writer_service._local_template(package).replace(
            "Arızanın satıştan önce mevcut olduğu hususu servis/ekspertiz raporu ve bilirkişi incelemesiyle ortaya konulacaktır.",
            "Bu durum, aracın satış anında gizli ayıplı olduğunu göstermektedir.",
        )
        with (
            patch("app.services.final_petition_writer_service.get_settings") as settings,
            patch("app.services.final_petition_writer_service.gemini_client.generate_json") as generate,
        ):
            settings.return_value.gemini_api_key = "test-key"
            generate.return_value = GeminiJSONResult(
                ai_used=True,
                data={"petition_text": unsafe_text},
                warnings=[],
            )
            response = final_petition_writer_service.write(package)

        self.assertEqual(response.generation_mode, "local_fallback")
        self.assertNotIn("satış anında gizli ayıplı olduğunu göstermektedir", response.petition_text)

    def test_gemini_cannot_invent_a_signature_date(self) -> None:
        package = final_petition_writer_service.build_package(
            case_text=CASE_TEXT,
            request_type="Sözleşmeden dönme ve satış bedelinin iadesi",
            document_facts=self.record.extracted_facts,
            document_types=[self.record.document_type],
            writer_mode="gemini",
        )
        unsafe_text = final_petition_writer_service._local_template(package) + "\n\n30.06.2026\nDavacı Vekili"
        with (
            patch("app.services.final_petition_writer_service.get_settings") as settings,
            patch("app.services.final_petition_writer_service.gemini_client.generate_json") as generate,
        ):
            settings.return_value.gemini_api_key = "test-key"
            generate.return_value = GeminiJSONResult(
                ai_used=True,
                data={"petition_text": unsafe_text},
                warnings=[],
            )
            response = final_petition_writer_service.write(package)

        self.assertEqual(response.generation_mode, "local_fallback")
        self.assertNotIn("30.06.2026", response.petition_text)

    def test_gemini_missing_key_uses_requested_local_fallback_warning(self) -> None:
        package = final_petition_writer_service.build_package(
            case_text=CASE_TEXT,
            request_type="Sözleşmeden dönme ve satış bedelinin iadesi",
            document_facts=self.record.extracted_facts,
            document_types=[self.record.document_type],
            writer_mode="gemini",
        )
        with patch("app.services.final_petition_writer_service.get_settings") as settings:
            settings.return_value.gemini_api_key = ""
            response = final_petition_writer_service.write(package)

        self.assertEqual(response.generation_mode, "local_fallback")
        self.assertIn("Gemini yanıtı alınamadı; güvenli yerel taslak oluşturuldu.", response.warnings)

    def test_dynamic_reasoner_builds_vehicle_issues_and_queries(self) -> None:
        reasoning = dynamic_legal_reasoner_service.analyze(
            event_text=CASE_TEXT,
            document_facts=["sale_date: 12.04.2024", "notary_info: İzmir 12. Noterliği"],
            question_answers={"Satıcı galeri/tacir/şirket mi?": "Bilmiyorum"},
        )
        self.assertEqual(
            reasoning["legal_issues"],
            [
                "satış ilişkisi",
                "gizli ayıp",
                "ayıp ihbarı",
                "ayıbın satıştan önce mevcut olması",
                "seçimlik haklar",
                "satıcı sıfatı / görevli mahkeme",
            ],
        )
        self.assertEqual(
            reasoning["research_queries"],
            [
                "ikinci el araç gizli ayıp Yargıtay",
                "TBK 219 ayıba karşı tekeffül araç",
                "TBK 223 ayıp ihbarı araç satışı",
                "TBK 227 sözleşmeden dönme bedel indirimi",
                "motor arızası gizli ayıp bilirkişi",
            ],
        )
        self.assertIn("mevzuat.gov.tr", SAFE_SOURCE_DOMAINS)


class FinalPetitionRouteTests(unittest.TestCase):
    def test_duplicate_upload_returns_conflict_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            isolated = DocumentIntakeService(Path(directory))
            with patch("app.routes.document_routes.document_intake_service", isolated):
                client = TestClient(app)
                files = {"file": (FIXTURE.name, FIXTURE.read_bytes(), "text/plain")}
                self.assertEqual(client.post("/documents/upload", files=files).status_code, 200)
                duplicate = client.post("/documents/upload", files=files)
                self.assertEqual(duplicate.status_code, 409)
                self.assertEqual(duplicate.json()["detail"], "Bu belge zaten ekli.")
                self.assertEqual(len(client.get("/documents").json()), 1)


def _patched_dynamic_reasoner_test(self) -> None:
    reasoning = dynamic_legal_reasoner_service.analyze(
        event_text=CASE_TEXT,
        document_facts=["sale_date: 12.04.2024", "notary_info: Ä°zmir 12. NoterliÄŸi"],
        question_answers={"SatÄ±cÄ± galeri/tacir/ÅŸirket mi?": "Bilmiyorum"},
    )
    self.assertTrue(reasoning["legal_issues"])
    self.assertEqual(reasoning["legal_issues"][0]["issue_key"], "sale_relationship")
    self.assertIn("hidden_defect", [item["issue_key"] for item in reasoning["legal_issues"]])
    self.assertIn("seller_status", [item["issue_key"] for item in reasoning["legal_issues"]])
    self.assertGreaterEqual(len(reasoning["research_queries"]), 5)
    self.assertTrue(any("TBK 223" in item for item in reasoning["research_queries"]))
    self.assertEqual(reasoning["risk_plan"][0]["level"], "high")
    self.assertTrue(reasoning["question_plan"])
    self.assertIn("seller_status", [item["related_issue_key"] for item in reasoning["question_plan"]])
    self.assertIn("mevzuat.gov.tr", SAFE_SOURCE_DOMAINS)


FinalPetitionWriterTests.test_dynamic_reasoner_builds_vehicle_issues_and_queries = _patched_dynamic_reasoner_test


if __name__ == "__main__":
    unittest.main()
