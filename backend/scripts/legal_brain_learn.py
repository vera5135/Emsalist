#!/usr/bin/env python3
"""Legal Brain learning agent CLI.

Usage:
    python backend/scripts/legal_brain_learn.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure backend root is importable when run as a script.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.legal_brain_learning_agent import legal_brain_learning_agent  # noqa: E402


def main() -> None:
    print("Legal Brain öğrenme ajanı başlatıldı.")
    print(f"Kaynak klasörü: {(BACKEND_ROOT / 'app' / 'legal_brain' / 'uploads').resolve()}")
    print("-" * 60)

    result = legal_brain_learning_agent.learn_from_uploads()

    print(f"Kaynak dosya sayısı        : {result.get('sources_seen', 0)}")
    print(f"Öğrenilen kaynak sayısı    : {result.get('sources_learned', 0)}")
    print(f"Atlanan kaynak sayısı      : {result.get('sources_skipped', 0)}")
    print(f"Oluşturulan kart sayısı    : {result.get('cards_created', 0)}")
    print(f"Kanun maddesi kartları     : {result.get('statute_cards', 0)}")
    print(f"İçtihat kartları           : {result.get('case_law_cards', 0)}")
    print(f"Doktrin kartları           : {result.get('doctrine_cards', 0)}")
    print(f"Soru önerisi sayısı       : {result.get('question_count', 0)}")
    print(f"Yüksek güvenilirlik kaynak: {result.get('high_reliability_sources', 0)}")
    print(f"Orta güvenilirlik kaynak  : {result.get('medium_reliability_sources', 0)}")
    print(f"Düşük güvenilirlik kaynak : {result.get('low_reliability_sources', 0)}")
    
    report = result.get("learning_report", {})
    if report:
        print("\nKaynak dağılımı:")
        print(f"  Klasörlere göre  : {report.get('sources_by_folder', {})}")
        print(f"  Türlere göre     : {report.get('sources_by_type', {})}")
        print(f"  Güvenilirliğe göre: {report.get('sources_by_reliability', {})}")
        print(f"  Dava türlerine göre: {report.get('cards_by_case_type', {})}")
        
        best_sources = report.get("best_learning_sources", [])
        if best_sources:
            print("\nEn iyi öğrenme kaynakları:")
            for src in best_sources[:3]:
                print(f"  - {src.get('folder')}: {src.get('count')} kart")
        
        weak_areas = report.get("weak_areas", [])
        if weak_areas:
            print("\nZayıf alanlar (ek kaynak gerekli):")
            for area in weak_areas[:5]:
                print(f"  - {area}")

    warnings = result.get("warnings", [])
    if warnings:
        print("\nUyarılar:")
        for warning in warnings:
            print(f"  - {warning}")

    recommendations = result.get("next_recommended_sources", [])
    if recommendations:
        print("\nSonraki önerilen kaynaklar:")
        for rec in recommendations[:5]:
            print(f"  - {rec}")


if __name__ == "__main__":
    main()