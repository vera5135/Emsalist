"""P1.4.1 — Repository base and dual-write support."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class BaseRepository(ABC):
    """Abstract repository with JSON fallback."""

    def __init__(self) -> None:
        self._json_store: dict[str, Any] = {}

    @property
    def backend(self) -> str:
        return settings.storage_backend or "json"

    def _get_json_data(self) -> dict:
        """Override in subclasses to provide JSON persistence."""
        return self._json_store

    async def _db_execute(self, stmt, session=None):
        if session:
            result = await session.execute(stmt)
            await session.commit()
            return result

    def _drift_check(self, db_version: int, json_version: int, key: str) -> None:
        if db_version != json_version and self.backend == "dual":
            logger.warning("drift_detected key=%s db=%s json=%s", key, db_version, json_version)


# -- Soft delete mixin --
class SoftDeleteQueryBuilder:
    """Add soft-delete filtering to queries."""

    @staticmethod
    def active_only(query, model_class):
        return query.where(model_class.deleted_at.is_(None))

    @staticmethod
    def include_deleted(query, model_class):
        return query


# -- Optimistic concurrency --
class OptimisticLock:
    """Check version before updating."""

    @staticmethod
    def check(expected_version: int, current_version: int) -> bool:
        return expected_version == current_version


# -- Transaction helper --
class TransactionContext:
    """Simple transaction wrapper for dual-write."""

    def __init__(self, case_id: str):
        self.case_id = case_id
        self.operations: list[dict] = []
        self.committed = False

    def add_op(self, store: str, action: str, key: str, data: dict) -> None:
        self.operations.append({"store": store, "action": action, "key": key, "data": data})

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.operations.clear()
