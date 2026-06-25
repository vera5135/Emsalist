"""Request and response contracts for the Yargıtay search integration."""

from pydantic import BaseModel, Field, field_validator


class YargitaySearchRequest(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=10)
    max_results: int = Field(default=20, ge=1, le=100)

    @field_validator("queries")
    @classmethod
    def normalize_queries(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            query = " ".join(value.split())
            if len(query) < 3:
                raise ValueError("Her sorgu en az 3 karakter olmalıdır.")
            key = query.casefold()
            if key not in seen:
                seen.add(key)
                normalized.append(query)
        return normalized


class YargitayDecision(BaseModel):
    source: str = "Yargıtay"
    query: str
    court: str
    esas_no: str
    karar_no: str
    date: str
    title: str
    detail_url: str
    raw_text: str
    clean_text: str


class YargitaySearchResponse(BaseModel):
    results: list[YargitayDecision]
    errors: list[str]
