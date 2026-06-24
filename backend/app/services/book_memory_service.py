"""Persistent storage and retrieval for Legal Brain chunks and cards."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from importlib.util import find_spec
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parents[1]
LEGAL_BRAIN_DIR = APP_DIR / "legal_brain"
UPLOADS_DIR = LEGAL_BRAIN_DIR / "uploads"
INDEXES_DIR = LEGAL_BRAIN_DIR / "indexes"
DOCTRINE_CARDS_DIR = LEGAL_BRAIN_DIR / "doctrine_cards"
STATUTE_CARDS_DIR = LEGAL_BRAIN_DIR / "statute_cards"
STYLE_CARDS_DIR = LEGAL_BRAIN_DIR / "style_cards"
METADATA_DIR = LEGAL_BRAIN_DIR / "metadata"

CHUNKS_JSONL = INDEXES_DIR / "chunks.jsonl"
SQLITE_INDEX = INDEXES_DIR / "keyword_index.sqlite3"
CHROMA_DIR = INDEXES_DIR / "chroma"
CHROMA_COLLECTION = "legal_brain_chunks"
BOOKS_METADATA_INDEX = METADATA_DIR / "books.json"


class BookMemoryService:
    """Store uploaded book metadata, indexed chunks and doctrine cards."""

    def __init__(self) -> None:
        self.ensure_directories()

    def ensure_directories(self) -> None:
        for directory in (
            UPLOADS_DIR,
            INDEXES_DIR,
            DOCTRINE_CARDS_DIR,
            STATUTE_CARDS_DIR,
            STYLE_CARDS_DIR,
            METADATA_DIR,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        self._ensure_sqlite()

    def save_book_metadata(self, metadata: dict[str, Any]) -> None:
        self.ensure_directories()
        path = self.metadata_path(metadata["book_id"])
        path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        self._upsert_books_index(metadata)

    def get_book_metadata(self, book_id: str) -> dict[str, Any]:
        path = self.metadata_path(book_id)
        if not path.exists():
            raise FileNotFoundError(f"Kitap metadata bulunamadı: {book_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def list_documents(self) -> list[dict[str, Any]]:
        if BOOKS_METADATA_INDEX.exists():
            try:
                books = json.loads(BOOKS_METADATA_INDEX.read_text(encoding="utf-8"))
                if isinstance(books, list):
                    return [book for book in books if isinstance(book, dict)]
            except json.JSONDecodeError:
                pass

        documents: list[dict[str, Any]] = []
        for path in METADATA_DIR.glob("*.json"):
            if path.name == BOOKS_METADATA_INDEX.name:
                continue
            try:
                documents.append(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
        return documents

    def metadata_path(self, book_id: str) -> Path:
        return METADATA_DIR / f"{book_id}.json"

    def upload_path(self, book_id: str, filename: str) -> Path:
        safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", filename) or "book.pdf"
        return UPLOADS_DIR / f"{book_id}_{safe_name}"

    def _upsert_books_index(self, metadata: dict[str, Any]) -> None:
        if BOOKS_METADATA_INDEX.exists():
            try:
                books = json.loads(BOOKS_METADATA_INDEX.read_text(encoding="utf-8"))
                if not isinstance(books, list):
                    books = []
            except json.JSONDecodeError:
                books = []
        else:
            books = []

        book_id = metadata["book_id"]
        public_metadata = {
            "book_id": book_id,
            "title": metadata.get("title", ""),
            "author": metadata.get("author", ""),
            "publisher": metadata.get("publisher", ""),
            "edition": metadata.get("edition", ""),
            "publication_year": metadata.get("publication_year", ""),
            "practice_area": metadata.get("practice_area", ""),
            "topics": metadata.get("topics", []),
            "license_status": metadata.get("license_status", ""),
            "allowed_use": metadata.get("allowed_use", ""),
            "file_path": metadata.get("file_path", ""),
            "original_filename": metadata.get("original_filename", ""),
            "source_type": metadata.get("source_type", "book"),
            "status": metadata.get("status", ""),
            "created_at": metadata.get("created_at", ""),
            "page_count": metadata.get("page_count"),
            "chunk_count": metadata.get("chunk_count"),
            "index_backend": metadata.get("index_backend"),
        }
        updated = False
        for index, existing in enumerate(books):
            if isinstance(existing, dict) and existing.get("book_id") == book_id:
                books[index] = public_metadata
                updated = True
                break
        if not updated:
            books.append(public_metadata)

        BOOKS_METADATA_INDEX.write_text(
            json.dumps(books, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def store_chunks(
        self,
        *,
        book_metadata: dict[str, Any],
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> tuple[str, list[str]]:
        warnings: list[str] = []
        self._remove_existing_book_chunks(book_metadata["book_id"])
        records: list[dict[str, Any]] = []
        for chunk, embedding in zip(chunks, embeddings, strict=False):
            record = {
                **chunk,
                "embedding": embedding,
                "metadata": self._chunk_metadata(book_metadata, chunk),
            }
            records.append(record)

        self._append_jsonl_records(records)
        self._index_keywords(records)

        backend = "jsonl_sqlite"
        if find_spec("chromadb") is None:
            return backend, warnings

        try:
            self._store_in_chroma(records)
            backend = "chromadb"
        except Exception as exc:
            warnings.append(f"ChromaDB kullanılamadı; JSONL + SQLite keyword index ile devam edildi: {self._short_error(exc)}")

        return backend, warnings

    def search_chunks(
        self,
        *,
        query: str,
        query_embedding: list[float],
        practice_area: str | None,
        max_results: int,
    ) -> list[dict[str, Any]]:
        chroma_records: list[dict[str, Any]] = []
        try:
            chroma_records = self._search_chroma(
                query_embedding=query_embedding,
                practice_area=practice_area,
                max_results=max_results,
            )
        except Exception:
            pass
        jsonl_records = self._search_jsonl(
            query=query,
            query_embedding=query_embedding,
            practice_area=practice_area,
            max_results=max_results,
        )
        return self._merge_records(chroma_records, jsonl_records, max_results=max_results)

    def list_book_chunks(self, book_id: str) -> list[dict[str, Any]]:
        chunks = [
            record
            for record in self._read_jsonl_records()
            if record.get("metadata", {}).get("book_id") == book_id
        ]
        if chunks:
            return chunks

        chunk_ids = self._book_chunk_ids_from_sqlite(book_id)
        if not chunk_ids:
            return []
        records_by_id = {record.get("chunk_id"): record for record in self._read_jsonl_records()}
        return [records_by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in records_by_id]

    def find_statute_article(self, *, code: str, article: str) -> dict[str, Any] | None:
        normalized_code = self._plain(code).upper()
        normalized_article = str(article).strip()
        for record in self._read_jsonl_records():
            metadata = record.get("metadata", {})
            record_code = self._plain(str(metadata.get("code") or "")).upper()
            record_article = str(metadata.get("article") or "").strip()
            if record_code == normalized_code and record_article == normalized_article:
                return record
        return None

    def save_doctrine_cards(self, book_id: str, cards: list[dict[str, Any]]) -> None:
        path = DOCTRINE_CARDS_DIR / f"{book_id}.jsonl"
        with path.open("w", encoding="utf-8") as file:
            for card in cards:
                file.write(json.dumps(card, ensure_ascii=False) + "\n")

    def list_doctrine_cards(
        self,
        *,
        book_id: str | None = None,
        practice_area: str | None = None,
    ) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        paths = [DOCTRINE_CARDS_DIR / f"{book_id}.jsonl"] if book_id else DOCTRINE_CARDS_DIR.glob("*.jsonl")
        for path in paths:
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8") as file:
                for line in file:
                    if not line.strip():
                        continue
                    card = json.loads(line)
                    card_area = str(card.get("practice_area") or "").strip()
                    if practice_area and card_area and card_area != practice_area:
                        continue
                    cards.append(card)
        return cards

    def search_doctrine_cards(
        self,
        *,
        query: str,
        practice_area: str | None,
        max_results: int,
    ) -> list[dict[str, Any]]:
        query_tokens = set(self._tokens(query))
        scored: list[tuple[int, dict[str, Any]]] = []
        for card in self.list_doctrine_cards(practice_area=practice_area):
            haystack = " ".join(
                str(card.get(key, ""))
                for key in ("topic", "principle", "practice_note", "source_label")
            )
            score = len(query_tokens & set(self._tokens(haystack)))
            if score:
                scored.append((score, card))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [card for _, card in scored[:max_results]]

    def _chunk_metadata(self, book_metadata: dict[str, Any], chunk: dict[str, Any]) -> dict[str, Any]:
        topics = book_metadata.get("topics") or []
        if isinstance(topics, str):
            topics = [item.strip() for item in topics.split(",") if item.strip()]
        source_type = book_metadata.get("source_type", "book")
        if chunk.get("code") and chunk.get("article"):
            source_type = "statute"
        return {
            "book_id": book_metadata["book_id"],
            "title": book_metadata.get("title", ""),
            "author": book_metadata.get("author", ""),
            "page_start": int(chunk.get("page_start") or 0),
            "page_end": int(chunk.get("page_end") or 0),
            "section_title": chunk.get("section_title") or "",
            "practice_area": book_metadata.get("practice_area", ""),
            "topics": ", ".join(topics),
            "source_type": source_type,
            "code": chunk.get("code") or book_metadata.get("code", ""),
            "article": chunk.get("article") or "",
            "article_title": chunk.get("article_title") or "",
            "chunk_text": chunk.get("chunk_text") or chunk.get("text") or "",
            "license_status": book_metadata.get("license_status", ""),
            "allowed_use": book_metadata.get("allowed_use", ""),
        }

    def _append_jsonl_records(self, records: list[dict[str, Any]]) -> None:
        with CHUNKS_JSONL.open("a", encoding="utf-8") as file:
            for record in records:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _read_jsonl_records(self) -> list[dict[str, Any]]:
        if not CHUNKS_JSONL.exists():
            return []
        records: list[dict[str, Any]] = []
        with CHUNKS_JSONL.open("r", encoding="utf-8") as file:
            for line in file:
                if line.strip():
                    records.append(json.loads(line))
        return records

    def _remove_existing_book_chunks(self, book_id: str) -> None:
        old_chunk_ids = [
            record.get("chunk_id")
            for record in self._read_jsonl_records()
            if record.get("metadata", {}).get("book_id") == book_id and record.get("chunk_id")
        ]
        records = [
            record
            for record in self._read_jsonl_records()
            if record.get("metadata", {}).get("book_id") != book_id
        ]
        with CHUNKS_JSONL.open("w", encoding="utf-8") as file:
            for record in records:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
        with sqlite3.connect(SQLITE_INDEX) as connection:
            connection.execute("DELETE FROM chunk_keywords WHERE book_id = ?", (book_id,))
            connection.commit()
        self._delete_chroma_chunks(old_chunk_ids)

    def _delete_chroma_chunks(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        try:
            import chromadb  # type: ignore

            client = chromadb.PersistentClient(path=str(CHROMA_DIR))
            collection = client.get_collection(CHROMA_COLLECTION)
            collection.delete(ids=chunk_ids)
        except Exception:
            return

    def _store_in_chroma(self, records: list[dict[str, Any]]) -> None:
        if not records:
            return
        import chromadb  # type: ignore

        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        collection = client.get_or_create_collection(CHROMA_COLLECTION)
        ids = [record["chunk_id"] for record in records]
        collection.upsert(
            ids=ids,
            documents=[record["text"] for record in records],
            embeddings=[record["embedding"] for record in records],
            metadatas=[self._chroma_metadata(record["metadata"]) for record in records],
        )

    def _search_chroma(
        self,
        *,
        query_embedding: list[float],
        practice_area: str | None,
        max_results: int,
    ) -> list[dict[str, Any]]:
        import chromadb  # type: ignore

        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        collection = client.get_collection(CHROMA_COLLECTION)
        where = {"practice_area": practice_area} if practice_area else None
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=max_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        records: list[dict[str, Any]] = []
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        for index, chunk_id in enumerate(ids):
            distance = float(distances[index] or 0)
            score = max(0, min(100, round(100 * (1 - min(distance, 2) / 2))))
            records.append(
                {
                    "chunk_id": chunk_id,
                    "text": documents[index],
                    "metadata": metadatas[index],
                    "relevance_score": score,
                }
            )
        return records

    @staticmethod
    def _chroma_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
        return {
            key: value
            for key, value in metadata.items()
            if isinstance(value, str | int | float | bool)
        }

    def _search_jsonl(
        self,
        *,
        query: str,
        query_embedding: list[float],
        practice_area: str | None,
        max_results: int,
    ) -> list[dict[str, Any]]:
        records = self._read_jsonl_records()
        query_tokens = set(self._tokens(query))
        candidate_ids = self._keyword_candidates(query_tokens)
        scored: list[dict[str, Any]] = []
        for record in records:
            metadata = record.get("metadata", {})
            source_area = str(metadata.get("practice_area") or "").strip()
            if practice_area and source_area and source_area != practice_area:
                continue
            if candidate_ids and record.get("chunk_id") not in candidate_ids:
                continue
            text_tokens = set(self._tokens(record.get("text", "")))
            keyword_score = len(query_tokens & text_tokens) / max(len(query_tokens), 1)
            vector_score = self._cosine(query_embedding, record.get("embedding", []))
            score = max(0, min(100, round((keyword_score * 55) + (vector_score * 45))))
            if score:
                scored.append({**record, "relevance_score": score})
        scored.sort(key=lambda item: item["relevance_score"], reverse=True)
        return scored[:max_results]

    @staticmethod
    def _merge_records(
        first: list[dict[str, Any]],
        second: list[dict[str, Any]],
        *,
        max_results: int,
    ) -> list[dict[str, Any]]:
        by_id: dict[str, dict[str, Any]] = {}
        for index, record in enumerate([*first, *second]):
            chunk_id = str(record.get("chunk_id") or f"anonymous:{index}")
            existing = by_id.get(chunk_id)
            if not existing or int(record.get("relevance_score") or 0) > int(existing.get("relevance_score") or 0):
                by_id[chunk_id] = record
        records = list(by_id.values())
        records.sort(key=lambda item: int(item.get("relevance_score") or 0), reverse=True)
        return records[:max_results]

    def _keyword_candidates(self, query_tokens: set[str]) -> set[str]:
        if not query_tokens:
            return set()
        with sqlite3.connect(SQLITE_INDEX) as connection:
            placeholders = ",".join("?" for _ in query_tokens)
            rows = connection.execute(
                f"SELECT DISTINCT chunk_id FROM chunk_keywords WHERE keyword IN ({placeholders})",
                tuple(query_tokens),
            ).fetchall()
        return {row[0] for row in rows}

    def _book_chunk_ids_from_sqlite(self, book_id: str) -> list[str]:
        with sqlite3.connect(SQLITE_INDEX) as connection:
            rows = connection.execute(
                "SELECT DISTINCT chunk_id FROM chunk_keywords WHERE book_id = ?",
                (book_id,),
            ).fetchall()
        return [row[0] for row in rows]

    def _index_keywords(self, records: list[dict[str, Any]]) -> None:
        with sqlite3.connect(SQLITE_INDEX) as connection:
            rows: list[tuple[str, str, str]] = []
            for record in records:
                metadata = record.get("metadata", {})
                book_id = metadata.get("book_id", "")
                keyword_text = " ".join(
                    str(value or "")
                    for value in (
                        record.get("text", ""),
                        metadata.get("code", ""),
                        metadata.get("article", ""),
                        metadata.get("article_title", ""),
                        metadata.get("section_title", ""),
                        metadata.get("title", ""),
                    )
                )
                for token in set(self._tokens(keyword_text)):
                    rows.append((token, record["chunk_id"], book_id))
            connection.executemany(
                "INSERT INTO chunk_keywords(keyword, chunk_id, book_id) VALUES (?, ?, ?)",
                rows,
            )
            connection.commit()

    def _ensure_sqlite(self) -> None:
        with sqlite3.connect(SQLITE_INDEX) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chunk_keywords (
                    keyword TEXT NOT NULL,
                    chunk_id TEXT NOT NULL,
                    book_id TEXT NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_chunk_keyword ON chunk_keywords(keyword)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_chunk_book ON chunk_keywords(book_id)")
            connection.commit()

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
        return " ".join(text.translate(translation).casefold().split())

    @staticmethod
    def _tokens(text: str) -> list[str]:
        return [
            token
            for token in re.findall(r"[a-zçğıöşü0-9]+", text.casefold())
            if len(token) > 2
        ]

    @staticmethod
    def _cosine(first: list[float], second: list[float]) -> float:
        if not first or not second:
            return 0.0
        length = min(len(first), len(second))
        dot = sum(first[index] * second[index] for index in range(length))
        first_norm = math.sqrt(sum(value * value for value in first[:length]))
        second_norm = math.sqrt(sum(value * value for value in second[:length]))
        if not first_norm or not second_norm:
            return 0.0
        return dot / (first_norm * second_norm)

    @staticmethod
    def _short_error(error: Exception) -> str:
        message = " ".join(str(error).split())
        return message[:200] or error.__class__.__name__


book_memory_service = BookMemoryService()
