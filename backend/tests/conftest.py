from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio


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
        import asyncio
        from app.db.session import dispose_engine

        async def _dispose():
            await dispose_engine()

        try:
            asyncio.run(_dispose())
        except RuntimeError:
            pass
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


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_per_test():
    """Dispose engine after each test so fresh connections use current event loop."""
    yield
    try:
        from app.db.session import dispose_engine
        await dispose_engine()
    except Exception:
        pass


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _guard_global_db_state(request):
    """Detect tests that leak global database configuration."""
    saved_db_url = os.environ.get("DATABASE_URL")
    saved_emsalist_db_url = os.environ.get("EMSALIST_DATABASE_URL")
    try:
        import app.db.session as _session_mod
    except ImportError:
        _session_mod = None
    saved_engine = _session_mod._engine if _session_mod else None
    saved_sessionmaker = _session_mod._sessionmaker if _session_mod else None

    yield

    current_db_url = os.environ.get("DATABASE_URL")
    current_emsalist_db_url = os.environ.get("EMSALIST_DATABASE_URL")
    current_engine = _session_mod._engine if _session_mod else None
    current_sessionmaker = _session_mod._sessionmaker if _session_mod else None

    leaked: list[str] = []
    if saved_db_url is not None and current_db_url is not None and current_db_url != saved_db_url:
        leaked.append(f"DATABASE_URL changed: {saved_db_url!r} -> {current_db_url!r}")
    if saved_emsalist_db_url is not None and current_emsalist_db_url is not None \
       and current_emsalist_db_url != saved_emsalist_db_url:
        leaked.append(f"EMSALIST_DATABASE_URL changed")
    if saved_engine is not None and current_engine is not saved_engine:
        leaked.append("app.db.session._engine replaced")
    if saved_sessionmaker is not None and current_sessionmaker is not saved_sessionmaker:
        leaked.append("app.db.session._sessionmaker replaced")

    if leaked:
        try:
            import app.config as _cfg
            _cfg.get_settings.cache_clear()
        except Exception:
            pass
        if _session_mod and saved_engine is not None and current_engine is not saved_engine:
            try:
                _session_mod._engine = saved_engine
            except Exception:
                pass
        if _session_mod and saved_sessionmaker is not None and current_sessionmaker is not saved_sessionmaker:
            try:
                _session_mod._sessionmaker = saved_sessionmaker
            except Exception:
                pass
        if saved_db_url is not None and current_db_url != saved_db_url:
            os.environ["DATABASE_URL"] = saved_db_url
        if saved_emsalist_db_url is not None and current_emsalist_db_url != saved_emsalist_db_url:
            os.environ["EMSALIST_DATABASE_URL"] = saved_emsalist_db_url

        nodeid = request.node.nodeid
        pytest.fail(
            f"Test polluted global DB state: {nodeid}\n  "
            + "\n  ".join(leaked)
        )