"""Seed Legal Brain from local PDFs and public legal sources.

This script is intentionally conservative about web sources:
- It scrapes the public Ministry of Justice legal dictionary.
- It downloads only publicly available Official Gazette PDF archive files.
- It indexes local PDFs from the workspace-owned legal_sources/pdfs folder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
LEGAL_SOURCES_DIR = ROOT_DIR / "legal_sources"
PDF_SOURCES_DIR = LEGAL_SOURCES_DIR / "pdfs"
RESMI_GAZETE_DIR = LEGAL_SOURCES_DIR / "resmi_gazete"
DICTIONARY_DIR = LEGAL_SOURCES_DIR / "hukuk_sozlugu"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.book_ingestion_service import book_ingestion_service  # noqa: E402
from app.services.book_memory_service import book_memory_service  # noqa: E402
from app.services.doctrine_card_service import doctrine_card_service  # noqa: E402
from app.services.legal_embedding_service import legal_embedding_service  # noqa: E402


DICTIONARY_BASE_URL = "https://sozluk.adalet.gov.tr"
DICTIONARY_LETTERS = (
    "A",
    "B",
    "C",
    "Ç",
    "D",
    "E",
    "F",
    "G",
    "Ğ",
    "H",
    "I",
    "İ",
    "J",
    "K",
    "L",
    "M",
    "N",
    "O",
    "Ö",
    "P",
    "R",
    "S",
    "Ş",
    "T",
    "U",
    "Ü",
    "V",
    "Y",
    "Z",
    "Â",
    "Î",
    "Û",
)


@dataclass(frozen=True)
class SeedResult:
    source: str
    book_id: str
    title: str
    status: str
    chunk_count: int = 0
    warnings: tuple[str, ...] = ()


def slugify(value: str) -> str:
    slug = "".join(character.lower() if character.isalnum() else "-" for character in value)
    return "-".join(part for part in slug.split("-") if part)[:60] or "source"


def stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    return f"{slugify(prefix)[:40]}-{digest}"


def clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def ensure_source_dirs() -> None:
    for directory in (LEGAL_SOURCES_DIR, PDF_SOURCES_DIR, RESMI_GAZETE_DIR, DICTIONARY_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    readme = LEGAL_SOURCES_DIR / "README.md"
    if not readme.exists():
        readme.write_text(
            "\n".join(
                [
                    "# Legal Sources",
                    "",
                    "Put your own licensed or publicly usable PDF files in `pdfs/`.",
                    "Run `./seed-legal-brain.ps1` from the project root to index them.",
                    "",
                    "Generated/downloaded public-source files are kept under:",
                    "- `hukuk_sozlugu/`",
                    "- `resmi_gazete/`",
                    "",
                ]
            ),
            encoding="utf-8",
        )


def fetch_url(url: str, *, timeout: int = 30) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "EmsalistLegalBrain/0.1 (+local legal research assistant)",
            "Accept": "text/html,application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def save_metadata(metadata: dict[str, Any]) -> None:
    book_memory_service.save_book_metadata(metadata)


def is_existing_ingested(book_id: str) -> bool:
    try:
        metadata = book_memory_service.get_book_metadata(book_id)
    except FileNotFoundError:
        return False
    return metadata.get("status") == "ingested" and int(metadata.get("chunk_count") or 0) > 0


def ingest_pdf_file(
    *,
    source_pdf: Path,
    title: str,
    source_type: str,
    practice_area: str,
    topics: list[str],
    source_url: str = "",
    publisher: str = "",
    author: str = "",
    force: bool = False,
) -> SeedResult:
    book_id = stable_id(title, str(source_pdf.resolve()).casefold())
    if not force and is_existing_ingested(book_id):
        metadata = book_memory_service.get_book_metadata(book_id)
        return SeedResult(
            source=source_type,
            book_id=book_id,
            title=title,
            status="skipped_existing",
            chunk_count=int(metadata.get("chunk_count") or 0),
        )

    target_path = book_memory_service.upload_path(book_id, source_pdf.name)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if source_pdf.resolve() != target_path.resolve():
        shutil.copy2(source_pdf, target_path)

    metadata = {
        "book_id": book_id,
        "title": title,
        "author": author,
        "publisher": publisher,
        "edition": "",
        "publication_year": "",
        "practice_area": practice_area,
        "topics": topics,
        "license_status": "public_or_user_provided",
        "allowed_use": "internal_petition_support",
        "file_path": str(target_path),
        "original_filename": source_pdf.name,
        "source_type": source_type,
        "source_url": source_url,
        "status": "uploaded",
    }
    save_metadata(metadata)
    ingest_result = book_ingestion_service.ingest(book_id)
    try_create_cards(book_id=book_id, practice_area=practice_area)
    return SeedResult(
        source=source_type,
        book_id=book_id,
        title=title,
        status=str(ingest_result.get("status") or "unknown"),
        chunk_count=int(ingest_result.get("chunk_count") or 0),
        warnings=tuple(ingest_result.get("warnings") or ()),
    )


def chunk_text_records(*, book_id: str, text: str, chunk_words: int = 900) -> list[dict[str, Any]]:
    words = text.split()
    if not words:
        return []
    chunks: list[dict[str, Any]] = []
    count = max(1, math.ceil(len(words) / chunk_words))
    for index in range(count):
        start = index * chunk_words
        end = min(len(words), start + chunk_words)
        body = " ".join(words[start:end]).strip()
        if not body:
            continue
        chunks.append(
            {
                "chunk_id": f"{book_id}:text:{index:05d}",
                "book_id": book_id,
                "chunk_index": index,
                "text": body,
                "page_start": index + 1,
                "page_end": index + 1,
                "section_title": f"Metin bölümü {index + 1}",
            }
        )
    return chunks


def ingest_text_document(
    *,
    book_id: str,
    title: str,
    source_type: str,
    text: str,
    storage_path: Path,
    practice_area: str,
    topics: list[str],
    source_url: str,
    publisher: str,
    force: bool = False,
) -> SeedResult:
    if not force and is_existing_ingested(book_id):
        metadata = book_memory_service.get_book_metadata(book_id)
        return SeedResult(
            source=source_type,
            book_id=book_id,
            title=title,
            status="skipped_existing",
            chunk_count=int(metadata.get("chunk_count") or 0),
        )

    metadata = {
        "book_id": book_id,
        "title": title,
        "author": "",
        "publisher": publisher,
        "edition": "",
        "publication_year": "",
        "practice_area": practice_area,
        "topics": topics,
        "license_status": "public_source",
        "allowed_use": "internal_petition_support",
        "file_path": str(storage_path),
        "original_filename": storage_path.name,
        "source_type": source_type,
        "source_url": source_url,
        "status": "uploaded",
    }
    chunks = chunk_text_records(book_id=book_id, text=text)
    embeddings = legal_embedding_service.embed_texts([chunk["text"] for chunk in chunks])
    backend, warnings = book_memory_service.store_chunks(
        book_metadata=metadata,
        chunks=chunks,
        embeddings=embeddings,
    )
    metadata["status"] = "ingested"
    metadata["page_count"] = len(chunks)
    metadata["chunk_count"] = len(chunks)
    metadata["index_backend"] = backend
    save_metadata(metadata)
    try_create_cards(book_id=book_id, practice_area=practice_area)
    return SeedResult(
        source=source_type,
        book_id=book_id,
        title=title,
        status="ingested",
        chunk_count=len(chunks),
        warnings=tuple(warnings),
    )


def parse_dictionary_page(html: str) -> tuple[list[tuple[str, str]], int | None]:
    soup = BeautifulSoup(html, "html.parser")
    entries: list[tuple[str, str]] = []
    for item in soup.select("div.terim"):
        term = clean_text(item.select_one(".col-md-4").get_text(" ", strip=True) if item.select_one(".col-md-4") else "")
        definition = clean_text(
            item.select_one(".col-md-8").get_text(" ", strip=True) if item.select_one(".col-md-8") else ""
        )
        if term and definition:
            entries.append((term, definition))

    page_count: int | None = None
    pager = soup.select_one("div.alert.alert-info")
    if pager:
        match = re.search(r"(\d+)\s+tane", pager.get_text(" ", strip=True))
        if match:
            total = int(match.group(1))
            page_count = max(1, math.ceil(total / 40))
    return entries, page_count


def seed_adalet_dictionary(*, max_pages_per_letter: int = 0, sleep_seconds: float = 0.15, force: bool = False) -> SeedResult:
    ensure_source_dirs()
    book_id = "adalet-bakanligi-hukuk-sozlugu"
    if not force and is_existing_ingested(book_id):
        metadata = book_memory_service.get_book_metadata(book_id)
        return SeedResult(
            source="dictionary",
            book_id=book_id,
            title="Adalet Bakanlığı Hukuk Sözlüğü",
            status="skipped_existing",
            chunk_count=int(metadata.get("chunk_count") or 0),
        )

    all_entries: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for letter in DICTIONARY_LETTERS:
        encoded_letter = urllib.parse.quote(letter)
        page = 1
        page_count: int | None = None
        while True:
            if max_pages_per_letter and page > max_pages_per_letter:
                break
            url = f"{DICTIONARY_BASE_URL}/Harf/{encoded_letter}"
            if page > 1:
                url = f"{url}?Sayfa={page}"
            html = fetch_url(url).decode("utf-8", errors="replace")
            entries, detected_pages = parse_dictionary_page(html)
            if page_count is None:
                page_count = detected_pages or 1
            if not entries:
                break
            for term, definition in entries:
                key = (term.casefold(), definition.casefold())
                if key in seen:
                    continue
                seen.add(key)
                all_entries.append({"term": term, "definition": definition, "letter": letter, "source_url": url})
            if page >= page_count:
                break
            page += 1
            time.sleep(sleep_seconds)

    storage_path = DICTIONARY_DIR / "adalet_bakanligi_hukuk_sozlugu.json"
    storage_path.write_text(json.dumps(all_entries, ensure_ascii=False, indent=2), encoding="utf-8")
    text = "\n".join(f"{entry['term']}: {entry['definition']}" for entry in all_entries)
    return ingest_text_document(
        book_id=book_id,
        title="Adalet Bakanlığı Hukuk Sözlüğü",
        source_type="dictionary",
        text=text,
        storage_path=storage_path,
        practice_area="Genel Hukuk",
        topics=["hukuk sözlüğü", "hukuk terimleri", "Adalet Bakanlığı"],
        source_url=DICTIONARY_BASE_URL,
        publisher="T.C. Adalet Bakanlığı",
        force=force,
    )


def official_gazette_pdf_url(day: date) -> str:
    return f"https://www.resmigazete.gov.tr/eskiler/{day:%Y/%m/%Y%m%d}.pdf"


def seed_official_gazette(*, days_back: int, force: bool = False) -> list[SeedResult]:
    ensure_source_dirs()
    results: list[SeedResult] = []
    today = date.today()
    for offset in range(max(days_back, 0) + 1):
        day = today - timedelta(days=offset)
        url = official_gazette_pdf_url(day)
        pdf_path = RESMI_GAZETE_DIR / f"{day:%Y%m%d}.pdf"
        title = f"Resmi Gazete {day:%d.%m.%Y}"
        book_id = stable_id(title, str(pdf_path.resolve()).casefold())
        if not force and is_existing_ingested(book_id):
            metadata = book_memory_service.get_book_metadata(book_id)
            results.append(
                SeedResult(
                    source="official_gazette",
                    book_id=book_id,
                    title=title,
                    status="skipped_existing",
                    chunk_count=int(metadata.get("chunk_count") or 0),
                )
            )
            continue
        try:
            content = fetch_url(url, timeout=45)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            continue
        if not content.startswith(b"%PDF"):
            continue
        pdf_path.write_bytes(content)
        results.append(
            ingest_pdf_file(
                source_pdf=pdf_path,
                title=title,
                source_type="official_gazette",
                practice_area="Genel Hukuk",
                topics=["resmi gazete", "mevzuat", "yönetmelik", "tebliğ", "karar"],
                source_url=url,
                publisher="T.C. Cumhurbaşkanlığı Resmî Gazete",
                force=force,
            )
        )
    return results


def seed_pdf_folder(pdf_dir: Path, *, force: bool = False) -> list[SeedResult]:
    ensure_source_dirs()
    pdf_dir.mkdir(parents=True, exist_ok=True)
    results: list[SeedResult] = []
    for pdf_path in sorted(pdf_dir.glob("*.pdf")):
        title = pdf_path.stem.replace("_", " ").replace("-", " ").strip().title() or pdf_path.name
        results.append(
            ingest_pdf_file(
                source_pdf=pdf_path,
                title=title,
                source_type="book",
                practice_area="Genel Hukuk",
                topics=["kullanıcı pdf", "hukuk kaynağı"],
                publisher="Kullanıcı Kaynağı",
                force=force,
            )
        )
    return results


def try_create_cards(*, book_id: str, practice_area: str) -> None:
    try:
        doctrine_card_service.create_cards(book_id=book_id, practice_area=practice_area or "Genel Hukuk")
    except Exception:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Emsalist Legal Brain sources.")
    parser.add_argument("--skip-dictionary", action="store_true", help="Do not scrape/index the Ministry dictionary.")
    parser.add_argument("--skip-resmi-gazete", action="store_true", help="Do not download/index Official Gazette PDFs.")
    parser.add_argument("--skip-pdfs", action="store_true", help="Do not index local PDFs.")
    parser.add_argument("--pdf-dir", default=str(PDF_SOURCES_DIR), help="Folder containing user-provided PDFs.")
    parser.add_argument("--resmi-gazete-days", type=int, default=0, help="Try today and this many previous days.")
    parser.add_argument("--dictionary-max-pages-per-letter", type=int, default=0, help="Debug limit; 0 means all pages.")
    parser.add_argument("--force", action="store_true", help="Re-download/re-index sources even when already ingested.")
    args = parser.parse_args()

    ensure_source_dirs()
    results: list[SeedResult] = []

    if not args.skip_pdfs:
        results.extend(seed_pdf_folder(Path(args.pdf_dir), force=args.force))
    if not args.skip_dictionary:
        results.append(
            seed_adalet_dictionary(max_pages_per_letter=args.dictionary_max_pages_per_letter, force=args.force)
        )
    if not args.skip_resmi_gazete:
        results.extend(seed_official_gazette(days_back=args.resmi_gazete_days, force=args.force))

    payload = [
        {
            "source": result.source,
            "book_id": result.book_id,
            "title": result.title,
            "status": result.status,
            "chunk_count": result.chunk_count,
            "warnings": list(result.warnings),
        }
        for result in results
    ]
    print(json.dumps({"results": payload, "source_root": str(LEGAL_SOURCES_DIR)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
