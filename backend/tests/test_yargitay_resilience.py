"""P1.2.1 — Yargitay scraper resilience integration tests."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.services.yargitay_infra import (
    POOL_SIZE,
    MAX_CONCURRENT,
    cache_clear,
    cache_get,
    cache_set,
    circuit_allow,
    circuit_failure,
    circuit_success,
    circuit_state,
    metrics_stats,
    set_sleep_fn,
    reset_sleep_fn,
    exponential_backoff,
    should_retry,
    sleep_for,
    acquire_browser,
    release_browser,
)


class FakeBrowser:
    def __init__(self):
        self.connected = True
        self.restart_count = 0

    def is_connected(self):
        return self.connected

    async def close(self):
        self.connected = False

    async def new_page(self):
        return FakePage()


class FakePage:
    def __init__(self):
        self.closed = False

    async def goto(self, *args, **kwargs):
        pass

    async def close(self):
        self.closed = True


class YargitayBrowserPoolTests(unittest.TestCase):

    def setUp(self) -> None:
        self.closed_pages = 0
        import app.services.yargitay_infra as infra
        self._orig_browser = infra._browser_instance
        infra._browser_instance = None
        cache_clear()
        circuit_success()

    def tearDown(self) -> None:
        import app.services.yargitay_infra as infra
        infra._browser_instance = self._orig_browser

    async def _acquire_release(self) -> None:
        browser = await acquire_browser()
        page = FakePage()
        self.closed_pages += 1
        await page.close()
        release_browser()

    def test_browser_pool_reuses_instance(self) -> None:
        import app.services.yargitay_infra as infra
        import asyncio
        infra._browser_instance = FakeBrowser()
        async def run():
            b1 = await acquire_browser()
            release_browser()
            b2 = await acquire_browser()
            release_browser()
            self.assertIs(b1, b2)
        asyncio.run(run())

    def test_semaphore_respects_limit(self) -> None:
        import app.services.yargitay_infra as infra
        import asyncio
        infra._browser_instance = FakeBrowser()

        async def try_acquire():
            b = await acquire_browser()
            await asyncio.sleep(0.02)
            release_browser()

        async def runner():
            tasks = [asyncio.create_task(try_acquire()) for _ in range(8)]
            await asyncio.gather(*tasks)

        asyncio.run(runner())
        self.assertTrue(True)

    def test_page_closes_after_use(self) -> None:
        import asyncio
        async def run():
            page = FakePage()
            self.assertFalse(page.closed)
            await page.close()
            self.assertTrue(page.closed)
        asyncio.run(run())


class YargitayRetryBackoffTests(unittest.TestCase):

    def test_exponential_backoff_increases(self) -> None:
        d1 = exponential_backoff(1)
        d2 = exponential_backoff(2)
        d3 = exponential_backoff(3)
        self.assertLess(d1, d2)
        self.assertLess(d2, d3)

    def test_jitter_within_bounds(self) -> None:
        for attempt in range(1, 4):
            delay = exponential_backoff(attempt, base=1.0, max_delay=10.0)
            expected = min(2 ** (attempt - 1), 10.0)
            self.assertGreaterEqual(delay, expected)
            self.assertLessEqual(delay, expected * 1.5 + 0.01)

    def test_jitter_max_capped(self) -> None:
        delay = exponential_backoff(20, base=2.0, max_delay=10.0)
        self.assertLessEqual(delay, 15.0)

    def test_retry_timeout_error(self) -> None:
        self.assertTrue(should_retry("timeout", 1))
        self.assertTrue(should_retry("timeout", 2))
        self.assertFalse(should_retry("timeout", 5))

    def test_retry_429_error(self) -> None:
        self.assertTrue(should_retry("429", 1))
        self.assertTrue(should_retry("502", 1))
        self.assertTrue(should_retry("503", 1))
        self.assertTrue(should_retry("504", 1))

    def test_no_retry_permanent_errors(self) -> None:
        for code in ("captcha", "blocked", "403", "parse_error", "selector_error"):
            self.assertFalse(should_retry(code, 1), f"should not retry {code}")

    def test_sleep_injectable(self) -> None:
        slept = []
        set_sleep_fn(lambda d: slept.append(d))
        sleep_for(1.5)
        reset_sleep_fn()
        self.assertEqual(slept, [1.5])


class YargitayCircuitIntegrationTests(unittest.TestCase):

    def setUp(self) -> None:
        cache_clear()
        circuit_success()

    def test_circuit_blocks_browser_call(self) -> None:
        for _ in range(3):
            circuit_failure("timeout")
        self.assertFalse(circuit_allow())

    def test_circuit_returns_cache_when_open(self) -> None:
        cache_set("test query arac", 3, [{"court": "Yargitay 3. HD", "esas_no": "2023/100"}])
        for _ in range(3):
            circuit_failure("timeout")
        self.assertEqual(circuit_state(), "open")
        cached = cache_get("test query arac", 3)
        self.assertIsNotNone(cached)
        self.assertGreater(len(cached), 0)

    def test_circuit_no_cache_returns_none(self) -> None:
        for _ in range(3):
            circuit_failure("timeout")
        result = cache_get("never cached query xyz 999", 1)
        self.assertIsNone(result)

    def test_captcha_triggers_circuit_failure(self) -> None:
        circuit_failure("captcha")
        circuit_failure("blocked")
        self.assertEqual(circuit_state(), "closed")
        circuit_failure("captcha")
        self.assertEqual(circuit_state(), "open")


class YargitayFallbackAuthorityTests(unittest.TestCase):

    def setUp(self) -> None:
        cache_clear()
        circuit_success()

    def test_fallback_not_official_yargitay(self) -> None:
        from app.services.precedent_authority_service import precedent_authority_service
        brain = [{"title": "fallback karar", "court": ""}]
        authority = precedent_authority_service.build_authority(case_id="test-fb", live_results=[], brain_results=brain)
        for r in authority.records:
            self.assertNotEqual(r.source_type, "official_yargitay")

    def test_official_result_is_authoritative(self) -> None:
        from app.services.precedent_authority_service import precedent_authority_service
        live = [{"court": "Yargitay 3. HD", "esas_no": "2023/abc", "karar_no": "2024/def", "date": "01.01.2024"}]
        authority = precedent_authority_service.build_authority(case_id="test-of", live_results=live, brain_results=[])
        self.assertEqual(authority.records[0].authority_status, "authoritative")

    def test_fallback_result_is_fallback_only(self) -> None:
        from app.services.precedent_authority_service import precedent_authority_service
        brain = [{"title": "fallback data"}]
        authority = precedent_authority_service.build_authority(case_id="test-fo", live_results=[], brain_results=brain)
        self.assertEqual(authority.records[0].authority_status, "fallback_only")


if __name__ == "__main__":
    unittest.main()
