"""Pydantic contracts for the Legal Brain module."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class BookUploadResponse(BaseModel):
    book_id: str
    title: str
    status: str


class BookIngestRequest(BaseModel):
    book_id: str = Field(min_length=3)


class BookIngestResponse(BaseModel):
    book_id: str
    page_count: int
    chunk_count: int
    status: str
    index_backend: str
    warnings: list[str]


class DoctrineCardRequest(BaseModel):
    book_id: str = Field(min_length=3)
    practice_area: str = Field(min_length=2)

    @field_validator("practice_area")
    @classmethod
    def normalize_practice_area(cls, value: str) -> str:
        return " ".join(value.split())


class DoctrineCard(BaseModel):
    topic: str
    principle: str
    related_articles: list[str]
    practice_note: str
    source_label: str


class DoctrineCardResponse(BaseModel):
    book_id: str
    doctrine_cards: list[DoctrineCard]
    warnings: list[str] = Field(default_factory=list)


class LegalBrainSearchRequest(BaseModel):
    query: str = Field(min_length=3)
    practice_area: str | None = None
    max_results: int = Field(default=10, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("practice_area")
    @classmethod
    def normalize_area(cls, value: str | None) -> str | None:
        return " ".join(value.split()) if value else None


class LegalBrainSearchResult(BaseModel):
    source_type: str
    title: str
    author: str
    page_start: int
    page_end: int
    section_title: str
    article: str = ""
    relevance_score: int
    matched_terms: list[str] = Field(default_factory=list)
    is_directly_relevant: bool = False
    relevance_reason: str = ""
    chunk_preview: str
    doctrine_principle: str
    usable_argument: str
    citation_label: str


class LegalBrainSearchResponse(BaseModel):
    results: list[LegalBrainSearchResult]
    warnings: list[str] = Field(default_factory=list)


class LegalBrainChunkDebugItem(BaseModel):
    page_start: int
    page_end: int
    practice_area: str
    topics: list[str]
    chunk_preview: str


class LegalBrainChunksDebugResponse(BaseModel):
    book_id: str
    chunk_count: int
    chunks: list[LegalBrainChunkDebugItem]


class LegalBrainDocumentItem(BaseModel):
    book_id: str
    title: str
    author: str
    practice_area: str
    topics: list[str]
    indexed: bool
    page_count: int
    chunk_count: int


class LegalBrainDocumentsResponse(BaseModel):
    documents: list[LegalBrainDocumentItem]


class LegalBrainStatuteArticleResponse(BaseModel):
    code: str
    article: str
    article_title: str
    title: str
    source_type: str
    page_start: int
    page_end: int
    chunk_text: str
    metadata: dict[str, Any]


class LegalBrainRetrieveForCaseRequest(BaseModel):
    case_text: str = Field(min_length=10)
    practice_area: str | None = None
    max_sources: int = Field(default=10, ge=1, le=50)
    legal_brain_query: str | None = None
    blocked_topics: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("case_text", "legal_brain_query")
    @classmethod
    def normalize_case_text(cls, value: str | None) -> str | None:
        return " ".join(value.split()) if value else value

    @field_validator("practice_area")
    @classmethod
    def normalize_practice_area(cls, value: str | None) -> str | None:
        return " ".join(value.split()) if value else None


class StatuteSource(BaseModel):
    code: str
    article: str
    relevance: str


class LegalBrainRetrieveForCaseResponse(BaseModel):
    detected_topic: str
    statute_sources: list[StatuteSource]
    book_sources: list[LegalBrainSearchResult]
    doctrine_cards: list[DoctrineCard]
    recommended_arguments: list[str]
    warnings: list[str]
