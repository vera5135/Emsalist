#!/usr/bin/env python3
"""Legal Brain agent search CLI.

Usage:
    python backend/scripts/legal_brain_agent_search.py "komşu gürültü müdahalenin önlenmesi"
    python backend/scripts/legal_brain_agent_search.py "kiracı kira ödemiyor TBK 315"
    python backend/scripts/legal_brain_agent_search.py "yoksulluk nafakası kaldırılması TMK 176"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure backend root is importable when run as a script.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.legal_brain_learning_agent import legal_brain_learning_agent  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("Kullanım: python backend/scripts/legal_brain_agent_search.py \"sorgu metni\"")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    print(f"Sorgu: {query}")
    print("-" * 60)

    results = legal_brain_learning_agent.search_legal_memory(query=query, limit=10)

    if not results:
        print("İlgili kart bulunamadı.")
        return

    for index, card in enumerate(results, start=1):
        print(f"{index}. {card.get('card_id', 'N/A')}")
        print(f"   Tür            : {card.get('card_type', 'N/A')}")
        print(f"   Hukuk alanı    : {card.get('legal_area', 'N/A')}")
        print(f"   Güvenilirlik   : {card.get('source_reliability', 'N/A')}")
        print(f"   Kaynak dosya   : {card.get('source_file', 'N/A')}")
        print(f"   Kaynak klasörü : {card.get('source_folder', 'N/A')}")
        print(f"   Learning value : {card.get('learning_value', 'N/A')}")
        summary = card.get("summary") or card.get("doctrine_summary") or card.get("article_text", "")
        try:
            print(f"   Özet           : {str(summary)[:180]}...")
        except UnicodeEncodeError:
            print(f"   Özet           : [Özet yüklenemedi]")
        if card.get("question_suggestions"):
            q = card["question_suggestions"][0]
            print(f"   Önerilen soru  : {q.get('question', 'N/A')}")
        if card.get("esas_no") and card.get("esas_no") != "unknown":
            print(f"   Esas no        : {card.get('esas_no')}")
        if card.get("karar_no") and card.get("karar_no") != "unknown":
            print(f"   Karar no       : {card.get('karar_no')}")
        if card.get("court"):
            print(f"   Mahkeme        : {card.get('court')}")
        if card.get("article_no"):
            print(f"   Madde no       : {card.get('article_no')}")
        print(f"   Güvenli kullanım:")
        print(f"     - Hukuki dayanak    : {'Evet' if card.get('safe_for_legal_basis') else 'Hayır'}")
        print(f"     - Soru üretimi      : {'Evet' if card.get('safe_for_question_generation') else 'Hayır'}")
        print(f"     - Dilekçe stili     : {'Evet' if card.get('safe_for_petition_style') else 'Hayır'}")
        if card.get("warnings"):
            try:
                print(f"   Uyarılar       : {', '.join(card['warnings'][:2])}")
            except UnicodeEncodeError:
                print(f"   Uyarılar       : [Uyarılar yüklenemedi]")
        print()


if __name__ == "__main__":
    main()