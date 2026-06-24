"""PDF extraction and chunking for Legal Brain books."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.book_memory_service import book_memory_service
from app.services.legal_embedding_service import legal_embedding_service


MIN_CHUNK_WORDS = 700
MAX_CHUNK_WORDS = 1200
ARTICLE_HEADING_RE = re.compile(
    r"^\s*(?:MADDE|Madde|madde|M\.|m\.)\s*(\d{1,4})(?:\s*[/.-]?\s*(.*))?$"
)


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str


class BookIngestionService:
    """Extract text from uploaded PDFs and persist indexed memory chunks."""

    def ingest(self, book_id: str) -> dict[str, Any]:
        metadata = book_memory_service.get_book_metadata(book_id)
        file_path = Path(metadata["file_path"])
        warnings: list[str] = []
        pages, extraction_warnings = self._extract_pages(file_path)
        warnings.extend(extraction_warnings)
        chunks = self._build_chunks(book_id=book_id, pages=pages, metadata=metadata)
        embeddings = legal_embedding_service.embed_texts([chunk["text"] for chunk in chunks])
        backend, storage_warnings = book_memory_service.store_chunks(
            book_metadata=metadata,
            chunks=chunks,
            embeddings=embeddings,
        )
        warnings.extend(storage_warnings)
        metadata["status"] = "ingested"
        metadata["page_count"] = len(pages)
        metadata["chunk_count"] = len(chunks)
        metadata["index_backend"] = backend
        book_memory_service.save_book_metadata(metadata)
        return {
            "book_id": book_id,
            "page_count": len(pages),
            "chunk_count": len(chunks),
            "status": "ingested",
            "index_backend": backend,
            "warnings": warnings,
        }

    def _extract_pages(self, file_path: Path) -> tuple[list[ExtractedPage], list[str]]:
        extractors = (
            self._extract_with_pymupdf,
            self._extract_with_pdfplumber,
            self._extract_with_pypdf,
        )
        warnings: list[str] = []
        for extractor in extractors:
            try:
                pages = extractor(file_path)
                if pages:
                    return pages, warnings
            except Exception as exc:
                warnings.append(f"{extractor.__name__} başarısız oldu: {self._short_error(exc)}")
        return [], warnings or ["PDF metni çıkarılamadı."]

    @staticmethod
    def _extract_with_pymupdf(file_path: Path) -> list[ExtractedPage]:
        import fitz  # type: ignore

        pages: list[ExtractedPage] = []
        with fitz.open(file_path) as document:
            for index, page in enumerate(document, start=1):
                pages.append(ExtractedPage(page_number=index, text=page.get_text("text") or ""))
        return pages

    @staticmethod
    def _extract_with_pdfplumber(file_path: Path) -> list[ExtractedPage]:
        import pdfplumber  # type: ignore

        pages: list[ExtractedPage] = []
        with pdfplumber.open(file_path) as document:
            for index, page in enumerate(document.pages, start=1):
                pages.append(ExtractedPage(page_number=index, text=page.extract_text() or ""))
        return pages

    @staticmethod
    def _extract_with_pypdf(file_path: Path) -> list[ExtractedPage]:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(file_path))
        return [
            ExtractedPage(page_number=index, text=page.extract_text() or "")
            for index, page in enumerate(reader.pages, start=1)
        ]

    def _build_chunks(
        self,
        *,
        book_id: str,
        pages: list[ExtractedPage],
        metadata: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if self._is_statute_source(metadata):
            statute_chunks = self._build_statute_chunks(book_id=book_id, pages=pages, metadata=metadata)
            if statute_chunks:
                return statute_chunks
        return self._build_page_chunks(book_id=book_id, pages=pages)

    def _build_page_chunks(self, *, book_id: str, pages: list[ExtractedPage]) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        current_words: list[str] = []
        page_start = 0
        page_end = 0
        section_title = ""

        for page in pages:
            page_lines = self._clean_lines(page.text)
            detected_title = self._detect_section_title(page_lines)
            if detected_title:
                section_title = detected_title

            page_words = " ".join(page_lines).split()
            if not page_words:
                continue

            if not page_start:
                page_start = page.page_number
            page_end = page.page_number
            current_words.extend(page_words)

            while len(current_words) >= MAX_CHUNK_WORDS:
                chunk_words = current_words[:MAX_CHUNK_WORDS]
                chunks.append(
                    self._chunk_record(
                        book_id=book_id,
                        chunk_index=len(chunks),
                        words=chunk_words,
                        page_start=page_start,
                        page_end=page_end,
                        section_title=section_title,
                    )
                )
                current_words = current_words[MAX_CHUNK_WORDS:]
                page_start = page.page_number

        if current_words:
            if chunks and len(current_words) < MIN_CHUNK_WORDS:
                chunks[-1]["text"] = f"{chunks[-1]['text']} {' '.join(current_words)}"
                chunks[-1]["page_end"] = page_end
            else:
                chunks.append(
                    self._chunk_record(
                        book_id=book_id,
                        chunk_index=len(chunks),
                        words=current_words,
                        page_start=page_start or page_end,
                        page_end=page_end,
                        section_title=section_title,
                    )
                )
        return chunks

    def _build_statute_chunks(
        self,
        *,
        book_id: str,
        pages: list[ExtractedPage],
        metadata: dict[str, Any],
    ) -> list[dict[str, Any]]:
        code = self._statute_code(metadata)
        chunks: list[dict[str, Any]] = []
        current_article = ""
        current_title = ""
        current_lines: list[str] = []
        page_start = 0
        page_end = 0

        def flush() -> None:
            nonlocal current_article, current_title, current_lines, page_start, page_end
            if not current_article or not current_lines:
                return
            text = "\n".join(current_lines).strip()
            if not text:
                return
            section_title = f"{code} Madde {current_article}"
            if current_title:
                section_title = f"{section_title} - {current_title}"
            chunks.append(
                {
                    "chunk_id": f"{book_id}:article:{code}:{current_article}",
                    "book_id": book_id,
                    "chunk_index": len(chunks),
                    "text": text,
                    "page_start": page_start,
                    "page_end": page_end,
                    "section_title": section_title,
                    "code": code,
                    "article": current_article,
                    "article_title": current_title,
                    "chunk_text": text,
                }
            )

        for page in pages:
            lines = self._clean_lines(page.text)
            for line in lines:
                article_match = ARTICLE_HEADING_RE.match(line)
                if article_match:
                    flush()
                    current_article = article_match.group(1)
                    current_title = self._clean_article_title(article_match.group(2) or "")
                    current_lines = [line]
                    page_start = page.page_number
                    page_end = page.page_number
                    continue

                if current_article:
                    current_lines.append(line)
                    page_end = page.page_number

        flush()
        return chunks

    @staticmethod
    def _clean_lines(text: str) -> list[str]:
        lines: list[str] = []
        for raw_line in text.replace("\r", "\n").split("\n"):
            line = re.sub(r"\s+", " ", raw_line).strip()
            if line:
                lines.append(line)
        return lines

    @staticmethod
    def _detect_section_title(lines: list[str]) -> str:
        for line in lines[:8]:
            clean = line.strip(" .:-")
            if 4 <= len(clean) <= 120 and (
                clean.isupper()
                or re.match(r"^(BÖLÜM|KISIM|MADDE|§|\d+(\.\d+)*[.)-])\s+", clean, flags=re.IGNORECASE)
            ):
                return clean.title() if clean.isupper() else clean
        return ""

    def _is_statute_source(self, metadata: dict[str, Any]) -> bool:
        combined = self._plain(
            " ".join(
                str(metadata.get(key, ""))
                for key in ("title", "source_type", "practice_area", "author", "publisher")
            )
            + " "
            + self._topics_text(metadata.get("topics", []))
        )
        statute_signals = (
            "kanun",
            "mevzuat",
            "statute",
            "turk medeni kanunu",
            "türk medeni kanunu",
            "tmk",
            "hmk",
            "hukuk muhakemeleri kanunu",
        )
        return any(signal in combined for signal in statute_signals)

    def _statute_code(self, metadata: dict[str, Any]) -> str:
        combined = self._plain(
            " ".join(
                str(metadata.get(key, ""))
                for key in ("title", "source_type", "practice_area", "author", "publisher")
            )
            + " "
            + self._topics_text(metadata.get("topics", []))
        )
        if "hmk" in combined or "hukuk muhakemeleri" in combined:
            return "HMK"
        if "tbk" in combined or "borclar kanunu" in combined:
            return "TBK"
        if "tmk" in combined or "medeni kanun" in combined:
            return "TMK"
        return "KANUN"

    @staticmethod
    def _clean_article_title(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip(" .:-–—")).strip()

    @staticmethod
    def _plain(text: str) -> str:
        translation = str.maketrans(
            {
                "ç": "c",
                "Ç": "c",
                "ğ": "g",
                "Ğ": "g",
                "ı": "i",
                "I": "i",
                "İ": "i",
                "ö": "o",
                "Ö": "o",
                "ş": "s",
                "Ş": "s",
                "ü": "u",
                "Ü": "u",
            }
        )
        normalized = text.translate(translation).casefold()
        return " ".join(normalized.split())

    @staticmethod
    def _topics_text(value: Any) -> str:
        if isinstance(value, list):
            return " ".join(str(item) for item in value if item)
        return str(value or "")

    @staticmethod
    def _chunk_record(
        *,
        book_id: str,
        chunk_index: int,
        words: list[str],
        page_start: int,
        page_end: int,
        section_title: str,
    ) -> dict[str, Any]:
        return {
            "chunk_id": f"{book_id}:chunk:{chunk_index:05d}",
            "book_id": book_id,
            "chunk_index": chunk_index,
            "text": " ".join(words),
            "page_start": page_start,
            "page_end": page_end,
            "section_title": section_title,
        }

    @staticmethod
    def _short_error(error: Exception) -> str:
        message = " ".join(str(error).split())
        return message[:200] or error.__class__.__name__


book_ingestion_service = BookIngestionService()
