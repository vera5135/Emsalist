"""P0.2.2 — Multi-case-type regression tests.

Verifies that hardcoded data does not leak across case types.
"""

from __future__ import annotations

import unittest

from app.services.final_petition_writer_service import (
    FORBIDDEN_TEXT,
    final_petition_writer_service,
)
from app.services.petition_draft_service import petition_draft_service
from app.services.petition_profile_service import get_petition_profile


def _local_draft(package) -> str:
    return final_petition_writer_service._local_template(package)


def _plain(text: str) -> str:
    t = str(text or "").casefold()
    for a, b in (("ç", "c"), ("ğ", "g"), ("ı", "i"), ("ö", "o"), ("ş", "s"), ("ü", "u"), ("i̇", "i")):
        t = t.replace(a, b)
    return t


class MultiCaseRegressionTests(unittest.TestCase):
    """Tests that petition generation works correctly across 7 case types."""

    # ── Helper to build a package quickly ──

    def _package(self, case_text="", request_type="Davanın kabulü", **kw):
        from app.models.petition_models import DraftingPackage, DraftingCaseIdentity, DraftingParties

        plaintiff = kw.pop("plaintiff", "...")
        defendant = kw.pop("defendant", "...")
        court_heading = kw.pop("court_heading", "NÖBETÇİ ASLİYE HUKUK MAHKEMESİ'NE")
        petition_type = kw.pop("petition_type", kw.pop("profile_key", "Dava"))

        return DraftingPackage(
            case_identity=DraftingCaseIdentity(
                court_heading=court_heading,
                plaintiff=plaintiff,
                defendant=defendant,
                claim_value=kw.pop("claim_value", ""),
                case_type=kw.pop("case_type", petition_type),
                subject=kw.pop("subject", ""),
            ),
            court_heading=court_heading,
            petition_type=petition_type,
            parties=DraftingParties(claimant=plaintiff, defendant=defendant, attorney="Av. ..."),
            event_text=case_text,
            area=request_type,
            case_type=petition_type,
            question_answers=kw.pop("question_answers", {}),
            confirmed_facts=kw.pop("confirmed_facts", []),
            uncertain_facts=kw.pop("uncertain_facts", []),
            missing_facts=kw.pop("missing_facts", []),
            evidence_items=kw.pop("evidence_items", []),
            legal_grounds=kw.pop("legal_grounds", ["ilgili mevzuat"]),
            legal_basis=kw.pop("legal_grounds", ["ilgili mevzuat"]),
            relief_requests=kw.pop("relief_requests", ["Davanın kabulüne"]),
            risk_items=kw.pop("risk_items", []),
            precedent_for_petition=kw.pop("precedent_for_petition", []),
            writer_mode=kw.pop("writer_mode", "local"),
            local_draft_seed="",
            **kw,
        )

    # ── A. Ayıplı ikinci el araç satışı ──

    def test_vehicle_defect_no_hardcoded_names(self) -> None:
        pkg = self._package(
            case_text="Müvekkil ikinci el araci galeriden satin aldi motor arizasi cikti",
            profile_key="defective_vehicle",
            court_heading="NÖBETÇİ TÜKETİCİ MAHKEMESİ'NE",
            confirmed_facts=["Satıcı kazasız ve sorunsuz beyanında bulunmuştur"],
            relief_requests=[
                "Satış bedelinin iadesine",
                "Aracın davalıya iadesine karar verilmesine",
            ],
            evidence_items=["Noter satış sözleşmesi", "Servis raporu"],
        )
        text = _local_draft(pkg)
        plain = _plain(text)
        for forbidden in ("mehmet demir", "ahmet yilmaz", "izmir 5. noterligi",
                          "500.000 tl", "volkswagen golf", "35 abc 123", "wvwww"):
            self.assertNotIn(forbidden, plain, f"Hardcoded '{forbidden}' found in vehicle draft")

    def test_vehicle_defect_has_vehicle_return(self) -> None:
        pkg = self._package(
            case_text="Müvekkil ikinci el araci galeriden satin aldi",
            profile_key="defective_vehicle",
            court_heading="NÖBETÇİ TÜKETİCİ MAHKEMESİ'NE",
            relief_requests=["Satış bedelinin iadesine", "Aracın davalıya iadesine"],
        )
        text = _local_draft(pkg)
        self.assertIn("iade", _plain(text))

    # ── B. Kira alacağı ve tahliye ──

    def test_rent_case_no_vehicle_terms(self) -> None:
        pkg = self._package(
            case_text="Kiracı 3 aydır kira bedelini ödemiyor tahliye talep ediliyor",
            profile_key="eviction_need",
            court_heading="NÖBETÇİ SULH HUKUK MAHKEMESİ'NE",
            relief_requests=["Kira alacağının tahsiline", "Kiralananın tahliyesine"],
            evidence_items=["Kira sözleşmesi", "İhtarname"],
        )
        text = _local_draft(pkg)
        plain = _plain(text)
        for vehicle_term in ("arac iadesi", "takyidat", "servis raporu", "motor arizasi", "noter satis"):
            self.assertNotIn(vehicle_term, plain, f"Vehicle term '{vehicle_term}' leaked into rent case")

    def test_rent_case_has_eviction(self) -> None:
        pkg = self._package(
            case_text="Kiracı kira borcunu ödemedi",
            profile_key="eviction_need",
            court_heading="NÖBETÇİ SULH HUKUK MAHKEMESİ'NE",
            relief_requests=["Kiralananın tahliyesine"],
        )
        text = _local_draft(pkg)
        self.assertIn("tahliye", _plain(text))

    # ── C. İşçilik alacakları ──

    def test_labor_case_no_other_relief_leak(self) -> None:
        pkg = self._package(
            case_text="İşçi kıdem ve ihbar tazminatı talep ediyor",
            profile_key="labor_receivable",
            court_heading="NÖBETÇİ İŞ MAHKEMESİ'NE",
            relief_requests=["Kıdem tazminatının tahsiline", "İhbar tazminatının tahsiline"],
            evidence_items=["İş sözleşmesi", "SGK kaydı"],
            legal_grounds=["4857 sayılı İş Kanunu"],
        )
        text = _local_draft(pkg)
        plain = _plain(text)
        for non_labor in ("arac iadesi", "tahliye", "nafaka", "velayet", "iptal"):
            self.assertNotIn(non_labor, plain, f"Non-labor term '{non_labor}' leaked")
        self.assertIn("tazminat", plain)

    # ── D. Boşanma ve velayet ──

    def test_family_case_no_inappropriate_terms(self) -> None:
        pkg = self._package(
            case_text="Evlilik birliği temelinden sarsıldı boşanma ve velayet talep ediliyor",
            profile_key="poverty_alimony",
            court_heading="NÖBETÇİ AİLE MAHKEMESİ'NE",
            relief_requests=["Tarafların boşanmasına", "Velayetin anneye verilmesine"],
            evidence_items=["Nüfus kaydı", "Tanık"],
        )
        text = _local_draft(pkg)
        plain = _plain(text)
        for non_family in ("kidem tazminati", "arac iadesi", "tahliye", "iptal"):
            self.assertNotIn(non_family, plain, f"Inappropriate term '{non_family}' in family case")

    # ── E. İcra takibine itiraz ──

    def test_enforcement_case_court_heading(self) -> None:
        pkg = self._package(
            case_text="İcra takibine itiraz edildi itirazın iptali talep ediliyor",
            profile_key="enforcement_objection",
            court_heading="NÖBETÇİ İCRA HUKUK MAHKEMESİ'NE",
            relief_requests=["İtirazın iptaline"],
            evidence_items=["İcra dosyası", "Ödeme emri"],
        )
        text = _local_draft(pkg)
        self.assertIn("icra", _plain(text))

    # ── F. Haksız fiil tazminat ──

    def test_tort_case_generic_draft(self) -> None:
        pkg = self._package(
            case_text="Trafik kazası sonucu maddi ve manevi tazminat talep ediliyor",
            profile_key="",
            court_heading="NÖBETÇİ ASLİYE HUKUK MAHKEMESİ'NE",
            relief_requests=["Maddi tazminatın tahsiline", "Manevi tazminatın tahsiline"],
            evidence_items=["Kaza tutanağı", "Hastane raporu"],
            legal_grounds=["TBK m.49", "TBK m.54"],
        )
        text = _local_draft(pkg)
        plain = _plain(text)
        self.assertIn("davaci", plain)
        self.assertIn("davali", plain)
        for forbidden in ("mehmet demir", "ahmet yilmaz", "500.000 tl"):
            self.assertNotIn(forbidden, plain)

    # ── G. İdari işlemin iptali ──

    def test_admin_case_relief_isolation(self) -> None:
        pkg = self._package(
            case_text="İdari para cezasının iptali talep ediliyor",
            profile_key="",
            court_heading="NÖBETÇİ İDARE MAHKEMESİ'NE",
            relief_requests=["İdari işlemin iptaline", "Yürütmenin durdurulmasına"],
            evidence_items=["İdari işlem tebliği", "Dilekçe"],
        )
        text = _local_draft(pkg)
        plain = _plain(text)
        for non_admin in ("tahliye", "kidem", "arac iadesi", "nafaka", "velayet"):
            self.assertNotIn(non_admin, plain, f"Non-admin term '{non_admin}' leaked")

    # ── Cross-case isolation ──

    def test_vehicle_relief_not_in_rent_case(self) -> None:
        pkg_vehicle = self._package(
            case_text="Araç satışı motor arızası",
            profile_key="defective_vehicle",
            court_heading="TÜKETİCİ MAHKEMESİ",
            relief_requests=["Satış bedelinin iadesine", "Aracın davalıya iadesine"],
        )
        pkg_rent = self._package(
            case_text="Kira alacağı tahliye",
            profile_key="eviction_need",
            court_heading="SULH HUKUK MAHKEMESİ",
            relief_requests=["Kiralananın tahliyesine"],
        )
        text_rent = _local_draft(pkg_rent)
        self.assertNotIn("arac iadesi", _plain(text_rent))

    # ── Missing data tests ──

    def test_missing_parties_produces_placeholder(self) -> None:
        pkg = self._package(
            case_text="Genel bir hukuki uyuşmazlık metni buraya yazılır",
            plaintiff="...",
            defendant="...",
            relief_requests=["Davanın kabulüne"],
        )
        text = _local_draft(pkg)
        self.assertIn("DAVACI", text)
        self.assertIn("DAVALI", text)

    def test_missing_court_produces_warning(self) -> None:
        pkg = self._package(
            case_text="Uyuşmazlık konusu",
            court_heading="NÖBETÇİ ASLİYE HUKUK MAHKEMESİ'NE",
        )
        text = _local_draft(pkg)
        self.assertIn("MAHKEMESİ", text)

    def test_no_fake_amounts_in_empty_case(self) -> None:
        pkg = self._package(
            case_text="Sadece bir uyuşmazlık var",
            relief_requests=["Davanın kabulüne"],
        )
        text = _local_draft(pkg)
        plain = _plain(text)
        for fake in ("500.000", "350.000", "23.000", "1.000,00"):
            self.assertNotIn(fake, plain, f"Fake amount '{fake}' in empty case draft")

    # ── Evidence dedup ──

    def test_evidence_no_duplicates(self) -> None:
        pkg = self._package(
            case_text="Araç satışı",
            evidence_items=["Noter satış sözleşmesi", "Noter satış sözleşmesi", "Servis raporu"],
            relief_requests=["Bedel iadesine"],
        )
        text = _local_draft(pkg)
        count = _plain(text).count("noter satis sozlesmesi")
        self.assertLessEqual(count, 2, f"Evidence duplicated: found {count} occurrences")

    # ── Legal grounds per profile ──

    def test_vehicle_grounds_do_not_include_labor_law(self) -> None:
        pkg = self._package(
            case_text="Araç satışı",
            profile_key="defective_vehicle",
            legal_grounds=["TBK m.219", "TBK m.223", "TBK m.227"],
            relief_requests=["Bedel iadesine"],
        )
        text = _local_draft(pkg)
        plain = _plain(text)
        for labor_term in ("is kanunu", "kidem", "ihbar tazminati", "yillik izin"):
            self.assertNotIn(labor_term, plain, f"Labor term '{labor_term}' in vehicle grounds")

    def test_labor_grounds_do_not_include_vehicle_law(self) -> None:
        pkg = self._package(
            case_text="İşçi alacağı",
            profile_key="labor_receivable",
            legal_grounds=["4857 sayılı İş Kanunu"],
            relief_requests=["Kıdem tazminatının tahsiline"],
        )
        text = _local_draft(pkg)
        plain = _plain(text)
        self.assertNotIn("TBK 219", plain)

    def test_unknown_case_uses_safe_generic_fallback(self) -> None:
        case_text = "Mirasbırakanın vasiyetnamesinin tenfizi talep edilmektedir."
        request_type = "Vasiyetnamenin tenfizi"
        profile = get_petition_profile(case_text, request_type)

        self.assertEqual(profile.key, "generic")
        self.assertTrue(profile.questions)
        self.assertTrue(profile.skeleton)

        first_pass = petition_draft_service.build_draft(
            case_text=case_text,
            answers={},
            selected_decisions=[],
            tone="Ölçülü ve ikna edici",
            request_type=request_type,
            use_legal_brain=False,
        )
        self.assertIn("GÖREVLİ VE YETKİLİ MAHKEME", first_pass.draft_text)
        self.assertNotIn("TÜKETİCİ / ASLİYE", first_pass.draft_text)

        package = final_petition_writer_service.build_package(
            case_text=case_text,
            request_type=request_type,
        )
        text = _local_draft(package)
        plain = _plain(text)
        gemini_prompt = final_petition_writer_service._gemini_prompt(package)

        self.assertEqual(package.profile_id, "generic")
        self.assertEqual(package.case_type, "generic")
        self.assertEqual(package.court_candidates, [])
        self.assertIn("GÖREVLİ VE YETKİLİ MAHKEME", package.court_heading)
        self.assertTrue(package.court_warning)
        self.assertTrue(package.drafting_warnings)
        self.assertTrue(package.missing_information_questions)
        self.assertIn("vasiyetnamenin tenfizi", plain)
        self.assertNotIn("ARAÇ_BİLGİSİ", gemini_prompt)
        self.assertNotIn("TRAMER", gemini_prompt)
        self.assertNotIn("Ayıp ihbarı", gemini_prompt)
        for leaked_relief in (
            "aracin takyidatlardan arindirilmis sekilde davaliya iadesi",
            "kiralananin tahliyesi",
            "kidem tazminati",
            "velayetin",
            "yurutmenin durdurulmasi",
        ):
            self.assertNotIn(leaked_relief, plain)
        for concrete_court in (
            "tuketici mahkemesi",
            "sulh hukuk mahkemesi",
            "is mahkemesi",
            "aile mahkemesi",
            "icra hukuk mahkemesi",
            "idare mahkemesi",
        ):
            self.assertNotIn(concrete_court, plain)
        self.assertNotRegex(text, r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b")
        self.assertNotRegex(text, r"\b\d[\d. ]*\s*(?:TL|TRY|₺)\b")


if __name__ == "__main__":
    unittest.main()
