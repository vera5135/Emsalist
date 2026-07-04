from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


_TEST_CASE_STORE = tempfile.TemporaryDirectory(prefix="emsalist-pytest-cases-")
os.environ["EMSALIST_CASE_STORE_DIR"] = str(Path(_TEST_CASE_STORE.name) / "case_store")


@pytest.fixture(scope="session", autouse=True)
def isolated_case_store_for_test_process():
    yield Path(os.environ["EMSALIST_CASE_STORE_DIR"])
    _TEST_CASE_STORE.cleanup()
