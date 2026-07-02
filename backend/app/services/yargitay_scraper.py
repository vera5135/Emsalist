"""Asynchronous Playwright integration for Yargıtay Karar Arama.

The site renders its result table after an AJAX request. The service submits the
visible search form with Playwright, reads the structured list response from the
same browser session, and downloads decision detail HTML with that session's
cookies. It intentionally stops when a CAPTCHA is displayed.
"""

import asyncio
import logging
import random
import sys
from contextlib import suppress
from typing import Any
from urllib.parse import quote, urljoin

try:
    from playwright.async_api import (
        Browser,
        BrowserContext,
        Error as PlaywrightError,
        Page,
        Response,
        TimeoutError as PlaywrightTimeoutError,
        async_playwright,
    )
    PLAYWRIGHT_IMPORT_ERROR: Exception | None = None
except Exception as exc:
    Browser = BrowserContext = Page = Response = Any  # type: ignore
    PlaywrightError = Exception  # type: ignore
    PlaywrightTimeoutError = TimeoutError  # type: ignore
    async_playwright = None  # type: ignore
    PLAYWRIGHT_IMPORT_ERROR = exc

from app.models.yargitay_models import YargitayDecision, YargitaySearchResponse
from app.services.decision_cleaner import DecisionCleaner, decision_cleaner

# Site adresleri ve HTML seçicileri, Yargıtay arayüzü değiştiğinde tek yerden
# güncellenebilmeleri için burada tutulur.
BASE_URL = "https://karararama.yargitay.gov.tr/"
DETAIL_PATH = "getDokuman?id={document_id}"
LIST_RESPONSE_FRAGMENT = "/aramalist"

SEARCH_INPUT_SELECTOR = "#aranan"
SEARCH_BUTTON_SELECTOR = "#aramaG"
RESULT_TABLE_SELECTOR = "#detayAramaSonuclar"
RESULT_ROW_SELECTOR = "#detayAramaSonuclar tbody tr"
NEXT_PAGE_SELECTOR = "#detayAramaSonuclar_paginate .paginate_button.next:not(.disabled)"
EMPTY_RESULT_SELECTOR = "#detayAramaSonuclar td.dataTables_empty"
DECISION_CONTENT_SELECTOR = ".card-scroll"
CAPTCHA_STATE_SELECTOR = "#isDisplayCaptcha"
CAPTCHA_VISIBLE_SELECTOR = ".g-recaptcha, iframe[src*='recaptcha']"
SITE_ERROR_SELECTOR = "#exceptionMsg:not(.d-none), .toast-message"

NAVIGATION_TIMEOUT_MS = 30_000
QUERY_TIMEOUT_MS = 30_000
DETAIL_TIMEOUT_MS = 20_000
BETWEEN_QUERY_DELAY_RANGE_SECONDS = (2.0, 4.0)
BETWEEN_DETAIL_DELAY_RANGE_SECONDS = (1.0, 2.0)
RATE_LIMIT_MESSAGE = "Yargıtay hız sınırı uyguladı; mevcut sonuçlarla devam edildi."
logger = logging.getLogger(__name__)


class YargitayAccessBlocked(Exception):
    """Raised when the remote site refuses further automated requests."""


class YargitayScraper:
    """Search and retrieve public Yargıtay decisions with a real browser session."""

    def __init__(self, cleaner: DecisionCleaner | None = None) -> None:
        self.cleaner = cleaner or decision_cleaner

    async def search(self, queries: list[str], max_results: int) -> YargitaySearchResponse:
        if sys.platform.startswith("win"):
            return await asyncio.to_thread(
                self._search_in_isolated_event_loop,
                queries,
                max_results,
            )
        return await self._search_with_browser(queries=queries, max_results=max_results)

    def _search_in_isolated_event_loop(
        self,
        queries: list[str],
        max_results: int,
    ) -> YargitaySearchResponse:
        """Run Playwright in a fresh loop on Windows.

        Some Windows ASGI server configurations run the app on a selector event
        loop. Playwright needs subprocess support to launch Chromium, which that
        loop cannot provide. A dedicated Proactor loop keeps the public API async
        while avoiding NotImplementedError during browser startup.
        """

        loop_factory = getattr(asyncio, "ProactorEventLoop", None)
        loop = loop_factory() if loop_factory is not None else asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(
                self._search_with_browser(queries=queries, max_results=max_results)
            )
        finally:
            with suppress(Exception):
                loop.run_until_complete(loop.shutdown_asyncgens())
            asyncio.set_event_loop(None)
            loop.close()

    async def _search_with_browser(self, queries: list[str], max_results: int) -> YargitaySearchResponse:
        results: list[YargitayDecision] = []
        errors: list[str] = []
        attempted_queries: list[str] = []
        seen_detail_urls: set[str] = set()
        skipped_due_to_rate_limit = False
        raw_live_result_count = 0
        official_yargitay_reached = False

        if async_playwright is None:
            message = self._short_error(PLAYWRIGHT_IMPORT_ERROR or RuntimeError("Playwright kullanılamıyor."))
            errors.append(f"Playwright kullanılamıyor; Yargıtay araması çalıştırılamadı: {message}")
            return self._build_search_response(
                results=results,
                errors=errors,
                attempted_queries=attempted_queries,
                skipped_due_to_rate_limit=skipped_due_to_rate_limit,
                raw_live_result_count=raw_live_result_count,
                official_yargitay_reached=official_yargitay_reached,
            )

        browser: Browser | None = None
        context: BrowserContext | None = None
        page: Page | None = None

        try:
            async with async_playwright() as playwright:
                try:
                    browser = await playwright.chromium.launch(headless=True)
                    context = await browser.new_context(locale="tr-TR")
                    page = await context.new_page()
                    page.set_default_timeout(QUERY_TIMEOUT_MS)

                    response = await page.goto(
                        BASE_URL,
                        wait_until="domcontentloaded",
                        timeout=NAVIGATION_TIMEOUT_MS,
                    )
                    official_yargitay_reached = True
                    if response is None or response.status >= 400:
                        status = response.status if response else "yanıt yok"
                        errors.append(f"Yargıtay sitesine erişilemedi (HTTP: {status}).")
                        return self._build_search_response(
                            results=results,
                            errors=errors,
                            attempted_queries=attempted_queries,
                            skipped_due_to_rate_limit=skipped_due_to_rate_limit,
                            raw_live_result_count=raw_live_result_count,
                            official_yargitay_reached=official_yargitay_reached,
                        )

                    if await self._captcha_is_active(page):
                        errors.append("Yargıtay sitesi CAPTCHA doğrulaması istiyor; otomatik arama durduruldu.")
                        return self._build_search_response(
                            results=results,
                            errors=errors,
                            attempted_queries=attempted_queries,
                            skipped_due_to_rate_limit=skipped_due_to_rate_limit,
                            raw_live_result_count=raw_live_result_count,
                            official_yargitay_reached=official_yargitay_reached,
                        )

                    if await self._access_is_blocked(page):
                        errors.append("Yargıtay sitesi otomatik erişimi engelledi; arama durduruldu.")
                        return self._build_search_response(
                            results=results,
                            errors=errors,
                            attempted_queries=attempted_queries,
                            skipped_due_to_rate_limit=skipped_due_to_rate_limit,
                            raw_live_result_count=raw_live_result_count,
                            official_yargitay_reached=official_yargitay_reached,
                        )

                    await page.locator(SEARCH_INPUT_SELECTOR).wait_for(state="visible")

                    for query_index, query in enumerate(queries):
                        if len(results) >= max_results:
                            break

                        attempted_queries.append(query)
                        metrics = {"raw_live_result_count": raw_live_result_count}
                        may_continue = await self._search_one_query(
                            page=page,
                            context=context,
                            query=query,
                            max_results=max_results,
                            results=results,
                            errors=errors,
                            seen_detail_urls=seen_detail_urls,
                            metrics=metrics,
                        )
                        raw_live_result_count = metrics["raw_live_result_count"]

                        if not may_continue:
                            skipped_due_to_rate_limit = self._has_rate_limit_error(errors)
                            break

                        if await self._captcha_is_active(page):
                            errors.append(
                                "Yargıtay sitesi CAPTCHA doğrulaması istedi; kalan sorgular çalıştırılmadı."
                            )
                            break

                        if query_index < len(queries) - 1 and len(results) < max_results:
                            await self._polite_sleep(BETWEEN_QUERY_DELAY_RANGE_SECONDS)

                finally:
                    if page is not None and not page.is_closed():
                        with suppress(Exception):
                            await page.close()
                    if context is not None:
                        with suppress(Exception):
                            await context.close()
                    if browser is not None:
                        with suppress(Exception):
                            await browser.close()

        except PlaywrightTimeoutError:
            errors.append("Yargıtay sitesine erişim zaman aşımına uğradı.")
        except PlaywrightError as exc:
            if "Executable doesn't exist" in str(exc):
                errors.append(
                    "Chromium kurulu değil. 'python -m playwright install chromium' komutunu çalıştırın."
                )
            else:
                errors.append(f"Playwright tarayıcı hatası: {self._short_error(exc)}")
        except Exception as exc:  # Dış sitenin beklenmeyen yanıtları API'yi düşürmemeli.
            errors.append(f"Yargıtay araması sırasında beklenmeyen hata: {self._short_error(exc)}")

        skipped_due_to_rate_limit = skipped_due_to_rate_limit or self._has_rate_limit_error(errors)
        return self._build_search_response(
            results=results,
            errors=errors,
            attempted_queries=attempted_queries,
            skipped_due_to_rate_limit=skipped_due_to_rate_limit,
            raw_live_result_count=raw_live_result_count,
            official_yargitay_reached=official_yargitay_reached,
        )

    async def _search_one_query(
        self,
        *,
        page: Page,
        context: BrowserContext,
        query: str,
        max_results: int,
        results: list[YargitayDecision],
        errors: list[str],
        seen_detail_urls: set[str],
        metrics: dict[str, int],
    ) -> bool:
        try:
            logger.info("yargitay_query_raw=%s", query)
            search_input = page.locator(SEARCH_INPUT_SELECTOR)
            search_button = page.locator(SEARCH_BUTTON_SELECTOR)
            await search_input.fill(query)

            async with page.expect_response(
                lambda candidate: LIST_RESPONSE_FRAGMENT in candidate.url,
                timeout=QUERY_TIMEOUT_MS,
            ) as response_info:
                await search_button.click()

            list_response = await response_info.value
            await self._consume_result_pages(
                page=page,
                context=context,
                query=query,
                first_response=list_response,
                max_results=max_results,
                results=results,
                errors=errors,
                seen_detail_urls=seen_detail_urls,
                metrics=metrics,
            )
            return True

        except YargitayAccessBlocked as exc:
            self._append_error(errors, str(exc))
            return False
        except PlaywrightTimeoutError:
            if await self._captcha_is_active(page):
                errors.append(f"'{query}' sorgusunda CAPTCHA doğrulaması istendi.")
            else:
                site_error = await self._visible_site_error(page)
                suffix = f" Site mesajı: {site_error}" if site_error else ""
                errors.append(f"'{query}' sorgusu zaman aşımına uğradı.{suffix}")
            return True
        except PlaywrightError as exc:
            errors.append(f"'{query}' sorgusunda tarayıcı hatası: {self._short_error(exc)}")
            return True
        except Exception as exc:
            errors.append(f"'{query}' sorgusu işlenemedi: {self._short_error(exc)}")
            return True

    async def _consume_result_pages(
        self,
        *,
        page: Page,
        context: BrowserContext,
        query: str,
        first_response: Response,
        max_results: int,
        results: list[YargitayDecision],
        errors: list[str],
        seen_detail_urls: set[str],
        metrics: dict[str, int],
    ) -> None:
        current_response = first_response
        examined_for_query = 0

        while len(results) < max_results:
            records, total = await self._read_listing(current_response, query, errors)
            if records is None:
                return
            if not records:
                if examined_for_query == 0:
                    errors.append(f"'{query}' sorgusu için sonuç bulunamadı.")
                return

            metrics["raw_live_result_count"] = metrics.get("raw_live_result_count", 0) + len(records)
            examined_for_query += len(records)
            for record in records:
                if len(results) >= max_results:
                    return

                detail_url = self._detail_url(record)
                if not detail_url or detail_url in seen_detail_urls:
                    continue

                decision = await self._build_decision(
                    context=context,
                    query=query,
                    record=record,
                    detail_url=detail_url,
                    errors=errors,
                )
                if decision is not None:
                    seen_detail_urls.add(decision.detail_url)
                    results.append(decision)

                if len(results) < max_results:
                    await self._polite_sleep(BETWEEN_DETAIL_DELAY_RANGE_SECONDS)

            if examined_for_query >= total or len(results) >= max_results:
                return

            await page.locator(RESULT_TABLE_SELECTOR).wait_for(state="visible", timeout=5_000)
            next_button = page.locator(NEXT_PAGE_SELECTOR)
            if await next_button.count() != 1:
                return

            try:
                async with page.expect_response(
                    lambda candidate: LIST_RESPONSE_FRAGMENT in candidate.url,
                    timeout=QUERY_TIMEOUT_MS,
                ) as response_info:
                    await next_button.click()
                current_response = await response_info.value
            except PlaywrightTimeoutError:
                errors.append(f"'{query}' sorgusunun sonraki sonuç sayfası yüklenemedi.")
                return

    async def _read_listing(
        self,
        response: Response,
        query: str,
        errors: list[str],
    ) -> tuple[list[dict[str, Any]] | None, int]:
        if response.status in {403, 429}:
            if response.status == 429:
                raise YargitayAccessBlocked(RATE_LIMIT_MESSAGE)
            reason = "hız sınırı" if response.status == 429 else "erişim engeli"
            raise YargitayAccessBlocked(
                f"Yargıtay sonuç servisi {reason} uyguladı (HTTP {response.status}); kalan istekler durduruldu."
            )
        if not response.ok:
            errors.append(f"'{query}' sorgusunda sonuç servisi HTTP {response.status} döndürdü.")
            return None, 0

        try:
            payload = await response.json()
        except Exception:
            errors.append(f"'{query}' sorgusunda sonuç servisi geçersiz JSON döndürdü.")
            return None, 0

        if self._payload_indicates_captcha(payload):
            errors.append(f"'{query}' sorgusunda CAPTCHA/erişim engeli bildirildi.")
            return None, 0

        metadata = payload.get("metadata") if isinstance(payload, dict) else None
        if isinstance(metadata, dict) and str(metadata.get("FMTY", "")).upper() == "ERROR":
            message = metadata.get("FMTE") or metadata.get("FMU") or "Bilinmeyen site hatası"
            errors.append(f"'{query}' sorgusunda Yargıtay sitesi hata döndürdü: {message}")
            return None, 0

        envelope = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(envelope, dict):
            errors.append(f"'{query}' sorgusunda beklenmeyen sonuç biçimi alındı.")
            return None, 0

        records = envelope.get("data") or []
        if not isinstance(records, list):
            errors.append(f"'{query}' sorgusundaki karar listesi okunamadı.")
            return None, 0

        total = envelope.get("recordsTotal")
        return [item for item in records if isinstance(item, dict)], int(total or len(records))

    async def _build_decision(
        self,
        *,
        context: BrowserContext,
        query: str,
        record: dict[str, Any],
        detail_url: str,
        errors: list[str],
    ) -> YargitayDecision | None:
        try:
            response = await context.request.get(detail_url, timeout=DETAIL_TIMEOUT_MS)
            if response.status in {403, 429}:
                if response.status == 429:
                    raise YargitayAccessBlocked(RATE_LIMIT_MESSAGE)
                reason = "hız sınırı" if response.status == 429 else "erişim engeli"
                raise YargitayAccessBlocked(
                    f"Yargıtay karar servisi {reason} uyguladı (HTTP {response.status}); "
                    "kalan istekler durduruldu."
                )
            if not response.ok:
                errors.append(f"Karar detayı alınamadı (HTTP {response.status}): {detail_url}")
                return None
            payload = await response.json()
        except PlaywrightTimeoutError:
            errors.append(f"Karar detayı zaman aşımına uğradı: {detail_url}")
            return None
        except YargitayAccessBlocked:
            raise
        except Exception as exc:
            errors.append(f"Karar detayı okunamadı ({detail_url}): {self._short_error(exc)}")
            return None

        if self._payload_indicates_captcha(payload):
            errors.append(f"Karar detayında CAPTCHA/erişim engeli bildirildi: {detail_url}")
            return None

        raw_text = payload.get("data", "") if isinstance(payload, dict) else ""
        if not isinstance(raw_text, str):
            raw_text = str(raw_text or "")
        raw_text = self.cleaner.repair_mojibake(raw_text)

        cleaned = self.cleaner.clean(raw_text)
        if "insufficient_text" in cleaned.warnings:
            errors.append(f"insufficient_text: {detail_url}")

        court = str(record.get("daire") or "Bilinmeyen Daire").strip()
        esas_no = str(record.get("esasNo") or "").strip()
        karar_no = str(record.get("kararNo") or "").strip()
        date = str(record.get("kararTarihi") or "").strip()
        title = f"{court} E. {esas_no}, K. {karar_no}".strip()

        return YargitayDecision(
            query=query,
            court=court,
            esas_no=esas_no,
            karar_no=karar_no,
            date=date,
            title=title,
            detail_url=detail_url,
            raw_text=raw_text,
            clean_text=cleaned.clean_text,
        )

    @staticmethod
    def _detail_url(record: dict[str, Any]) -> str:
        document_id = str(record.get("id") or "").strip()
        if not document_id:
            return ""
        return urljoin(BASE_URL, DETAIL_PATH.format(document_id=quote(document_id)))

    @staticmethod
    async def _captcha_is_active(page: Page) -> bool:
        state = page.locator(CAPTCHA_STATE_SELECTOR)
        if await state.count() == 1:
            marker = (await state.text_content() or "").strip().casefold()
            if marker == "true":
                return True

        captcha = page.locator(CAPTCHA_VISIBLE_SELECTOR)
        for index in range(await captcha.count()):
            if await captcha.nth(index).is_visible():
                return True
        return False

    @staticmethod
    async def _access_is_blocked(page: Page) -> bool:
        title = (await page.title()).casefold()
        return any(marker in title for marker in ("access denied", "forbidden", "erişim engellendi"))

    @staticmethod
    async def _visible_site_error(page: Page) -> str:
        locator = page.locator(SITE_ERROR_SELECTOR)
        messages: list[str] = []
        for index in range(await locator.count()):
            item = locator.nth(index)
            if await item.is_visible():
                text = " ".join((await item.inner_text()).split())
                if text:
                    messages.append(text)
        return " | ".join(messages[:2])

    @staticmethod
    def _payload_indicates_captcha(payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        status = str(payload.get("status") or "").casefold()
        detail = str(payload.get("detailMessage") or "").casefold()
        combined = f"{status} {detail}"
        return any(marker in combined for marker in ("captcha", "displaycaptcha", "access denied", "forbidden"))

    @staticmethod
    def _short_error(error: Exception) -> str:
        message = " ".join(str(error).split())
        return message[:300] or error.__class__.__name__

    @staticmethod
    async def _polite_sleep(delay_range: tuple[float, float]) -> None:
        await asyncio.sleep(random.uniform(*delay_range))

    @staticmethod
    def _append_error(errors: list[str], message: str) -> None:
        if message and message not in errors:
            errors.append(message)

    @staticmethod
    def _has_rate_limit_error(errors: list[str]) -> bool:
        markers = ("hız sınırı", "rate limit", "http 429")
        return any(any(marker in error.casefold() for marker in markers) for error in errors)

    @staticmethod
    def _build_search_response(
        *,
        results: list[YargitayDecision],
        errors: list[str],
        attempted_queries: list[str],
        skipped_due_to_rate_limit: bool,
        raw_live_result_count: int,
        official_yargitay_reached: bool,
    ) -> YargitaySearchResponse:
        parsed_live_result_count = len(results)
        return YargitaySearchResponse(
            results=results,
            errors=errors,
            attempted_queries=attempted_queries,
            skipped_due_to_rate_limit=skipped_due_to_rate_limit,
            raw_live_result_count=raw_live_result_count,
            parsed_live_result_count=parsed_live_result_count,
            final_live_result_count=parsed_live_result_count,
            official_yargitay_reached=official_yargitay_reached,
            official_yargitay_returned_results=raw_live_result_count > 0,
            failure_reason=YargitayScraper._failure_reason(
                errors=errors,
                raw_live_result_count=raw_live_result_count,
                parsed_live_result_count=parsed_live_result_count,
                official_yargitay_reached=official_yargitay_reached,
            ),
        )

    @staticmethod
    def _failure_reason(
        *,
        errors: list[str],
        raw_live_result_count: int,
        parsed_live_result_count: int,
        official_yargitay_reached: bool,
    ) -> str:
        combined = " ".join(errors).casefold()
        if "runtime exception" in combined or "hata oluştu" in combined:
            return "runtime_exception"
        if "zaman aşımı" in combined or "timeout" in combined:
            return "timeout"
        if "hız sınırı" in combined or "rate limit" in combined or "http 429" in combined:
            return "rate_limited"
        if "erişilemedi" in combined or "network" in combined or "connection" in combined:
            return "network_error"
        if raw_live_result_count > 0 and parsed_live_result_count == 0:
            if any(marker in combined for marker in ("beklenmeyen sonuç biçimi", "karar listesi okunamadı", "geçersiz json")):
                return "selector_changed"
            return "parser_failed"
        if official_yargitay_reached and raw_live_result_count == 0:
            return "no_results"
        if errors:
            return "unknown"
        return ""


yargitay_scraper = YargitayScraper()
