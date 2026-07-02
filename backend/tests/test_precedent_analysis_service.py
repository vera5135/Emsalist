from __future__ import annotations

import unittest

from app.services.precedent_analysis_service import precedent_analysis_service


CASE_TEXT = "Müvekkil ikinci el aracı satın aldıktan kısa süre sonra araçta motor arızası ortaya çıkmıştır. Gizli ayıp nedeniyle bedel iadesi talep edilmektedir."


class PrecedentAnalysisServiceTests(unittest.TestCase):
    def test_procedural_signals_do_not_become_direct_support(self) -> None:
        analysis = precedent_analysis_service.analyze(
            case_text=CASE_TEXT,
            decision={
                "court": "Yargıtay 3. Hukuk Dairesi",
                "esas_no": "2020/226",
                "karar_no": "2020/196",
                "date": "09.01.2020",
                "short_summary": "Dosyanın 13. Hukuk Dairesine gönderilmesine ve inceleme görevi yönünden ön inceleme yapılmasına.",
                "petition_paragraph": "Dosyanın görevli daireye gönderilmesine karar verilmiştir.",
                "similarity_score": 74,
            },
        )
        self.assertIn(analysis.precedent_use_class, {"procedural_or_jurisdiction_only", "distinguishable"})
        self.assertNotEqual(analysis.precedent_use_class, "direct_support")

    def test_substantive_hidden_defect_signals_are_supportive(self) -> None:
        analysis = precedent_analysis_service.analyze(
            case_text=CASE_TEXT,
            decision={
                "court": "Yargıtay 19. Hukuk Dairesi",
                "esas_no": "2013/17670",
                "karar_no": "2014/508",
                "date": "15.01.2014",
                "short_summary": "Kısa süre sonra araçta motor arızası çıkması üzerine servise başvuru, ihtarname ve bilirkişi incelemesi değerlendirilmiştir.",
                "petition_paragraph": "Aracın gizli ayıplı olduğu, servise başvuru, ihtarname ve bilirkişi raporuyla değerlendirilmiştir.",
                "similarity_score": 82,
            },
        )
        self.assertIn(analysis.precedent_use_class, {"direct_support", "supporting_with_caution"})

    def test_short_or_cut_summary_is_not_direct_support(self) -> None:
        analysis = precedent_analysis_service.analyze(
            case_text=CASE_TEXT,
            decision={
                "court": "Yargıtay 13. Hukuk Dairesi",
                "esas_no": "2012/11016",
                "karar_no": "2012/20281",
                "date": "10.10.2012",
                "short_summary": "Davacı; davalıdan satın aldığı ve diğer davalının ithalatçısı olduğu",
                "petition_paragraph": "Davacı; davalıdan satın aldığı ve diğer davalının ithalatçısı olduğu",
                "similarity_score": 77,
            },
        )
        self.assertIn(analysis.precedent_use_class, {"insufficient_summary", "supporting_with_caution"})
        self.assertNotEqual(analysis.precedent_use_class, "direct_support")


if __name__ == "__main__":
    unittest.main()
