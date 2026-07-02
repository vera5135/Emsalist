"""Models used by case analysis and search query endpoints."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class CaseAnalyzeRequest(BaseModel):
    case_id: str | None = None
    case_text: str = Field(min_length=10, description="Avukat tarafından yazılan olay özeti")
    enriched_case_text: str | None = None

    @field_validator("case_text", "enriched_case_text")
    @classmethod
    def normalize_case_text(cls, value: str | None) -> str | None:
        return " ".join(value.split()) if value else value


class CaseAnalyzeResponse(BaseModel):
    legal_topic: str
    case_facts: list[str]
    legal_keywords: list[str]
    case_state: dict[str, Any] = Field(default_factory=dict)
    dynamic_reasoning: dict[str, Any] = Field(default_factory=dict)


class CaseStateRequest(BaseModel):
    case_id: str | None = None
    event_text: str = Field(min_length=1)
    area: str = ""
    case_type: str = ""
    document_facts: list[str] = Field(default_factory=list)
    question_answers: dict[str, str] = Field(default_factory=dict)
    legal_sources: list[str] = Field(default_factory=list)
    precedent_candidates: list[dict[str, Any]] = Field(default_factory=list)
    drafting_package: dict[str, Any] = Field(default_factory=dict)
    analysis_context: dict[str, Any] = Field(default_factory=dict)


class DynamicReasonerRequest(BaseModel):
    case_id: str | None = None
    event_text: str = Field(min_length=1)
    document_facts: list[str] = Field(default_factory=list)
    question_answers: dict[str, str] = Field(default_factory=dict)
    analysis_context: dict[str, Any] = Field(default_factory=dict)


class SearchBuildRequest(BaseModel):
    case_text: str = Field(min_length=10)
    legal_topic: str = Field(min_length=2)
    legal_keywords: list[str] = Field(default_factory=list, max_length=20)
    yargitay_query_templates: list[str] = Field(default_factory=list, max_length=20)
    legal_brain_query: str | None = None

    @field_validator("case_text", "legal_topic", "legal_brain_query")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return " ".join(value.split()) if value else value

    @field_validator("legal_keywords", "yargitay_query_templates")
    @classmethod
    def normalize_keywords(cls, values: list[str]) -> list[str]:
        # Sırayı koruyarak boş ve tekrarlanan değerleri temizle.
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = " ".join(value.split())
            key = cleaned.casefold()
            if cleaned and key not in seen:
                seen.add(key)
                result.append(cleaned)
        return result


class SearchBuildResponse(BaseModel):
    queries: list[str]
