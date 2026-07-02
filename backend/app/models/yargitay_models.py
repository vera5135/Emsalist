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
    source_type: str = "yargitay_live"
    official_verification_status: str = "verified_live"
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
    attempted_queries: list[str] = Field(default_factory=list)
    skipped_due_to_rate_limit: bool = False
    raw_live_result_count: int = 0
    parsed_live_result_count: int = 0
    final_live_result_count: int = 0
    official_yargitay_reached: bool = False
    official_yargitay_returned_results: bool = False
    failure_reason: str = ""
