import asyncio
import logging
import os
import sys
import time
from pathlib import Path

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.core.logging import setup_logging
from app.db.session import check_db_health

settings = get_settings()

os.environ.setdefault("ENVIRONMENT", settings.environment)
os.environ.setdefault("LOG_LEVEL", settings.log_level)
os.environ.setdefault("LOG_FORMAT", settings.log_format)
os.environ.setdefault("LOG_SERVICE_NAME", settings.log_service_name)
setup_logging()

from app.core.correlation import (
    extract_or_create_correlation_id,
    get_correlation_id,
    clear_correlation_id,
    clear_request_id,
)
from app.routes.case_routes import router as case_router
from app.routes.search_routes import router as search_router
from app.routes.decision_routes import router as decision_router
from app.routes.yargitay_routes import router as yargitay_router
from app.routes.research_routes import router as research_router
from app.routes.petition_routes import router as petition_router
from app.routes.legal_brain_routes import router as legal_brain_router
from app.routes.ai_routes import router as ai_router
from app.routes.document_routes import router as document_router
from app.routes.workflow_routes import router as workflow_router
from app.routes.legal_ground_routes import router as legal_ground_router
from app.routes.precedent_routes import router as precedent_router
from app.routes.grounding_routes import router as grounding_router
from app.routes.security_routes import router as security_router
from app.routes.auth_routes_new import router as auth_router
from app.routes.lifecycle_routes import router as lifecycle_router
from app.routes.ai_run_routes import router as ai_run_router
from app.routes.yargitay_health_routes import router as yargitay_health_router
from app.routes.legal_issue_graph_routes import router as legal_issue_graph_router
from app.routes.job_routes import router as job_router

logger = logging.getLogger(__name__)
WEB_DIR = Path(__file__).resolve().parent / "web"

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Emsalist backend API. "
        "Olay analizi, arama sorgusu üretimi, karar sıralama "
        "ve Yargıtay karar arama modüllerini içerir."
    ),
    debug=settings.debug,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000", "http://localhost:4096", "http://127.0.0.1:4096"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Correlation-ID"],
)

HEALTH_LIKE_PATHS = frozenset({"/health", "/live", "/ready", "/styles.css", "/app.js", "/", "/docs", "/openapi.json"})

@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    cid = extract_or_create_correlation_id(request.headers.get("X-Correlation-ID"))
    start_ms = int(time.time() * 1000)

    response = await call_next(request)

    duration_ms = int(time.time() * 1000) - start_ms
    status_code = response.status_code

    log_extra = {
        "correlation_id": cid,
        "method": request.method,
        "path": request.url.path,
        "status_code": status_code,
        "duration_ms": duration_ms,
    }
    if status_code >= 500:
        logger.error("http_access %s %s %s %dms", request.method, request.url.path, status_code, duration_ms, extra=log_extra)
    elif status_code >= 400:
        logger.warning("http_access %s %s %s %dms", request.method, request.url.path, status_code, duration_ms, extra=log_extra)
    else:
        logger.info("http_access %s %s %s %dms", request.method, request.url.path, status_code, duration_ms, extra=log_extra)

    response.headers["X-Correlation-ID"] = cid
    clear_correlation_id()
    clear_request_id()
    return response


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    from app.services.security_service import SECURITY_HEADERS, check_rate_limit

    if request.url.path in HEALTH_LIKE_PATHS:
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    client_ip = request.client.host if request.client else "unknown"
    if client_ip in ("127.0.0.1", "::1", "testclient"):
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response

    limited, retry_after = check_rate_limit(client_ip)
    if limited:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={"Retry-After": str(retry_after)},
        )

    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    return response


app.mount("/ui-assets", StaticFiles(directory=WEB_DIR), name="ui-assets")

app.include_router(case_router)
app.include_router(search_router)
app.include_router(decision_router)
app.include_router(yargitay_router)
app.include_router(research_router)
app.include_router(petition_router)
app.include_router(legal_brain_router)
app.include_router(ai_router)
app.include_router(document_router)
app.include_router(workflow_router)
app.include_router(legal_ground_router)
app.include_router(precedent_router)
app.include_router(grounding_router)
app.include_router(security_router)
app.include_router(auth_router)
app.include_router(lifecycle_router)
app.include_router(ai_run_router)
app.include_router(yargitay_health_router)
app.include_router(legal_issue_graph_router)
app.include_router(job_router)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def search_home() -> HTMLResponse:
    return HTMLResponse((WEB_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/styles.css", include_in_schema=False)
def web_styles() -> FileResponse:
    return FileResponse(WEB_DIR / "styles.css", media_type="text/css")


@app.get("/app.js", include_in_schema=False)
def web_script() -> FileResponse:
    return FileResponse(WEB_DIR / "app.js", media_type="application/javascript")


@app.get("/health", tags=["System"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/live", tags=["System"])
def liveness_check() -> dict[str, str]:
    return {"status": "alive", "service": settings.log_service_name}


@app.get("/ready", tags=["System"])
async def readiness_check() -> JSONResponse:
    checks: dict[str, dict[str, str]] = {}

    try:
        db_health = await check_db_health()
        if db_health.get("connected"):
            checks["database"] = {"status": "ok"}
        else:
            checks["database"] = {"status": "failed", "detail": (db_health.get("error", "unknown") or "")[:100]}
    except Exception as e:
        checks["database"] = {"status": "failed", "detail": str(e)[:100]}

    try:
        settings = get_settings()
        checks["configuration"] = {"status": "ok"}
    except Exception as e:
        checks["configuration"] = {"status": "failed", "detail": str(e)[:100]}

    all_ok = all(c.get("status") == "ok" for c in checks.values())
    status = "ready" if all_ok else "not_ready"
    status_code = 200 if all_ok else 503

    return JSONResponse(
        status_code=status_code,
        content={"status": status, "checks": checks},
    )


@app.get("/system-health", tags=["System"])
async def system_health() -> JSONResponse:
    checks: dict[str, dict[str, str]] = {}
    critical_failed = False

    try:
        db_health = await check_db_health()
        if db_health.get("connected"):
            checks["database"] = {"status": "ok"}
        else:
            checks["database"] = {"status": "failed"}
            critical_failed = True
    except Exception:
        checks["database"] = {"status": "failed"}
        critical_failed = True

    try:
        get_settings()
        checks["configuration"] = {"status": "ok"}
    except Exception:
        checks["configuration"] = {"status": "failed"}
        critical_failed = True

    if critical_failed:
        overall = "unhealthy"
        status_code = 503
    else:
        overall = "healthy"
        status_code = 200

    return JSONResponse(
        status_code=status_code,
        content={"status": overall, "service": settings.log_service_name, "checks": checks},
    )
