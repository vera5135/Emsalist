import asyncio
import logging
import os
import sys
import time
from pathlib import Path

if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings, validate_production_config
from app.core.logging import setup_logging
from app.db.session import check_db_health, dispose_engine, get_sessionmaker

settings = get_settings()

os.environ.setdefault("EMSALIST_ENVIRONMENT", settings.environment)
os.environ.setdefault("EMSALIST_LOG_LEVEL", settings.log_level)
os.environ.setdefault("EMSALIST_LOG_FORMAT", settings.log_format)
os.environ.setdefault("EMSALIST_LOG_SERVICE_NAME", settings.log_service_name)
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
from app.routes.auth_routes_new import apple_router as apple_auth_router
from app.routes.lifecycle_routes import router as lifecycle_router
from app.routes.ai_run_routes import router as ai_run_router
from app.routes.yargitay_health_routes import router as yargitay_health_router
from app.routes.legal_issue_graph_routes import router as legal_issue_graph_router
from app.routes.job_routes import router as job_router
from app.routes.metrics_routes import router as metrics_router
from app.api.v1 import api_v1_router

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

# -- production middleware: trusted hosts --
if settings.allowed_hosts:
    hosts = [h.strip() for h in settings.allowed_hosts.split(",") if h.strip()]
    if hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

# -- production CORS --
if settings.cors_allow_origins:
    cors_origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
else:
    cors_origins = ["http://localhost:8000", "http://127.0.0.1:8000",
                    "http://localhost:4096", "http://127.0.0.1:4096"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Correlation-ID"],
)


@app.exception_handler(RequestValidationError)
async def safe_provider_validation_error(request: Request, exc: RequestValidationError):
    """Do not echo rejected provider-run inputs in a 422 response."""
    if request.url.path.startswith("/api/v1/official-source-providers/"):
        safe_errors = [
            {
                key: value
                for key, value in error.items()
                if key not in {"input", "ctx", "url"}
            }
            for error in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": safe_errors})
    return await request_validation_exception_handler(request, exc)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    from fastapi.exceptions import HTTPException as _HTTPExc
    from starlette.responses import JSONResponse as _JSONResp

    if isinstance(exc, _HTTPExc):
        return _JSONResp(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )

    from app.core.error_classification import classify_exception, build_error_response
    from app.core.correlation import get_correlation_id

    try:
        from app.core.degraded_state import update_component_state, ComponentStatus
        cat = classify_exception(exc)
        if cat.value == "database_unavailable":
            update_component_state("database", ComponentStatus.UNHEALTHY, error_code="database_unavailable")
        elif cat.value == "filesystem_error":
            update_component_state("storage", ComponentStatus.DEGRADED, error_code="filesystem_error")
        elif cat.value == "insufficient_disk_space":
            update_component_state("storage", ComponentStatus.UNHEALTHY, error_code="insufficient_disk_space")
    except Exception:
        pass

    category = classify_exception(exc)
    resp = build_error_response(exc)
    http_status = resp["error"].pop("_http_status", 500)
    cid = resp["error"]["correlation_id"]

    logger.error(
        "unhandled_exception category=%s exception_type=%s correlation_id=%s",
        category.value, type(exc).__name__, cid,
        extra={"correlation_id": cid, "exception_type": type(exc).__name__},
    )

    return JSONResponse(
        status_code=http_status,
        content=resp,
    )

HEALTH_LIKE_PATHS = frozenset({"/health", "/live", "/ready", "/metrics",
                              "/styles.css", "/app.js", "/", "/docs", "/openapi.json"})

@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    cid = extract_or_create_correlation_id(request.headers.get("X-Correlation-ID"))
    start_ms = int(time.time() * 1000)

    if is_metrics_enabled():
        from app.core.metrics import http_requests_in_flight
        http_requests_in_flight.inc()

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

    if is_metrics_enabled():
        from app.core.metrics import http_requests_in_flight, record_http_request
        http_requests_in_flight.inc(-1)
        record_http_request(request.method, request.url.path, status_code, duration_ms / 1000.0)

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

# -- P1.12: Versioned API (canonical /api/v1)
app.include_router(api_v1_router)

# -- Legacy compatibility paths (preserved for web frontend; excluded from OpenAPI schema)
app.include_router(case_router, include_in_schema=False)
app.include_router(search_router, include_in_schema=False)
app.include_router(decision_router, include_in_schema=False)
app.include_router(yargitay_router, include_in_schema=False)
app.include_router(research_router, include_in_schema=False)
app.include_router(petition_router, include_in_schema=False)
app.include_router(legal_brain_router, include_in_schema=False)
app.include_router(ai_router, include_in_schema=False)
app.include_router(document_router, include_in_schema=False)
app.include_router(workflow_router, include_in_schema=False)
app.include_router(legal_ground_router, include_in_schema=False)
app.include_router(precedent_router, include_in_schema=False)
app.include_router(grounding_router, include_in_schema=False)
app.include_router(security_router, include_in_schema=False)
app.include_router(auth_router, include_in_schema=False)
app.include_router(apple_auth_router, include_in_schema=False)
app.include_router(lifecycle_router, include_in_schema=False)
app.include_router(ai_run_router, include_in_schema=False)
app.include_router(yargitay_health_router, include_in_schema=False)
app.include_router(legal_issue_graph_router, include_in_schema=False)
app.include_router(job_router, include_in_schema=False)
app.include_router(metrics_router, include_in_schema=False)

from app.core.metrics import register_route_pattern, set_metrics_enabled, is_metrics_enabled # noqa: E402
from app.core.degraded_state import (  # noqa: E402
    get_registry, update_component_state, ComponentStatus, ComponentState, # noqa: F811
)

set_metrics_enabled(settings.metrics_enabled)

for _route in app.routes:
    if hasattr(_route, "path") and hasattr(_route, "methods"):
        _path: str = _route.path
        _methods = _route.methods or set()
        if not _path:
            continue
        register_route_pattern(_path, _path)


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
async def health_check() -> JSONResponse:
    checks: dict[str, dict[str, object]] = {}
    critical_failed = False
    registry = get_registry()

    try:
        t0 = time.time()
        db_health = await check_db_health()
        t1 = time.time()
        if db_health.get("connected"):
            checks["database"] = {"status": "ok"}
            update_component_state("database", ComponentStatus.HEALTHY)
            if is_metrics_enabled():
                from app.core.metrics import record_db_health
                record_db_health(True, t1 - t0)
        else:
            checks["database"] = {"status": "failed", "code": "database_unavailable"}
            update_component_state("database", ComponentStatus.UNHEALTHY, error_code="database_unavailable")
            if is_metrics_enabled():
                from app.core.metrics import record_db_health
                record_db_health(False, t1 - t0)
            critical_failed = True
    except Exception:
        logger.error(
            "health_db_check_failed correlation_id=%s",
            get_correlation_id(),
            extra={"correlation_id": get_correlation_id()},
        )
        checks["database"] = {"status": "failed", "code": "database_unavailable"}
        update_component_state("database", ComponentStatus.UNHEALTHY, error_code="database_unavailable")
        critical_failed = True

    try:
        get_settings()
        checks["configuration"] = {"status": "ok"}
    except Exception:
        checks["configuration"] = {"status": "failed", "code": "configuration_error"}
        critical_failed = True

    _all_states = registry.get_all()
    components: dict[str, dict[str, object]] = {}
    for name, state in sorted(_all_states.items()):
        components[name] = {
            "status": state.status.value,
            "checked_at": state.checked_at,
            "message_code": state.message_code,
            "last_error_code": state.last_error_code,
            "consecutive_failures": state.consecutive_failures,
        }

    overall_registry = registry.get_overall_status()
    if critical_failed or overall_registry == ComponentStatus.UNHEALTHY:
        overall = "unhealthy"
        status_code = 503
    elif overall_registry == ComponentStatus.DEGRADED:
        overall = "degraded"
        status_code = 200
    else:
        overall = "healthy"
        status_code = 200

    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall,
            "service": settings.log_service_name,
            "checks": checks,
            "components": components,
        },
    )


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
            checks["database"] = {"status": "failed", "code": "database_unavailable"}
    except Exception:
        logger.error(
            "ready_db_check_failed correlation_id=%s",
            get_correlation_id(),
            extra={"correlation_id": get_correlation_id()},
        )
        checks["database"] = {"status": "failed", "code": "database_unavailable"}

    try:
        get_settings()
        checks["configuration"] = {"status": "ok"}
    except Exception:
        checks["configuration"] = {"status": "failed", "code": "configuration_error"}

    all_ok = all(c.get("status") == "ok" for c in checks.values())
    status = "ready" if all_ok else "not_ready"
    status_code = 200 if all_ok else 503

    return JSONResponse(
        status_code=status_code,
        content={"status": status, "checks": checks},
    )


@app.get("/system-health", tags=["System"], include_in_schema=False)
async def system_health_alias() -> JSONResponse:
    return await health_check()
