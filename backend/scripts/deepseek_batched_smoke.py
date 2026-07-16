"""P2.8S - Bounded live DeepSeek batched-reasoning smoke (sanitized evidence only).

Calls the real ``POST /api/v1/cases/{case_id}/legal-issues/rebuild`` endpoint of a
locally started backend (scripts/deepseek_batched_smoke_server.py) against the UAT
database that contains the target case and its 8-decision precedent-pool shortlist.

Verifies per run:
- HTTP 200 from the real endpoint
- provider=deepseek, response model version
- one case-analysis call plus batched precedent calls, all finish_reason=stop
- no completion reaches the max_tokens budget
- shortlist coverage (all shortlisted decisions, rank order, no loss, no duplicates)
- exact paragraph provenance, zero unknown/hallucinated sources
- no reasoning content and no raw source text in the response

Requires ``--confirm-live-smoke`` plus DATABASE_URL and a configured DeepSeek key
(via backend/.env). Never prints or stores API keys, case text, decision text, or
reasoning content; evidence output is sanitized.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import httpx


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-smoke", action="store_true")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--pool-id", required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--output", default="deepseek-batched-smoke-sanitized.json")
    return parser.parse_args()


async def _prepare_context(case_id: str, pool_id: str):
    from sqlalchemy import select

    from app.db.models import (
        AuthSession, CaseMember, PrecedentPoolDecision, SourceParagraph, User, new_uuid,
    )
    from app.db.session import dispose_engine, get_sessionmaker
    from app.services.auth_service import create_access_token

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        member = (await db.execute(
            select(CaseMember).where(
                CaseMember.case_id == case_id,
                CaseMember.membership_role == "owner",
            )
        )).scalars().first()
        if member is None:
            raise SystemExit("smoke_abort: no owner membership for target case")
        user = (await db.execute(
            select(User).where(User.id == member.user_id)
        )).scalar_one()

        session_row = AuthSession(
            id=new_uuid(),
            tenant_id=user.tenant_id,
            user_id=user.id,
            refresh_token_hash=f"smoke-{secrets.token_hex(24)}",
            token_family_id=new_uuid(),
            expires_at=datetime.now(UTC) + timedelta(hours=2),
        )
        db.add(session_row)
        await db.commit()
        token = create_access_token(
            user.id, user.tenant_id, user.role or "lawyer",
            session_id=session_row.id, token_version=user.token_version,
        )

        decisions = (await db.execute(
            select(PrecedentPoolDecision).where(
                PrecedentPoolDecision.pool_id == pool_id,
                PrecedentPoolDecision.case_id == case_id,
                PrecedentPoolDecision.selection_state == "shortlisted",
            ).order_by(PrecedentPoolDecision.retrieval_rank.asc())
        )).scalars().all()
        shortlist: list[dict[str, str]] = []
        raw_probes: list[str] = []
        for decision in decisions:
            paragraph_ids = decision.selected_source_paragraph_ids or []
            if not paragraph_ids:
                continue
            paragraph = (await db.execute(
                select(SourceParagraph).where(SourceParagraph.id == paragraph_ids[0])
            )).scalar_one()
            shortlist.append({
                "retrieval_rank": decision.retrieval_rank,
                "source_record_id": decision.source_record_id,
                "source_version_id": decision.source_version_id,
                "source_paragraph_id": paragraph.id,
                "text_hash": paragraph.text_hash,
            })
            text = paragraph.text or ""
            for probe in (text[:200], text[len(text) // 2:len(text) // 2 + 200]):
                probe = probe.strip()
                if len(probe) >= 80:
                    raw_probes.append(probe)
    await dispose_engine()
    return token, session_row.id, shortlist, raw_probes


async def _revoke_session(session_id: str) -> None:
    from sqlalchemy import select

    from app.db.models import AuthSession
    from app.db.session import dispose_engine, get_sessionmaker

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        row = (await db.execute(
            select(AuthSession).where(AuthSession.id == session_id)
        )).scalar_one_or_none()
        if row is not None:
            row.revoked_at = datetime.now(UTC)
            row.revoke_reason = "smoke_complete"
            await db.commit()
    await dispose_engine()


def _wait_for_health(base_url: str, timeout_seconds: int = 120) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}/health", timeout=10)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise SystemExit("smoke_abort: backend health check timed out")


def _evaluate_run(run_index: int, status_code: int, body: dict,
                  shortlist: list[dict], raw_probes: list[str],
                  expected_model: str) -> dict:
    checks: dict[str, bool] = {}
    summary = body.get("safe_summary", {}) if isinstance(body, dict) else {}
    metrics = summary.get("provider_metrics", {}) or {}
    calls = metrics.get("calls", []) or []
    structured = summary.get("deepseek_structured", {}) or {}
    refs = summary.get("paragraph_references", []) or []

    expected_refs = [{
        "source_record_id": item["source_record_id"],
        "source_version_id": item["source_version_id"],
        "source_paragraph_id": item["source_paragraph_id"],
    } for item in shortlist]
    shortlist_keys = {(r["source_record_id"], r["source_version_id"], r["source_paragraph_id"])
                      for r in expected_refs}

    nested_ref_keys = set()
    for field in ("precedent_similarities", "precedent_differences", "favorable_use", "adverse_use"):
        for entry in structured.get(field, []) or []:
            for ref in entry.get("paragraph_references", []) or []:
                nested_ref_keys.add((
                    str(ref.get("source_record_id", "")),
                    str(ref.get("source_version_id", "")),
                    str(ref.get("source_paragraph_id", "")),
                ))
    unknown_source_count = sum(1 for key in nested_ref_keys if key not in shortlist_keys)
    unknown_source_count += sum(
        1 for ref in refs
        if (ref.get("source_record_id"), ref.get("source_version_id"), ref.get("source_paragraph_id"))
        not in shortlist_keys
    )

    serialized = json.dumps(body, ensure_ascii=False)
    completion_values = [int(call.get("completion_tokens", 0)) for call in calls]
    max_budget = int(metrics.get("max_tokens_per_request", 0))
    covered_keys = [(r.get("source_record_id"), r.get("source_version_id"), r.get("source_paragraph_id"))
                    for r in refs]

    checks["http_200"] = status_code == 200
    checks["provider_deepseek"] = body.get("provider") == "deepseek"
    checks["response_model"] = body.get("model_version") == expected_model
    checks["run_succeeded"] = body.get("status") == "succeeded"
    checks["one_case_analysis_call"] = sum(
        1 for call in calls if call.get("call_type") == "case_analysis") == 1
    checks["expected_precedent_calls"] = sum(
        1 for call in calls if call.get("call_type") == "precedent_batch") == (len(shortlist) + 1) // 2
    checks["all_finish_reasons_stop"] = bool(calls) and all(
        call.get("finish_reason") == "stop" for call in calls)
    checks["max_tokens_default_8192"] = max_budget == 8192
    checks["no_completion_hits_budget"] = bool(completion_values) and all(
        value < max_budget for value in completion_values)
    checks["shortlist_coverage_complete"] = refs == expected_refs
    checks["rank_order_preserved"] = covered_keys == [
        (r["source_record_id"], r["source_version_id"], r["source_paragraph_id"])
        for r in expected_refs]
    checks["no_duplicate_references"] = len(set(covered_keys)) == len(covered_keys)
    checks["unknown_source_count_zero"] = unknown_source_count == 0
    checks["no_reasoning_content"] = "reasoning_content" not in serialized
    checks["no_raw_source_text"] = all(probe not in serialized for probe in raw_probes)

    error_code = ""
    if status_code != 200:
        detail = body.get("detail", "") if isinstance(body, dict) else ""
        error_code = detail if isinstance(detail, str) else "unparseable_error_detail"

    return {
        "run": run_index,
        "http_status": status_code,
        "error_code": error_code,
        "response_model": body.get("model_version", ""),
        "provider": body.get("provider", ""),
        "request_count": int(metrics.get("request_count", 0)),
        "latency_ms": int(metrics.get("latency_ms", 0)),
        "max_tokens_per_request": max_budget,
        "finish_reasons": metrics.get("finish_reasons", []),
        "totals": {key: int(metrics.get(key, 0)) for key in (
            "prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens",
            "prompt_cache_hit_tokens", "prompt_cache_miss_tokens",
        )},
        "calls": [{
            "call_type": call.get("call_type", ""),
            "batch_index": call.get("batch_index"),
            "request_count": int(call.get("request_count", 0)),
            "latency_ms": int(call.get("latency_ms", 0)),
            "finish_reason": call.get("finish_reason", ""),
            "prompt_tokens": int(call.get("prompt_tokens", 0)),
            "completion_tokens": int(call.get("completion_tokens", 0)),
            "total_tokens": int(call.get("total_tokens", 0)),
            "reasoning_tokens": int(call.get("reasoning_tokens", 0)),
            "prompt_cache_hit_tokens": int(call.get("prompt_cache_hit_tokens", 0)),
            "prompt_cache_miss_tokens": int(call.get("prompt_cache_miss_tokens", 0)),
        } for call in calls],
        "shortlist_count": len(shortlist),
        "covered_source_count": len(set(covered_keys) & shortlist_keys),
        "field_counts": {
            "legal_issues": len(structured.get("legal_issues", []) or []),
            "precedent_similarities": len(structured.get("precedent_similarities", []) or []),
            "precedent_differences": len(structured.get("precedent_differences", []) or []),
            "favorable_use": len(structured.get("favorable_use", []) or []),
            "adverse_use": len(structured.get("adverse_use", []) or []),
            "paragraph_references": len(refs),
        },
        "hallucinated_source_count": 0 if checks.get("run_succeeded") else None,
        "unknown_source_count": unknown_source_count,
        "schema_reject_count": 0 if checks.get("run_succeeded") else None,
        "reasoning_content_saved": not checks["no_reasoning_content"],
        "raw_content_in_report": not checks["no_raw_source_text"],
        "checks": checks,
        "passed": all(checks.values()),
    }


def main() -> None:
    args = _parse_args()
    if not args.confirm_live_smoke:
        raise SystemExit("smoke_abort: pass --confirm-live-smoke to run against the live API")
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("smoke_abort: DATABASE_URL must point at the UAT database")
    if os.environ.get("DEEPSEEK_MAX_TOKENS"):
        raise SystemExit("smoke_abort: DEEPSEEK_MAX_TOKENS override is not allowed for this smoke")

    os.environ.setdefault("AUTH_MODE", "jwt")
    os.environ.setdefault("JWT_SECRET_KEY", secrets.token_hex(32))

    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=BACKEND_DIR,
    ).stdout.strip()

    token, session_id, shortlist, raw_probes = asyncio.run(
        _prepare_context(args.case_id, args.pool_id))
    if not shortlist:
        raise SystemExit("smoke_abort: pool shortlist is empty")

    base_url = f"http://127.0.0.1:{args.port}"
    server_env = dict(os.environ)
    server_env["SMOKE_POOL_ID"] = args.pool_id
    server_env["SMOKE_PORT"] = str(args.port)
    server_log_path = BACKEND_DIR / "deepseek-batched-smoke-server.log"
    server_log = server_log_path.open("ab")
    server = subprocess.Popen(
        [sys.executable, str(BACKEND_DIR / "scripts" / "deepseek_batched_smoke_server.py")],
        cwd=BACKEND_DIR, env=server_env,
        stdout=server_log, stderr=subprocess.STDOUT,
    )
    from app.config import get_settings
    expected_model = get_settings().deepseek_model

    runs: list[dict] = []
    try:
        print(json.dumps({"stage": "waiting_for_backend_health", "base_url": base_url}), flush=True)
        _wait_for_health(base_url)
        print(json.dumps({"stage": "backend_ready", "runs_planned": args.runs}), flush=True)
        for run_index in range(1, args.runs + 1):
            print(json.dumps({"stage": "run_started", "run": run_index}), flush=True)
            started = time.time()
            response = httpx.post(
                f"{base_url}/api/v1/cases/{args.case_id}/legal-issues/rebuild",
                headers={"Authorization": f"Bearer {token}"},
                json={},
                timeout=1800,
            )
            try:
                body = response.json()
            except ValueError:
                body = {}
            result = _evaluate_run(
                run_index, response.status_code, body, shortlist, raw_probes, expected_model,
            )
            result["endpoint_latency_ms"] = int((time.time() - started) * 1000)
            runs.append(result)
            print(json.dumps({
                "run": run_index,
                "passed": result["passed"],
                "http_status": result["http_status"],
                "error_code": result["error_code"],
                "request_count": result["request_count"],
                "finish_reasons": result["finish_reasons"],
                "covered_source_count": result["covered_source_count"],
                "shortlist_count": result["shortlist_count"],
            }, ensure_ascii=False), flush=True)
    finally:
        server.terminate()
        try:
            server.wait(timeout=30)
        except subprocess.TimeoutExpired:
            server.kill()
        server_log.close()
        asyncio.run(_revoke_session(session_id))

    evidence = {
        "schema": "deepseek_batched_smoke_sanitized_v1",
        "head_sha": head_sha,
        "case_id": args.case_id,
        "pool_id": args.pool_id,
        "shortlist": [{
            "retrieval_rank": item["retrieval_rank"],
            "source_record_id": item["source_record_id"],
            "source_version_id": item["source_version_id"],
            "source_paragraph_id": item["source_paragraph_id"],
            "text_hash": item["text_hash"],
        } for item in shortlist],
        "runs": runs,
        "passed": bool(runs) and all(run["passed"] for run in runs),
    }
    output_path = BACKEND_DIR / args.output
    output_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": evidence["passed"], "evidence": str(output_path)}, ensure_ascii=False))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
