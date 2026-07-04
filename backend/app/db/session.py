"""P1.4 — Database session manager and config."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

logger = logging.getLogger(__name__)

_engine = None
_sessionmaker = None


def _build_url() -> str:
    settings = get_settings()
    url = settings.database_url
    if not url:
        url = "sqlite+aiosqlite:///./case_store/emsalist.db"
    return url


def get_engine():
    global _engine
    if _engine is None:
        url = _build_url()
        logger.info("db_engine_created backend=%s", "postgresql" if "postgres" in url else "sqlite")
        _engine = create_async_engine(
            url,
            echo=False,
            pool_size=5,
            max_overflow=5,
            pool_timeout=30,
        )
    return _engine


def get_sessionmaker():
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with get_sessionmaker()() as session:
        yield session


@asynccontextmanager
async def unit_of_work():
    async with get_sessionmaker()() as session:
        async with session.begin():
            yield session


async def check_db_health() -> dict:
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            import time
            t0 = time.time()
            await conn.execute(engine.dialect.statement_compiler(engine.dialect, None).visit_textual("SELECT 1"))
            lat = int((time.time() - t0) * 1000)
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        alc = Config()
        alc.set_main_option("script_location", "app/db/migrations")
        script = ScriptDirectory.from_config(alc)
        return {"backend": "sqlalchemy", "connected": True, "latency_ms": lat, "migration_head": script.get_current_head()}
    except Exception as e:
        return {"backend": "sqlalchemy", "connected": False, "error": str(e)[:100]}
