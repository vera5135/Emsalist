"""Pydantic contracts for petition strategy and draft endpoints."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.models.document_models import ExtractedFact


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


class PrecedentAnalysis(BaseModel):
    precedent_id: str = Field(min_length=1)
    citation: str = Field(min_length=1)
    verification_status: Literal[
        "verified_supportive_precedent",
        "verification_required_precedent_candidate",
        "weak_or_partial_precedent",
        "adverse_or_distinguishable_precedent",
    ]
    similarity_reasons: list[str] = Field(default_factory=list)
    shared_facts: list[str] = Field(default_factory=list)
    shared_legal_issues: list[str] = Field(default_factory=list)
    supported_arguments: list[str] = Field(default_factory=list)
    evidence_connection: list[str] = Field(default_factory=list)
    distinguishing_risks: list[str] = Field(default_factory=list)
    recommended_use: str = Field(min_length=1)
    confidence_score: int = Field(ge=0, le=100)
    legal_area: str = ""
    case_type: str = ""
    matched_terms: list[str] = Field(default_factory=list)
    excluded_reason: str = ""

    @field_validator("precedent_id", "citation", "recommended_use")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator(
        "similarity_reasons",
        "shared_facts",
        "shared_legal_issues",
        "supported_arguments",
        "evidence_connection",
        "distinguishing_risks",
    )
    @classmethod
    def normalize_list(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = " ".join(str(value).split())
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                normalized.append(cleaned)
        return normalized


class PetitionDraftRequest(BaseModel):
    case_text: str = Field(min_length=10)
    enriched_case_text: str | None = None
    case_enrichment: dict[str, object] = Field(default_factory=dict)
    confirmed_facts: list[str] = Field(default_factory=list, max_length=30)
    missing_facts: list[str] = Field(default_factory=list, max_length=30)
    document_ids: list[str] = Field(default_factory=list, max_length=100)
    document_facts: list[ExtractedFact] = Field(default_factory=list, max_length=100)
    petition_strategy_hint: str = ""
    answers: dict[str, str] = Field(default_factory=dict)
    selected_decisions: list[SelectedDecisionForDraft] = Field(default_factory=list, max_length=20)
    precedent_candidates: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
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
    precedent_analyses: list[PrecedentAnalysis] = Field(default_factory=list)
    warnings: list[str]


class DraftingParties(BaseModel):
    claimant: str = ""
    defendant: str = ""
    attorney: str = "Av. ..."


class FinalPetitionDraftRequest(PetitionDraftRequest):
    analysis_approved: bool = False
    review_completed: bool = False
    evidence_items: list[str] = Field(default_factory=list, max_length=50)
    legal_grounds: list[str] = Field(default_factory=list, max_length=50)
    relief_requests: list[str] = Field(default_factory=list, max_length=30)
    drafting_warnings: list[str] = Field(default_factory=list, max_length=50)
    writer_mode: str = "local"  # "local" | "gemini"


class DraftingPackage(BaseModel):
    event_text: str = ""
    area: str = ""
    case_type: str = ""
    question_answers: dict[str, str] = Field(default_factory=dict)
    document_facts: list[str] = Field(default_factory=list)
    legal_issues: list[str] = Field(default_factory=list)
    evidence_plan: list[str] = Field(default_factory=list)
    risk_plan: list[str] = Field(default_factory=list)
    petition_type: str
    court_heading: str
    court_safety_note: str = ""
    parties: DraftingParties
    confirmed_facts: list[str] = Field(default_factory=list)
    uncertain_facts: list[str] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    evidence_items: list[str] = Field(default_factory=list)
    legal_sources: list[str] = Field(default_factory=list)
    legal_grounds: list[str] = Field(default_factory=list)
    precedent_for_petition: list[str] = Field(default_factory=list)
    precedents_for_petition: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    relief_requests: list[str] = Field(default_factory=list)
    drafting_warnings: list[str] = Field(default_factory=list)
    writer_mode: str = "local"


class FinalPetitionDraftResponse(BaseModel):
    petition_text: str
    generation_mode: Literal["local_template_mode", "gemini_mode", "local_fallback"]
    drafting_package: DraftingPackage
    case_state: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
