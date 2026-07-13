"""Focused P2.6C article subtype and citable locator regressions."""
from __future__ import annotations

import pytest

from app.services.source_paragraphs import (
    ARTICLE_BEARING_SOURCE_TYPES,
    ARTICLE_KIND_ADDITIONAL,
    ARTICLE_KIND_PROVISIONAL,
    ARTICLE_KIND_REGULAR,
    ARTICLE_KIND_REPEATED,
    ARTICLE_LOCATOR_METHOD,
    ARTICLE_LOCATOR_VERSION,
    build_article_locator,
    controlled_article_locator,
    normalize_article_number,
    parse_article_heading,
    split_paragraphs,
)


@pytest.mark.parametrize(("heading", "kind", "number", "label"), [
    ("Madde 1", ARTICLE_KIND_REGULAR, "1", "Madde 1"),
    ("MADDE 1", ARTICLE_KIND_REGULAR, "1", "Madde 1"),
    ("M. 1", ARTICLE_KIND_REGULAR, "1", "Madde 1"),
    ("Ek Madde 1", ARTICLE_KIND_ADDITIONAL, "1", "Ek Madde 1"),
    ("EK MADDE 1", ARTICLE_KIND_ADDITIONAL, "1", "Ek Madde 1"),
    ("Ek Madde 2/A", ARTICLE_KIND_ADDITIONAL, "2/A", "Ek Madde 2/A"),
    ("Geçici Madde 1", ARTICLE_KIND_PROVISIONAL, "1", "Geçici Madde 1"),
    ("GEÇİCİ MADDE 1/A", ARTICLE_KIND_PROVISIONAL, "1/A", "Geçici Madde 1/A"),
    ("Mükerrer Madde 1", ARTICLE_KIND_REPEATED, "1", "Mükerrer Madde 1"),
    ("MÜKERRER MADDE 1", ARTICLE_KIND_REPEATED, "1", "Mükerrer Madde 1"),
])
def test_anchored_article_heading_vocabulary(heading, kind, number, label):
    locator = parse_article_heading(heading)
    assert locator is not None
    assert locator.article_kind == kind
    assert locator.article_number == number
    assert locator.article_label == label


@pytest.mark.parametrize("text", [
    "Bu düzenlemenin geçici madde 1 hükmüne göre işlem yapılır.",
    "01.01.2026",
    "2024/123",
    "GEÇİCİ MADDE",
    "Madde arama",
])
def test_non_heading_text_does_not_create_locator(text):
    assert parse_article_heading(text) is None


def test_article_number_normalization_preserves_identity():
    assert normalize_article_number("1") == "1"
    assert normalize_article_number("01") == "01"
    assert normalize_article_number("1 / A") == "1/A"
    assert normalize_article_number("1/a") == "1/A"
    assert normalize_article_number("") is None


def test_same_number_cross_kind_keys_do_not_collide():
    regular = build_article_locator(ARTICLE_KIND_REGULAR, "1")
    provisional = build_article_locator(ARTICLE_KIND_PROVISIONAL, "1")
    assert regular.article_locator_key == "regular_article:1"
    assert provisional.article_locator_key == "provisional_article:1"
    assert regular.article_locator_key != provisional.article_locator_key


def test_locator_json_has_only_controlled_provenance_keys():
    locator = build_article_locator(ARTICLE_KIND_PROVISIONAL, "1/A")
    assert locator.to_json() == {
        "locator_type": "article",
        "article_kind": "provisional_article",
        "article_number": "1/A",
        "article_label": "Geçici Madde 1/A",
        "article_locator_key": "provisional_article:1/A",
        "article_locator_method": ARTICLE_LOCATOR_METHOD,
        "article_locator_version": ARTICLE_LOCATOR_VERSION,
    }


def test_split_preserves_body_and_canonical_heading_path():
    paragraphs = split_paragraphs(
        "legislation",
        "Başlangıç metni.\nMadde 1\nBirinci gövde.\nGeçici Madde 1\nGeçici gövde.",
    )
    assert len(paragraphs) == 3
    assert paragraphs[1].heading_path == "Madde 1"
    assert paragraphs[1].text == "Madde 1 Birinci gövde."
    assert paragraphs[2].heading_path == "Geçici Madde 1"
    assert paragraphs[2].text == "Geçici Madde 1 Geçici gövde."


def test_official_gazette_issue_is_not_article_bearing():
    assert "official_gazette_issue" not in ARTICLE_BEARING_SOURCE_TYPES
    paragraphs = split_paragraphs(
        "official_gazette_issue",
        "Madde 1\nBu bir yayımlanmış enstrümanın metnidir.",
    )
    assert len(paragraphs) == 1
    assert paragraphs[0].article_number == ""
    assert paragraphs[0].heading_path == ""
    assert paragraphs[0].locator_json == {}


@pytest.mark.parametrize("source_type", sorted(ARTICLE_BEARING_SOURCE_TYPES))
def test_each_controlled_instrument_type_is_article_aware(source_type):
    paragraph = split_paragraphs(source_type, "Ek Madde 2/A\nEk hüküm.")[0]
    assert paragraph.article_number == "2/A"
    assert paragraph.locator_json["article_kind"] == ARTICLE_KIND_ADDITIONAL


def test_unknown_or_incoherent_locator_data_fails_closed():
    valid = build_article_locator(ARTICLE_KIND_REGULAR, "1").to_json()
    assert controlled_article_locator(valid, stored_article_number="1") is not None

    unknown = {**valid, "article_kind": "provider_supplied_kind"}
    assert controlled_article_locator(unknown, stored_article_number="1") is None

    mismatched = {**valid, "article_locator_key": "provisional_article:1"}
    assert controlled_article_locator(mismatched, stored_article_number="1") is None

    assert controlled_article_locator({}, stored_article_number="1") is None
    assert controlled_article_locator(valid, stored_article_number="2") is None


def test_arbitrary_article_kind_is_rejected():
    with pytest.raises(ValueError, match="unknown article kind"):
        build_article_locator("provider_metadata_kind", "1")
