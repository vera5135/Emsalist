"""Models used by case analysis and search query endpoints."""

from pydantic import BaseModel, Field, field_validator


class CaseAnalyzeRequest(BaseModel):
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
