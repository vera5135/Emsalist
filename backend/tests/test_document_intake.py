from __future__ import annotations

import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

import fitz
from fastapi.testclient import TestClient

from app.main import app
from app.models.document_models import ExtractedFact
from app.models.petition_models import PetitionDraftRequest, PetitionDraftResponse
from app.routes.petition_routes import build_petition_draft
from app.services.petition_draft_service import PetitionDraftService
from app.services.petition_profile_service import get_petition_profile
from app.services.case_session_service import case_session_service
from app.services.document_intake_service import (
    IMAGE_OCR_WARNING,
    PDF_OCR_WARNING,
    UDF_CONVERSION_WARNING,
    DocumentIntakeError,
    DocumentIntakeService,
)


def make_docx(paragraphs: list[str], table_cells: list[str] | None = None) -> bytes:
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    paragraph_xml = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{value}</w:t></w:r></w:p>' for value in paragraphs
    )
    table_xml = ""
    if table_cells:
        cells = "".join(
            f'<w:tc><w:p><w:r><w:t>{value}</w:t></w:r></w:p></w:tc>' for value in table_cells
        )
        table_xml = f"<w:tbl><w:tr>{cells}</w:tr></w:tbl>"
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{namespace}"><w:body>{paragraph_xml}{table_xml}</w:body></w:document>'
    )
    package = BytesIO()
    with ZipFile(package, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        archive.writestr("word/document.xml", document_xml)
    return package.getvalue()


def make_pdf(text: str | None = None) -> bytes:
    document = fitz.open()
    page = document.new_page()
    if text:
        page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


def test_conflict_marks_fact_and_blocks_grounding_ready() -> None:
    with tempfile.TemporaryDirectory() as directory:
        service = DocumentIntakeService(Path(directory), max_file_size=2 * 1024 * 1024)
        text = "Noter satış sözleşmesi\nSatış bedeli: 350.000 TL\nSatış tarihi: 12.06.2026"
        record = service.create_document(file_name="noter_satis.txt", content=text.encode())
        sale_fact = next(fact for fact in record.extracted_facts if fact.fact_key == "sale_price")
        assert sale_fact.fact_value == "350.000 TL"

        analysis = service.analyze_documents(
            document_ids=[record.document_id],
            user_claims={"satış bedeli": "500.000 TL"},
            document_types={record.document_id: "noter satış sözleşmesi"},
        )

        assert len(analysis.conflicts) == 1
        assert analysis.conflicts[0].fact_key == "sale_price"
        assert "çelişki" in analysis.conflicts[0].warning
        analyzed_sale_fact = next(
            fact for fact in analysis.documents[0].extracted_facts
            if fact.fact_key == "sale_price"
        )
        assert analyzed_sale_fact.verification_status == "conflict_detected"
        assert analysis.grounding_ready is False


class DocumentIntakeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.service = DocumentIntakeService(Path(self.temporary.name), max_file_size=2 * 1024 * 1024)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_txt_decodes_utf8_and_windows_1254_without_losing_turkish(self) -> None:
        content = "İhtar tarihi: 12.06.2026\nÇalışma, şasi ve ödeme bilgisi." 
        for index, encoding in enumerate(("utf-8", "cp1254", "iso-8859-9")):
            record = self.service.create_document(
                file_name=f"ihtar_{index}.txt",
                content=f"{content}\nBelge sıra no: {index}".encode(encoding),
                document_type="ihtarname",
            )
            self.assertEqual(record.extraction_status, "extracted")
            self.assertIn("İhtar", record.extracted_text_preview)
            self.assertIn("şasi", record.extracted_text_preview)

    def test_docx_extracts_paragraphs_and_table_cells(self) -> None:
        content = make_docx(
            ["NOTER SATIŞ SÖZLEŞMESİ", "Satış tarihi: 12.06.2026", "Satış bedeli: 500.000 TL"],
            ["Plaka: 34 ABC 123", "Marka/Model: Renault Clio"],
        )
        record = self.service.create_document(file_name="noter_satis.docx", content=content)
        self.assertEqual(record.extraction_status, "extracted")
        self.assertIn("500.000 TL", record.extracted_text_preview)
        self.assertIn("34 ABC 123", record.extracted_text_preview)
        fact_map = {fact.fact_key: fact for fact in record.extracted_facts}
        self.assertEqual(fact_map["sale_date"].fact_value, "12.06.2026")
        self.assertEqual(fact_map["sale_price"].fact_value, "500.000 TL")
        self.assertEqual(fact_map["vehicle_plate"].source_file_name, "noter_satis.docx")

    def test_requested_notary_txt_extracts_all_vehicle_sale_facts(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "NOTER._TEST.txt"
        record = self.service.create_document(file_name=fixture.name, content=fixture.read_bytes())
        facts = {fact.fact_key: fact for fact in record.extracted_facts}

        self.assertEqual(record.extraction_status, "extracted")
        self.assertEqual(record.detected_document_type, "noter satış sözleşmesi")
        self.assertEqual(facts["sale_date"].fact_value, "12.04.2024")
        self.assertEqual(facts["sale_price"].fact_value, "500.000 TL")
        self.assertEqual(facts["vehicle_make_model"].fact_value, "Volkswagen Golf 1.6 TDI")
        self.assertEqual(facts["vehicle_plate"].fact_value, "35 ABC 123")
        self.assertEqual(facts["vehicle_vin"].fact_value, "WVWZZZ123456789")
        self.assertEqual(facts["notary_info"].fact_value, "İzmir 5. Noterliği")
        self.assertTrue(all(fact.source_document_id == record.document_id for fact in facts.values()))

    def test_scanned_or_unreadable_pdf_requires_ocr(self) -> None:
        record = self.service.create_document(file_name="taranmis.pdf", content=make_pdf())
        self.assertEqual(record.extraction_status, "ocr_required")
        self.assertEqual(record.extraction_warning, PDF_OCR_WARNING)
        self.assertEqual(record.extracted_facts, [])

    def test_pdf_with_embedded_text_is_extracted(self) -> None:
        record = self.service.create_document(
            file_name="dava_dilekcesi.pdf",
            content=make_pdf("Dosya No: 2026/123"),
            document_type="dava dilekçesi",
        )
        self.assertEqual(record.extraction_status, "extracted")
        self.assertIn("Dosya No: 2026/123", record.extracted_text_preview)
        case_number = next(fact for fact in record.extracted_facts if fact.fact_key == "case_number")
        self.assertEqual(case_number.fact_value, "2026/123")
        self.assertEqual(case_number.page_number, 1)

    def test_images_are_saved_and_require_ocr(self) -> None:
        samples = {
            "ruhsat.jpg": b"\xff\xd8\xff\xe0" + b"image",
            "dekont.png": b"\x89PNG\r\n\x1a\n" + b"image",
        }
        for file_name, content in samples.items():
            record = self.service.create_document(file_name=file_name, content=content)
            self.assertEqual(record.extraction_status, "ocr_required")
            self.assertEqual(record.extraction_warning, IMAGE_OCR_WARNING)
            self.assertTrue((self.service.upload_dir / f"{record.document_id}{record.file_extension}").exists())

    def test_binary_udf_requires_conversion_and_is_never_executed(self) -> None:
        record = self.service.create_document(file_name="uyap_evraki.udf", content=b"\x00\x01\x02\x03\xff" * 20)
        self.assertEqual(record.extraction_status, "conversion_required")
        self.assertEqual(record.extraction_warning, UDF_CONVERSION_WARNING)

    def test_plain_xml_udf_is_read_as_content(self) -> None:
        content = "<evrak><metin>İhtarname\nİhtar tarihi: 12.06.2026\nMuhatap: Mehmet Kaya</metin></evrak>".encode()
        record = self.service.create_document(file_name="ihtar.udf", content=content)
        self.assertEqual(record.extraction_status, "extracted")
        self.assertIn("Mehmet Kaya", record.extracted_text_preview)
        self.assertEqual(record.detected_document_type, "ihtarname")

    def test_petition_facts_have_provenance_and_missing_fields(self) -> None:
        text = """İSTANBUL 4. ASLİYE HUKUK MAHKEMESİ
Dosya No: 2026/123
Davacı: Ayşe Yılmaz
Davalı: Örnek Otomotiv A.Ş.
SONUÇ VE İSTEM: Satış bedelinin iadesine karar verilmesini talep ederiz.
DELİLLER: Noter satış sözleşmesi, servis raporu, banka dekontu.
"""
        record = self.service.create_document(
            file_name="dava_dilekcesi.txt",
            content=text.encode(),
            document_type="dava dilekçesi",
        )
        facts = {fact.fact_key: fact for fact in record.extracted_facts}
        for key in ("court", "case_number", "parties", "claim_result", "evidence"):
            self.assertIn(key, facts)
            self.assertEqual(facts[key].source_document_id, record.document_id)
            self.assertTrue(facts[key].excerpt)
            self.assertEqual(facts[key].verification_status, "fact_confirmed")
        self.assertEqual(record.missing_fields, [])

    def test_closed_txt_file_extracts_sale_price_and_detects_conflict(self) -> None:
        source = Path(self.temporary.name) / "noter_satis_kaynagi.txt"
        source.write_text(
            "Noter satış sözleşmesi\nSatış bedeli: 350.000 TL\nSatış tarihi: 12.06.2026",
            encoding="utf-8",
        )

        record = self.service.create_document(file_name=source.name, content=source.read_bytes())
        stored_path = self.service.upload_dir / f"{record.document_id}{record.file_extension}"
        self.assertTrue(stored_path.is_file())

        analysis = self.service.analyze_documents(
            document_ids=[record.document_id],
            user_claims={"satış bedeli": "500.000 TL"},
            document_types={record.document_id: "noter satış sözleşmesi"},
        )

        sale_fact = next(
            fact for fact in analysis.documents[0].extracted_facts
            if fact.fact_key == "sale_price"
        )
        self.assertEqual(analysis.documents[0].extraction_status, "extracted")
        self.assertIn("Satış bedeli: 350.000 TL", analysis.documents[0].extracted_text_preview)
        self.assertEqual(sale_fact.fact_value, "350.000 TL")
        self.assertEqual(sale_fact.verification_status, "conflict_detected")
        self.assertEqual(analysis.conflicts[0].fact_key, "sale_price")
        self.assertFalse(analysis.grounding_ready)

    def test_unsafe_files_and_oversized_files_are_rejected(self) -> None:
        with self.assertRaises(DocumentIntakeError):
            self.service.create_document(file_name="zararli.exe", content=b"MZpayload")
        with self.assertRaises(DocumentIntakeError):
            self.service.create_document(file_name="sahte.pdf", content=b"MZpayload")
        small_service = DocumentIntakeService(Path(self.temporary.name) / "small", max_file_size=5)
        with self.assertRaises(DocumentIntakeError):
            small_service.create_document(file_name="buyuk.txt", content=b"123456")


class DocumentRoutesTests(unittest.TestCase):
    def test_upload_list_analyze_get_and_delete_routes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            isolated = DocumentIntakeService(Path(directory), max_file_size=1024 * 1024)
            with patch("app.routes.document_routes.document_intake_service", isolated):
                client = TestClient(app)
                upload = client.post(
                    "/documents/upload",
                    files={"file": ("noter_satis.txt", "Satış bedeli: 350.000 TL".encode(), "text/plain")},
                    data={"document_type": "noter satış sözleşmesi"},
                )
                self.assertEqual(upload.status_code, 200, upload.text)
                document = upload.json()
                document_id = document["document_id"]
                self.assertEqual(client.get("/documents").status_code, 200)
                self.assertEqual(client.get(f"/documents/{document_id}").status_code, 200)
                analyzed = client.post(
                    "/documents/analyze",
                    json={"document_ids": [document_id], "user_claims": {"sale_price": "500.000 TL"}},
                )
                self.assertEqual(analyzed.status_code, 200, analyzed.text)
                self.assertEqual(analyzed.json()["conflicts"][0]["fact_key"], "sale_price")
                self.assertEqual(client.delete(f"/documents/{document_id}").status_code, 204)
                self.assertEqual(client.get(f"/documents/{document_id}").status_code, 404)

    def test_petition_route_keeps_document_provenance_in_grounding(self) -> None:
        document_fact = ExtractedFact(
            fact_key="sale_price",
            fact_value="350.000 TL",
            source_document_id="doc-1",
            source_file_name="noter_satis.txt",
            excerpt="Satış bedeli: 350.000 TL",
            confidence_score=0.97,
            verification_status="fact_confirmed",
        )
        request = PetitionDraftRequest(
            case_id=case_session_service.new_case()["case_id"],
            case_text="Ayıplı araç satışından doğan bedel iadesi talebidir.",
            request_type="Satış bedelinin iadesi",
            document_facts=[document_fact],
        )
        service_response = PetitionDraftResponse(
            draft_title="Dava dilekçesi",
            draft_text="Taslak metin",
            checklist=[],
            grounding_notes=[],
            warnings=[],
        )
        with patch(
            "app.routes.petition_routes.petition_draft_service.build_draft",
            return_value=service_response,
        ) as mocked:
            response = build_petition_draft(request)

        confirmed_facts = mocked.call_args.kwargs["confirmed_facts"]
        self.assertIn("Kaynak belge: noter_satis.txt", confirmed_facts[0])
        self.assertEqual(response.grounding_notes[-1].status, "source_confirmed")
        self.assertIn("noter_satis.txt", response.grounding_notes[-1].detail)

    def test_grounding_deduplicates_confirmed_and_missing_sale_price(self) -> None:
        profile = get_petition_profile("İkinci el araç gizli ayıp ve satış bedeli iadesi", "bedel iadesi")
        notes = PetitionDraftService._grounding_notes(
            profile=profile,
            case_text="Müvekkil ikinci el araç satın aldı.",
            answers={},
            confirmed_facts=["sale_price: 500.000 TL (Kaynak belge: NOTER._TEST.txt)"],
            missing_facts=[
                "Satış bedelinin miktarı somutlaştırılmalıdır.",
                "Satış bedelinin miktarı yazılmalı",
            ],
            legal_memory=None,
        )
        missing_sale_notes = [
            note for note in notes
            if note.status == "fact_missing" and "satış bedeli" in f"{note.title} {note.detail}".casefold()
        ]
        self.assertEqual(missing_sale_notes, [])
        confirmed_sale_notes = [
            note for note in notes
            if note.status == "fact_confirmed" and "satış bedeli" in f"{note.title} {note.detail}".casefold()
        ]
        self.assertEqual(len(confirmed_sale_notes), 1)


if __name__ == "__main__":
    unittest.main()
