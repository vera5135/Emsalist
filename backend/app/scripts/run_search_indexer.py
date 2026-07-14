"""P2.7 — Offline paragraph embedding indexer.

Usage:
    python -m app.scripts.run_search_indexer --once --batch-size 100
"""
from __future__ import annotations

import asyncio
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import SourceParagraph, SourceRecord, SourceVersion
from app.db.session import get_sessionmaker
from app.services.search_embedding_provider import create_embedding_provider
from app.services.source_ingestion_service import resolve_version_verification_status
from app.services.source_verification import index_eligibility


async def run_indexer(batch_size: int = 100, once: bool = True) -> None:
    settings = get_settings()
    provider = create_embedding_provider(settings)

    print(f"Embedding sağlayıcı: {provider.model_name}, kullanılabilir: {provider.is_available}")
    if not provider.is_available:
        print("UYARI: Embedding sağlayıcı kullanılamıyor. Embedding oluşturulmayacak.")
        return

    sessionmaker = get_sessionmaker()

    while True:
        async with sessionmaker() as session:
            async with session.begin():
                result = await session.execute(
                    select(SourceParagraph)
                    .where(SourceParagraph.embedding_status == "pending")
                    .limit(batch_size)
                )
                paragraphs = list(result.scalars().all())

            if not paragraphs:
                print("İndekslenecek paragraf kalmadı.")
                return

            print(f"İşleniyor: {len(paragraphs)} paragraf...")

            valid_paragraphs = []
            valid_texts = []

            for par in paragraphs:
                version_result = await session.execute(
                    select(SourceVersion).where(SourceVersion.id == par.source_version_id)
                )
                version = version_result.scalar_one_or_none()
                if version is None:
                    par.embedding_status = "failed"
                    continue

                record_result = await session.execute(
                    select(SourceRecord).where(SourceRecord.id == version.source_record_id)
                )
                record = record_result.scalar_one_or_none()
                if record is None:
                    par.embedding_status = "failed"
                    continue

                if record.current_version_id != par.source_version_id:
                    par.embedding_status = "failed"
                    continue

                resolved_status = await resolve_version_verification_status(
                    session, record.id, version.id, record.verification_status
                )
                eligibility = index_eligibility(resolved_status)
                if not eligibility.eligible:
                    par.embedding_status = "failed"
                    continue

                title = record.title or ""
                heading = par.heading_path or ""
                text = par.text or ""
                formatted = f"{title}\n{heading}\n{text}"

                valid_paragraphs.append(par)
                valid_texts.append(formatted)

            if not valid_paragraphs:
                print("  Tüm paragraflar indeksleme dışı bırakıldı.")
                if once:
                    return
                continue

            try:
                vectors = provider.embed_documents(valid_texts)
            except Exception as e:
                print(f"  Embedding hatası: {e}")
                for par in valid_paragraphs:
                    par.embedding_status = "failed"
                await session.commit()
                if once:
                    return
                continue

            for i, (par, text) in enumerate(zip(valid_paragraphs, valid_texts)):
                vector = vectors[i] if i < len(vectors) else []
                if vector:
                    par.embedding_vector_json = json.dumps(vector)
                    par.embedding_model = provider.model_name
                    par.embedding_version = provider.embedding_version
                    par.embedding_dimension = len(vector)
                    par.embedding_status = "indexed"
                    par.embedding_updated_at = datetime.utcnow()
                else:
                    par.embedding_status = "failed"

            await session.commit()
            print(f"  {len(valid_paragraphs)} paragraf indekslendi.")

        if once:
            return


def main():
    parser = argparse.ArgumentParser(description="P2.7 Paragraph embedding indexer")
    parser.add_argument("--once", action="store_true", default=True, help="Tek seferlik çalıştır")
    parser.add_argument("--batch-size", type=int, default=100, help="Parti boyutu")
    args = parser.parse_args()

    asyncio.run(run_indexer(batch_size=args.batch_size, once=args.once))


if __name__ == "__main__":
    main()
