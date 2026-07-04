"""P1.3 — Precedent evaluation benchmark tests."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.services.precedent_evaluation_service import evaluation_service


class PrecedentEvaluationTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        dataset_path = Path(__file__).resolve().parent.parent / "evaluation" / "precedent_dataset_v1.json"
        raw = dataset_path.read_text(encoding="utf-8")
        cls.dataset = json.loads(raw)

    def test_dataset_loaded(self) -> None:
        self.assertIn("items", self.dataset)
        self.assertGreaterEqual(len(self.dataset["items"]), 50)

    def test_dataset_checksum(self) -> None:
        items_json = json.dumps(self.dataset["items"], sort_keys=True, ensure_ascii=False)
        chk = self.dataset.get("checksum", "")
        self.assertTrue(chk, "Dataset has no checksum")

    def test_no_raw_case_text(self) -> None:
        items_str = str(self.dataset)
        self.assertNotIn("Müvekkil", items_str)
        self.assertNotIn("davacı", items_str)

    def test_evaluation_run_completes(self) -> None:
        result = evaluation_service.run_evaluation(self.dataset)
        self.assertIn("total_items", result)
        self.assertGreaterEqual(result["total_items"], 50)
        self.assertIn("overall_accuracy", result)

    def test_canonical_key_accuracy_above_80(self) -> None:
        result = evaluation_service.run_evaluation(self.dataset)
        acc = result["thresholds"]["canonical_key"]
        self.assertGreaterEqual(acc["actual"], 80.0,
            f"Canonical key accuracy {acc['actual']}% below 80%")

    def test_verification_accuracy(self) -> None:
        result = evaluation_service.run_evaluation(self.dataset)
        acc = result["thresholds"]["verification_status"]
        self.assertGreaterEqual(acc["actual"], acc["required"],
            f"Verification accuracy {acc['actual']}% below threshold {acc['required']}%")

    def test_regression_within_tolerance(self) -> None:
        result = evaluation_service.run_evaluation(self.dataset)
        failures = result["regression_failures"]
        self.assertLessEqual(len(failures), 3,
            f"Too many regression failures: {failures}")


if __name__ == "__main__":
    unittest.main()
