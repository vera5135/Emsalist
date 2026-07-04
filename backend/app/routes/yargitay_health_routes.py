"""P1.2 — Yargitay health and metrics endpoint."""

from __future__ import annotations

from fastapi import APIRouter

from app.services.yargitay_infra import yargitay_health

router = APIRouter(prefix="/yargitay", tags=["Yargıtay"])


@router.get("/health")
def health() -> dict:
    return yargitay_health()
