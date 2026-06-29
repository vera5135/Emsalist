"""Pydantic contracts for petition strategy and draft endpoints."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


ToneOption = Literal[
    "Ölçülü ve ikna edici",
    "Sert ve itiraz odaklı",
    "Mağduriyet vurgulu",
    "Kısa ve teknik",
]

LegalLanguageLevel = Literal["standart", "usta_avukat"]


class PetitionStrategyDecision(BaseModel):
    similarity_score: int = Field(ge=0, le=100)
    usefulness_score: str = Field(min_length=1)
    court: str = Field(min_length=1)
    esas_no: str = Field(min_length=1)
    karar_no: str = Field(min_length=1)
    date: str = Field(min_length=1)
    short_summary: str = Field(min_length=1)
    legal_principle: str = Field(min_length=1)
    why_relevant: str = Field(min_length=1)
    lehe_aleyhe: str = Field(min_length=1)
    petition_paragraph: str = Field(min_length=1)

    @field_validator(
        "usefulness_score",
        "court",
        "esas_no",
        "karar_no",
        "date",
        "short_summary",
        "legal_principle",
        "why_relevant",
        "lehe_aleyhe",
        "petition_paragraph",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return " ".join(value.split())


class PetitionStrategyRequest(BaseModel):
    case_text: str = Field(min_length=10)
    top_decisions: list[PetitionStrategyDecision] = Field(default_factory=list, max_length=20)

    @field_validator("case_text")
    @classmethod
    def normalize_case_text(cls, value: str) -> str:
        return " ".join(value.split())


class PetitionStrategyResponse(BaseModel):
    petition_type: str
    strategy_summary: str
    recommended_tone: str
    legal_basis: list[str]
    missing_information_questions: list[str]
    petition_skeleton: list[str]
    risk_notes: list[str]


class SelectedDecisionForDraft(BaseModel):
    court: str = Field(min_length=1)
    esas_no: str = Field(min_length=1)
    karar_no: str = Field(min_length=1)
    date: str = Field(min_length=1)
    petition_paragraph: str = Field(min_length=1)

    @field_validator("court", "esas_no", "karar_no", "date", "petition_paragraph")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return " ".join(value.split())


class PetitionDraftRequest(BaseModel):
    case_text: str = Field(min_length=10)
    enriched_case_text: str | None = None
    case_enrichment: dict[str, object] = Field(default_factory=dict)
    confirmed_facts: list[str] = Field(default_factory=list, max_length=30)
    missing_facts: list[str] = Field(default_factory=list, max_length=30)
    petition_strategy_hint: str = ""
    answers: dict[str, str] = Field(default_factory=dict)
    selected_decisions: list[SelectedDecisionForDraft] = Field(default_factory=list, max_length=20)
    audited_precedents: list[SelectedDecisionForDraft] = Field(default_factory=list, max_length=20)
    tone: ToneOption = "Ölçülü ve ikna edici"
    request_type: str = Field(default="Talebimizin kabulü", min_length=3)
    use_legal_brain: bool = True
    legal_language_level: LegalLanguageLevel = "usta_avukat"

    @field_validator("case_text", "enriched_case_text", "request_type", "petition_strategy_hint")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return " ".join(value.split()) if value else value

    @field_validator("answers")
    @classmethod
    def normalize_answers(cls, values: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, value in values.items():
            clean_key = " ".join(str(key).split())
            clean_value = " ".join(str(value).split())
            if clean_key and clean_value:
                normalized[clean_key] = clean_value
        return normalized


class GroundingNote(BaseModel):
    status: Literal["fact_confirmed", "fact_inferred", "fact_missing", "source_confirmed", "needs_verification"]
    title: str = Field(min_length=1)
    detail: str = Field(min_length=1)


class PetitionDraftResponse(BaseModel):
    draft_title: str
    draft_text: str
    checklist: list[str]
    grounding_notes: list[GroundingNote] = Field(default_factory=list)
    warnings: list[str]
