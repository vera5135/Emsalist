import asyncio
import sys
from pathlib import Path

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
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

settings = get_settings()
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
    allow_headers=["Content-Type", "Authorization"],
)

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    from app.services.security_service import SECURITY_HEADERS, check_rate_limit

    if request.url.path in ("/health", "/styles.css", "/app.js", "/", "/docs", "/openapi.json"):
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
    response.headers["X-Request-Id"] = request.headers.get("X-Request-Id", "")
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
