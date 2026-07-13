"""Operator-only bounded live smoke for non-browser official providers.

This is an observation harness, not an ingestion engine. It performs at most
one discovery result and one detail fetch per eligible enabled provider. Every
network operation goes through the existing provider/source_fetcher seam and
shared retry executor. No canonical database writes are performed.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable, Mapping
from urllib.parse import urlparse

from app.services.provider_ingestion_service import _execute_provider_network_operation
from app.services.source_fetcher import ALLOWED_CONTENT_TYPES
from app.services.source_providers import registry
from app.services.source_providers.base import (
    ERR_ACCESS_DENIED,
    ERR_CHALLENGE,
    ERR_FETCH_FAILED,
    ERR_MANUAL_REVIEW_REQUIRED,
    ERR_RATE_LIMITED,
    ERR_SSRF_BLOCKED,
    ERR_STRUCTURE_CHANGED,
    ERR_TRANSPORT_UNAVAILABLE,
    ProviderError,
)

HARNESS_VERSION = "p2.6c-live-smoke-1"
LIVE_SMOKE_ENV = "OFFICIAL_PROVIDER_LIVE_SMOKE"
MAX_DISCOVERY_CANDIDATES = 1
MAX_DETAIL_FETCHES = 1
ERR_LIVE_SMOKE_NOT_AUTHORIZED = "live_smoke_not_authorized"
ERR_NO_ENABLED_ELIGIBLE_PROVIDER = "no_enabled_eligible_provider"

SMOKE_OUTCOMES = frozenset({
    "not_attempted",
    "not_eligible",
    "not_enabled",
    "discovery_success",
    "no_candidates",
    "detail_success",
    "ingestion_success",
    ERR_CHALLENGE,
    ERR_ACCESS_DENIED,
    ERR_RATE_LIMITED,
    ERR_STRUCTURE_CHANGED,
    ERR_TRANSPORT_UNAVAILABLE,
    ERR_FETCH_FAILED,
    ERR_MANUAL_REVIEW_REQUIRED,
})

_SAFE_ERROR_CODES = frozenset({
    "",
    ERR_CHALLENGE,
    ERR_ACCESS_DENIED,
    ERR_RATE_LIMITED,
    ERR_STRUCTURE_CHANGED,
    ERR_TRANSPORT_UNAVAILABLE,
    ERR_FETCH_FAILED,
    ERR_MANUAL_REVIEW_REQUIRED,
    ERR_SSRF_BLOCKED,
    "empty_legal_body",
    "missing_identifier",
    "parse_failed",
})

_REPO_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_PATH = _REPO_ROOT / "docs" / "p2" / "P2_6C_CONTROLLED_LIVE_SMOKE.md"


@dataclass(frozen=True)
class ProviderSmokeReport:
    provider_code: str
    eligible: bool
    attempted: bool
    discovery_outcome: str
    candidate_count: int
    detail_fetch_attempted: bool
    detail_fetch_outcome: str
    safe_error_code: str
    http_status: int | None
    content_type: str
    content_size_bytes: int
    final_host: str
    canonical_ingestion_attempted: bool
    canonical_ingestion_outcome: str
    verification_status: str


@dataclass(frozen=True)
class SmokeExecutionReport:
    executed_at_utc: str
    git_sha: str
    harness_version: str
    environment_guard_enabled: bool
    providers: tuple[ProviderSmokeReport, ...]


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes"}


def live_smoke_authorized(
    *,
    confirm_live_smoke: bool,
    environ: Mapping[str, str] | None = None,
) -> bool:
    env = os.environ if environ is None else environ
    return bool(confirm_live_smoke and _truthy(env.get(LIVE_SMOKE_ENV)))


def eligible_provider_codes() -> tuple[str, ...]:
    """Derive smoke eligibility solely from the closed provider registry."""
    return tuple(
        code
        for code in registry.all_provider_codes()
        if _provider_is_smoke_eligible(registry.get_definition(code))
    )


def _provider_is_smoke_eligible(provider) -> bool:
    caps = provider.capabilities
    return bool(caps.discovery and caps.fetch and not caps.requires_browser)


def _safe_final_host(final_url: str) -> str:
    try:
        host = (urlparse(final_url).hostname or "").lower().rstrip(".")
    except (TypeError, ValueError):
        return ""
    if not host or len(host) > 253 or any(ord(ch) < 33 for ch in host):
        return ""
    return host


def _safe_content_type(value: str) -> str:
    content_type = (value or "").split(";", 1)[0].strip().lower()
    return content_type if content_type in ALLOWED_CONTENT_TYPES else ""


def _safe_http_status(value: object) -> int | None:
    return value if isinstance(value, int) and 100 <= value <= 599 else None


def _safe_error_code(value: object) -> str:
    return value if isinstance(value, str) and value in _SAFE_ERROR_CODES else ERR_FETCH_FAILED


def _safe_error_outcome(error: ProviderError) -> str:
    code = _safe_error_code(error.code)
    return code if code in SMOKE_OUTCOMES else ERR_FETCH_FAILED


def _base_report(
    provider_code: str,
    *,
    eligible: bool,
    attempted: bool,
    discovery_outcome: str,
    candidate_count: int = 0,
    detail_fetch_attempted: bool = False,
    detail_fetch_outcome: str = "not_attempted",
    safe_error_code: str = "",
    http_status: int | None = None,
    content_type: str = "",
    content_size_bytes: int = 0,
    final_host: str = "",
) -> ProviderSmokeReport:
    return ProviderSmokeReport(
        provider_code=provider_code,
        eligible=eligible,
        attempted=attempted,
        discovery_outcome=discovery_outcome,
        candidate_count=min(max(candidate_count, 0), MAX_DISCOVERY_CANDIDATES),
        detail_fetch_attempted=detail_fetch_attempted,
        detail_fetch_outcome=detail_fetch_outcome,
        safe_error_code=safe_error_code,
        http_status=http_status,
        content_type=content_type,
        content_size_bytes=max(content_size_bytes, 0),
        final_host=final_host,
        canonical_ingestion_attempted=False,
        canonical_ingestion_outcome="not_attempted",
        verification_status="",
    )


def _smoke_inputs(provider_code: str, execution_day: str) -> dict[str, str | None]:
    # Fixed neutral public inputs. They are never logged or included in reports.
    if provider_code == "resmi_gazete":
        return {"query": None, "from_date": execution_day, "to_date": execution_day}
    return {"query": "hukuk", "from_date": None, "to_date": None}


async def _default_sleeper(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def run_controlled_live_smoke(
    *,
    transport,
    authorized: bool = False,
    resolver: Callable[[str], list[str]] | None = None,
    sleeper=None,
    now: datetime | None = None,
    git_sha: str,
) -> SmokeExecutionReport:
    """Execute one bounded dry smoke across registry-derived providers."""
    if not authorized:
        raise ProviderError(
            ERR_LIVE_SMOKE_NOT_AUTHORIZED,
            ERR_LIVE_SMOKE_NOT_AUTHORIZED,
        )
    if transport is None:
        raise ProviderError(ERR_TRANSPORT_UNAVAILABLE, ERR_TRANSPORT_UNAVAILABLE)
    executed_at = now or datetime.now(UTC)
    execution_day = executed_at.date().isoformat()
    sleep = sleeper or _default_sleeper
    reports: list[ProviderSmokeReport] = []

    for provider_code in registry.all_provider_codes():
        provider = registry.get_definition(provider_code)
        eligible = _provider_is_smoke_eligible(provider)
        if not eligible:
            reports.append(_base_report(
                provider_code,
                eligible=False,
                attempted=False,
                discovery_outcome="not_eligible",
            ))
            continue
        if not registry.is_enabled(provider_code):
            reports.append(_base_report(
                provider_code,
                eligible=True,
                attempted=False,
                discovery_outcome="not_enabled",
            ))
            continue

        inputs = _smoke_inputs(provider_code, execution_day)
        active_resolver = resolver or provider.default_resolver()
        try:
            page = await _execute_provider_network_operation(
                provider,
                operation="discover",
                sleeper=sleep,
                call=lambda: provider.discover(
                    query=inputs["query"],
                    cursor=None,
                    limit=MAX_DISCOVERY_CANDIDATES,
                    from_date=inputs["from_date"],
                    to_date=inputs["to_date"],
                    transport=transport,
                    resolver=active_resolver,
                ),
            )
        except ProviderError as error:
            reports.append(_base_report(
                provider_code,
                eligible=True,
                attempted=True,
                discovery_outcome=_safe_error_outcome(error),
                safe_error_code=_safe_error_code(error.code),
                http_status=_safe_http_status(error.http_status),
            ))
            continue
        except Exception:
            reports.append(_base_report(
                provider_code,
                eligible=True,
                attempted=True,
                discovery_outcome=ERR_FETCH_FAILED,
                safe_error_code=ERR_FETCH_FAILED,
            ))
            continue

        discovered_candidates = list(page.candidates[:MAX_DISCOVERY_CANDIDATES])
        if not discovered_candidates:
            reports.append(_base_report(
                provider_code,
                eligible=True,
                attempted=True,
                discovery_outcome="no_candidates",
            ))
            continue

        detail_candidates = discovered_candidates[:MAX_DETAIL_FETCHES]
        await sleep(provider.request_policy.min_interval_seconds)
        try:
            fetch_result = await _execute_provider_network_operation(
                provider,
                operation="fetch",
                sleeper=sleep,
                call=lambda: provider.fetch(
                    detail_candidates[0],
                    transport=transport,
                    resolver=active_resolver,
                ),
            )
        except ProviderError as error:
            reports.append(_base_report(
                provider_code,
                eligible=True,
                attempted=True,
                discovery_outcome="discovery_success",
                candidate_count=1,
                detail_fetch_attempted=True,
                detail_fetch_outcome=_safe_error_outcome(error),
                safe_error_code=_safe_error_code(error.code),
                http_status=_safe_http_status(error.http_status),
            ))
            continue
        except Exception:
            reports.append(_base_report(
                provider_code,
                eligible=True,
                attempted=True,
                discovery_outcome="discovery_success",
                candidate_count=1,
                detail_fetch_attempted=True,
                detail_fetch_outcome=ERR_FETCH_FAILED,
                safe_error_code=ERR_FETCH_FAILED,
            ))
            continue

        reports.append(_base_report(
            provider_code,
            eligible=True,
            attempted=True,
            discovery_outcome="discovery_success",
            candidate_count=1,
            detail_fetch_attempted=True,
            detail_fetch_outcome="detail_success",
            http_status=_safe_http_status(fetch_result.status_code),
            content_type=_safe_content_type(fetch_result.content_type),
            content_size_bytes=len(fetch_result.content),
            final_host=_safe_final_host(fetch_result.final_url),
        ))

    return SmokeExecutionReport(
        executed_at_utc=executed_at.astimezone(UTC).isoformat(),
        git_sha=git_sha,
        harness_version=HARNESS_VERSION,
        environment_guard_enabled=True,
        providers=tuple(reports),
    )


def render_evidence_document(report: SmokeExecutionReport) -> str:
    """Render only safe, structured smoke evidence."""
    eligible = ", ".join(p.provider_code for p in report.providers if p.eligible) or "none"
    rows = []
    for item in report.providers:
        rows.append(
            "| {provider} | {eligible} | {attempted} | {discovery} | {count} | "
            "{detail_attempted} | {detail} | {error} | {host} | {ctype} | {size} |".format(
                provider=item.provider_code,
                eligible=str(item.eligible).lower(),
                attempted=str(item.attempted).lower(),
                discovery=item.discovery_outcome,
                count=item.candidate_count,
                detail_attempted=str(item.detail_fetch_attempted).lower(),
                detail=item.detail_fetch_outcome,
                error=item.safe_error_code or "-",
                host=item.final_host or "-",
                ctype=item.content_type or "-",
                size=item.content_size_bytes,
            )
        )
    return "\n".join([
        "# P2.6C Controlled Non-Browser Live Smoke Evidence",
        "",
        f"- Execution UTC: `{report.executed_at_utc}`",
        f"- Exact git SHA: `{report.git_sha}`",
        f"- Harness version: `{report.harness_version}`",
        f"- Environment guard enabled: `{str(report.environment_guard_enabled).lower()}`",
        f"- Eligible provider codes: `{eligible}`",
        "- Mode: bounded discovery plus detail observation; no canonical ingestion or database writes",
        "",
        "| Provider | Eligible | Attempted | Discovery outcome | Candidates | Detail attempted | Detail outcome | Safe error | Final host | Content type | Content bytes |",
        "|---|---:|---:|---|---:|---:|---|---|---|---|---:|",
        *rows,
        "",
        "## Browser-deferred providers",
        "",
        "Yargıtay, Danıştay and AYM browser discovery remains deferred to P2.6D. "
        "They were not live-smoked in P2.6C. Uyuşmazlık was also excluded from "
        "this smoke because its current provider capability declares `requires_browser=True`.",
        "",
        "This evidence contains no raw query, external identifier, title, decision number, "
        "URL path/query, response body, headers, cookies, or raw exception message.",
        "",
    ])


def _write_evidence(report: SmokeExecutionReport) -> None:
    EVIDENCE_PATH.write_text(render_evidence_document(report), encoding="utf-8")


def _current_git_sha() -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    if status.stdout.strip():
        raise RuntimeError("live_smoke_requires_clean_worktree")
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    sha = completed.stdout.strip().lower()
    if len(sha) != 40 or any(ch not in "0123456789abcdef" for ch in sha):
        raise RuntimeError("git_sha_unavailable")
    return sha


def _real_transport_factory():
    from app.services.source_fetcher import create_real_transport

    return create_real_transport()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bounded operator-only smoke for non-browser official providers"
    )
    parser.add_argument(
        "--confirm-live-smoke",
        action="store_true",
        help="confirm the single bounded real-network smoke execution",
    )
    return parser


async def _run(
    args,
    *,
    environ: Mapping[str, str] | None = None,
    transport_factory=None,
    evidence_writer=None,
    git_sha_resolver=None,
    resolver=None,
    sleeper=None,
) -> int:
    if not live_smoke_authorized(
        confirm_live_smoke=args.confirm_live_smoke,
        environ=environ,
    ):
        print("live smoke blocked: dual_opt_in_required", file=sys.stderr)
        return 2

    factory = transport_factory or _real_transport_factory
    writer = evidence_writer or _write_evidence
    sha_resolver = git_sha_resolver or _current_git_sha
    transport = None
    try:
        try:
            git_sha = sha_resolver()
            transport = factory()
        except Exception:
            print(f"live smoke error: {ERR_TRANSPORT_UNAVAILABLE}", file=sys.stderr)
            return 1
        try:
            report = await run_controlled_live_smoke(
                transport=transport,
                authorized=True,
                resolver=resolver,
                sleeper=sleeper,
                git_sha=git_sha,
            )
            if not any(item.attempted for item in report.providers):
                print(
                    f"live smoke error: {ERR_NO_ENABLED_ELIGIBLE_PROVIDER}",
                    file=sys.stderr,
                )
                return 1
            writer(report)
        except Exception:
            print(f"live smoke error: {ERR_FETCH_FAILED}", file=sys.stderr)
            return 1
        print(json.dumps(asdict(report), ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        close = getattr(transport, "close", None)
        if callable(close):
            close()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
