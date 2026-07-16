"""P2.8S - Live DeepSeek batched-reasoning smoke server.

Runs the real FastAPI app with the configured (DeepSeek) reasoning provider.
Only the legal source acquirer is replaced with one that returns the target
precedent-pool shortlist in retrieval-rank order, so the real
``POST /cases/{case_id}/legal-issues/rebuild`` endpoint reasons over the exact
shortlisted Yargitay decisions.

Never logs API keys, case text, decision text, or reasoning content.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PrecedentPoolDecision, SourceRecord
from app.services.auth_service import SecurityContext
from app.services.legal_reasoning_service import legal_reasoning_service


class PoolShortlistSourceAcquirer:
    """Return the exact pool shortlist (rank order, one paragraph per decision)."""

    def __init__(self, pool_id: str):
        self._pool_id = pool_id

    async def acquire(self, db: AsyncSession, *, case_id: str,
                      security_context: SecurityContext) -> list[dict[str, str]]:
        rows = (await db.execute(
            select(PrecedentPoolDecision, SourceRecord)
            .join(SourceRecord, SourceRecord.id == PrecedentPoolDecision.source_record_id)
            .where(
                PrecedentPoolDecision.pool_id == self._pool_id,
                PrecedentPoolDecision.case_id == case_id,
                PrecedentPoolDecision.selection_state == "shortlisted",
            )
            .order_by(PrecedentPoolDecision.retrieval_rank.asc())
        )).all()
        acquired: list[dict[str, str]] = []
        for decision, record in rows:
            paragraph_ids = decision.selected_source_paragraph_ids or []
            if not paragraph_ids:
                continue
            acquired.append({
                "source_record_id": decision.source_record_id,
                "source_version_id": decision.source_version_id,
                "source_paragraph_id": paragraph_ids[0],
                "effective_trust": record.verification_status,
            })
        return acquired


def main() -> None:
    pool_id = os.environ["SMOKE_POOL_ID"]
    port = int(os.environ.get("SMOKE_PORT", "8010"))
    legal_reasoning_service.source_acquirer = PoolShortlistSourceAcquirer(pool_id)
    print(
        f"smoke_server_ready provider={legal_reasoning_service.provider.provider_name} "
        f"model={legal_reasoning_service.provider.model_version} pool_id={pool_id} port={port}",
        flush=True,
    )
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=False, log_level="warning")


if __name__ == "__main__":
    main()
