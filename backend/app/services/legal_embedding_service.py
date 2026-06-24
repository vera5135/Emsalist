"""Embedding helper for Legal Brain.

The service prefers sentence-transformers when it is installed and a local model
is available. If that stack is missing, it falls back to deterministic hashed
embeddings so ingestion and retrieval still work in the MVP.
"""

from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache


EMBEDDING_DIMENSION = 384


class LegalEmbeddingService:
    """Produce stable vector representations for legal text chunks."""

    def __init__(self) -> None:
        self._model = None
        self._model_checked = False

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        if model is not None:
            try:
                vectors = model.encode(texts, normalize_embeddings=True)
                return [list(map(float, vector)) for vector in vectors]
            except Exception:
                self._model = None
        return [self._hashed_embedding(text) for text in texts]

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def _load_model(self):
        if self._model_checked:
            return self._model
        self._model_checked = True
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer(
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                local_files_only=True,
            )
        except Exception:
            self._model = None
        return self._model

    @staticmethod
    @lru_cache(maxsize=10_000)
    def _token_index(token: str) -> int:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return int(digest[:8], 16) % EMBEDDING_DIMENSION

    def _hashed_embedding(self, text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIMENSION
        tokens = self._tokens(text)
        if not tokens:
            return vector
        for token in tokens:
            vector[self._token_index(token)] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return [
            token
            for token in re.findall(r"[a-zçğıöşü0-9]+", text.casefold())
            if len(token) > 2
        ]


legal_embedding_service = LegalEmbeddingService()
