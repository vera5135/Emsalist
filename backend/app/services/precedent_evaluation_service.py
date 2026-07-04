"""P1.3 — Precedent evaluation service."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from app.services.precedent_authority_service import (
    PrecedentAuthorityService,
    build_canonical_key,
)


class PrecedentEvaluationService:

    def __init__(self) -> None:
        self.service = PrecedentAuthorityService()

    def load_dataset(self, path: str | None = None) -> dict:
        dataset_path = Path(path) if path else Path(__file__).resolve().parent.parent / "evaluation" / "precedent_dataset_v1.json"
        raw = dataset_path.read_text(encoding="utf-8")
        return json.loads(raw)

    def run_evaluation(self, dataset: dict | None = None) -> dict:
        if dataset is None:
            dataset = self.load_dataset()
        items = dataset.get("items", [])
        results = []
        for item in items:
            result = self._evaluate_item(item)
            results.append(result)
        return self._summarize(dataset, results)

    def _evaluate_item(self, item: dict) -> dict:
        t0 = time.time()
        precinct_input = item.get("precedent_input", {})
        live_results = [precinct_input] if precinct_input.get("source_type") == "official_yargitay" else []
        brain_results = [precinct_input] if precinct_input.get("source_type") != "official_yargitay" else []

        authority = self.service.build_authority(
            case_id="eval",
            live_results=live_results,
            brain_results=brain_results,
        )

        records = authority.records
        record = records[0].model_dump(mode="json") if records else {}
        canonical_match = record.get("canonical_key") if records else ""

        field_results = {
            "canonical_key": canonical_match == item.get("expected_canonical_key", ""),
            "verification_status": record.get("verification_status") == item.get("expected_verification_status"),
            "authority_status": record.get("authority_status") == item.get("expected_authority_status"),
            "relevance_status": record.get("relevance_status") == item.get("expected_relevance_status"),
            "selection_status": record.get("selection_status") == item.get("expected_selection_status"),
        }

        passed = all(field_results.values())
        errors = [k for k, v in field_results.items() if not v] if not passed else []

        return {
            "item_id": item["item_id"],
            "predicted": record,
            "expected": item,
            "field_results": field_results,
            "passed": passed,
            "errors": errors,
            "warnings": authority.warnings,
            "duration_ms": int((time.time() - t0) * 1000),
        }

    def _summarize(self, dataset: dict, results: list[dict]) -> dict:
        total = len(results)
        passed = sum(1 for r in results if r["passed"])
        failed = total - passed

        def acc(field: str) -> float:
            ok = sum(1 for r in results if r["field_results"].get(field))
            return round(ok / total * 100, 1) if total else 0

        thresholds = {
            "canonical_key": {"required": 100, "actual": acc("canonical_key")},
            "verification_status": {"required": 95, "actual": acc("verification_status")},
            "authority_status": {"required": 95, "actual": acc("authority_status")},
            "relevance_status": {"required": 85, "actual": acc("relevance_status")},
            "selection_status": {"required": 85, "actual": acc("selection_status")},
        }

        regression_failures = [k for k, v in thresholds.items() if v["actual"] < v["required"]]

        return {
            "dataset_version": dataset.get("version", ""),
            "total_items": total,
            "passed_items": passed,
            "failed_items": failed,
            "overall_accuracy": round(passed / total * 100, 1) if total else 0,
            "thresholds": thresholds,
            "regression_failures": regression_failures,
            "profile_breakdown": {},
            "difficulty_breakdown": {},
            "false_positive_count": 0,
            "false_negative_count": 0,
        }


evaluation_service = PrecedentEvaluationService()
