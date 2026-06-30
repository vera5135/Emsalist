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

    def test_final_route_requires_review_approval(self) -> None:
        request = FinalPetitionDraftRequest(
            case_text=CASE_TEXT,
            request_type="Satış bedelinin iadesi",
        )
        with self.assertRaises(Exception) as raised:
            build_final_petition_draft(request)
        self.assertEqual(getattr(raised.exception, "status_code", None), 409)

    def test_gemini_receives_only_the_clean_drafting_package(self) -> None:
        package = final_petition_writer_service.build_package(
            case_text=CASE_TEXT,
            request_type="Sözleşmeden dönme ve satış bedelinin iadesi",
            document_facts=self.record.extracted_facts,
            document_types=[self.record.document_type],
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

        self.assertEqual(response.generation_mode, "local_template_mode")
        self.assertNotIn("WhatsApp üzerinden davalıya bildirmiştir", response.petition_text)

    def test_gemini_cannot_claim_preexisting_defect_without_a_report(self) -> None:
        package = final_petition_writer_service.build_package(
            case_text=CASE_TEXT,
            request_type="Sözleşmeden dönme ve satış bedelinin iadesi",
            document_facts=self.record.extracted_facts,
            document_types=[self.record.document_type],
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

        self.assertEqual(response.generation_mode, "local_template_mode")
        self.assertNotIn("satış anında gizli ayıplı olduğunu göstermektedir", response.petition_text)

    def test_gemini_cannot_invent_a_signature_date(self) -> None:
        package = final_petition_writer_service.build_package(
            case_text=CASE_TEXT,
            request_type="Sözleşmeden dönme ve satış bedelinin iadesi",
            document_facts=self.record.extracted_facts,
            document_types=[self.record.document_type],
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

        self.assertEqual(response.generation_mode, "local_template_mode")
        self.assertNotIn("30.06.2026", response.petition_text)


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


if __name__ == "__main__":
    unittest.main()
