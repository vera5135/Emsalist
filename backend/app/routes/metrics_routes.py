"""P1.10.4 — Prometheus /metrics endpoint."""
from __future__ import annotations

from fastapi import APIRouter
from starlette.responses import PlainTextResponse

from app.core.metrics import collect_metrics, is_metrics_enabled

router = APIRouter(tags=["System"])


@router.get("/metrics", include_in_schema=False)
async def metrics_endpoint() -> PlainTextResponse:
    if not is_metrics_enabled():
        return PlainTextResponse("metrics disabled", status_code=200, media_type="text/plain")
    text = collect_metrics()
    return PlainTextResponse(text, media_type="text/plain; version=0.0.4")
