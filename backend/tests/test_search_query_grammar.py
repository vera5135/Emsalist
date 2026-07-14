# -*- coding: utf-8 -*-
"""P2.7 — Deterministic search query grammar tests.

Covers the mandatory grammar test matrix (addendum Section J), the semantic
bypass / missing-required regressions (Section K), and a provider-agnostic
multi-source-type benchmark (Section L + parallel-development addendum).

These tests are pure: no DB, no network, no LLM, no embeddings. The corpus is
provider-agnostic canonical P2.6-shaped data (source_type / court / text);
trust is never inferred from any provider code.
"""
from __future__ import annotations

import pytest

from app.services.search_query_grammar import (
    MalformedQueryError,
    SearchQueryPlan,
    filter_candidates,
    normalize_phrase,
    parse_query,
    phrase_matches,
    term_matches,
)


# --- J.1 PLAIN TERMS -> optional terms, OR behavior -----------------------
def test_plain_terms_are_optional_or_not_mandatory_and():
    plan = parse_query("arsa payı")
    assert plan.optional_terms == ["arsa", "payı"]
    assert plan.required_terms == []
    assert plan.required_phrases == []
    # Whitespace is NOT mandatory AND: a doc with only one term is not filtered
    # out (no hard constraints exist).
    assert plan.has_constraints() is False
    assert plan.matches("burada yalnızca arsa geçiyor") is True


# --- J.2 SINGLE QUOTED PHRASE -> one exact optional phrase ----------------
def test_single_quoted_phrase():
    plan = parse_query('"arsa payı"')
    assert plan.optional_phrases == ["arsa payı"]
    assert plan.optional_terms == []
    assert phrase_matches("arsa payı", "sözleşmede arsa payı belirtilmiştir")


# --- J.3 MULTIPLE OPTIONAL PHRASES -> phrase OR ---------------------------
def test_multiple_optional_phrases_or():
    plan = parse_query('"arsa payı" "bozma sebebi"')
    assert plan.optional_phrases == ["arsa payı", "bozma sebebi"]
    assert plan.required_phrases == []
    assert plan.has_constraints() is False


# --- J.4 REQUIRED PHRASES -> both mandatory (AND) -------------------------
def test_required_phrases_are_conjunctive():
    plan = parse_query('+"arsa payı" +"bozma sebebi"')
    assert plan.required_phrases == ["arsa payı", "bozma sebebi"]
    assert plan.matches("arsa payı ve ayrıca bozma sebebi vardır") is True
    assert plan.matches("yalnızca arsa payı geçiyor") is False
    assert plan.matches("yalnızca bozma sebebi geçiyor") is False


# --- J.5 REQUIRED + EXCLUDED ----------------------------------------------
def test_required_plus_excluded():
    plan = parse_query('+"arsa payı" -"bozma sebebi"')
    assert plan.required_phrases == ["arsa payı"]
    assert plan.excluded_phrases == ["bozma sebebi"]
    assert plan.matches("arsa payı hesaplaması") is True
    assert plan.matches("arsa payı ve bozma sebebi birlikte") is False
    assert plan.matches("bozma sebebi tek başına") is False


# --- J.6 MULTIPLE REQUIRED + EXCLUDED -------------------------------------
def test_multiple_required_and_excluded():
    plan = parse_query('+"arsa payı" +"inşaat sözleşmesi" -"bozma sebebi"')
    assert plan.required_phrases == ["arsa payı", "inşaat sözleşmesi"]
    assert plan.excluded_phrases == ["bozma sebebi"]
    ok = "arsa payı karşılığı inşaat sözleşmesi düzenlendi"
    assert plan.matches(ok) is True
    assert plan.matches(ok + " ancak bozma sebebi de var") is False
    assert plan.matches("arsa payı var ama inşaat yok") is False


# --- J.7 SEMANTIC BYPASS REGRESSION ---------------------------------------
def test_semantic_bypass_regression_excluded_phrase_cannot_be_rescued():
    plan = parse_query('+"arsa payı" -"bozma sebebi"')
    # A candidate with (hypothetically) perfect semantic similarity that
    # nevertheless contains the excluded phrase MUST be excluded.
    candidate = {
        "text": "arsa payı karşılığı inşaat; temyiz incelemesinde bozma sebebi görüldü",
        "semantic_score": 1.0,
        "lexical_score": 1.0,
    }
    assert plan.matches(candidate["text"]) is False
    kept = filter_candidates(plan, [candidate], text_getter=lambda c: c["text"])
    assert kept == []


# --- J.8 MISSING REQUIRED REGRESSION --------------------------------------
def test_missing_required_regression_high_score_cannot_rescue():
    plan = parse_query('+"arsa payı"')
    candidate = {
        "text": "kat karşılığı inşaat ve tapu payı üzerine çok benzer bir karar",
        "semantic_score": 0.99,
        "lexical_score": 0.9,
    }
    # The exact phrase "arsa payı" does not occur contiguously.
    assert plan.matches(candidate["text"]) is False
    assert filter_candidates(plan, [candidate], text_getter=lambda c: c["text"]) == []


# --- J.9 PHRASE VS TERMS --------------------------------------------------
def test_phrase_does_not_match_separated_tokens():
    text = "arsanın büyük bölümünde imar payı ayrı ayrı geçiyor"
    assert phrase_matches("arsa payı", text) is False
    # But both tokens are individually present:
    assert term_matches("payı", text) is True


# --- J.10 MALFORMED QUOTES ------------------------------------------------
@pytest.mark.parametrize("bad", ['"arsa payı', '+"arsa payı', '-"bozma', 'foo "bar'])
def test_malformed_unterminated_quote_raises(bad):
    with pytest.raises(MalformedQueryError) as exc:
        parse_query(bad)
    assert exc.value.reason == "unterminated_quote"


@pytest.mark.parametrize("bad", ["+", "-", "arsa +", 'x + "y"'])
def test_malformed_dangling_operator_raises(bad):
    with pytest.raises(MalformedQueryError) as exc:
        parse_query(bad)
    assert exc.value.reason == "dangling_operator"


# --- J.11 TURKISH CASING --------------------------------------------------
def test_turkish_casing_normalizes_compatibly():
    assert normalize_phrase("ARSA PAYI") == "arsa payı"
    assert normalize_phrase("arsa payı") == "arsa payı"
    plan = parse_query('"ARSA PAYI"')
    assert plan.optional_phrases == ["arsa payı"]
    assert phrase_matches("ARSA PAYI", "dosyada arsa payı geçmektedir")


# --- J.12 WHITESPACE ------------------------------------------------------
def test_bounded_whitespace_normalization():
    assert normalize_phrase("arsa   payı") == "arsa payı"
    plan = parse_query('"arsa   payı"')
    assert plan.optional_phrases == ["arsa payı"]


# --- J.13 CITATION COEXISTENCE --------------------------------------------
def test_citation_coexists_with_phrase_grammar():
    plan = parse_query('+"gizli ayıp" "E. 2020/123"')
    assert plan.required_phrases == ["gizli ayıp"]
    assert "arsa" not in plan.required_phrases
    assert "E. 2020/123" in plan.exact_citation_candidates
    assert "2020/123" in plan.exact_citation_candidates


def test_article_and_legislation_candidates():
    plan = parse_query("TBK 227 6098 sayılı kanun madde 12")
    assert "TBK 227" in plan.article_candidates
    assert "regular:12" in plan.article_candidates
    assert "6098 sayılı" in plan.legislation_number_candidates


# --- Query plan hygiene ---------------------------------------------------
def test_raw_query_transient_not_in_safe_summary():
    plan = parse_query('+"arsa payı" -"bozma sebebi"')
    assert plan.raw_query_transient == '+"arsa payı" -"bozma sebebi"'
    summary = plan.safe_summary()
    assert "raw_query_transient" not in summary
    assert summary["required_phrase_count"] == 1
    assert summary["excluded_phrase_count"] == 1


def test_semantic_query_derivation_strips_operators():
    plan = parse_query('+"arsa payı" -"bozma sebebi" inşaat')
    sem = plan.semantic_query()
    # No plus/minus/quotes leak into the semantic query text.
    assert "+" not in sem and "-" not in sem and '"' not in sem
    assert "arsa payı" in sem
    assert "inşaat" in sem
    # The excluded phrase must not be part of the positive semantic query.
    assert "bozma sebebi" not in sem


def test_required_term_and_excluded_term_unquoted():
    plan = parse_query("+nafaka -boşanma tazminat")
    assert plan.required_terms == ["nafaka"]
    assert plan.excluded_terms == ["boşanma"]
    assert plan.optional_terms == ["tazminat"]
    assert plan.matches("nafaka ve tazminat talebi") is True
    assert plan.matches("nafaka ve boşanma davası") is False
    assert plan.matches("yalnızca tazminat") is False


def test_explanation_is_human_readable_not_internal():
    plan = parse_query('+"arsa payı" -"bozma sebebi"')
    reasons = plan.explain_match("arsa payı hesabı yapıldı")
    assert any("arsa payı" in r for r in reasons)
    # No AST / token IDs / BM25 internals leak to users.
    joined = " ".join(reasons)
    for forbidden in ("token", "ast", "bm25", "node_id"):
        assert forbidden not in joined.lower()


# ======================================================================
# Section L + parallel-development addendum: multi-source-type benchmark.
# Provider-agnostic canonical corpus. Trust/provider is NOT encoded here;
# these fixtures only carry canonical source_type / court / text and a
# nominal semantic_score used to prove hard constraints beat similarity.
# ======================================================================
def _corpus() -> list[dict]:
    return [
        {
            "id": "yarg-1",
            "source_type": "supreme_court_decision",
            "court": "Yargıtay",
            "text": "arsa payı karşılığı inşaat sözleşmesi kapsamında arsa payı devri",
            "semantic_score": 0.70,
        },
        {
            "id": "yarg-2",
            "source_type": "supreme_court_decision",
            "court": "Yargıtay",
            "text": "arsa payı karşılığı inşaat sözleşmesinin bozma sebebi yapılması",
            "semantic_score": 0.95,
        },
        {
            "id": "danistay-1",
            "source_type": "council_of_state_decision",
            "court": "Danıştay",
            "text": "idari işlemin iptali ve idari yargı yetkisi bakımından değerlendirme",
            "semantic_score": 0.30,
        },
        {
            "id": "danistay-2",
            "source_type": "council_of_state_decision",
            "court": "Danıştay",
            # Superficially similar phrasing but wrong legal domain; must not win
            # a consumer-defect query merely on similarity.
            "text": "kamu ihalesinde arsa tahsisi ve idari sözleşme uyuşmazlığı payı",
            "semantic_score": 0.99,
        },
        {
            "id": "aym-1",
            "source_type": "constitutional_court_decision",
            "court": "Anayasa Mahkemesi",
            "text": "mülkiyet hakkı ihlali ve adil yargılanma hakkı bireysel başvuru",
            "semantic_score": 0.40,
        },
        {
            "id": "uyusmazlik-1",
            "source_type": "court_of_jurisdictional_disputes_decision",
            "court": "Uyuşmazlık Mahkemesi",
            "text": "adli ve idari yargı arasında görev uyuşmazlığı çözümü",
            "semantic_score": 0.35,
        },
        {
            "id": "mevzuat-1",
            "source_type": "legislation",
            "court": "",  # legislation has no court/chamber — must stay empty, not fabricated
            "text": "TBK 227 ayıplı ifada alıcının seçimlik hakları bedel indirimi",
            "semantic_score": 0.55,
        },
    ]


def _by_source_type(results: list[dict]) -> dict[str, int]:
    dist: dict[str, int] = {}
    for r in results:
        dist[r["source_type"]] = dist.get(r["source_type"], 0) + 1
    return dist


BENCHMARK_QUERIES = [
    "arsa payı",
    '"arsa payı"',
    '"arsa payı" "bozma sebebi"',
    '+"arsa payı" +"bozma sebebi"',
    '+"arsa payı" -"bozma sebebi"',
    '+"arsa payı" +"inşaat sözleşmesi" -"bozma sebebi"',
]


def _run(query: str) -> set[str]:
    plan = parse_query(query)
    kept = filter_candidates(plan, _corpus(), text_getter=lambda c: c["text"])
    return {c["id"] for c in kept}


def test_benchmark_operator_scenarios_produce_materially_different_sets():
    result_sets = {q: _run(q) for q in BENCHMARK_QUERIES}
    # Not all six queries may return identical documents.
    distinct = {frozenset(s) for s in result_sets.values()}
    assert len(distinct) >= 3, result_sets

    # Required-only tightens vs excluded variant.
    assert result_sets['+"arsa payı" +"bozma sebebi"'] == {"yarg-2"}
    assert result_sets['+"arsa payı" -"bozma sebebi"'] == {"yarg-1"}
    assert result_sets['+"arsa payı" +"inşaat sözleşmesi" -"bozma sebebi"'] == {"yarg-1"}


def test_benchmark_source_type_competition_semantic_does_not_bypass_constraint():
    # The highest semantic_score candidate (danistay-2 @ 0.99) is administrative
    # law and lacks the required phrase; it must NOT survive the consumer query.
    plan = parse_query('+"arsa payı" -"bozma sebebi"')
    kept = filter_candidates(plan, _corpus(), text_getter=lambda c: c["text"])
    ids = {c["id"] for c in kept}
    assert "danistay-2" not in ids
    assert ids == {"yarg-1"}


def test_benchmark_corpus_is_not_yargitay_only():
    types = {c["source_type"] for c in _corpus()}
    assert {
        "supreme_court_decision",
        "council_of_state_decision",
        "constitutional_court_decision",
        "court_of_jurisdictional_disputes_decision",
        "legislation",
    } <= types


def test_benchmark_legislation_exact_lookup():
    # Exact article query must be able to surface the canonical legislation
    # source (and yields an article candidate deterministically).
    plan = parse_query('+"TBK 227"')
    assert "TBK 227" in plan.article_candidates
    kept = filter_candidates(plan, _corpus(), text_getter=lambda c: c["text"])
    assert {c["id"] for c in kept} == {"mevzuat-1"}
    assert kept[0]["source_type"] == "legislation"


def test_benchmark_result_distribution_by_source_type_is_reportable():
    plan = parse_query('"arsa" "idari" "mülkiyet"')  # optional -> no hard filter
    kept = filter_candidates(plan, _corpus(), text_getter=lambda c: c["text"])
    dist = _by_source_type(kept)
    # All source types remain representable in the generic model.
    assert dist["legislation"] >= 1
    assert dist["council_of_state_decision"] >= 1


def test_legislation_has_no_fabricated_decision_identifiers():
    leg = next(c for c in _corpus() if c["source_type"] == "legislation")
    # Legislation must not carry a fabricated court/case_number/decision_number.
    assert leg.get("court", "") == ""
    assert "case_number" not in leg
    assert "decision_number" not in leg
