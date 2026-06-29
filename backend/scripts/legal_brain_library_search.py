#!/usr/bin/env python3
"""Legal Brain Library Search - simple keyword search over library indexes."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


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
        if isinstance(data, dict):
            for key in ("cards", "items", "entries"):
                if isinstance(data.get(key), list):
                    return data[key]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _load_foundation_seed(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("cards"), list):
            return []
        defaults = data.get("defaults") if isinstance(data.get("defaults"), dict) else {}
        cards: list[dict[str, Any]] = []
        for item in data["cards"]:
            if not isinstance(item, dict):
                continue
            card = {**defaults, **item}
            card.setdefault("legal_area", card.get("title", ""))
            card.setdefault("source_file", "metadata/legal_foundation_seed.json")
            cards.append(card)
        return cards
    except (OSError, json.JSONDecodeError, TypeError):
        return []


def search(query: str, limit: int = 10) -> list[dict[str, Any]]:
    project_root = Path(__file__).resolve().parents[1]
    library_dir = project_root / "app" / "legal_brain" / "library"
    foundation_seed = project_root / "app" / "legal_brain" / "metadata" / "legal_foundation_seed.json"
    cards: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    index_paths = [library_dir / "library_index.json", library_dir / "internet_source_index.json"]
    index_paths.extend(sorted(library_dir.glob("*_index.json")))
    for index_path in dict.fromkeys(index_paths):
        for card in _load_index(index_path):
            if not isinstance(card, dict):
                continue
            card_id = str(card.get("card_id") or "")
            if not card_id:
                continue
            if card_id in by_id:
                by_id[card_id].update({k: v for k, v in card.items() if v not in (None, "", [])})
            else:
                by_id[card_id] = dict(card)
    for card in _load_foundation_seed(foundation_seed):
        card_id = str(card.get("card_id") or "")
        if not card_id:
            continue
        if card_id in by_id:
            by_id[card_id].update(card)
        else:
            by_id[card_id] = card
    cards.extend(by_id.values())

    if not cards:
        return []

    terms = [t for t in re.findall(r"[a-zçğıöşü]{3,}", _plain(query)) if len(t) > 2]
    if not terms:
        return cards[:limit]

    scored: list[tuple[int, dict[str, Any]]] = []
    for card in cards:
        # If this card points to a full card JSON (internet source), try to load it
        try:
            card_path = card.get("card_path")
            if card_path:
                p = Path(card_path)
                if not p.is_absolute():
                    p = library_dir / p
                if p.exists():
                    try:
                        full = json.loads(p.read_text(encoding="utf-8"))
                        if isinstance(full, dict):
                            # Merge fields from full card into the index entry for richer haystack
                            card.update(full)
                    except Exception:
                        pass
            elif card.get("card_id"):
                candidates = list(library_dir.glob(f"**/{card['card_id']}.json"))
                if candidates:
                    full = json.loads(candidates[0].read_text(encoding="utf-8"))
                    if isinstance(full, dict):
                        card.update(full)
        except Exception:
            pass
        haystack = " ".join([
            str(card.get("title") or card.get("summary") or ""),
            str(card.get("source_url") or ""),
            str(card.get("source_path") or card.get("source_file") or ""),
            str(card.get("source_type") or ""),
            str(card.get("content") or ""),
            str(card.get("text") or ""),
            str(card.get("chunk_text") or ""),
            str(card.get("summary") or ""),
            str(card.get("excerpt") or ""),
            " ".join(card.get("primary_statutes", []) or []),
            " ".join(card.get("expected_rules", []) or []),
            " ".join(card.get("expected_questions", []) or []),
            " ".join(card.get("tags", []) or []),
            " ".join(card.get("keywords", []) or []),
            str(card.get("legal_area") or ""),
            str(card.get("case_type") or ""),
            str(card.get("code") or ""),
            str(card.get("article_no") or ""),
            str(card.get("court") or ""),
            str(card.get("esas_no") or ""),
            str(card.get("karar_no") or ""),
            str(card.get("area_id") or ""),
            str(card.get("description") or ""),
            " ".join(card.get("core_concepts", []) or []),
            " ".join(card.get("typical_disputes", []) or []),
            " ".join(card.get("required_facts", []) or []),
            " ".join(card.get("common_evidence", []) or []),
            " ".join(card.get("common_risks", []) or []),
            " ".join(card.get("limitation_or_deadline_risks", []) or []),
            " ".join(card.get("possible_claims_or_remedies", []) or []),
            " ".join(card.get("related_statutes", []) or []),
            " ".join(card.get("related_procedures", []) or []),
            " ".join(card.get("search_keywords", []) or []),
            " ".join(card.get("issue_spotting_signals", []) or []),
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
