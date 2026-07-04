import asyncio
import sys
from pathlib import Path

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
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
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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
