"""P1.2 — Yargitay infrastructure tests."""

from __future__ import annotations

import unittest

from app.services.yargitay_infra import (
    _normalize_query,
    _cache_key,
    cache_get,
    cache_set,
    cache_clear,
    cache_stats,
    cache_negative,
    circuit_state,
    circuit_success,
    circuit_failure,
    circuit_allow,
    circuit_stats,
    metrics_record,
    metrics_stats,
    browser_stats,
    yargitay_health,
)


class YargitayCacheTests(unittest.TestCase):

    def setUp(self) -> None:
        cache_clear()

    def test_cache_set_get(self) -> None:
        cache_set("ayipli arac gizli ayip", 5, [{"court": "Yargitay"}])
        results = cache_get("ayipli arac gizli ayip", 5)
        self.assertIsNotNone(results)

    def test_cache_miss(self) -> None:
        results = cache_get("never_searched_query_xyz", 5)
        self.assertIsNone(results)

    def test_different_max_results_different_cache(self) -> None:
        cache_set("test query", 3, [{"a": 1}])
        self.assertIsNotNone(cache_get("test query", 3))
        self.assertIsNone(cache_get("test query", 5))

    def test_negative_cache(self) -> None:
        cache_negative("empty query", 5)
        self.assertIsNotNone(cache_get("empty query", 5))
        self.assertEqual(len(cache_get("empty query", 5) or []), 0)

    def test_cache_stats(self) -> None:
        cache_set("q1", 5, [{}])
        stats = cache_stats()
        self.assertGreaterEqual(stats["entries"], 1)

    def test_no_raw_case_text_in_cache_key(self) -> None:
        key = _cache_key("Müvekkil Ahmet Yılmaz TC 12345 aracı satın aldı", 5)
        self.assertNotIn("Ahmet", key)
        self.assertNotIn("12345", key)
        self.assertLess(len(key), 40)


class YargitayCircuitBreakerTests(unittest.TestCase):

    def setUp(self) -> None:
        circuit_success()

    def test_initial_closed(self) -> None:
        self.assertEqual(circuit_state(), "closed")
        self.assertTrue(circuit_allow())

    def test_failures_open_circuit(self) -> None:
        for _ in range(3):
            circuit_failure("timeout")
        self.assertEqual(circuit_state(), "open")
        self.assertFalse(circuit_allow())

    def test_success_resets_circuit(self) -> None:
        circuit_failure("timeout")
        circuit_failure("timeout")
        circuit_success()
        self.assertEqual(circuit_state(), "closed")

    def test_metrics_record(self) -> None:
        metrics_record("success", 100)
        metrics_record("cache_hit", 50)
        stats = metrics_stats()
        self.assertGreaterEqual(stats["total_searches"], 2)


class YargitayHealthEndpointTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        from fastapi.testclient import TestClient
        from app.main import app
        cls.client = TestClient(app)

    def test_health_returns_ok(self) -> None:
        response = self.client.get("/yargitay/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("status", data)
        self.assertIn("circuit", data)
        self.assertIn("browser", data)

    def test_health_no_raw_query(self) -> None:
        response = self.client.get("/yargitay/health")
        data = response.json()
        data_str = str(data)
        self.assertNotIn("Ahmet", data_str)
        self.assertNotIn("12345", data_str)


if __name__ == "__main__":
    unittest.main()
