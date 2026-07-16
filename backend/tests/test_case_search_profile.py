"""Core-value acceptance for natural-language case to Yargıtay search profile."""

from app.models.case_models import CaseSearchProfileRequest
from app.services.case_search_profile import DeterministicCaseSearchProfileProvider


provider = DeterministicCaseSearchProfileProvider()


def build(text: str, **kwargs):
    return provider.build(CaseSearchProfileRequest(case_text=text, **kwargs))


def test_defective_vehicle_profile_classifies_pilot_dispute():
    result = build(
        "Müvekkil ikinci el araç satın aldı. Satıştan üç gün sonra motor arızası "
        "çıktı. Satıcı arızayı kabul etmiyor ve araç satış öncesi ekspertize girdi."
    )

    assert result.legal_area == "Tüketici Hukuku / Satış Hukuku"
    assert result.dispute_type == "Ayıplı ikinci el araç satışı"
    assert result.confidence == 0.9
    assert "Alıcı" in result.party_roles
    assert "Satıcı" in result.party_roles


def test_profile_extracts_vehicle_facts_without_inventing_values():
    result = build(
        "34 ABC 123 plakalı araç 12.03.2026 tarihinde 850.000 TL bedelle satın alındı. "
        "Motor arızası daha sonra ortaya çıktı."
    )

    joined = " | ".join(result.material_facts)
    assert "12.03.2026" in joined
    assert "850.000 TL" in joined
    assert "34 ABC 123" in joined
    assert result.chronology[0].date_text == "12.03.2026"


def test_profile_extracts_vin_when_explicitly_present():
    result = build(
        "İkinci el aracın şasi numarası WBA12345678901234 olarak sözleşmede yazıyor. "
        "Satıştan sonra şanzıman arızası çıktı."
    )

    assert any("WBA12345678901234" in fact for fact in result.material_facts)


def test_claims_include_requested_vehicle_remedy():
    result = build(
        "İkinci el araçta gizli ayıp çıktı. Müvekkil sözleşmeden dönmek ve satış "
        "bedelini iade almak istiyor."
    )

    assert any("Sözleşmeden dönme" in claim for claim in result.claims)
    assert any("satış bedelinin iadesi" in claim for claim in result.claims)


def test_profile_surfaces_opposing_arguments_and_evidence_needs():
    result = build(
        "İkinci el araç satıştan hemen sonra arızalandı. Ekspertiz raporunda motor "
        "sağlam görünüyordu fakat servis motorun önceden sorunlu olduğunu söyledi."
    )

    assert any("kullanım veya bakım hatası" in item for item in result.possible_defenses)
    assert any("Olumlu ekspertiz raporu" in item for item in result.possible_defenses)
    assert any("teknik bilirkişi" in item for item in result.evidence_issues)
    assert any("Servis kayıtları" in item for item in result.evidence_issues)


def test_profile_marks_missing_critical_vehicle_information():
    result = build(
        "Müvekkil ikinci el araç aldı ve motor arızası çıktı. Satıcı sorumluluğu "
        "kabul etmiyor."
    )

    assert "Satış ve teslim tarihi" in result.missing_information
    assert "Satış bedeli" in result.missing_information
    assert any("Ayıp ihbarının" in item for item in result.missing_information)
    assert any("Satıcının tacir" in item for item in result.missing_information)


def test_yargitay_queries_are_bounded_unique_and_fact_sensitive():
    result = build(
        "Galeriden alınan ikinci el aracın TRAMER kaydında ağır hasar bulundu. "
        "Müvekkil bedel iadesi ve sözleşmeden dönme talep ediyor.",
        max_queries=6,
    )

    assert 3 <= len(result.yargitay_queries) <= 6
    assert len(result.yargitay_queries) == len({q.casefold() for q in result.yargitay_queries})
    assert any("TRAMER" in query for query in result.yargitay_queries)
    assert any("sözleşmeden dönme" in query for query in result.yargitay_queries)


def test_query_limit_is_honored():
    result = build(
        "İkinci el araçta motor arızası, ağır hasar, TRAMER kaydı ve kilometre "
        "düşürülmesi tespit edildi. Sözleşmeden dönme talep ediliyor.",
        max_queries=3,
    )

    assert len(result.yargitay_queries) == 3


def test_preferred_relief_is_normalized_and_deduplicated():
    result = build(
        "İkinci el araçta gizli ayıp ve motor arızası çıktı. Satıcı kabul etmiyor.",
        preferred_relief=[" Bedel indirimi ", "bedel indirimi", "Tazminat"],
    )

    folded = [item.casefold() for item in result.claims]
    assert folded.count("bedel indirimi") == 1
    assert "tazminat" in folded


def test_nonpilot_area_fails_conservatively_with_lower_confidence():
    result = build(
        "Kiraya veren gerçek ihtiyaç nedeniyle kiralananın tahliyesini istiyor. "
        "Kiracı ihtiyacın samimi olmadığını savunuyor."
    )

    assert result.legal_area == "Kira Hukuku"
    assert result.confidence == 0.45
    assert 3 <= len(result.yargitay_queries) <= 6
    assert result.legislation_hypotheses == []
