"""P2.5 — Pure document parsing, validation and support-level classification.

This module contains stateless, filesystem-free helpers used by the DB-backed
document pipeline. Parsing logic mirrors the proven approaches already used in
``document_intake_service`` (pypdf per-page, DOCX XML paragraphs, UDF ZIP text,
multi-encoding TXT) but returns plain data so it can be driven from an async,
DB-backed service. No uploaded content is ever executed.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree

# Real, verified capability level per extension. A format is only "supported"
# to the degree a working parser exists — never merely because the extension is
# on an allowlist.
SUPPORT_FULL = "fully_supported"
SUPPORT_TEXT = "text_extraction_only"
SUPPORT_UPLOAD = "upload_only"
SUPPORT_UNSUPPORTED = "unsupported"

SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".docx", ".udf", ".jpg", ".jpeg", ".png"}
BLOCKED_EXTENSIONS = {".exe", ".bat", ".cmd", ".ps1", ".js", ".vbs", ".scr", ".sh", ".dll"}

MIME_TYPES = {
    ".txt": "text/plain",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".udf": "application/octet-stream",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}

# Declared support level per extension (the honest matrix).
SUPPORT_LEVEL = {
    ".txt": SUPPORT_FULL,
    ".pdf": SUPPORT_TEXT,
    ".docx": SUPPORT_TEXT,
    ".udf": SUPPORT_TEXT,
    ".jpg": SUPPORT_UPLOAD,
    ".jpeg": SUPPORT_UPLOAD,
    ".png": SUPPORT_UPLOAD,
}

MAX_ARCHIVE_ENTRIES = 2000
MAX_ARCHIVE_UNCOMPRESSED = 50 * 1024 * 1024
MAX_TEXT_CHARS = 5_000_000


class DocumentValidationError(Exception):
    """Raised when an upload fails a security/format precondition."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class ParsedPage:
    page_number: int | None
    text: str


@dataclass
class ParseResult:
    # "extracted" (full), "partial", "ocr_required", "unsupported", "failed"
    status: str
    pages: list[ParsedPage] = field(default_factory=list)
    warning: str | None = None

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages if p.text).strip()


def sanitize_filename(file_name: str) -> str:
    original = Path(file_name or "belge").name
    normalized = unicodedata.normalize("NFKC", original).replace("\x00", "")
    extension = Path(normalized).suffix.lower()
    stem = Path(normalized).stem
    stem = re.sub(r"[^0-9A-Za-zÇĞİÖŞÜçğıöşü._ -]+", "_", stem)
    stem = re.sub(r"[\s._-]+", "_", stem).strip("_.")[:120] or "belge"
    return f"{stem}{extension}"


def extension_of(file_name: str) -> str:
    return Path(sanitize_filename(file_name)).suffix.lower()


def support_level_for(extension: str) -> str:
    return SUPPORT_LEVEL.get(extension, SUPPORT_UNSUPPORTED)


def _content_looks_like(extension: str, content: bytes) -> None:
    """Magic-byte / structural validation guarding against MIME spoofing."""
    if content.startswith(b"MZ"):
        raise DocumentValidationError("DOC-TYPE-02", "Çalıştırılabilir dosya içeriği kabul edilmiyor.")
    if extension == ".pdf" and not content.lstrip()[:1024].startswith(b"%PDF"):
        raise DocumentValidationError("DOC-TYPE-02", "Dosya içeriği geçerli bir PDF değil.")
    if extension == ".png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise DocumentValidationError("DOC-TYPE-02", "Dosya içeriği geçerli bir PNG değil.")
    if extension in {".jpg", ".jpeg"} and not content.startswith(b"\xff\xd8\xff"):
        raise DocumentValidationError("DOC-TYPE-02", "Dosya içeriği geçerli bir JPEG değil.")
    if extension == ".docx" and not zipfile.is_zipfile(BytesIO(content)):
        raise DocumentValidationError("DOC-TYPE-02", "Dosya içeriği geçerli bir DOCX değil.")


def validate_upload(file_name: str, content: bytes, max_size: int) -> str:
    """Validates a candidate upload; returns the sanitized extension.

    Raises :class:`DocumentValidationError` with a stable error code on any
    security/format failure (extension allowlist, blocked type, empty file,
    size, magic-byte / MIME spoofing).
    """
    if "\x00" in (file_name or ""):
        raise DocumentValidationError("DOC-TYPE-02", "Geçersiz dosya adı.")
    extension = extension_of(file_name)
    if not extension:
        raise DocumentValidationError("DOC-TYPE-02", "Dosya uzantısı tanınmıyor.")
    if extension in BLOCKED_EXTENSIONS:
        raise DocumentValidationError("DOC-TYPE-02", "Bu dosya türü güvenlik nedeniyle kabul edilmiyor.")
    if extension not in SUPPORTED_EXTENSIONS:
        raise DocumentValidationError("DOC-TYPE-02", f"Desteklenmeyen dosya türü: {extension}")
    if not content:
        raise DocumentValidationError("DOC-EXTRACT-06", "Boş dosya yüklenemez.")
    if len(content) > max_size:
        raise DocumentValidationError(
            "DOC-SIZE-03", f"Dosya boyutu {max_size // (1024 * 1024)} MB sınırını aşıyor."
        )
    _content_looks_like(extension, content)
    return extension


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:MAX_TEXT_CHARS]


def _decode_turkish_text(content: bytes) -> str:
    candidates: list[tuple[float, str]] = []
    for encoding in ("utf-8-sig", "utf-8", "cp1254", "iso-8859-9"):
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        controls = sum(
            1 for ch in text if unicodedata.category(ch) == "Cc" and ch not in "\n\r\t"
        )
        mojibake = sum(text.count(tok) for tok in ("Ã", "Ä", "Å", "\ufffd"))
        turkish = sum(text.count(ch) for ch in "çğıöşüÇĞİÖŞÜ")
        score = turkish * 2 - controls * 20 - mojibake * 8
        if encoding.startswith("utf-8"):
            score += 5
        candidates.append((score, text))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _looks_like_text(text: str) -> bool:
    if not text:
        return False
    printable = sum(1 for ch in text if ch.isprintable() or ch in "\n\r\t")
    return printable / max(len(text), 1) > 0.8


def _validate_archive(archive: zipfile.ZipFile) -> None:
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_ENTRIES:
        raise DocumentValidationError("DOC-SECURITY-04", "Arşiv çok fazla dosya içeriyor.")
    total = 0
    for info in infos:
        name = info.filename
        if name.startswith("/") or ".." in Path(name).parts:
            raise DocumentValidationError("DOC-SECURITY-04", "Arşiv güvenli olmayan yol içeriyor.")
        total += info.file_size
        if total > MAX_ARCHIVE_UNCOMPRESSED:
            raise DocumentValidationError("DOC-SECURITY-04", "Arşiv açılım boyutu sınırı aşıyor.")


def _strip_markup(text: str) -> str:
    import html as _html

    text = re.sub(r"<[^>]+>", " ", text)
    return _html.unescape(text)


def _parse_pdf(content: bytes) -> ParseResult:
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content), strict=False)
        pages: list[ParsedPage] = []
        any_failure = False
        for number, page in enumerate(reader.pages, start=1):
            try:
                page_text = _clean_text(page.extract_text() or "")
            except Exception:
                any_failure = True
                continue
            if page_text:
                pages.append(ParsedPage(page_number=number, text=page_text))
    except Exception:
        return ParseResult(status="failed", warning="PDF okunamadı.")
    if not pages:
        # Likely a scanned PDF with no text layer; OCR not available in P2.5.
        return ParseResult(status="ocr_required", warning="Bu PDF taranmış olabilir; metin katmanı bulunamadı.")
    status = "partial" if any_failure else "extracted"
    return ParseResult(status=status, pages=pages)


def _parse_docx(content: bytes) -> ParseResult:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            _validate_archive(archive)
            if "word/document.xml" not in archive.namelist():
                return ParseResult(status="failed", warning="DOCX yapısı okunamadı.")
            root = ElementTree.fromstring(archive.read("word/document.xml"))
            ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            blocks: list[str] = []
            for paragraph in root.iter(f"{ns}p"):
                chunks: list[str] = []
                for node in paragraph.iter():
                    if node.tag == f"{ns}t" and node.text:
                        chunks.append(node.text)
                    elif node.tag == f"{ns}tab":
                        chunks.append("\t")
                    elif node.tag == f"{ns}br":
                        chunks.append("\n")
                line = "".join(chunks).strip()
                if line:
                    blocks.append(line)
            text = _clean_text("\n".join(blocks))
    except DocumentValidationError:
        raise
    except Exception:
        return ParseResult(status="failed", warning="DOCX okunamadı.")
    if not text:
        return ParseResult(status="partial", warning="DOCX içinde okunabilir metin bulunamadı.")
    # DOCX has no reliable page numbers; never fabricate one.
    return ParseResult(status="extracted", pages=[ParsedPage(page_number=None, text=text)])


def _parse_udf(content: bytes) -> ParseResult:
    candidates: list[str] = []
    try:
        if zipfile.is_zipfile(BytesIO(content)):
            with zipfile.ZipFile(BytesIO(content)) as archive:
                _validate_archive(archive)
                for member in archive.infolist():
                    if member.is_dir():
                        continue
                    suffix = Path(member.filename).suffix.lower()
                    if suffix not in {".txt", ".xml", ".html", ".htm"}:
                        continue
                    decoded = _decode_turkish_text(archive.read(member))
                    if decoded:
                        candidates.append(_strip_markup(decoded))
        else:
            decoded = _decode_turkish_text(content)
            if decoded:
                candidates.append(_strip_markup(decoded))
    except DocumentValidationError:
        raise
    except Exception:
        candidates = []
    text = _clean_text("\n".join(candidates))
    if len(text) < 20 or not _looks_like_text(text):
        # Real binary UDF without embedded readable text — do not fabricate.
        return ParseResult(status="unsupported", warning="UYAP/UDF dönüştürücü veya PDF çıktısı gerekli.")
    return ParseResult(status="extracted", pages=[ParsedPage(page_number=None, text=text)])


def _parse_txt(content: bytes) -> ParseResult:
    text = _clean_text(_decode_turkish_text(content))
    if not text:
        return ParseResult(status="failed", warning="Metin çözümlenemedi.")
    return ParseResult(status="extracted", pages=[ParsedPage(page_number=None, text=text)])


def parse_document(extension: str, content: bytes) -> ParseResult:
    """Dispatches to the real parser for the extension.

    Images are upload-only (no OCR engine in P2.5) and return ``ocr_required``
    so the document card still exists without pretending text was extracted.
    """
    if extension == ".pdf":
        return _parse_pdf(content)
    if extension == ".docx":
        return _parse_docx(content)
    if extension == ".udf":
        return _parse_udf(content)
    if extension == ".txt":
        return _parse_txt(content)
    if extension in {".jpg", ".jpeg", ".png"}:
        return ParseResult(status="ocr_required", warning="Görsel belgeler için metin çıkarımı (OCR) henüz mevcut değil.")
    return ParseResult(status="unsupported", warning="Bu dosya türü analiz edilemiyor.")


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
