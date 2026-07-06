"""P1.10.6 — Thread-safe component state registry for health monitoring."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ComponentStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentState:
    status: ComponentStatus = ComponentStatus.UNKNOWN
    checked_at: float = 0.0
    message_code: str = ""
    last_error_code: str = ""
    consecutive_failures: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


CRITICAL_COMPONENTS = frozenset({
    "database",
    "storage",
})

NON_CRITICAL_COMPONENTS = frozenset({
    "queue",
    "yargitay",
    "legal_source_ingest",
    "backup",
    "restore",
    "ai_provider",
})

ALL_COMPONENTS = CRITICAL_COMPONENTS | NON_CRITICAL_COMPONENTS


class DegradedStateRegistry:
    """Thread/async-safe registry for component health states."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[str, ComponentState] = {
            name: ComponentState() for name in ALL_COMPONENTS
        }

    def update(
        self,
        component: str,
        status: ComponentStatus,
        message_code: str = "",
        error_code: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        from app.core.redaction import redact_dict
        with self._lock:
            state = self._states.get(component)
            if state is None:
                state = ComponentState()
                self._states[component] = state

            if status == ComponentStatus.HEALTHY:
                state.consecutive_failures = 0
            else:
                state.consecutive_failures += 1

            state.status = status
            state.checked_at = time.time()
            state.message_code = message_code
            state.last_error_code = error_code
            if metadata:
                state.metadata = redact_dict(metadata)

    def get(self, component: str) -> ComponentState | None:
        with self._lock:
            return self._states.get(component)

    def get_all(self) -> dict[str, ComponentState]:
        with self._lock:
            return dict(self._states)

    def get_overall_status(self) -> ComponentStatus:
        with self._lock:
            critical_unhealthy = any(
                self._states.get(name, ComponentState()).status == ComponentStatus.UNHEALTHY
                for name in CRITICAL_COMPONENTS
            )
            if critical_unhealthy:
                return ComponentStatus.UNHEALTHY

            any_degraded = False
            for name, state in self._states.items():
                if state.status == ComponentStatus.UNHEALTHY:
                    if name in CRITICAL_COMPONENTS:
                        return ComponentStatus.UNHEALTHY
                if state.status == ComponentStatus.DEGRADED:
                    any_degraded = True

            if any_degraded:
                return ComponentStatus.DEGRADED

            return ComponentStatus.HEALTHY

    def reset(self) -> None:
        with self._lock:
            for name in list(self._states.keys()):
                self._states[name] = ComponentState()


_registry: DegradedStateRegistry | None = None
_lock = threading.Lock()


def get_registry() -> DegradedStateRegistry:
    global _registry
    if _registry is None:
        with _lock:
            if _registry is None:
                _registry = DegradedStateRegistry()
    return _registry


def update_component_state(
    component: str,
    status: ComponentStatus,
    message_code: str = "",
    error_code: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    get_registry().update(component, status, message_code, error_code, metadata)
