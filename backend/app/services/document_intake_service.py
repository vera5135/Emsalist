"""Safe, format-aware document intake without executing uploaded content."""

from __future__ import annotations

import html
import hashlib
import json
import os
import re
import threading
import unicodedata
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree

from app.models.document_models import (
    DocumentAnalyzeResponse,
    DocumentConflict,
    DocumentRecord,
    ExtractedFact,
)


SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".docx", ".udf", ".jpg", ".jpeg", ".png"}
BLOCKED_EXTENSIONS = {".exe", ".bat", ".cmd", ".ps1", ".js", ".vbs", ".scr"}
DOCUMENT_TYPES = {
    "vekaletname",
    "noter satış sözleşmesi",
    "ihtarname",
    "tebligat belgesi",
    "dava dilekçesi",
    "cevap dilekçesi",
    "tensip zaptı",
    "bilirkişi raporu",
    "ekspertiz raporu",
    "servis raporu",
    "dekont",
    "ruhsat",
    "TRAMER kaydı",
    "mahkeme kararı",
    "ara karar",
    "delil listesi",
    "UYAP evrakı",
    "diğer",
}

MIME_TYPES = {
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".udf": "application/octet-stream",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}

PDF_OCR_WARNING = "Bu PDF’den doğrudan metin çıkarılamadı. OCR veya metin içeren PDF gereklidir."
UDF_CONVERSION_WARNING = (
    "Bu UDF dosyasından doğrudan metin çıkarılamadı. "
    "UYAP/UDF dönüştürücü veya PDF çıktısı gerekli."
)
IMAGE_OCR_WARNING = "Bu görsel belgeden metin çıkarılması için OCR gereklidir."
DOCX_WARNING = "Bu Word belgesinin metni doğrudan okunamadı. Belge kaydedildi; manuel inceleme gereklidir."

EXPECTED_FIELDS = {
    "noter satış sözleşmesi": ["sale_date", "sale_price", "vehicle_make_model", "vehicle_plate", "notary_info", "parties"],
    "dava dilekçesi": ["court", "case_number", "parties", "claim_result", "evidence"],
    "cevap dilekçesi": ["court", "case_number", "parties", "claim_result", "evidence"],
    "tebligat belgesi": ["service_date", "parties"],
    "tensip zaptı": ["court", "case_number", "hearing_date", "deadlines"],
    "bilirkişi raporu": ["report_date", "report_number", "technical_findings"],
    "ekspertiz raporu": ["report_date", "report_number", "technical_findings", "vehicle_plate"],
    "servis raporu": ["report_date", "technical_findings", "vehicle_plate"],
    "dekont": ["payment_info", "document_date", "parties"],
    "ruhsat": ["vehicle_make_model", "vehicle_plate", "vehicle_vin"],
    "ihtarname": ["notice_date", "parties", "claim_result"],
    "vekaletname": ["power_of_attorney_info", "parties", "notary_info"],
    "mahkeme kararı": ["court", "case_number", "parties", "document_date"],
    "ara karar": ["court", "case_number", "deadlines"],
    "delil listesi": ["evidence"],
}

FACT_LABELS = {
    "court": "mahkeme",
    "case_number": "dosya numarası",
    "parties": "taraflar",
    "document_date": "belge tarihi",
    "service_date": "tebliğ tarihi",
    "hearing_date": "duruşma tarihi",
    "deadlines": "süreler",
    "sale_date": "satış tarihi",
    "sale_price": "satış bedeli",
    "vehicle_make_model": "araç marka/model",
    "vehicle_plate": "araç plakası",
    "vehicle_vin": "araç şasi numarası",
    "notary_info": "noterlik bilgisi",
    "notice_date": "ihtar tarihi",
    "claim_result": "talep sonucu",
    "evidence": "deliller",
    "report_date": "rapor tarihi",
    "report_number": "rapor numarası",
    "technical_findings": "teknik tespitler",
    "payment_info": "ödeme/dekont bilgileri",
    "power_of_attorney_info": "vekalet bilgileri",
    "risk_signals": "risk sinyalleri",
}


@dataclass
class ExtractionResult:
    text: str
    pages: list[tuple[int | None, str]]
    status: str
    warning: str | None = None


class DocumentIntakeError(ValueError):
    """A safe validation error suitable for an HTTP 4xx response."""


class DocumentDuplicateError(DocumentIntakeError):
    """Raised when the exact same file content is already stored."""

    def __init__(self, existing_document_id: str) -> None:
        super().__init__("Bu belge zaten ekli.")
        self.existing_document_id = existing_document_id


class DocumentIntakeService:
    def __init__(self, storage_dir: Path | None = None, max_file_size: int | None = None) -> None:
        import os as _os

        root = storage_dir or Path(__file__).resolve().parents[1] / "document_store"
        raw_root = Path(root).expanduser().absolute()

        if raw_root.is_symlink():
            raise DocumentIntakeError("Storage directory must not be a symlink.")
        if _os.path.lexists(str(raw_root)) and not raw_root.exists() and raw_root.is_symlink():
            raise DocumentIntakeError("Storage directory must not be a broken symlink.")

        self.storage_dir = raw_root
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.storage_dir = self.storage_dir.resolve()

        raw_upload_dir = raw_root / "uploads"
        if raw_upload_dir.is_symlink():
            raise DocumentIntakeError("Upload directory must not be a symlink.")
        if _os.path.lexists(str(raw_upload_dir)) and not raw_upload_dir.exists() and raw_upload_dir.is_symlink():
            raise DocumentIntakeError("Upload directory must not be a broken symlink.")

        if raw_upload_dir.exists():
            try:
                resolved_uploads = raw_upload_dir.resolve()
                try:
                    resolved_uploads.relative_to(self.storage_dir)
                except ValueError:
                    raise DocumentIntakeError("Upload directory resolves outside storage root.")
            except (OSError, RuntimeError):
                raise DocumentIntakeError("Cannot resolve upload directory path.")

        try:
            raw_upload_dir.mkdir(parents=True, exist_ok=True)
        except FileExistsError:
            if raw_upload_dir.is_symlink():
                raise DocumentIntakeError("Upload directory must not be a symlink.")
            raise

        self.upload_dir = raw_upload_dir.resolve()
        try:
            self.upload_dir.relative_to(self.storage_dir)
        except ValueError:
            raise DocumentIntakeError("Upload directory is outside storage root.")

        self.index_path = self.storage_dir / "documents.json"
        from app.config import get_settings
        _settings = get_settings()
        self.max_file_size = max_file_size or _settings.max_upload_size_bytes
        self._lock = threading.RLock()
        self._records: dict[str, DocumentRecord] = self._load_records()

    def _validate_upload_dir(self) -> None:
        if self.upload_dir.is_symlink():
            raise DocumentIntakeError("Upload directory must not be a symlink.")
        try:
            self.upload_dir.relative_to(self.storage_dir)
        except ValueError:
            raise DocumentIntakeError("Upload directory resolves outside storage root.")

    def create_document(
        self,
        *,
        case_id: str = "legacy",
        file_name: str,
        content: bytes,
        document_type: str | None = None,
    ) -> DocumentRecord:
        safe_name = self.sanitize_file_name(file_name)
        extension = Path(safe_name).suffix.lower()
        self._validate_upload(extension, content)
        if len(content) > self.max_file_size:
            raise DocumentIntakeError(f"Dosya boyutu {self.max_file_size // (1024 * 1024)} MB sınırını aşıyor.")

        selected_type = self._normalize_document_type(document_type)
        content_sha256 = hashlib.sha256(content).hexdigest()
        with self._lock:
            duplicate = self._find_duplicate(content_sha256, case_id=case_id)
            if duplicate:
                raise DocumentDuplicateError(duplicate.document_id)

            document_id = uuid.uuid4().hex
            destination = self._file_path(document_id, extension)
            destination.write_bytes(content)
            record = DocumentRecord(
                document_id=document_id,
                case_id=case_id,
                file_name=Path(file_name or safe_name).name,
                safe_file_name=safe_name,
                file_extension=extension,
                mime_type=MIME_TYPES[extension],
                file_size=len(content),
                content_sha256=content_sha256,
                upload_time=datetime.now(UTC).isoformat(),
                document_type=selected_type or "diğer",
                detected_document_type="UYAP evrakı" if extension == ".udf" else "diğer",
                extraction_status="failed",
                extraction_warning=None,
                text_length=0,
                extracted_text_preview="",
                confidence_score=0,
            )
            try:
                record = self._analyze_record(record, content, selected_type=selected_type)
            except Exception:
                record.extraction_status = "failed"
                record.extraction_warning = "Belge işlenirken güvenli okuma tamamlanamadı; manuel inceleme gereklidir."
            self._set_record(record)
            return record

    def analyze_documents(
        self,
        case_id: str = "legacy",
        document_ids: list[str] | None = None,
        user_claims: dict[str, str] | None = None,
        document_types: dict[str, str] | None = None,
    ) -> DocumentAnalyzeResponse:
        ids = list(dict.fromkeys(document_ids or [
            record.document_id
            for record in self._records.values()
            if record.case_id == case_id
        ]))
        claims = {self._canonical_fact_key(key): str(value).strip() for key, value in (user_claims or {}).items() if str(value).strip()}
        overrides = document_types or {}
        documents: list[DocumentRecord] = []
        all_conflicts: list[DocumentConflict] = []
        all_facts: list[ExtractedFact] = []
        warnings: list[str] = []
        analyzed_signatures: set[str] = set()

        for document_id in ids:
            existing = self.get_document(document_id, case_id=case_id)
            signature = self._content_signature(existing)
            if signature and signature in analyzed_signatures:
                continue
            if signature:
                analyzed_signatures.add(signature)
            extension = existing.file_extension
            path = self._file_path(document_id, extension)
            if not path.exists():
                existing.extraction_status = "failed"
                existing.extraction_warning = "Kaydedilen belge dosyası bulunamadı."
                self._set_record(existing)
                documents.append(existing)
                warnings.append(existing.extraction_warning)
                continue
            selected_type = self._normalize_document_type(overrides.get(document_id)) or (
                existing.document_type if existing.document_type != "diğer" else None
            )
            record = self._analyze_record(existing, path.read_bytes(), selected_type=selected_type)
            record.conflicts = self._find_conflicts(record, claims)
            self._set_record(record)
            documents.append(record)
            all_conflicts.extend(record.conflicts)
            all_facts.extend(record.extracted_facts)
            if record.extraction_warning:
                warnings.append(record.extraction_warning)

        confirmed = list({
            (fact.fact_key, self._ascii_fold(fact.fact_value), self._ascii_fold(fact.source_file_name)): fact
            for fact in all_facts
            if fact.verification_status == "fact_confirmed"
        }.values())
        confirmed_keys = {fact.fact_key for fact in confirmed}
        missing = sorted(
            {field for record in documents for field in record.missing_fields}
            - confirmed_keys
        )
        grounding_ready = bool(documents) and not all_conflicts and all(
            record.extraction_status in {"extracted", "partial"} for record in documents
        )
        return DocumentAnalyzeResponse(
            documents=documents,
            confirmed_facts=confirmed,
            conflicts=all_conflicts,
            missing_fields=missing,
            grounding_ready=grounding_ready,
            warnings=list(dict.fromkeys(warnings)),
        )

    def get_document(self, document_id: str, *, case_id: str | None = None) -> DocumentRecord:
        with self._lock:
            record = self._records.get(document_id)
            if record is None or (case_id and record.case_id != case_id):
                raise KeyError(document_id)
            return record.model_copy(deep=True)

    def list_documents(self, *, case_id: str | None = None) -> list[DocumentRecord]:
        with self._lock:
            records = [
                record.model_copy(deep=True)
                for record in self._records.values()
                if case_id is None or record.case_id == case_id
            ]
        unique: list[DocumentRecord] = []
        seen_signatures: set[str] = set()
        for record in sorted(records, key=lambda item: item.upload_time, reverse=True):
            signature = self._content_signature(record)
            if signature and signature in seen_signatures:
                continue
            if signature:
                seen_signatures.add(signature)
            unique.append(record)
        return unique

    def delete_document(self, document_id: str, *, case_id: str | None = None) -> None:
        with self._lock:
            record = self._records.get(document_id)
            if record is None or (case_id and record.case_id != case_id):
                raise KeyError(document_id)
            self._records.pop(document_id, None)
            path = self._file_path(record.document_id, record.file_extension)
            if path.exists():
                path.unlink()
            self._persist_records()

    @staticmethod
    def sanitize_file_name(file_name: str) -> str:
        original = Path(file_name or "belge").name
        normalized = unicodedata.normalize("NFKC", original).replace("\x00", "")
        extension = Path(normalized).suffix.lower()
        stem = Path(normalized).stem
        stem = re.sub(r"[^0-9A-Za-zÇĞİÖŞÜçğıöşü._ -]+", "_", stem)
        stem = re.sub(r"[\s._-]+", "_", stem).strip("_.")[:120] or "belge"
        return f"{stem}{extension}"

    def _validate_upload(self, extension: str, content: bytes) -> None:
        if extension in BLOCKED_EXTENSIONS:
            raise DocumentIntakeError("Bu dosya türü güvenlik nedeniyle kabul edilmiyor.")
        if extension not in SUPPORTED_EXTENSIONS:
            raise DocumentIntakeError("Desteklenmeyen dosya türü. TXT, PDF, DOCX, UDF, JPG, JPEG veya PNG yükleyin.")
        if not content:
            raise DocumentIntakeError("Boş dosya yüklenemez.")
        if content.startswith(b"MZ"):
            raise DocumentIntakeError("Çalıştırılabilir dosya içeriği kabul edilmiyor.")
        if extension == ".pdf" and not content.lstrip().startswith(b"%PDF"):
            raise DocumentIntakeError("Dosya içeriği geçerli bir PDF değil.")
        if extension == ".png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise DocumentIntakeError("Dosya içeriği geçerli bir PNG değil.")
        if extension in {".jpg", ".jpeg"} and not content.startswith(b"\xff\xd8\xff"):
            raise DocumentIntakeError("Dosya içeriği geçerli bir JPEG değil.")
        if extension == ".docx" and not zipfile.is_zipfile(BytesIO(content)):
            raise DocumentIntakeError("Dosya içeriği geçerli bir DOCX değil.")

    def _analyze_record(self, record: DocumentRecord, content: bytes, selected_type: str | None = None) -> DocumentRecord:
        result = self._extract(record.file_extension, content)
        detected_type, type_confidence = self._detect_document_type(record.safe_file_name, result.text, record.file_extension)
        effective_type = selected_type or (record.document_type if record.document_type != "diğer" else detected_type)
        facts = self._extract_facts(record.document_id, record.file_name, result.text, result.pages)
        extracted_keys = {fact.fact_key for fact in facts}
        expected = EXPECTED_FIELDS.get(effective_type, [])

        record.document_type = effective_type
        record.detected_document_type = detected_type
        record.extraction_status = result.status
        record.extraction_warning = result.warning
        record.text_length = len(result.text)
        record.extracted_text_preview = self._preview(result.text)
        record.confidence_score = type_confidence if result.text else 0
        record.extracted_facts = facts
        record.conflicts = []
        record.missing_fields = [field for field in expected if field not in extracted_keys]
        return record

    def _extract(self, extension: str, content: bytes) -> ExtractionResult:
        if extension == ".txt":
            text = self._decode_turkish_text(content)
            return ExtractionResult(text=text, pages=[(None, text)], status="extracted" if text else "failed")
        if extension == ".pdf":
            return self._extract_pdf(content)
        if extension == ".docx":
            return self._extract_docx(content)
        if extension == ".udf":
            return self._extract_udf(content)
        if extension in {".jpg", ".jpeg", ".png"}:
            return ExtractionResult(text="", pages=[], status="ocr_required", warning=IMAGE_OCR_WARNING)
        return ExtractionResult(text="", pages=[], status="unsupported", warning="Desteklenmeyen dosya türü.")

    @staticmethod
    def _decode_turkish_text(content: bytes) -> str:
        candidates: list[tuple[float, str]] = []
        for encoding in ("utf-8-sig", "utf-8", "cp1254", "iso-8859-9"):
            try:
                text = content.decode(encoding)
            except UnicodeDecodeError:
                continue
            controls = sum(1 for char in text if unicodedata.category(char) == "Cc" and char not in "\n\r\t")
            mojibake = sum(text.count(token) for token in ("Ã", "Ä", "Å", "�"))
            turkish = sum(text.count(char) for char in "çğıöşüÇĞİÖŞÜ")
            score = turkish * 2 - controls * 20 - mojibake * 8
            if encoding.startswith("utf-8"):
                score += 5
            candidates.append((score, text))
        if not candidates:
            return ""
        text = max(candidates, key=lambda item: item[0])[1]
        return DocumentIntakeService._clean_text(text)

    @staticmethod
    def _extract_pdf(content: bytes) -> ExtractionResult:
        pages: list[tuple[int | None, str]] = []
        try:
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content), strict=False)
            for number, page in enumerate(reader.pages, start=1):
                page_text = DocumentIntakeService._clean_text(page.extract_text() or "")
                if page_text:
                    pages.append((number, page_text))
        except Exception:
            return ExtractionResult(text="", pages=[], status="ocr_required", warning=PDF_OCR_WARNING)
        text = "\n\n".join(page_text for _, page_text in pages).strip()
        if not text:
            return ExtractionResult(text="", pages=[], status="ocr_required", warning=PDF_OCR_WARNING)
        return ExtractionResult(text=text, pages=pages, status="extracted")

    @staticmethod
    def _extract_docx(content: bytes) -> ExtractionResult:
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                DocumentIntakeService._validate_archive(archive)
                if "word/document.xml" not in archive.namelist():
                    raise ValueError("document.xml missing")
                root = ElementTree.fromstring(archive.read("word/document.xml"))
                namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
                blocks: list[str] = []
                for paragraph in root.iter(f"{namespace}p"):
                    chunks: list[str] = []
                    for node in paragraph.iter():
                        if node.tag == f"{namespace}t" and node.text:
                            chunks.append(node.text)
                        elif node.tag == f"{namespace}tab":
                            chunks.append("\t")
                        elif node.tag == f"{namespace}br":
                            chunks.append("\n")
                    line = "".join(chunks).strip()
                    if line:
                        blocks.append(line)
                text = DocumentIntakeService._clean_text("\n".join(blocks))
        except Exception:
            return ExtractionResult(text="", pages=[], status="failed", warning=DOCX_WARNING)
        if not text:
            return ExtractionResult(text="", pages=[], status="partial", warning=DOCX_WARNING)
        return ExtractionResult(text=text, pages=[(None, text)], status="extracted")

    @staticmethod
    def _extract_udf(content: bytes) -> ExtractionResult:
        candidates: list[str] = []
        try:
            if zipfile.is_zipfile(BytesIO(content)):
                with zipfile.ZipFile(BytesIO(content)) as archive:
                    DocumentIntakeService._validate_archive(archive)
                    for member in archive.infolist():
                        suffix = Path(member.filename).suffix.lower()
                        if suffix not in {".txt", ".xml", ".html", ".htm"} or member.is_dir():
                            continue
                        decoded = DocumentIntakeService._decode_turkish_text(archive.read(member))
                        if decoded:
                            candidates.append(DocumentIntakeService._strip_markup(decoded))
            else:
                decoded = DocumentIntakeService._decode_turkish_text(content)
                if decoded:
                    candidates.append(DocumentIntakeService._strip_markup(decoded))
        except Exception:
            candidates = []
        text = DocumentIntakeService._clean_text("\n".join(candidates))
        if len(text) < 20 or not DocumentIntakeService._looks_like_text(text):
            return ExtractionResult(text="", pages=[], status="conversion_required", warning=UDF_CONVERSION_WARNING)
        return ExtractionResult(text=text, pages=[(None, text)], status="extracted")

    @staticmethod
    def _validate_archive(archive: zipfile.ZipFile) -> None:
        members = archive.infolist()
        if len(members) > 2_000:
            raise ValueError("archive has too many entries")
        total_uncompressed = sum(member.file_size for member in members)
        if total_uncompressed > 50 * 1024 * 1024:
            raise ValueError("archive expands beyond safe limit")
        for member in members:
            path = Path(member.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("unsafe archive path")

    @staticmethod
    def _strip_markup(value: str) -> str:
        value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
        value = re.sub(r"(?s)<[^>]+>", " ", value)
        return html.unescape(value)

    @staticmethod
    def _looks_like_text(value: str) -> bool:
        visible = [char for char in value if not char.isspace()]
        if not visible:
            return False
        readable = sum(char.isprintable() and (char.isalnum() or char in ".,;:!?()-/%₺") for char in visible)
        return readable / len(visible) >= 0.72

    @staticmethod
    def _clean_text(value: str) -> str:
        value = value.replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()

    @staticmethod
    def _preview(text: str, limit: int = 800) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        return compact if len(compact) <= limit else f"{compact[: limit - 1].rstrip()}…"

    def _detect_document_type(self, file_name: str, text: str, extension: str) -> tuple[str, float]:
        haystack = self._ascii_fold(f"{Path(file_name).stem} {text[:6000]}")
        rules = [
            ("noter satış sözleşmesi", ("noter satis", "arac satis sozlesmesi", "satis sozlesmesi")),
            ("cevap dilekçesi", ("cevap dilekcesi", "cevaplarimiz")),
            ("dava dilekçesi", ("dava dilekcesi", "davaci", "sonuc ve istem")),
            ("tensip zaptı", ("tensip zapti", "tensip tutanagi")),
            ("bilirkişi raporu", ("bilirkisi raporu",)),
            ("ekspertiz raporu", ("ekspertiz raporu", "ekspertiz")),
            ("servis raporu", ("servis raporu", "servis formu")),
            ("tebligat belgesi", ("tebligat", "teblig mazbatasi")),
            ("ihtarname", ("ihtarname", "ihtar eden")),
            ("vekaletname", ("vekaletname", "vekil tayin")),
            ("TRAMER kaydı", ("tramer", "hasar kaydi")),
            ("mahkeme kararı", ("gerekceli karar", "mahkeme karari", "hukum")),
            ("ara karar", ("ara karar",)),
            ("delil listesi", ("delil listesi", "delillerimiz")),
            ("dekont", ("dekont", "islem referans", "odeme makbuzu")),
            ("ruhsat", ("arac tescil belgesi", "ruhsat")),
        ]
        for document_type, needles in rules:
            if any(needle in haystack for needle in needles):
                return document_type, 0.9 if any(needle in self._ascii_fold(file_name) for needle in needles) else 0.78
        if extension == ".udf":
            return "UYAP evrakı", 0.95
        return "diğer", 0.35 if text else 0.15

    def _extract_facts(
        self,
        document_id: str,
        file_name: str,
        text: str,
        pages: list[tuple[int | None, str]],
    ) -> list[ExtractedFact]:
        if not text:
            return []
        facts: list[ExtractedFact] = []

        self._add_first(facts, "court", text, pages, document_id, file_name, [
            r"(?im)^\s*(?:mahkeme\s*[:\-]\s*)?([^\n:]{3,100}?\s+Mahkemesi)\s*$",
        ], 0.94)
        self._add_first(facts, "case_number", text, pages, document_id, file_name, [
            r"(?i)\b(?:esas|dosya)\s*(?:no|numarası|sayısı)?\s*[:\-]?\s*(\d{4}\s*/\s*\d+(?:\s*[A-Za-zÇĞİÖŞÜçğıöşü.]*)?)",
        ], 0.95)

        party_values: list[str] = []
        party_matches: list[re.Match[str]] = []
        for match in re.finditer(r"(?im)^\s*(Davacı|Davalı|Alıcı|Satıcı|Başvurucu|Talep Eden|İhtar Eden|Muhatap)\s*[:\-]\s*([^\n]{2,160})", text):
            party_values.append(f"{match.group(1)}: {match.group(2).strip()}")
            party_matches.append(match)
        if party_values:
            self._append_fact(facts, "parties", "; ".join(party_values[:8]), text, pages, document_id, file_name, party_matches[0], 0.92)

        date = r"(\d{1,2}[./-]\d{1,2}[./-]\d{4})"
        self._add_first(facts, "service_date", text, pages, document_id, file_name, [rf"(?i)\b(?:tebliğ|tebellüğ)\s*(?:tarihi)?\s*[:\-]?\s*{date}"], 0.96)
        self._add_first(facts, "hearing_date", text, pages, document_id, file_name, [rf"(?i)\b(?:duruşma|celse)\s*(?:günü|tarihi)?\s*[:\-]?\s*{date}"], 0.96)
        self._add_first(facts, "sale_date", text, pages, document_id, file_name, [rf"(?i)\b(?:satış|devir)\s*(?:tarihi)?\s*[:\-]?\s*{date}"], 0.96)
        self._add_first(facts, "notice_date", text, pages, document_id, file_name, [rf"(?i)\b(?:ihtar|ihtarname)\s*(?:tarihi)?\s*[:\-]?\s*{date}"], 0.94)
        self._add_first(facts, "report_date", text, pages, document_id, file_name, [rf"(?i)\b(?:rapor|inceleme)\s*(?:tarihi)?\s*[:\-]?\s*{date}"], 0.94)
        self._add_first(facts, "document_date", text, pages, document_id, file_name, [rf"(?im)^\s*(?:belge|düzenleme|işlem)?\s*tarih(?:i)?\s*[:\-]\s*{date}"], 0.9)

        self._add_first(facts, "sale_price", text, pages, document_id, file_name, [
            r"(?i)\b(?:satış|devir|araç)\s*bedel(?:i)?\s*[:\-]?\s*((?:\d{1,3}(?:[. ]\d{3})+|\d+)(?:,\d{1,2})?\s*(?:TL|TRY|₺))",
        ], 0.97)
        self._add_first(facts, "vehicle_plate", text, pages, document_id, file_name, [
            r"(?i)\bplaka(?:\s*(?:no|numarası))?\s*[:\-]?\s*(\d{2}\s*[A-ZÇĞİÖŞÜ]{1,3}\s*\d{2,5})\b",
        ], 0.96)
        self._add_first(facts, "vehicle_vin", text, pages, document_id, file_name, [
            r"(?i)\b(?:şasi|şase|VIN)(?:\s*(?:no|numarası))?\s*[:\-]?\s*([A-HJ-NPR-Z0-9]{15,20})\b",
        ], 0.97)
        self._add_first(facts, "vehicle_make_model", text, pages, document_id, file_name, [
            r"(?im)^\s*(?:marka\s*/\s*model|marka\s+model|araç)\s*[:\-]\s*([^\n]{2,100})",
            r"(?im)^\s*Marka\s*[:\-]\s*([^\n]{2,50})(?:\n|\s{2,})\s*Model\s*[:\-]\s*([^\n]{2,50})",
        ], 0.9)
        self._add_first(facts, "notary_info", text, pages, document_id, file_name, [
            r"(?i)\bnoterlik\s*[:\-]\s*([^\n]{2,100})",
            r"(?im)^\s*([^\n]{2,100}?\s+Noterliği)(?:\s|$)",
        ], 0.92)
        self._add_first(facts, "report_number", text, pages, document_id, file_name, [
            r"(?i)\brapor\s*(?:no|numarası|sayısı)\s*[:\-]?\s*([A-Z0-9./-]{2,50})",
        ], 0.92)
        self._add_first(facts, "deadlines", text, pages, document_id, file_name, [
            r"(?i)\b((?:tebliğden|bildirimden|karardan)?\s*itibaren\s+\d+\s*(?:gün|hafta|ay)\s*(?:içinde|süreyle)?)",
            r"(?i)\b(\d+\s*(?:günlük|haftalık|aylık)\s+süre)",
        ], 0.88)
        self._add_first(facts, "claim_result", text, pages, document_id, file_name, [
            r"(?is)\b(?:SONUÇ\s+VE\s+İSTEM|TALEP\s+SONUCU)\s*[:\-]?\s*(.{20,700}?)(?:\n\s*(?:DELİLLER|HUKUKİ NEDENLER|EKLER)\b|$)",
        ], 0.88)
        self._add_first(facts, "evidence", text, pages, document_id, file_name, [
            r"(?is)\b(?:DELİLLER|DELİL LİSTESİ|DELİLLERİMİZ)\s*[:\-]?\s*(.{5,600}?)(?:\n\s*(?:HUKUKİ NEDENLER|SONUÇ|EKLER)\b|$)",
        ], 0.88)
        self._add_first(facts, "technical_findings", text, pages, document_id, file_name, [
            r"(?im)^\s*(?:teknik\s+)?(?:tespit|bulgu|sonuç)(?:ler|ları)?\s*[:\-]\s*([^\n]{10,500})",
            r"(?im)^\s*([^\n]{0,80}(?:arıza|hasar|değişen parça|motor)[^\n]{10,300})$",
        ], 0.82)
        self._add_first(facts, "payment_info", text, pages, document_id, file_name, [
            r"(?im)^\s*([^\n]{0,100}(?:dekont|ödeme|havale|EFT|işlem referans)[^\n]{2,300})$",
        ], 0.86)
        self._add_first(facts, "power_of_attorney_info", text, pages, document_id, file_name, [
            r"(?is)\b(?:vekil\s+tayin|vekalet\s+veren|vekaletname)\b(.{10,500}?)(?:\n\n|$)",
        ], 0.84)
        self._add_first(facts, "risk_signals", text, pages, document_id, file_name, [
            r"(?im)^\s*([^\n]{0,100}(?:zamanaşımı|hak düşürücü|yetki itirazı|görev itirazı|imza inkârı|sahtecilik|süre aşımı)[^\n]{0,200})$",
        ], 0.8)
        return facts

    def _add_first(
        self,
        facts: list[ExtractedFact],
        key: str,
        text: str,
        pages: list[tuple[int | None, str]],
        document_id: str,
        file_name: str,
        patterns: Iterable[str],
        confidence: float,
    ) -> None:
        if any(fact.fact_key == key for fact in facts):
            return
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            groups = [part.strip() for part in match.groups() if part and part.strip()]
            value = " ".join(groups) if groups else match.group(0).strip()
            self._append_fact(facts, key, value, text, pages, document_id, file_name, match, confidence)
            return

    def _append_fact(
        self,
        facts: list[ExtractedFact],
        key: str,
        value: str,
        text: str,
        pages: list[tuple[int | None, str]],
        document_id: str,
        file_name: str,
        match: re.Match[str],
        confidence: float,
    ) -> None:
        clean_value = re.sub(r"\s+", " ", value).strip(" :-\n\t")[:1000]
        if not clean_value:
            return
        start, end = match.span()
        excerpt = re.sub(r"\s+", " ", text[max(0, start - 90): min(len(text), end + 90)]).strip()[:500]
        page_number = self._page_for_excerpt(match.group(0), pages)
        facts.append(ExtractedFact(
            fact_key=key,
            fact_value=clean_value,
            source_document_id=document_id,
            source_file_name=file_name,
            page_number=page_number,
            excerpt=excerpt,
            confidence_score=confidence,
            verification_status="fact_confirmed",
        ))

    @staticmethod
    def _page_for_excerpt(value: str, pages: list[tuple[int | None, str]]) -> int | None:
        needle = re.sub(r"\s+", " ", value).strip()[:80]
        for number, page_text in pages:
            if needle and needle in re.sub(r"\s+", " ", page_text):
                return number
        return None

    def _find_conflicts(self, record: DocumentRecord, claims: dict[str, str]) -> list[DocumentConflict]:
        conflicts: list[DocumentConflict] = []
        for fact in record.extracted_facts:
            user_value = claims.get(fact.fact_key)
            if not user_value or self._values_equivalent(user_value, fact.fact_value):
                continue
            fact.verification_status = "conflict_detected"
            label = FACT_LABELS.get(fact.fact_key, fact.fact_key)
            warning = (
                f"{label.capitalize()} bakımından kullanıcı beyanı ile {record.safe_file_name} "
                "belgesi arasında çelişki var. Dilekçede kullanılacak bilgi doğrulanmalıdır."
            )
            conflicts.append(DocumentConflict(
                fact_key=fact.fact_key,
                user_value=user_value,
                document_value=fact.fact_value,
                source_document_id=record.document_id,
                source_file_name=record.file_name,
                warning=warning,
            ))
        return conflicts

    @classmethod
    def _values_equivalent(cls, left: str, right: str) -> bool:
        left_norm = cls._ascii_fold(left)
        right_norm = cls._ascii_fold(right)
        left_numbers = re.sub(r"\D", "", left_norm)
        right_numbers = re.sub(r"\D", "", right_norm)
        if left_numbers and right_numbers:
            return left_numbers == right_numbers
        return left_norm == right_norm or left_norm in right_norm or right_norm in left_norm

    @staticmethod
    def _canonical_fact_key(key: str) -> str:
        folded = DocumentIntakeService._ascii_fold(key).replace(" ", "_")
        aliases = {
            "mahkeme": "court",
            "dosya_numarasi": "case_number",
            "taraflar": "parties",
            "belge_tarihi": "document_date",
            "teblig_tarihi": "service_date",
            "durusma_tarihi": "hearing_date",
            "sureler": "deadlines",
            "satis_tarihi": "sale_date",
            "satis_bedeli": "sale_price",
            "arac_marka_model": "vehicle_make_model",
            "plaka": "vehicle_plate",
            "sasi": "vehicle_vin",
            "noterlik_bilgisi": "notary_info",
            "ihtar_tarihi": "notice_date",
            "talep_sonucu": "claim_result",
            "deliller": "evidence",
            "rapor_tarihi": "report_date",
            "rapor_numarasi": "report_number",
            "teknik_tespitler": "technical_findings",
            "odeme_bilgisi": "payment_info",
            "vekalet_bilgileri": "power_of_attorney_info",
        }
        return aliases.get(folded, folded)

    @staticmethod
    def _ascii_fold(value: str) -> str:
        translated = str(value).translate(str.maketrans({"ı": "i", "İ": "I", "ğ": "g", "Ğ": "G", "ş": "s", "Ş": "S"}))
        return " ".join(
            "".join(char for char in unicodedata.normalize("NFKD", translated) if not unicodedata.combining(char))
            .casefold()
            .split()
        )

    @staticmethod
    def _normalize_document_type(value: str | None) -> str | None:
        if not value:
            return None
        clean = " ".join(str(value).split())
        for allowed in DOCUMENT_TYPES:
            if DocumentIntakeService._ascii_fold(clean) == DocumentIntakeService._ascii_fold(allowed):
                return allowed
        raise DocumentIntakeError("Geçersiz belge türü seçildi.")

    def _file_path(self, document_id: str, extension: str) -> Path:
        safe = (self.upload_dir / f"{document_id}{extension}").resolve()
        if not str(safe).startswith(str(self.upload_dir)):
            raise DocumentIntakeError("Document storage path traversal blocked.")
        return safe

    def _find_duplicate(self, content_sha256: str, *, case_id: str) -> DocumentRecord | None:
        for record in self._records.values():
            if record.case_id != case_id:
                continue
            record_hash = record.content_sha256
            if not record_hash:
                path = self._file_path(record.document_id, record.file_extension)
                if path.exists():
                    try:
                        record_hash = hashlib.sha256(path.read_bytes()).hexdigest()
                        record.content_sha256 = record_hash
                    except OSError:
                        record_hash = ""
            if record_hash == content_sha256:
                return record
        return None

    def _content_signature(self, record: DocumentRecord) -> str:
        if record.content_sha256:
            return record.content_sha256
        path = self._file_path(record.document_id, record.file_extension)
        if path.exists():
            try:
                return hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                pass
        return f"{record.safe_file_name.casefold()}:{record.file_size}"

    def _set_record(self, record: DocumentRecord) -> None:
        with self._lock:
            self._records[record.document_id] = record.model_copy(deep=True)
            self._persist_records()

    def _load_records(self) -> dict[str, DocumentRecord]:
        if not self.index_path.exists():
            return {}
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            return {item["document_id"]: DocumentRecord.model_validate(item) for item in payload}
        except (OSError, ValueError, KeyError):
            return {}

    def _persist_records(self) -> None:
        payload = [record.model_dump(mode="json") for record in self._records.values()]
        temporary = self.index_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.index_path)


document_intake_service = DocumentIntakeService()
