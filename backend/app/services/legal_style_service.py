"""Legal drafting style helpers for Legal Brain enriched petitions."""

from app.models.legal_brain_models import LegalBrainRetrieveForCaseResponse


class LegalStyleService:
    """Render doctrine/statute memory in a senior-lawyer drafting style."""

    def legal_brain_section(self, memory: LegalBrainRetrieveForCaseResponse) -> str:
        if not memory.statute_sources and not memory.book_sources and not memory.doctrine_cards:
            return ""

        lines: list[str] = ["MEVZUAT, DOKTRİN VE KAYNAK DEĞERLENDİRMESİ:"]
        if memory.statute_sources:
            statute_text = "; ".join(
                f"{source.code} m. {source.article}: {source.relevance}"
                for source in memory.statute_sources
            )
            lines.append(f"Mevzuat dayanakları: {statute_text}")

        for card in memory.doctrine_cards[:4]:
            citation = f" ({card.source_label})" if card.source_label else ""
            lines.append(f"Doktrin ve kaynak notu - {card.topic}: {card.principle}{citation}")

        for source in memory.book_sources[:3]:
            citation = f" ({source.citation_label})" if source.citation_label else ""
            if source.usable_argument:
                lines.append(f"Kaynak değerlendirmesi: {source.usable_argument}{citation}")
        return "\n".join(lines)

    @staticmethod
    def senior_lawyer_sentence() -> str:
        return (
            "Somut olayda maddi vakıalar, talep sonucu, ispat vasıtaları ve ilgili içtihat çizgisi birlikte "
            "değerlendirildiğinde; dilekçenin yalnızca olay anlatımına değil, her vakıanın hangi delille "
            "ispatlanacağına ve bu delilin talep sonucunu nasıl desteklediğine dayandırılması gerekir."
        )


legal_style_service = LegalStyleService()
