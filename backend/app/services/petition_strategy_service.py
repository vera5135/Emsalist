"""Rule-based petition strategy generation."""

from app.models.petition_models import PetitionStrategyDecision, PetitionStrategyResponse
from app.services.legal_retrieval_service import legal_retrieval_service
from app.services.petition_profile_service import get_petition_profile


RECOMMENDED_TONE = "Ölçülü ve ikna edici"


class PetitionStrategyService:
    """Create a concise litigation strategy from the case text and chosen decisions."""

    def build_strategy(
        self,
        *,
        case_text: str,
        top_decisions: list[PetitionStrategyDecision],
    ) -> PetitionStrategyResponse:
        profile = get_petition_profile(case_text)
        legal_memory = legal_retrieval_service.retrieve_for_case(
            case_text=case_text,
            practice_area=profile.practice_area,
            max_sources=6,
        )
        lehe_count = self._count_by_alignment(top_decisions, "Lehe")
        aleyhe_count = self._count_by_alignment(top_decisions, "Aleyhe")
        notr_count = self._count_by_alignment(top_decisions, "Nötr")
        high_value_decisions = [
            decision
            for decision in top_decisions
            if decision.lehe_aleyhe.casefold() == "lehe" and decision.similarity_score >= 75
        ]

        return PetitionStrategyResponse(
            petition_type=profile.petition_type,
            strategy_summary=self._strategy_summary(
                profile_type=profile.petition_type,
                lehe_count=lehe_count,
                aleyhe_count=aleyhe_count,
                notr_count=notr_count,
                high_value_decisions=high_value_decisions,
                legal_memory_arguments=legal_memory.recommended_arguments,
            ),
            recommended_tone=RECOMMENDED_TONE,
            legal_basis=self._legal_basis(profile.legal_basis, legal_memory.statute_sources),
            missing_information_questions=self._missing_information_questions(
                base_questions=profile.questions,
                arguments=legal_memory.recommended_arguments,
            ),
            petition_skeleton=list(profile.skeleton),
            risk_notes=self._risk_notes(
                base_notes=profile.risk_notes,
                top_decisions=top_decisions,
                legal_brain_warnings=legal_memory.warnings,
            ),
        )

    @staticmethod
    def _strategy_summary(
        *,
        profile_type: str,
        lehe_count: int,
        aleyhe_count: int,
        notr_count: int,
        high_value_decisions: list[PetitionStrategyDecision],
        legal_memory_arguments: list[str],
    ) -> str:
        decision_note = (
            f"Araştırma sonucunda {lehe_count} lehe, {aleyhe_count} aleyhe/riskli ve "
            f"{notr_count} nötr karar sinyali görülmektedir."
            if lehe_count + aleyhe_count + notr_count
            else "Henüz seçilmiş emsal karar bulunmadığından strateji olay, delil ve ilgili mevzuat üzerine kurulmalıdır."
        )
        strongest = ""
        if high_value_decisions:
            identities = ", ".join(
                f"{decision.court} E. {decision.esas_no}, K. {decision.karar_no}"
                for decision in high_value_decisions[:2]
            )
            strongest = f" Özellikle {identities} kararları dilekçede ana destek olarak kullanılabilir."

        memory_note = ""
        if legal_memory_arguments:
            memory_note = " Legal Brain kaynaklarından çıkan ana argümanlar: " + " ".join(legal_memory_arguments[:3])

        return (
            f"Temel strateji, {profile_type} bakımından talebi doğuran maddi vakıaların tarih, kişi, belge ve delil "
            f"bağlantısıyla somutlaştırılmasıdır. Dilekçe; olay anlatımı, hukuki dayanak, emsal içtihat ve delil "
            f"bölümleri arasında kopukluk bırakmadan kurulmalıdır. {decision_note}{strongest}{memory_note}"
        )

    @staticmethod
    def _risk_notes(
        *,
        base_notes: tuple[str, ...],
        top_decisions: list[PetitionStrategyDecision],
        legal_brain_warnings: list[str],
    ) -> list[str]:
        notes = list(base_notes)
        if any("aleyhe" in decision.lehe_aleyhe.casefold() for decision in top_decisions):
            notes.append("Aleyhe/riskli kararlar varsa maddi olguların bu kararlardan neden ayrıldığı açıklanmalıdır.")
        notes.extend(legal_brain_warnings)
        return list(dict.fromkeys(notes))

    @staticmethod
    def _legal_basis(base_basis: tuple[str, ...], statute_sources) -> list[str]:
        basis = list(base_basis)
        for source in statute_sources:
            label = f"{source.code} {source.article}"
            if label not in basis:
                basis.append(label)
        return basis

    @staticmethod
    def _missing_information_questions(*, base_questions: tuple[str, ...], arguments: list[str]) -> list[str]:
        questions = list(base_questions)
        combined = " ".join(arguments).casefold()
        if "ispat" in combined:
            questions.append("Bu talebi güçlendiren vakıalar hangi belgelerle ispatlanacaktır?")
        if "ödeme gücü" in combined:
            questions.append("Müvekkilin ödeme gücü veya mali durumunu gösteren kayıtlar mevcut mu?")
        return list(dict.fromkeys(questions))

    @staticmethod
    def _count_by_alignment(decisions: list[PetitionStrategyDecision], marker: str) -> int:
        marker_lower = marker.casefold()
        return sum(marker_lower in decision.lehe_aleyhe.casefold() for decision in decisions)


petition_strategy_service = PetitionStrategyService()
