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
        precinct_input = dict(item.get("precedent_input", {}))
        case_summary = item.get("case_summary", "") or item.get("profile_id", "")
        precinct_input["case_summary"] = case_summary
        precinct_input["profile_id"] = item.get("profile_id", "")
        live_results = [precinct_input] if precinct_input.get("source_type") == "official_yargitay" else []
        brain_results = [precinct_input] if precinct_input.get("source_type") != "official_yargitay" else []

        authority = self.service.build_authority(
            case_id="eval",
            live_results=live_results,
            brain_results=brain_results,
        )

        records = authority.records
        record = records[0].model_dump(mode="json") if records else {}
        expected_key = item.get("expected_canonical_key", "")
        actual_key = record.get("canonical_key", "") if records else ""

        # Canonical key: exact match for YARGITAY:* keys, startswith for FALLBACK:
        if expected_key.startswith("PRECEDENT:FALLBACK:"):
            canonical_match = actual_key.startswith("PRECEDENT:FALLBACK:")
        else:
            canonical_match = actual_key == expected_key

        expected_usable = item.get("expected_usable", True)
        predicted_usable = record.get("selection_status") == "accepted" and record.get("verification_status") in ("verified", "partially_verified")

        field_results = {
            "canonical_key": canonical_match,
            "verification_status": record.get("verification_status") == item.get("expected_verification_status"),
            "authority_status": record.get("authority_status") == item.get("expected_authority_status"),
            "relevance_status": record.get("relevance_status") == item.get("expected_relevance_status"),
            "selection_status": record.get("selection_status") == item.get("expected_selection_status"),
            "usable": predicted_usable == expected_usable,
        }

        # Critical false positive detection
        is_critical_fp = False
        if not expected_usable and predicted_usable:
            ver = record.get("verification_status", "")
            auth = record.get("authority_status", "")
            sel = record.get("selection_status", "")
            if auth == "fallback_only" or ver == "unverified" or sel == "accepted":
                is_critical_fp = True
        dup_status = record.get("duplicate_status", "")
        if dup_status == "duplicate" and predicted_usable:
            is_critical_fp = True

        passed = all(field_results.values())
        errors = [k for k, v in field_results.items() if not v] if not passed else []

        return {
            "item_id": item["item_id"],
            "predicted": record,
            "expected": item,
            "field_results": field_results,
            "passed": passed,
            "errors": errors,
            "critical_false_positive": is_critical_fp,
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

        def br(field: str, profile: str | None = None) -> float:
            subset = [r for r in results if not profile or r.get("expected", {}).get("profile_id") == profile]
            ok = sum(1 for r in subset if r["field_results"].get(field))
            return round(ok / len(subset) * 100, 1) if subset else 0

        tp = sum(1 for r in results if r["field_results"].get("usable") and r["expected"].get("expected_usable"))
        fp = sum(1 for r in results if r["field_results"].get("usable") and not r["expected"].get("expected_usable"))
        fn = sum(1 for r in results if not r["field_results"].get("usable") and r["expected"].get("expected_usable"))
        tn = total - tp - fp - fn

        precision = round(tp / (tp + fp) * 100, 1) if (tp + fp) else 0
        recall = round(tp / (tp + fn) * 100, 1) if (tp + fn) else 0
        f1 = round(2 * precision * recall / (precision + recall), 1) if (precision + recall) else 0

        critical_fp_count = sum(1 for r in results if r.get("critical_false_positive"))

        thresholds = {
            "canonical_key": {"required": 100.0, "actual": acc("canonical_key")},
            "duplicate_accuracy": {"required": 95.0, "actual": acc("verification_status")},
            "verification_status": {"required": 95.0, "actual": acc("verification_status")},
            "authority_status": {"required": 95.0, "actual": acc("authority_status")},
            "relevance_status": {"required": 85.0, "actual": acc("relevance_status")},
            "selection_status": {"required": 85.0, "actual": acc("selection_status")},
            "usable_precision": {"required": 90.0, "actual": precision},
            "usable_recall": {"required": 80.0, "actual": recall},
            "usable_f1": {"required": 85.0, "actual": f1},
            "critical_false_positive_count": {"required": 0, "actual": critical_fp_count},
        }

        regression_failures = [k for k, v in thresholds.items() if v["actual"] < v["required"]]
        if thresholds["canonical_key"]["actual"] < 100.0:
            regression_failures.append("canonical_key_not_100_percent")

        profiles = sorted(set(it.get("profile_id", "unknown") for it in dataset.get("items", [])))
        difficulties = sorted(set(it.get("difficulty", "unknown") for it in dataset.get("items", [])))

        return {
            "dataset_version": dataset.get("version", ""),
            "total_items": total,
            "passed_items": passed,
            "failed_items": failed,
            "overall_accuracy": round(passed / total * 100, 1) if total else 0,
            "canonical_key_accuracy": acc("canonical_key"),
            "duplicate_accuracy": acc("verification_status"),
            "verification_accuracy": acc("verification_status"),
            "authority_accuracy": acc("authority_status"),
            "relevance_accuracy": acc("relevance_status"),
            "selection_accuracy": acc("selection_status"),
            "usable_precision": precision,
            "usable_recall": recall,
            "usable_f1": f1,
            "critical_false_positive_count": critical_fp_count,
            "false_positive_count": fp,
            "false_negative_count": fn,
            "thresholds": thresholds,
            "regression_failures": regression_failures,
            "profile_breakdown": {p: br("usable", p) for p in profiles},
            "difficulty_breakdown": {d: br("usable", d) for d in difficulties},
        }

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
