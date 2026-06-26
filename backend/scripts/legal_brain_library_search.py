#!/usr/bin/env python3
"""Legal Brain Library Search - simple keyword search over library indexes."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def _configure_utf8_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def _plain(text: str) -> str:
    import unicodedata
    normalized = str(text or "").casefold().translate(
        str.maketrans({
            "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
            "Ç": "c", "Ğ": "g", "İ": "i", "Ö": "o", "Ş": "s", "Ü": "u",
        })
    )
    decomposed = unicodedata.normalize("NFKD", normalized)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _load_index(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    project_root = Path(__file__).resolve().parents[1]
    library_dir = project_root / "app" / "legal_brain" / "library"
    main_index = library_dir / "library_index.json"
    cards = _load_index(main_index)
    if not cards:
        return []

    terms = [t for t in re.findall(r"[a-zçğıöşü]{3,}", _plain(query)) if len(t) > 2]
    if not terms:
        return cards[:limit]

    scored: list[tuple[int, dict[str, Any]]] = []
    for card in cards:
        haystack = " ".join([
            str(card.get("summary") or ""),
            str(card.get("legal_area") or ""),
            str(card.get("case_type") or ""),
            " ".join(card.get("keywords", []) or []),
            str(card.get("code") or ""),
            str(card.get("article_no") or ""),
            str(card.get("court") or ""),
            str(card.get("esas_no") or ""),
            str(card.get("karar_no") or ""),
        ])
        plain_haystack = _plain(haystack)
        score = sum(1 for term in terms if term in plain_haystack)
        if score:
            scored.append((score, card))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [card for _, card in scored[:limit]]


def _print_card(card: dict[str, Any]) -> None:
    print("----------------------------------------")
    print(f"card_id          : {card.get('card_id')}")
    print(f"card_type        : {card.get('card_type')}")
    print(f"source_type      : {card.get('source_type')}")
    print(f"source_reliability: {card.get('source_reliability')}")
    print(f"legal_area       : {card.get('legal_area')}")
    print(f"case_type        : {card.get('case_type')}")
    print(f"code/article_no  : {card.get('code')} {card.get('article_no') or ''}".rstrip())
    print(f"court/E.K        : {card.get('court')} {card.get('esas_no') or ''} {card.get('karar_no') or ''}".rstrip())
    print(f"library_folder   : {card.get('library_folder')}")
    print(f"summary          : {(card.get('summary') or '')[:220]}")
    print(f"safe_for_legal_basis       : {card.get('safe_for_legal_basis')}")
    print(f"safe_for_question_generation: {card.get('safe_for_question_generation')}")
    print(f"safe_for_petition_style    : {card.get('safe_for_petition_style')}")
    warnings = card.get("warnings") or []
    if warnings:
        print(f"warnings         : {warnings[0]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Legal Brain Library Search")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--limit", type=int, default=10, help="Max results")
    args = parser.parse_args()

    _configure_utf8_stdout()
    results = search(args.query, limit=args.limit)
    if not results:
        print("Sonuç bulunamadı.")
        return 0
    print(f"Bulunan sonuç sayısı: {len(results)}")
    for card in results:
        _print_card(card)
    return 0


if __name__ == "__main__":
    sys.exit(main())