from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


_TEST_CASE_STORE = tempfile.TemporaryDirectory(prefix="emsalist-pytest-cases-")
os.environ.setdefault("EMSALIST_CASE_STORE_DIR", str(Path(_TEST_CASE_STORE.name) / "case_store"))


@pytest.fixture(scope="session", autouse=True)
def isolated_case_store_for_test_process():
    yield Path(os.environ["EMSALIST_CASE_STORE_DIR"])
    _TEST_CASE_STORE.cleanup()
    _dispose_db_engine()
    _reset_registry()


def _dispose_db_engine():
    try:
        from app.db.session import get_engine
        engine = get_engine()
        import asyncio

        async def _dispose():
            await engine.dispose()

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_dispose())
            else:
                loop.run_until_complete(_dispose())
        except RuntimeError:
            asyncio.run(_dispose())
    except Exception:
        pass


def _reset_registry():
    try:
        from app.core.degraded_state import get_registry
        get_registry().reset()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def _reset_registry_per_test():
    try:
        from app.core.degraded_state import get_registry
        get_registry().reset()
    except Exception:
        pass
    yield


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"
