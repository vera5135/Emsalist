"""P2.6D secure browser-only candidate discovery.

Browser output is deliberately identifier-only and untrusted. It can never
carry canonical bytes, DOM text, response bodies, or verification evidence.
"""
from __future__ import annotations

import asyncio
import inspect
import ipaddress
import os
import re
from contextlib import suppress
from dataclasses import dataclass
from typing import Mapping, Protocol
from urllib.parse import urlparse

from app.services.source_fetcher import (
    ALLOWED_DOMAINS,
    SourceFetchError,
    default_resolver,
    url_matches_allowed_domains,
    validate_destination,
)
from app.services.source_providers.base import (
    ERR_ACCESS_DENIED,
    ERR_BROWSER_DISCOVERY_UNAVAILABLE,
    ERR_CHALLENGE,
    ERR_FETCH_FAILED,
    ERR_RATE_LIMITED,
    ERR_SSRF_BLOCKED,
    ERR_STRUCTURE_CHANGED,
    ProviderDiscoveryCandidate,
    ProviderError,
)

MAX_BROWSER_CANDIDATES = 100
MAX_CANDIDATE_ID_LENGTH = 128
_CANDIDATE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_PROXY_ENV_KEYS = frozenset({
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
})
_BLOCKED_HOSTS = frozenset({"localhost", "metadata", "metadata.google.internal"})
_CHALLENGE_MARKERS = (
    "captcha", "robot olmadığınızı", "güvenlik kodu", "doğrulama kodu",
)
_ACCESS_DENIED_MARKERS = (
    "access denied", "erişim engellendi", "yetkisiz erişim", "forbidden",
)


@dataclass(frozen=True)
class BrowserDiscoveryStrategy:
    provider_code: str
    surface_code: str
    origin: str
    allowed_hosts: tuple[str, ...]
    input_selector: str = ""
    submit_selector: str = ""
    submit_text: str = ""
    response_method: str = ""
    response_path: str = ""
    candidate_id_field: str = "id"
    bank_kind: str = ""
    live_supported: bool = False
    navigation_paths: tuple[str, ...] = ("/",)
    static_path_prefixes: tuple[str, ...] = ()
    detail_path_markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class BrowserDiscoveryResult:
    surface_code: str
    candidate_ids: tuple[str, ...]
    next_cursor: str | None = None
    exhausted: bool = True
    detail_download_count: int = 0


class BrowserDiscoveryBackend(Protocol):
    async def discover(
        self,
        strategy: BrowserDiscoveryStrategy,
        *,
        query: str | None,
        cursor: str | None,
        limit: int,
    ) -> BrowserDiscoveryResult: ...

    async def close(self) -> None: ...


_STRATEGIES: dict[str, tuple[BrowserDiscoveryStrategy, ...]] = {
    "yargitay": (
        BrowserDiscoveryStrategy(
            provider_code="yargitay",
            surface_code="yargitay_search",
            origin="https://karararama.yargitay.gov.tr/",
            allowed_hosts=("karararama.yargitay.gov.tr",),
            live_supported=False,
            detail_path_markers=("/getdokuman",),
        ),
    ),
    "danistay": (
        BrowserDiscoveryStrategy(
            provider_code="danistay",
            surface_code="danistay_search",
            origin="https://karararama.danistay.gov.tr/",
            allowed_hosts=("karararama.danistay.gov.tr",),
            input_selector="#andKelime",
            live_supported=False,
            detail_path_markers=("/getdokuman",),
        ),
    ),
    "aym": (
        BrowserDiscoveryStrategy(
            provider_code="aym",
            surface_code="aym_norm",
            bank_kind="norm",
            origin="https://normkararlarbilgibankasi.anayasa.gov.tr/",
            allowed_hosts=("normkararlarbilgibankasi.anayasa.gov.tr",),
            input_selector="#query",
            submit_selector="button",
            submit_text="Ara",
            response_method="POST",
            response_path="/api/core/public/search",
            live_supported=False,
            navigation_paths=("/", "/kbb", "/kbb/"),
            static_path_prefixes=("/kbb/",),
            detail_path_markers=("/bb", "/detail", "/document", "/download"),
        ),
        BrowserDiscoveryStrategy(
            provider_code="aym",
            surface_code="aym_individual",
            bank_kind="individual",
            origin="https://kararlarbilgibankasi.anayasa.gov.tr/",
            allowed_hosts=("kararlarbilgibankasi.anayasa.gov.tr",),
            input_selector="#query",
            submit_selector="button",
            submit_text="Ara",
            response_method="POST",
            response_path="/api/core/public/search",
            live_supported=True,
            navigation_paths=("/", "/kbb", "/kbb/"),
            static_path_prefixes=("/kbb/",),
            detail_path_markers=("/bb", "/detail", "/document", "/download"),
        ),
    ),
    "uyusmazlik": (
        BrowserDiscoveryStrategy(
            provider_code="uyusmazlik",
            surface_code="uyusmazlik_search",
            origin="https://kararlar.uyusmazlik.gov.tr/",
            allowed_hosts=("kararlar.uyusmazlik.gov.tr",),
            input_selector="#txtSearch",
            submit_selector="#btnSearch",
            response_method="POST",
            response_path="/",
            live_supported=False,
            detail_path_markers=("/getdokuman", "/download", "/document"),
        ),
    ),
}


def strategy_provider_codes() -> tuple[str, ...]:
    return tuple(_STRATEGIES)


def get_browser_strategies(provider_code: str) -> tuple[BrowserDiscoveryStrategy, ...]:
    return _STRATEGIES.get(provider_code, ())


def browser_strategy_available(provider_code: str) -> bool:
    return any(strategy.live_supported for strategy in get_browser_strategies(provider_code))


def browser_process_environment(
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    source = os.environ if environ is None else environ
    return {key: value for key, value in source.items() if key not in _PROXY_ENV_KEYS}


def validate_candidate_identifier(candidate_id: object) -> str:
    if not isinstance(candidate_id, str):
        raise ProviderError(ERR_STRUCTURE_CHANGED, "browser_candidate_id_invalid")
    value = candidate_id.strip()
    if (
        not value
        or value != candidate_id
        or len(value) > MAX_CANDIDATE_ID_LENGTH
        or not _CANDIDATE_ID_RE.fullmatch(value)
    ):
        raise ProviderError(ERR_STRUCTURE_CHANGED, "browser_candidate_id_invalid")
    return value


def _host_is_intrinsically_unsafe(host: str) -> bool:
    normalized = host.lower().rstrip(".")
    if not normalized or normalized in _BLOCKED_HOSTS:
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return bool(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )


def browser_request_allowed(
    strategy: BrowserDiscoveryStrategy,
    url: str,
    *,
    resource_type: str = "",
    method: str = "GET",
) -> bool:
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except (TypeError, ValueError):
        return False
    if (
        parsed.scheme != "https"
        or port not in (None, 443)
        or parsed.username
        or parsed.password
    ):
        return False
    if resource_type.lower() == "websocket" or _host_is_intrinsically_unsafe(host):
        return False
    if host not in {item.lower().rstrip(".") for item in strategy.allowed_hosts}:
        return False
    path = parsed.path or "/"
    lowered_path = path.lower()
    if any(marker.lower() in lowered_path for marker in strategy.detail_path_markers):
        return False
    kind = resource_type.lower() or "document"
    if kind == "document":
        return method.upper() == "GET" and path in strategy.navigation_paths
    if kind in {"xhr", "fetch"}:
        return (
            method.upper() == strategy.response_method
            and path == strategy.response_path
        )
    static_suffixes = {
        "script": (".js", ".mjs"),
        "stylesheet": (".css",),
        "image": (".avif", ".gif", ".ico", ".jpeg", ".jpg", ".png", ".svg", ".webp"),
        "font": (".eot", ".otf", ".ttf", ".woff", ".woff2"),
    }
    suffixes = static_suffixes.get(kind)
    return bool(
        method.upper() == "GET"
        and suffixes
        and lowered_path.endswith(suffixes)
        and any(path.startswith(prefix) for prefix in strategy.static_path_prefixes)
    )


def validate_strategy_contract(strategy: BrowserDiscoveryStrategy, provider) -> None:
    if strategy.provider_code != provider.provider_code:
        raise ProviderError(ERR_SSRF_BLOCKED, "browser_strategy_provider_mismatch")
    if not strategy.allowed_hosts:
        raise ProviderError(ERR_SSRF_BLOCKED, "browser_strategy_host_scope_invalid")
    if not url_matches_allowed_domains(strategy.origin, ALLOWED_DOMAINS):
        raise ProviderError(ERR_SSRF_BLOCKED, "browser_strategy_origin_invalid")
    if not provider.is_official_url(strategy.origin):
        raise ProviderError(ERR_SSRF_BLOCKED, "browser_strategy_origin_invalid")
    origin_host = (urlparse(strategy.origin).hostname or "").lower().rstrip(".")
    if origin_host not in {host.lower().rstrip(".") for host in strategy.allowed_hosts}:
        raise ProviderError(ERR_SSRF_BLOCKED, "browser_strategy_host_scope_invalid")
    for host in strategy.allowed_hosts:
        if _host_is_intrinsically_unsafe(host):
            raise ProviderError(ERR_SSRF_BLOCKED, "browser_strategy_host_scope_invalid")
        if not url_matches_allowed_domains(f"https://{host}/", provider.official_domains):
            raise ProviderError(ERR_SSRF_BLOCKED, "browser_strategy_host_scope_invalid")


def _require_registered_strategy(strategy: BrowserDiscoveryStrategy) -> None:
    if strategy not in get_browser_strategies(strategy.provider_code):
        raise ProviderError(ERR_SSRF_BLOCKED, "browser_strategy_not_registered")


def validate_browser_response_status(status: int) -> None:
    if status in {401, 403}:
        raise ProviderError(ERR_ACCESS_DENIED, "browser_access_denied")
    if status == 429:
        raise ProviderError(ERR_RATE_LIMITED, "browser_rate_limited")
    if status >= 500:
        raise ProviderError(ERR_FETCH_FAILED, "browser_http_error", retryable=True)
    if status < 200 or status >= 300:
        raise ProviderError(ERR_FETCH_FAILED, "browser_http_error")


def extract_listing_candidate_ids(
    payload: object,
    strategy: BrowserDiscoveryStrategy,
    *,
    limit: int,
) -> tuple[str, ...]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ProviderError(ERR_STRUCTURE_CHANGED, "browser_listing_shape_changed")
    page_number = payload.get("page")
    page_size = payload.get("page_size")
    total = payload.get("total")
    if (
        not isinstance(page_number, int)
        or page_number != 1
        or not isinstance(page_size, int)
        or page_size < 1
        or not isinstance(total, int)
        or total < 0
        or total > len(payload["data"])
    ):
        raise ProviderError(ERR_STRUCTURE_CHANGED, "browser_pagination_not_supported")
    candidate_ids: list[str] = []
    for item in payload["data"][:max(1, min(limit, MAX_BROWSER_CANDIDATES))]:
        if not isinstance(item, dict):
            raise ProviderError(ERR_STRUCTURE_CHANGED, "browser_listing_shape_changed")
        candidate_ids.append(validate_candidate_identifier(
            item.get(strategy.candidate_id_field),
        ))
    return tuple(candidate_ids)


async def discover_browser_candidates(
    provider,
    backend: BrowserDiscoveryBackend,
    *,
    query: str | None,
    cursor: str | None,
    limit: int,
) -> list[ProviderDiscoveryCandidate]:
    registered = get_browser_strategies(provider.provider_code)
    availability = getattr(backend, "strategy_available", None)
    strategies = tuple(
        strategy for strategy in registered
        if not callable(availability) or availability(strategy)
    )
    if not strategies:
        raise ProviderError(ERR_BROWSER_DISCOVERY_UNAVAILABLE, "browser_strategy_unavailable")
    bounded_limit = max(1, min(int(limit), MAX_BROWSER_CANDIDATES))
    candidates: list[ProviderDiscoveryCandidate] = []
    seen_ids: set[str] = set()
    for strategy in strategies:
        validate_strategy_contract(strategy, provider)
        remaining = bounded_limit - len(candidates)
        if remaining <= 0:
            break
        result = await backend.discover(
            strategy,
            query=query,
            cursor=cursor,
            limit=remaining,
        )
        if result.surface_code != strategy.surface_code:
            raise ProviderError(ERR_STRUCTURE_CHANGED, "browser_surface_mismatch")
        if result.detail_download_count:
            raise ProviderError(ERR_STRUCTURE_CHANGED, "browser_detail_download_attempted")
        for raw_candidate_id in result.candidate_ids[:remaining]:
            candidate_id = validate_candidate_identifier(raw_candidate_id)
            if candidate_id in seen_ids:
                continue
            seen_ids.add(candidate_id)
            candidate = provider.build_exact_candidate(candidate_id)
            candidate.source_type = provider.source_types[0]
            candidate.discovered_metadata = {
                "browser_surface": strategy.surface_code,
                "bank_kind": strategy.bank_kind,
            }
            candidates.append(candidate)
    return candidates


class PlaywrightBrowserDiscoveryBackend:
    """Headless, ephemeral, provider-scoped Playwright discovery backend."""

    def __init__(self, *, resolver=default_resolver):
        self._resolver = resolver
        self._closed = False

    @staticmethod
    def strategy_available(strategy: BrowserDiscoveryStrategy) -> bool:
        return strategy.live_supported

    async def discover(
        self,
        strategy: BrowserDiscoveryStrategy,
        *,
        query: str | None,
        cursor: str | None,
        limit: int,
    ) -> BrowserDiscoveryResult:
        if self._closed:
            raise ProviderError(ERR_BROWSER_DISCOVERY_UNAVAILABLE, "browser_backend_closed")
        _require_registered_strategy(strategy)
        if not strategy.live_supported:
            raise ProviderError(ERR_STRUCTURE_CHANGED, "browser_inventory_contract_unavailable")
        if cursor not in (None, "", "1"):
            raise ProviderError(ERR_STRUCTURE_CHANGED, "browser_pagination_not_validated")

        from app.services.source_providers import registry

        provider = registry.get_definition(strategy.provider_code)
        validate_strategy_contract(strategy, provider)
        try:
            destination = validate_destination(
                strategy.origin,
                resolver=self._resolver,
                allowed_domains=provider.official_domains,
            )
        except SourceFetchError as exc:
            raise ProviderError(ERR_SSRF_BLOCKED, exc.code) from exc

        try:
            from playwright.async_api import (
                Error as PlaywrightError,
                TimeoutError as PlaywrightTimeoutError,
                async_playwright,
            )
        except Exception:
            raise ProviderError(
                ERR_BROWSER_DISCOVERY_UNAVAILABLE, "browser_runtime_unavailable",
            ) from None

        playwright = browser = context = page = None
        popup_tasks: list[asyncio.Task] = []
        detail_attempts = 0
        try:
            playwright = await async_playwright().start()
            host = destination.hostname.lower().rstrip(".")
            pinned_ip = destination.validated_ips[0]
            browser = await playwright.chromium.launch(
                headless=True,
                env=browser_process_environment(),
                args=[
                    "--no-proxy-server",
                    "--disable-background-networking",
                    "--disable-sync",
                    "--disable-extensions",
                    "--disable-component-update",
                    "--no-first-run",
                    f"--host-resolver-rules=MAP {host} {pinned_ip}, EXCLUDE localhost",
                ],
            )
            context = await browser.new_context(
                storage_state=None,
                accept_downloads=False,
                service_workers="block",
            )
            page = await context.new_page()

            async def route_request(route, request):
                nonlocal detail_attempts
                if request.is_navigation_request() and request.frame != page.main_frame:
                    await route.abort()
                    return
                if not browser_request_allowed(
                    strategy,
                    request.url,
                    resource_type=request.resource_type,
                    method=request.method,
                ):
                    path = (urlparse(request.url).path or "/").lower()
                    if any(marker.lower() in path for marker in strategy.detail_path_markers):
                        detail_attempts += 1
                    await route.abort()
                    return
                await route.continue_()

            await context.route("**/*", route_request)

            def close_popup(popup):
                popup_tasks.append(asyncio.create_task(popup.close()))

            page.on("popup", close_popup)
            await page.goto(strategy.origin, wait_until="domcontentloaded", timeout=30_000)
            loaded = urlparse(page.url)
            if (
                loaded.scheme != "https"
                or (loaded.hostname or "").lower().rstrip(".")
                not in {item.lower().rstrip(".") for item in strategy.allowed_hosts}
            ):
                raise ProviderError(ERR_SSRF_BLOCKED, "browser_navigation_scope_changed")
            await self._raise_for_page_markers(page)

            query_input = page.locator(strategy.input_selector).first
            if await query_input.count() != 1:
                raise ProviderError(ERR_STRUCTURE_CHANGED, "browser_search_input_missing")
            await query_input.fill(query or "")
            submit = page.locator(strategy.submit_selector)
            if strategy.submit_text:
                submit = submit.filter(has_text=strategy.submit_text)
            submit = submit.first
            if await submit.count() != 1:
                raise ProviderError(ERR_STRUCTURE_CHANGED, "browser_search_submit_missing")

            def is_listing_response(response) -> bool:
                parsed = urlparse(response.url)
                return (
                    parsed.scheme == "https"
                    and parsed.port in (None, 443)
                    and response.request.method.upper() == strategy.response_method
                    and parsed.path == strategy.response_path
                    and (parsed.hostname or "").lower().rstrip(".")
                    in {host.lower().rstrip(".") for host in strategy.allowed_hosts}
                )

            async with page.expect_response(is_listing_response, timeout=30_000) as response_info:
                await submit.click()
            response = await response_info.value
            validate_browser_response_status(response.status)
            payload = await response.json()
            await self._raise_for_page_markers(page)
            if detail_attempts:
                raise ProviderError(ERR_STRUCTURE_CHANGED, "browser_detail_download_attempted")
            candidate_ids = extract_listing_candidate_ids(
                payload, strategy, limit=limit,
            )
            return BrowserDiscoveryResult(
                surface_code=strategy.surface_code,
                candidate_ids=candidate_ids,
                exhausted=True,
                detail_download_count=detail_attempts,
            )
        except ProviderError:
            raise
        except PlaywrightTimeoutError:
            raise ProviderError(
                ERR_FETCH_FAILED, "browser_timeout", retryable=True,
            ) from None
        except PlaywrightError:
            raise ProviderError(
                ERR_FETCH_FAILED, "browser_network_error", retryable=True,
            ) from None
        except Exception:
            raise ProviderError(ERR_STRUCTURE_CHANGED, "browser_surface_changed") from None
        finally:
            if popup_tasks:
                await asyncio.gather(*popup_tasks, return_exceptions=True)
            for resource in (page, context, browser):
                close = getattr(resource, "close", None)
                if callable(close):
                    with suppress(Exception):
                        result = close()
                        if inspect.isawaitable(result):
                            await result
            stop = getattr(playwright, "stop", None)
            if callable(stop):
                with suppress(Exception):
                    result = stop()
                    if inspect.isawaitable(result):
                        await result

    @staticmethod
    async def _raise_for_page_markers(page) -> None:
        text = (await page.locator("body").inner_text(timeout=5_000)).lower()
        if any(marker in text for marker in _CHALLENGE_MARKERS):
            raise ProviderError(ERR_CHALLENGE, "browser_challenge_detected")
        if any(marker in text for marker in _ACCESS_DENIED_MARKERS):
            raise ProviderError(ERR_ACCESS_DENIED, "browser_access_denied")

    async def close(self) -> None:
        self._closed = True


def create_browser_discovery_backend() -> PlaywrightBrowserDiscoveryBackend:
    return PlaywrightBrowserDiscoveryBackend()
