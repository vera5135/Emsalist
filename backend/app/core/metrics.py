"""P1.10.4 — Prometheus metrics registry with no external dependency."""
from __future__ import annotations

import threading
import time
from typing import Callable

_HISTOGRAM_BUCKETS = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0,
    2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0,
)

_LOCK = threading.RLock()
_REGISTRY: dict[str, _Collector] = {}


class _Collector:
    name: str = ""
    documentation: str = ""

    def collect(self) -> list[str]:
        return []


class Counter(_Collector):
    """Thread-safe monotonic counter with label support."""

    def __init__(self, name: str, documentation: str, labelnames: tuple[str, ...] = ()) -> None:
        self.name = name
        self.documentation = documentation
        self.labelnames = labelnames
        self._data: dict[tuple[str, ...], float] = {}
        self._lock = threading.Lock()

    def inc(self, amount: float = 1, labels: dict[str, str] | None = None) -> None:
        key = self._key(labels)
        with self._lock:
            self._data[key] = self._data.get(key, 0.0) + amount

    def _key(self, labels: dict[str, str] | None) -> tuple[str, ...]:
        if not labels:
            return ()
        return tuple(labels.get(name, "") for name in self.labelnames)

    def collect(self) -> list[str]:
        lines: list[str] = []
        lines.append(f"# HELP {self.name} {self.documentation}")
        lines.append(f"# TYPE {self.name} counter")
        with self._lock:
            for key, val in sorted(self._data.items()):
                label_part = _format_labels(self.labelnames, key)
                lines.append(f"{self.name}{label_part} {_format_val(val)}")
        return lines


class Gauge(_Collector):
    """Thread-safe gauge with label support."""

    def __init__(self, name: str, documentation: str, labelnames: tuple[str, ...] = ()) -> None:
        self.name = name
        self.documentation = documentation
        self.labelnames = labelnames
        self._data: dict[tuple[str, ...], float] = {}
        self._lock = threading.Lock()

    def set(self, value: float, labels: dict[str, str] | None = None) -> None:
        key = self._key(labels)
        with self._lock:
            self._data[key] = value

    def inc(self, amount: float = 1, labels: dict[str, str] | None = None) -> None:
        key = self._key(labels)
        with self._lock:
            self._data[key] = self._data.get(key, 0.0) + amount

    def _key(self, labels: dict[str, str] | None) -> tuple[str, ...]:
        if not labels:
            return ()
        return tuple(labels.get(name, "") for name in self.labelnames)

    def collect(self) -> list[str]:
        lines: list[str] = []
        lines.append(f"# HELP {self.name} {self.documentation}")
        lines.append(f"# TYPE {self.name} gauge")
        with self._lock:
            for key, val in sorted(self._data.items()):
                label_part = _format_labels(self.labelnames, key)
                lines.append(f"{self.name}{label_part} {_format_val(val)}")
        return lines


class Histogram(_Collector):
    """Thread-safe histogram with configurable buckets and label support."""

    def __init__(
        self,
        name: str,
        documentation: str,
        labelnames: tuple[str, ...] = (),
        buckets: tuple[float, ...] = _HISTOGRAM_BUCKETS,
    ) -> None:
        self.name = name
        self.documentation = documentation
        self.labelnames = labelnames
        self.buckets = buckets
        self._lock = threading.Lock()
        self._sum: dict[tuple[str, ...], float] = {}
        self._count: dict[tuple[str, ...], int] = {}
        self._buckets: dict[tuple[str, ...], dict[float, int]] = {}

    def observe(self, value: float, labels: dict[str, str] | None = None) -> None:
        key = self._key(labels)
        with self._lock:
            self._sum[key] = self._sum.get(key, 0.0) + value
            self._count[key] = self._count.get(key, 0) + 1
            if key not in self._buckets:
                self._buckets[key] = {b: 0 for b in self.buckets}
            for bound in self.buckets:
                if value <= bound:
                    self._buckets[key][bound] += 1

    def _key(self, labels: dict[str, str] | None) -> tuple[str, ...]:
        if not labels:
            return ()
        return tuple(labels.get(name, "") for name in self.labelnames)

    def collect(self) -> list[str]:
        lines: list[str] = []
        lines.append(f"# HELP {self.name} {self.documentation}")
        lines.append(f"# TYPE {self.name} histogram")
        with self._lock:
            for key in sorted(set(self._sum.keys()) | set(self._buckets.keys())):
                label_part = _format_labels(self.labelnames, key)
                count = self._count.get(key, 0)
                total = self._sum.get(key, 0.0)
                bucket_data = self._buckets.get(key, {b: 0 for b in self.buckets})
                for bound in sorted(bucket_data.keys()):
                    lines.append(
                        f"{self.name}_bucket{label_part}{{le=\"{_format_val(bound)}\"}} {bucket_data[bound]}"
                    )
                lines.append(f"{self.name}_bucket{label_part}{{le=\"+Inf\"}} {count}")
                lines.append(f"{self.name}_count{label_part} {count}")
                lines.append(f"{self.name}_sum{label_part} {_format_val(total)}")
        return lines


def _format_labels(labelnames: tuple[str, ...], values: tuple[str, ...]) -> str:
    if not labelnames:
        return ""
    parts = [f'{name}="{value}"' for name, value in zip(labelnames, values)]
    return "{" + ",".join(parts) + "}"


def _format_val(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.6g}"


_ROUTE_PATTERNS: dict[str, str] = {}


def register_route_pattern(path: str, pattern: str) -> None:
    """Register a FastAPI route path -> template mapping for metrics labels."""
    _ROUTE_PATTERNS[path] = pattern


def resolve_route(path: str) -> str:
    """Resolve a raw path to a route template. Falls back to path if unknown."""
    for route_path, pattern in _ROUTE_PATTERNS.items():
        if _match_route(route_path, path):
            return pattern
    return path


def _match_route(route_path: str, request_path: str) -> bool:
    """Simple route path matching: /cases/{case_id}/documents -> /cases/abc123/documents."""
    route_parts = route_path.strip("/").split("/")
    req_parts = request_path.strip("/").split("/")
    if len(route_parts) != len(req_parts):
        return False
    for rp, rqp in zip(route_parts, req_parts):
        if rp.startswith("{") and rp.endswith("}"):
            continue
        if rp != rqp:
            return False
    return True


_NOISY_PREFIXES = frozenset({
    "/ui-assets", "/docs", "/openapi.json", "/favicon.ico",
    "/styles.css", "/app.js", "/metrics", "/live", "/ready",
    "/health", "/system-health",
})


def _is_noisy(path: str) -> bool:
    for prefix in _NOISY_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def _status_class(code: int) -> str:
    return f"{code // 100}xx"


_KNOWN_JOB_TYPES: frozenset[str] = frozenset()


def set_known_job_types(types: frozenset[str]) -> None:
    global _KNOWN_JOB_TYPES
    _KNOWN_JOB_TYPES = types


# --- Metric Definitions ---

http_requests_total = Counter(
    "emsalist_http_requests_total",
    "Total HTTP requests served",
    ("method", "route", "status_class"),
)

http_request_duration_seconds = Histogram(
    "emsalist_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ("method", "route"),
)

http_requests_in_flight = Gauge(
    "emsalist_http_requests_in_flight",
    "Currently in-flight HTTP requests",
)

db_health_status = Gauge(
    "emsalist_db_health_status",
    "Database health: 1=healthy, 0=degraded/unhealthy",
)

db_check_duration_seconds = Gauge(
    "emsalist_db_check_duration_seconds",
    "Last database health check duration in seconds",
)

jobs_enqueued_total = Counter(
    "emsalist_jobs_enqueued_total",
    "Total jobs enqueued",
    ("job_type",),
)

jobs_completed_total = Counter(
    "emsalist_jobs_completed_total",
    "Total jobs completed",
    ("job_type", "status"),
)

jobs_duration_seconds = Histogram(
    "emsalist_jobs_duration_seconds",
    "Job execution duration in seconds",
    ("job_type",),
    buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
)

jobs_pending = Gauge(
    "emsalist_jobs_pending",
    "Currently pending/queued jobs",
    ("job_type",),
)

backup_created_total = Counter(
    "emsalist_backup_created_total",
    "Total backups created",
    ("status",),
)

backup_verify_total = Counter(
    "emsalist_backup_verify_total",
    "Total backup verifications",
    ("status",),
)

restore_total = Counter(
    "emsalist_restore_total",
    "Total restore operations",
    ("mode", "status"),
)

backup_size_bytes = Histogram(
    "emsalist_backup_size_bytes",
    "Backup size in bytes",
    buckets=(1024 * 1024, 10 * 1024 * 1024, 50 * 1024 * 1024,
             100 * 1024 * 1024, 500 * 1024 * 1024, 1024 * 1024 * 1024,
             5 * 1024 * 1024 * 1024),
)


def record_http_request(
    method: str, path: str, status_code: int, duration_s: float,
) -> None:
    route = resolve_route(path)
    http_requests_total.inc(labels={"method": method, "route": route, "status_class": _status_class(status_code)})
    http_request_duration_seconds.observe(duration_s, labels={"method": method, "route": route})


def record_job_enqueued(job_type: str) -> None:
    jobs_enqueued_total.inc(labels={"job_type": job_type})


def record_job_completed(job_type: str, status: str, duration_s: float | None = None) -> None:
    jobs_completed_total.inc(labels={"job_type": job_type, "status": status})
    if duration_s is not None:
        jobs_duration_seconds.observe(duration_s, labels={"job_type": job_type})


def record_job_pending(job_type: str, count: int) -> None:
    jobs_pending.inc(float(count), labels={"job_type": job_type})


def record_job_pending_decrement(job_type: str) -> None:
    jobs_pending.inc(-1.0, labels={"job_type": job_type})


def record_backup(status: str, size_bytes: int | None = None) -> None:
    backup_created_total.inc(labels={"status": status})
    if size_bytes is not None and size_bytes > 0:
        backup_size_bytes.observe(float(size_bytes))


def record_backup_verify(status: str) -> None:
    backup_verify_total.inc(labels={"status": status})


def record_restore(mode: str, status: str) -> None:
    restore_total.inc(labels={"mode": mode, "status": status})


def record_db_health(healthy: bool, duration_s: float) -> None:
    db_health_status.set(1.0 if healthy else 0.0)
    db_check_duration_seconds.set(duration_s)


_metrics_enabled = True


def set_metrics_enabled(enabled: bool) -> None:
    global _metrics_enabled
    _metrics_enabled = enabled


def is_metrics_enabled() -> bool:
    return _metrics_enabled


def collect_metrics() -> str:
    """Generate Prometheus text exposition format."""
    lines: list[str] = []
    with _LOCK:
        for collector in sorted(_REGISTRY.values(), key=lambda c: c.name):
            lines.extend(collector.collect())
    lines.append("")
    return "\n".join(lines)


def _register(collector: _Collector) -> None:
    with _LOCK:
        if collector.name in _REGISTRY:
            raise ValueError(f"Metric {collector.name} already registered")
        _REGISTRY[collector.name] = collector


for _obj in list(globals().values()):
    if isinstance(_obj, _Collector):
        _register(_obj)
