"""P1.3.1 — Precedent benchmark quality gate tests."""

from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

from app.services.precedent_evaluation_service import evaluation_service

DATASET_PATH = Path(__file__).resolve().parent.parent / "evaluation" / "precedent_dataset_v1.json"


class PrecedentBenchmarkTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        raw = DATASET_PATH.read_text(encoding="utf-8")
        cls.dataset = json.loads(raw)
        cls.result = evaluation_service.run_evaluation(cls.dataset)

    def test_canonical_key_accuracy_100(self) -> None:
        self.assertEqual(self.result["canonical_key_accuracy"], 100.0,
            f"Canonical key accuracy must be 100%, got {self.result['canonical_key_accuracy']}%")

    def test_critical_false_positive_tracked(self) -> None:
        self.assertIsInstance(self.result["critical_false_positive_count"], int)

    def test_verification_accuracy_above_95(self) -> None:
        self.assertGreaterEqual(self.result["verification_accuracy"], 95.0)

    def test_authority_accuracy_above_95(self) -> None:
        self.assertGreaterEqual(self.result["authority_accuracy"], 95.0)

    def test_relevance_baseline(self) -> None:
        self.assertGreaterEqual(self.result["relevance_accuracy"], 20.0,
            f"Relevance accuracy {self.result['relevance_accuracy']}% below baseline 20%")

    def test_selection_accuracy_above_85(self) -> None:
        self.assertGreaterEqual(self.result["selection_accuracy"], 85.0)

    def test_usable_precision_above_90(self) -> None:
        self.assertGreaterEqual(self.result["usable_precision"], 90.0,
            f"Precision {self.result['usable_precision']}% below 90%")

    def test_usable_recall_above_80(self) -> None:
        self.assertGreaterEqual(self.result["usable_recall"], 80.0,
            f"Recall {self.result['usable_recall']}% below 80%")

    def test_usable_f1_above_85(self) -> None:
        self.assertGreaterEqual(self.result["usable_f1"], 85.0,
            f"F1 {self.result['usable_f1']}% below 85%")

    def test_canonical_key_must_be_100(self) -> None:
        self.assertEqual(self.result["canonical_key_accuracy"], 100.0,
            f"Canonical key accuracy must be 100%, got {self.result['canonical_key_accuracy']}%")

    def test_profile_coverage(self) -> None:
        profiles = self.result["profile_breakdown"]
        self.assertGreaterEqual(len(profiles), 5)

    def test_metrics_present(self) -> None:
        for key in ("canonical_key_accuracy", "duplicate_accuracy", "verification_accuracy",
                     "authority_accuracy", "relevance_accuracy", "selection_accuracy",
                     "usable_precision", "usable_recall", "usable_f1",
                     "critical_false_positive_count", "false_positive_count", "false_negative_count"):
            self.assertIn(key, self.result, f"Missing metric: {key}")

    def test_benchmark_deterministic(self) -> None:
        r2 = evaluation_service.run_evaluation(self.dataset)
        self.assertEqual(self.result["canonical_key_accuracy"], r2["canonical_key_accuracy"])
        self.assertEqual(self.result["critical_false_positive_count"], r2["critical_false_positive_count"])
        self.assertEqual(self.result["failed_items"], r2["failed_items"])


class DatasetIntegrityTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        raw = DATASET_PATH.read_text(encoding="utf-8")
        cls.dataset = json.loads(raw)
        cls.items = cls.dataset["items"]

    def test_item_count_100(self) -> None:
        self.assertGreaterEqual(len(self.items), 100)

    def test_item_ids_unique(self) -> None:
        ids = [it["item_id"] for it in self.items]
        self.assertEqual(len(ids), len(set(ids)))

    def test_checksum_valid(self) -> None:
        items_json = json.dumps(self.items, sort_keys=True, ensure_ascii=False)
        expected = hashlib.sha256(items_json.encode()).hexdigest()[:16]
        self.assertEqual(self.dataset.get("checksum", ""), expected)

    def test_has_all_tag_types(self) -> None:
        all_tags = set()
        for it in self.items:
            all_tags.update(it.get("tags", []))
        for required in ("direct", "duplicate", "fallback", "irrelevant", "ai", "invalid"):
            self.assertIn(required, all_tags, f"Missing tag type: {required}")

    def test_has_all_profiles(self) -> None:
        profiles = set(it["profile_id"] for it in self.items)
        self.assertGreaterEqual(len(profiles), 7)

    def test_has_all_difficulties(self) -> None:
        diffs = set(it.get("difficulty", "") for it in self.items)
        for d in ("easy", "medium", "hard", "adversarial"):
            self.assertIn(d, diffs, f"Missing difficulty: {d}")

    def test_no_secrets(self) -> None:
        text = str(self.dataset)
        self.assertNotIn("sk-", text)
        self.assertNotIn("Bearer", text)
        self.assertNotIn("C:\\Users", text)
        self.assertNotIn("/home/", text)
        self.assertFalse(re.search(r"\b\d{11}\b", text), "TC Kimlik found")
        self.assertFalse(re.search(r"\d{3}[.\s]?\d{3}[.\s]?\d{4}", text), "Phone found")

    def test_no_long_text(self) -> None:
        for it in self.items:
            for key in it:
                val = str(it[key])
                self.assertLess(len(val), 5000, f"Item {it['item_id']} has long field {key}")

    def test_split_leakage_acceptable(self) -> None:
        from hashlib import sha256
        dev = [it for it in self.items if int(sha256(it['scenario_id'].encode()).hexdigest()[:2], 16) % 10 < 6]
        val = [it for it in self.items if 6 <= int(sha256(it['scenario_id'].encode()).hexdigest()[:2], 16) % 10 < 8]
        hold = [it for it in self.items if int(sha256(it['scenario_id'].encode()).hexdigest()[:2], 16) % 10 >= 8]
        dev_keys = set(it.get("expected_canonical_key", "") for it in dev)
        hold_keys = set(it.get("expected_canonical_key", "") for it in hold)
        leaked = dev_keys & hold_keys
        self.assertLessEqual(len(leaked), 10,
            f"Canonical keys leaking across splits: {len(leaked)}. Expected <=10 for duplicate items.")


if __name__ == "__main__":
    unittest.main()
