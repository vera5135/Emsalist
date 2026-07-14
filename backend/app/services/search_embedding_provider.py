"""P2.7 — Search embedding provider abstraction and implementations."""
from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Sequence


class SearchEmbeddingProvider(ABC):
    """Abstract interface for generating text embeddings for hybrid search."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier used for embeddings."""

    @property
    @abstractmethod
    def embedding_version(self) -> str:
        """Version tag for the embedding configuration."""

    @property
    @abstractmethod
    def embedding_dimension(self) -> int:
        """Output dimension of the embedding vectors."""

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Whether the provider is ready to serve embeddings."""

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Produce embeddings for source documents (retrieval target vectors)."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Produce an embedding for a search query."""


# ---------------------------------------------------------------------------
# Disabled provider (no-embedding fallback)
# ---------------------------------------------------------------------------

class DisabledSearchEmbeddingProvider(SearchEmbeddingProvider):
    """Returns empty embeddings when semantic search is disabled."""

    @property
    def model_name(self) -> str:
        return "disabled"

    @property
    def embedding_version(self) -> str:
        return "disabled"

    @property
    def embedding_dimension(self) -> int:
        return 0

    @property
    def is_available(self) -> bool:
        return False

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return []


# ---------------------------------------------------------------------------
# Gemini embedding provider
# ---------------------------------------------------------------------------

class GeminiSearchEmbeddingProvider(SearchEmbeddingProvider):
    """Uses google-genai to produce embeddings via Gemini Embedding API."""

    def __init__(self, api_key: str, model: str, embedding_version: str) -> None:
        self._api_key = api_key
        self._model = model
        self._embedding_version = embedding_version
        self._client: object | None = None

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def embedding_version(self) -> str:
        return self._embedding_version

    @property
    def embedding_dimension(self) -> int:
        return 768

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    def _get_client(self) -> object:
        if self._client is None:
            import google.genai as genai
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            client = self._get_client()
            result = client.models.embed_content(
                model=self._model,
                contents=texts,
                config={"task_type": "RETRIEVAL_DOCUMENT"},
            )
            return _extract_embeddings(result, len(texts))
        except Exception:
            return [[] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        if not text.strip():
            return []
        try:
            client = self._get_client()
            result = client.models.embed_content(
                model=self._model,
                contents=[text],
                config={"task_type": "RETRIEVAL_QUERY"},
            )
            vectors = _extract_embeddings(result, 1)
            return vectors[0] if vectors else []
        except Exception:
            return []


def _extract_embeddings(result: object, expected_count: int) -> list[list[float]]:
    """Safely extract embedding vectors from a Gemini API response."""
    try:
        raw = result.embeddings
        if raw is None:
            return [[] for _ in range(expected_count)]
        vectors: list[list[float]] = []
        for entry in raw:
            if entry.values is not None:
                vectors.append(list(entry.values))
            else:
                vectors.append([])
        return vectors
    except Exception:
        return [[] for _ in range(expected_count)]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_embedding_provider(settings: object) -> SearchEmbeddingProvider:
    """Instantiate the appropriate embedding provider based on application settings."""
    if not getattr(settings, "search_semantic_enabled", False):
        return DisabledSearchEmbeddingProvider()

    api_key = getattr(settings, "gemini_api_key", "")
    if not api_key:
        return DisabledSearchEmbeddingProvider()

    model = getattr(settings, "search_embedding_model", "gemini-embedding-001")
    version = getattr(settings, "search_embedding_version", "p2.7-embedding-1")
    return GeminiSearchEmbeddingProvider(
        api_key=api_key,
        model=model,
        embedding_version=version,
    )


# ---------------------------------------------------------------------------
# Sensitive query detection
# ---------------------------------------------------------------------------

_TC_ID_RE = re.compile(r"\b[1-9]\d{10}\b")
_IBAN_RE = re.compile(r"\bTR\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{2}\b", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE_RE = re.compile(r"\b(?:\+90|0)?[5-9]\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}\b")
_TOKEN_RE = re.compile(r"\b[a-zA-Z0-9_-]{32,}\b")


def is_sensitive_query(text: str) -> bool:
    """Detect whether a search query text likely contains sensitive PII."""
    if not text or not text.strip():
        return False
    candidates = text[:200]
    if _TC_ID_RE.search(candidates):
        return True
    if _IBAN_RE.search(candidates):
        return True
    if _EMAIL_RE.search(candidates):
        return True
    if _PHONE_RE.search(candidates):
        return True
    if _TOKEN_RE.search(candidates):
        return True
    return False
