"""Models used for mock judicial decision ranking."""

from pydantic import BaseModel, Field, field_validator


class DecisionInput(BaseModel):
    source: str = Field(min_length=1)
    court: str = Field(min_length=1)
    esas_no: str = Field(min_length=1)
    karar_no: str = Field(min_length=1)
    date: str = Field(min_length=1, description="Karar tarihi; kaynakta göründüğü biçimiyle")
    raw_text: str = Field(min_length=10)


class DecisionRankRequest(BaseModel):
    case_text: str = Field(min_length=10)
    decisions: list[DecisionInput] = Field(min_length=1, max_length=100)

    @field_validator("case_text")
    @classmethod
    def normalize_case_text(cls, value: str) -> str:
        return " ".join(value.split())


class RankedDecision(BaseModel):
    similarity_score: int = Field(ge=0, le=100)
    usefulness_score: str
    decision_identity: str
    summary: str
    why_relevant: str
    petition_paragraph: str


class DecisionRankResponse(BaseModel):
    top_decisions: list[RankedDecision]
