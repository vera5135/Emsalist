"""Facade service for Legal Brain upload, ingest, cards and retrieval."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.models.legal_brain_models import (
    BookIngestResponse,
    BookUploadResponse,
    DoctrineCardResponse,
    LegalBrainChunksDebugResponse,
    LegalBrainDocumentItem,
    LegalBrainDocumentsResponse,
    LegalBrainRetrieveForCaseResponse,
    LegalBrainSearchResponse,
    LegalBrainStatuteArticleResponse,
)
from app.services.book_ingestion_service import book_ingestion_service
from app.services.book_memory_service import book_memory_service
from app.services.doctrine_card_service import doctrine_card_service
from app.services.legal_retrieval_service import legal_retrieval_service


class LegalBrainService:
    """High-level Legal Brain operations exposed by HTTP routes."""

    async def upload_book(
        self,
        *,
        file: Any,
        title: str,
        author: str = "",
        publisher: str = "",
        edition: str = "",
        publication_year: str = "",
        practice_area: str = "",
        topics: str = "",
        license_status: str = "user_confirmed",
        allowed_use: str = "internal_petition_support",
    ) -> BookUploadResponse:
        title = self._clean(title)
        if not title:
            raise ValueError("title alanı zorunludur.")

        filename = self._validate_pdf_filename(getattr(file, "filename", None))
        content = await file.read()
        self._validate_pdf_content(content)

        book_id = self._book_id(title)
        upload_path = book_memory_service.upload_path(book_id, filename)
        upload_path.write_bytes(content)

        metadata = {
            "book_id": book_id,
            "title": title,
            "author": self._clean(author),
            "publisher": self._clean(publisher),
            "edition": self._clean(edition),
            "publication_year": self._clean(publication_year),
            "practice_area": self._clean(practice_area),
            "topics": self._topics(topics),
            "license_status": self._clean(license_status) or "user_confirmed",
            "allowed_use": self._clean(allowed_use) or "internal_petition_support",
            "file_path": str(upload_path),
            "original_filename": filename,
            "source_type": "book",
            "status": "uploaded",
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }
        book_memory_service.save_book_metadata(metadata)
        return BookUploadResponse(book_id=book_id, title=title, status="uploaded")

    def ingest_book(self, book_id: str) -> BookIngestResponse:
        return BookIngestResponse(**book_ingestion_service.ingest(book_id))

    def create_doctrine_cards(self, *, book_id: str, practice_area: str) -> DoctrineCardResponse:
        return DoctrineCardResponse(**doctrine_card_service.create_cards(book_id=book_id, practice_area=practice_area))

    def list_documents(self) -> LegalBrainDocumentsResponse:
        documents: list[LegalBrainDocumentItem] = []
        for metadata in book_memory_service.list_documents():
            book_id = metadata.get("book_id", "")
            chunk_count = int(metadata.get("chunk_count") or 0)
            if not chunk_count and book_id:
                chunk_count = len(book_memory_service.list_book_chunks(book_id))
            page_count = int(metadata.get("page_count") or 0)
            topics = metadata.get("topics") or []
            if isinstance(topics, str):
                topics = [item.strip() for item in topics.split(",") if item.strip()]
            documents.append(
                LegalBrainDocumentItem(
                    book_id=book_id,
                    title=metadata.get("title", ""),
                    author=metadata.get("author", ""),
                    practice_area=metadata.get("practice_area", ""),
                    topics=topics,
                    indexed=chunk_count > 0 or metadata.get("status") == "ingested",
                    page_count=page_count,
                    chunk_count=chunk_count,
                )
            )
        return LegalBrainDocumentsResponse(documents=documents)

    def debug_book_chunks(self, book_id: str) -> LegalBrainChunksDebugResponse:
        self.ingest_metadata_exists(book_id)
        chunks = book_memory_service.list_book_chunks(book_id)
        debug_chunks = []
        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            topics = metadata.get("topics") or []
            if isinstance(topics, str):
                topics = [item.strip() for item in topics.split(",") if item.strip()]
            preview = " ".join(str(chunk.get("text") or "").split())
            debug_chunks.append(
                {
                    "page_start": int(metadata.get("page_start") or chunk.get("page_start") or 0),
                    "page_end": int(metadata.get("page_end") or chunk.get("page_end") or 0),
                    "practice_area": metadata.get("practice_area") or "",
                    "topics": topics,
                    "chunk_preview": preview[:1500],
                }
            )
        return LegalBrainChunksDebugResponse(
            book_id=book_id,
            chunk_count=len(debug_chunks),
            chunks=debug_chunks,
        )

    def get_statute_article(self, *, code: str, article: str) -> LegalBrainStatuteArticleResponse:
        record = book_memory_service.find_statute_article(code=code, article=article)
        if not record:
            raise FileNotFoundError(f"{code} {article} maddesi Legal Brain indeksinde bulunamadı.")
        metadata = record.get("metadata", {})
        return LegalBrainStatuteArticleResponse(
            code=metadata.get("code") or code.upper(),
            article=str(metadata.get("article") or article),
            article_title=metadata.get("article_title") or "",
            title=metadata.get("title") or "",
            source_type=metadata.get("source_type") or "statute",
            page_start=int(metadata.get("page_start") or record.get("page_start") or 0),
            page_end=int(metadata.get("page_end") or record.get("page_end") or 0),
            chunk_text=record.get("text") or metadata.get("chunk_text") or "",
            metadata=metadata,
        )

    def ingest_metadata_exists(self, book_id: str) -> None:
        book_memory_service.get_book_metadata(book_id)

    def search(
        self,
        *,
        query: str,
        practice_area: str | None,
        max_results: int,
    ) -> LegalBrainSearchResponse:
        return legal_retrieval_service.search(
            query=query,
            practice_area=practice_area,
            max_results=max_results,
        )

    def retrieve_for_case(
        self,
        *,
        case_text: str,
        practice_area: str | None,
        max_sources: int,
        legal_brain_query: str | None = None,
        blocked_topics: list[str] | None = None,
    ) -> LegalBrainRetrieveForCaseResponse:
        return legal_retrieval_service.retrieve_for_case(
            case_text=case_text,
            practice_area=practice_area,
            max_sources=max_sources,
            legal_brain_query=legal_brain_query,
            blocked_topics=blocked_topics or [],
        )

    @staticmethod
    def _book_id(title: str) -> str:
        slug = "".join(character.lower() if character.isalnum() else "-" for character in title)
        slug = "-".join(part for part in slug.split("-") if part)[:40] or "book"
        return f"{slug}-{uuid.uuid4().hex[:10]}"

    @staticmethod
    def _clean(value: Any) -> str:
        return " ".join(str(value or "").split())

    @staticmethod
    def _validate_pdf_filename(filename: str | None) -> str:
        cleaned = " ".join(str(filename or "").split())
        if not cleaned:
            raise ValueError("file.filename boş olamaz.")
        if not cleaned.casefold().endswith(".pdf"):
            raise ValueError("Sadece PDF dosyaları kabul edilir.")
        return cleaned

    @staticmethod
    def _validate_pdf_content(content: bytes) -> None:
        if not content:
            raise ValueError("PDF dosyası boştur.")
        if not content.startswith(b"%PDF"):
            raise ValueError("Yüklenen dosya geçerli bir PDF gibi görünmüyor.")

    @staticmethod
    def _topics(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            raw_values = value
        else:
            raw_values = str(value).split(",")
        return [" ".join(str(item).split()) for item in raw_values if " ".join(str(item).split())]


legal_brain_service = LegalBrainService()
