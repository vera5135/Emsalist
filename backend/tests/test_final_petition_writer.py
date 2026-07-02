from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.petition_models import DraftingPrecedentItem, FinalPetitionDraftRequest
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
        self.assertIn("12.04.2024", response.petition_text)
        self.assertIn("500.000 TL", response.petition_text)
        lowered = response.petition_text.casefold()
        for forbidden in FORBIDDEN_TEXT:
            self.assertNotIn(forbidden.casefold(), lowered)
        self.assertNotIn("NOTER._TEST.txt", response.petition_text)

    def test_vehicle_drafting_package_is_hierarchical_and_complete(self) -> None:
        package = final_petition_writer_service.build_package(
            case_text=CASE_TEXT,
            request_type="Sözleşmeden dönme ve satış bedelinin iadesi",
            document_facts=self.record.extracted_facts,
            document_types=[self.record.document_type],
        )

        self.assertEqual(package.case_identity.plaintiff, "Mehmet Demir")
        self.assertEqual(package.case_identity.defendant, "Ahmet Yılmaz")
        self.assertIn("500.000 TL", package.case_identity.claim_value)
        self.assertIn("Gizli ayıplı ikinci el araç satışı", package.case_identity.subject)
        self.assertIn("Mehmet Demir alıcıdır", package.confirmed_facts)
        self.assertIn("Ahmet Yılmaz satıcıdır", package.confirmed_facts)
        self.assertIn("Servis/ekspertiz rapor tarihi ve numarası eksiktir", package.uncertain_facts)
        self.assertIn("TRAMER / SBM kayıtları", package.evidence_to_request)
        self.assertIn("Bilirkişi incelemesi", package.evidence_to_request)
        self.assertTrue(package.local_draft_seed)
        self.assertTrue(package.missing_fields_to_flag)

    def test_gemini_prompt_contains_required_structure_and_bans(self) -> None:
        package = final_petition_writer_service.build_package(
            case_text=CASE_TEXT,
            request_type="Sözleşmeden dönme ve satış bedelinin iadesi",
            document_facts=self.record.extracted_facts,
            document_types=[self.record.document_type],
            writer_mode="gemini",
        )
        package.precedent_for_petition = [
            DraftingPrecedentItem(
                court="Yargıtay 3. Hukuk Dairesi",
                esas_no="2020/5001",
                karar_no="2021/1102",
                date="09.02.2021",
                summary="İkinci el araç satışında pert kaydı ve bedel indirimi değerlendirilmiştir.",
                relevance="Gizli ayıp iddiasının teknik delillerle ispatı bakımından somut olaya benzerlik taşır.",
                supported_issue="Gizli ayıp ve seçimlik haklar",
            )
        ]
        safe_text = (
            "NÖBETÇİ ASLİYE HUKUK MAHKEMESİ'NE\n\n"
            "DAVACI: Mehmet Demir\nVEKİLİ: Av. ...\nDAVALI: Ahmet Yılmaz\n\n"
            "DAVA DEĞERİ: 500.000 TL\n"
            "KONU: Gizli ayıplı araç satışı nedeniyle satış bedelinin faiziyle tahsili talebidir.\n"
            "DAVA ŞARTI ARABULUCULUK: Gerekirse son tutanak sunulacaktır.\n\n"
            "AÇIKLAMALAR\n"
            "I. Satış ilişkisi ve aracın temel bilgileri\n"
            "1. Müvekkil aracı satın almıştır.\n"
            "II. Ayıbın ortaya çıkışı\n"
            "2. Satıştan kısa süre sonra motor arızası ortaya çıkmıştır.\n"
            "III. Ayıbın gizli niteliği\n"
            "3. Teknik durum bilirkişi incelemesiyle ortaya konulacaktır.\n"
            "IV. Davalının ayıba karşı sorumluluğu\n"
            "4. Satıcı ayıptan sorumludur.\n"
            "V. Seçimlik haklar ve terditli talepler\n"
            "5. Öncelikle sözleşmeden dönme, aksi halde bedel indirimi talep olunur.\n"
            "VI. Ayıp ihbarı ve ispat\n"
            "6. Ayıp ihbarı yazışmalarla ortaya konulacaktır.\n\n"
            "EMSAL İÇTİHATLAR\n"
            "1. Yargıtay 3. Hukuk Dairesi, E. 2020/5001, K. 2021/1102, T. 09.02.2021.\n\n"
            "HUKUKİ DEĞERLENDİRME\n"
            "1. Gizli ayıp hükümleri uygulanmalıdır.\n\n"
            "HUKUKİ NEDENLER\n"
            "TBK m. 219 ve devamı.\n\n"
            "DELİLLER\n"
            "1. Noter satış sözleşmesi.\n\n"
            "CELBİ TALEP EDİLEN KAYITLAR\n"
            "1. TRAMER kayıtları.\n\n"
            "SONUÇ VE İSTEM\n"
            "1. Satış bedelinin tahsiline karar verilmesini talep ederiz.\n\n"
            "EKLER\n"
            "1. Noter satış sözleşmesi."
        )

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
        self.assertIn("Gerçek dava dilekçesi yaz. Kısa özet yazma.", prompt)
        self.assertIn("Mahkeme başlığı", prompt)
        self.assertIn("Dava değeri", prompt)
        self.assertIn("EMSAL İÇTİHATLAR", prompt)
        self.assertIn('"confirmed_facts"', prompt)
        self.assertIn('"uncertain_facts"', prompt)
        self.assertIn('"evidence_to_request"', prompt)
        self.assertIn('"precedent_for_petition"', prompt)
        self.assertIn('"case_identity"', prompt)
        self.assertIn('"local_draft_seed"', prompt)
        self.assertIn("local_draft_seed yalnızca asgari iskelet ve veri kontrolü içindir", prompt)
        self.assertIn("Şunları yazma", prompt)
        self.assertNotIn('"source_document_id":', prompt)
        self.assertNotIn('"confidence_score":', prompt)
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

    def test_gemini_output_cannot_contain_technical_fields(self) -> None:
        package = final_petition_writer_service.build_package(
            case_text=CASE_TEXT,
            request_type="Sözleşmeden dönme ve satış bedelinin iadesi",
            document_facts=self.record.extracted_facts,
            document_types=[self.record.document_type],
            writer_mode="gemini",
        )
        unsafe_text = (
            final_petition_writer_service._local_template(package)
            + "\n\nKontrol Listesi\nconfidence_score: 92\nKaynak: NOTER._TEST.txt"
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
        self.assertNotIn("confidence_score", response.petition_text)
        self.assertNotIn("Kontrol Listesi", response.petition_text)

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

    def test_dynamic_reasoner_builds_vehicle_issues_and_queries(self) -> None:
        reasoning = dynamic_legal_reasoner_service.analyze(
            event_text=CASE_TEXT,
            document_facts=["sale_date: 12.04.2024", "notary_info: İzmir 12. Noterliği"],
            question_answers={"Satıcı galeri/tacir/şirket mi?": "Bilmiyorum"},
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
