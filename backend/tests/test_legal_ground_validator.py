"""P0.4 — Legal ground validation tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.case_session_service import CaseSessionService
from app.services.legal_ground_validator_service import (
    CANONICAL_ARTICLES,
    CANONICAL_LEGISLATION,
    LEGISLATION_ALIASES,
    build_canonical_registry,
    citation_normalizer,
    legal_ground_validator,
    registry_scope,
)


class CitationNormalizerTests(unittest.TestCase):

    def test_tbk_219_formats_normalize(self) -> None:
        self.assertEqual(citation_normalizer.normalize("TBK 219"), "TBK:m.219")
        self.assertEqual(citation_normalizer.normalize("TBK m. 219"), "TBK:m.219")
        self.assertEqual(citation_normalizer.normalize("TBK m.219"), "TBK:m.219")

    def test_hard_formats_normalize(self) -> None:
        result = citation_normalizer.normalize("6098 sayılı Kanun m.219")
        self.assertIn("219", result)

    def test_hmk_article_normalize(self) -> None:
        self.assertEqual(citation_normalizer.normalize("HMK 190"), "HMK:m.190")

    def test_different_citations_produce_different_keys(self) -> None:
        a = citation_normalizer.normalize("TBK 219")
        b = citation_normalizer.normalize("TBK 223")
        self.assertNotEqual(a, b)

    def test_resolve_known_legislation(self) -> None:
        info = citation_normalizer.resolve("TBK:m.219")
        self.assertIsNotNone(info)
        if info:
            self.assertEqual(info["legislation_code"], "TBK")
            self.assertEqual(info["article"], "219")

    def test_resolve_unknown_legislation(self) -> None:
        info = citation_normalizer.resolve("XYZ:m.999")
        self.assertIsNotNone(info)
        if info:
            self.assertEqual(info["legislation_name"], "")

    def test_parse_article_basic(self) -> None:
        info = citation_normalizer.parse_article("TBK m.219 f.1")
        self.assertEqual(info["article"], "219")
        self.assertEqual(info["paragraph"], "1")

    def test_parse_article_simple(self) -> None:
        info = citation_normalizer.parse_article("219")
        self.assertEqual(info["article"], "219")

    def test_canonical_codes_are_unique_and_kidem_is_only_an_alias(self) -> None:
        self.assertEqual(len(CANONICAL_LEGISLATION), len(set(CANONICAL_LEGISLATION)))
        self.assertEqual(len(CANONICAL_LEGISLATION), 10)
        self.assertNotIn("KIDEM", CANONICAL_LEGISLATION)
        self.assertEqual(LEGISLATION_ALIASES["kidem"], "1475:m.14")

    def test_duplicate_canonical_registry_code_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "Duplicate canonical legislation code"):
            build_canonical_registry(({"code": "TBK"}, {"code": "TBK"}))

    def test_aliases_resolve_to_canonical_codes(self) -> None:
        self.assertEqual(citation_normalizer.normalize("Türk Borçlar Kanunu m.219"), "TBK:m.219")
        self.assertEqual(citation_normalizer.normalize("6098 sayılı Kanun m.219"), "TBK:m.219")
        self.assertEqual(citation_normalizer.normalize("İş Kanunu m.41"), "İŞK:m.41")
        self.assertEqual(citation_normalizer.normalize("4857 sayılı İş Kanunu m.41"), "İŞK:m.41")

    def test_kidem_normalizes_to_1475_article_14(self) -> None:
        self.assertEqual(citation_normalizer.normalize("KIDEM"), "1475:m.14")
        self.assertEqual(citation_normalizer.normalize("1475 sayılı Kanun m.14"), "1475:m.14")


class LegalGroundValidatorTests(unittest.TestCase):

    def test_known_law_verified(self) -> None:
        grounds = legal_ground_validator.validate(["TBK 219", "TBK 223", "HMK 190"])
        verified = [g for g in grounds if g.verification_status == "verified"]
        self.assertGreaterEqual(len(verified), 2)

    def test_unknown_law_unverified(self) -> None:
        grounds = legal_ground_validator.validate(["XYZ 999"])
        self.assertEqual(len(grounds), 1)
        self.assertEqual(grounds[0].verification_status, "unverified")

    def test_duplicate_grounds_deduplicated(self) -> None:
        grounds = legal_ground_validator.validate(["TBK 219", "TBK 219", "TBK m. 219"])
        self.assertEqual(len(grounds), 1)

    def test_vehicle_case_applicability(self) -> None:
        grounds = legal_ground_validator.validate(
            ["TBK 219", "TBK 223", "TBK 227", "İŞK 41"],
            case_type="ayipli arac satisi",
        )
        tbk_219 = next((g for g in grounds if "219" in g.normalized_citation), None)
        self.assertIsNotNone(tbk_219)
        self.assertEqual(tbk_219.applicability_status, "directly_applicable")

    def test_labor_article_in_vehicle_irrelevant(self) -> None:
        grounds = legal_ground_validator.validate(
            ["4857 sayılı İş Kanunu m.41"],
            case_type="ayipli arac satisi gizli ayip motor arizasi",
        )
        isk = next((g for g in grounds if g.legislation_code == "İŞK"), None)
        self.assertIsNotNone(isk)
        self.assertEqual(isk.applicability_status, "irrelevant")

    def test_validate_response_structure(self) -> None:
        response = legal_ground_validator.validate_response(
            case_id="test-1",
            raw_grounds=["TBK 219", "HMK 190"],
        )
        self.assertEqual(response.case_id, "test-1")
        self.assertGreater(len(response.verified_grounds), 0)

    def test_ai_suggested_ground_not_auto_verified(self) -> None:
        grounds = legal_ground_validator.validate(
            ["Meclis İçtüzüğü m.5"],
            source_type="enrichment",
        )
        self.assertEqual(grounds[0].source_type, "enrichment")
        self.assertEqual(grounds[0].verification_status, "unverified")

    def test_known_code_without_registered_article_is_unverified(self) -> None:
        ground = legal_ground_validator.validate(["TBK 999"])[0]
        self.assertEqual(ground.verification_status, "unverified")
        self.assertEqual(ground.canonical_article_id, "")
        self.assertEqual(ground.source_ref, "")
        self.assertEqual(ground.title, "")
        self.assertEqual(ground.rule_summary, "")

    def test_unparseable_citation_is_invalid(self) -> None:
        ground = legal_ground_validator.validate(["TBK maddesi belirtilmemiş"])[0]
        self.assertEqual(ground.verification_status, "invalid")

    def test_explicit_alias_article_mismatch_is_invalid(self) -> None:
        ground = legal_ground_validator.validate(["KIDEM m.41"])[0]
        self.assertEqual(ground.normalized_citation, "1475:m.41")
        self.assertEqual(ground.verification_status, "invalid")

    def test_conflicting_law_number_and_name_is_invalid(self) -> None:
        ground = legal_ground_validator.validate(["6098 sayılı İş Kanunu m.41"])[0]
        self.assertEqual(ground.verification_status, "invalid")

    def test_verified_ground_has_article_level_source_evidence(self) -> None:
        ground = legal_ground_validator.validate(["TBK 219"])[0]
        self.assertEqual(ground.verification_status, "verified")
        self.assertEqual(ground.canonical_legislation_id, "tr-law-6098")
        self.assertTrue(ground.canonical_article_id)
        self.assertEqual(ground.verified_article, "219")
        self.assertTrue(ground.source_ref)
        self.assertEqual(ground.source_title, "Türk Borçlar Kanunu")
        self.assertEqual(ground.official_source_id, "mevzuat-6098")

    def test_registry_scope_distinguishes_recognition_from_article_coverage(self) -> None:
        scope = registry_scope()
        self.assertEqual(scope["canonical_legislation_count"], 10)
        self.assertEqual(scope["verified_article_count"], len(CANONICAL_ARTICLES))
        self.assertIn("İYUK", scope["coverage_notes"])
        self.assertIn("CMK", scope["out_of_scope"])


class LegalGroundEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.cases = CaseSessionService(Path(self.temporary.name) / "legal-ground-cases")
        self.patcher = patch("app.routes.legal_ground_routes.case_session_service", self.cases)
        self.patcher.start()
        self.client = TestClient(app)
        self.case_id = self.cases.new_case()["case_id"]

    def tearDown(self) -> None:
        self.client.close()
        self.patcher.stop()
        self.temporary.cleanup()

    def test_missing_case_id_returns_422(self) -> None:
        response = self.client.post("/legal-grounds/validate", json={"legal_grounds": []})
        self.assertEqual(response.status_code, 422)

    def test_unknown_case_id_returns_404(self) -> None:
        response = self.client.post("/legal-grounds/validate", json={
            "case_id": "bilinmeyen-dosya",
            "legal_grounds": [],
        })
        self.assertEqual(response.status_code, 404)

    def test_valid_request_succeeds(self) -> None:
        response = self.client.post("/legal-grounds/validate", json={
            "case_id": self.case_id,
            "legal_grounds": [{"citation": "TBK 219"}, {"citation": "HMK 190"}],
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data["verified_grounds"]), 0)

    def test_unverified_articles_reported(self) -> None:
        response = self.client.post("/legal-grounds/validate", json={
            "case_id": self.case_id,
            "legal_grounds": [{"citation": "XYZ 999"}],
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["unverified_grounds"]), 1)

    def test_cross_case_isolation(self) -> None:
        case_b = self.cases.new_case()["case_id"]
        self.client.post("/legal-grounds/validate", json={
            "case_id": self.case_id,
            "legal_grounds": [{"citation": "TBK 219"}],
        })
        state_b = self.cases.get_case_state(case_b)
        self.assertFalse(
            state_b.get("legal_ground_validation", {}).get("verified_grounds"),
        )


if __name__ == "__main__":
    unittest.main()
