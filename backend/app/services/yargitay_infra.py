"""P1.2 — Yargitay scraper hardening: browser pool, circuit breaker, cache."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# ── Config ──
POOL_SIZE = 1
MAX_CONCURRENT = 2
BROWSER_IDLE_SECONDS = 300
HEADLESS = True
LAUNCH_TIMEOUT_MS = 30000
CACHE_TTL_SECONDS = 3600
NEGATIVE_CACHE_TTL = 300
CACHE_MAX_ENTRIES = 200
CIRCUIT_THRESHOLD = 3
CIRCUIT_OPEN_SECONDS = 120
HALF_OPEN_PROBES = 1

# ── Cache ──

_query_cache: dict[str, tuple[float, list[dict]]] = {}


def _normalize_query(raw: str) -> str:
    text = re.sub(r"\s+", " ", str(raw or "").strip().casefold())
    text = text[:120]
    return text


def _cache_key(query: str, max_results: int = 10) -> str:
    return hashlib.sha256(f"{_normalize_query(query)}:{max_results}".encode()).hexdigest()[:16]


def cache_get(query: str, max_results: int = 10) -> list[dict] | None:
    key = _cache_key(query, max_results)
    entry = _query_cache.get(key)
    if not entry:
        return None
    ts, results = entry
    if time.time() - ts > CACHE_TTL_SECONDS:
        del _query_cache[key]
        return None
    return results


def cache_set(query: str, max_results: int, results: list[dict]) -> None:
    key = _cache_key(query, max_results)
    _query_cache[key] = (time.time(), results)
    if len(_query_cache) > CACHE_MAX_ENTRIES:
        oldest = min(_query_cache, key=lambda k: _query_cache[k][0])
        del _query_cache[oldest]


def cache_negative(query: str, max_results: int = 10) -> None:
    key = _cache_key(query, max_results)
    _query_cache[key] = (time.time() - CACHE_TTL_SECONDS + NEGATIVE_CACHE_TTL, [])


def cache_clear() -> None:
    _query_cache.clear()


def cache_stats() -> dict:
    return {"entries": len(_query_cache), "ttl": CACHE_TTL_SECONDS, "max": CACHE_MAX_ENTRIES}


# ── Circuit Breaker ──

_circuit_state = "closed"
_circuit_failures = 0
_circuit_opened_at = 0.0
_last_failure_code = ""
_last_success_at = ""


def circuit_state() -> str:
    if _circuit_state == "open":
        if time.time() - _circuit_opened_at > CIRCUIT_OPEN_SECONDS:
            return "half_open"
        return "open"
    return _circuit_state


def circuit_success() -> None:
    global _circuit_state, _circuit_failures, _last_success_at
    _circuit_failures = 0
    _circuit_state = "closed"
    _last_success_at = datetime.now(UTC).isoformat()


def circuit_failure(error_code: str = "") -> None:
    global _circuit_state, _circuit_failures, _circuit_opened_at, _last_failure_code
    _circuit_failures += 1
    _last_failure_code = error_code
    if _circuit_failures >= CIRCUIT_THRESHOLD:
        _circuit_state = "open"
        _circuit_opened_at = time.time()


def circuit_allow() -> bool:
    return circuit_state() != "open"


def circuit_stats() -> dict:
    return {
        "state": circuit_state(),
        "failures": _circuit_failures,
        "threshold": CIRCUIT_THRESHOLD,
        "open_seconds": CIRCUIT_OPEN_SECONDS,
        "last_failure_code": _last_failure_code,
        "last_success_at": _last_success_at,
    }


# ── Metrics ──

_metrics: dict[str, int] = {
    "total_searches": 0, "success_count": 0, "partial_count": 0,
    "failure_count": 0, "timeout_count": 0, "blocked_count": 0,
    "cache_hit_count": 0, "retry_count": 0, "circuit_open_count": 0,
    "browser_restart_count": 0, "total_duration_ms": 0,
}


def metrics_record(status: str, duration_ms: int = 0) -> None:
    _metrics["total_searches"] += 1
    _metrics["total_duration_ms"] += duration_ms
    key = {
        "success": "success_count", "partial": "partial_count",
        "failure": "failure_count", "timeout": "timeout_count",
        "blocked": "blocked_count", "cache_hit": "cache_hit_count",
    }.get(status)
    if key:
        _metrics[key] += 1


def metrics_stats() -> dict:
    total = _metrics["total_searches"]
    return {
        **{k: v for k, v in _metrics.items()},
        "average_duration_ms": _metrics["total_duration_ms"] // max(total, 1),
    }


# ── Browser Pool ──

_browser_lock = asyncio.Lock()
_browser_semaphore = asyncio.Semaphore(MAX_CONCURRENT)
_browser_instance: Any = None
_browser_last_used = 0.0


async def _get_browser():
    global _browser_instance, _browser_last_used
    from playwright.async_api import async_playwright
    if _browser_instance is None or not _browser_instance.is_connected():
        _metrics["browser_restart_count"] += 1
        pw = await async_playwright().start()
        _browser_instance = await pw.chromium.launch(headless=HEADLESS, args=["--disable-dev-shm-usage"])
    _browser_last_used = time.time()
    return _browser_instance


async def acquire_browser():
    await _browser_semaphore.acquire()
    return await _get_browser()


def release_browser():
    _browser_semaphore.release()


async def close_browser():
    global _browser_instance
    if _browser_instance and _browser_instance.is_connected():
        await _browser_instance.close()
    _browser_instance = None


def browser_stats() -> dict:
    return {
        "pool_size": POOL_SIZE,
        "max_concurrent": MAX_CONCURRENT,
        "idle_seconds": BROWSER_IDLE_SECONDS,
        "restarts": _metrics["browser_restart_count"],
        "connected": _browser_instance is not None and _browser_instance.is_connected() if _browser_instance else False,
    }


def yargitay_health() -> dict:
    return {
        "status": "ok" if circuit_state() != "open" else "degraded",
        "circuit": circuit_stats(),
        "cache": cache_stats(),
        "metrics": metrics_stats(),
        "browser": browser_stats(),
        "last_success_at": _last_success_at,
        "last_failure_code": _last_failure_code,
    }


# ── Retry / Backoff ──

import random as _random

RETRY_MAX = 3
RETRY_BASE_DELAY = 1.0
RETRY_MAX_DELAY = 30.0
RETRYABLE_ERRORS = ("timeout", "429", "502", "503", "504", "connection", "browser_crash")
PERMANENT_ERRORS = ("captcha", "blocked", "403", "invalid", "parse_error", "selector_error")

_sleep_fn = time.sleep  # injectable for tests


def set_sleep_fn(fn) -> None:
    global _sleep_fn
    _sleep_fn = fn


def reset_sleep_fn() -> None:
    global _sleep_fn
    _sleep_fn = time.sleep


def exponential_backoff(attempt: int, base: float = RETRY_BASE_DELAY, max_delay: float = RETRY_MAX_DELAY) -> float:
    delay = min(base * (2 ** (attempt - 1)), max_delay)
    jitter = _random.uniform(0, delay * 0.5)
    return round(delay + jitter, 3)


def should_retry(error_code: str, attempt: int) -> bool:
    if error_code in PERMANENT_ERRORS:
        return False
    if error_code in RETRYABLE_ERRORS:
        return attempt < RETRY_MAX
    return False


def sleep_for(delay: float) -> None:
    _sleep_fn(delay)
