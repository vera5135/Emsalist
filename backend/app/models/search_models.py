"""P2.7 — Hybrid legal search request/response contract models."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Request models ────────────────────────────────────────────────────────────

class LegalSearchRequest(BaseModel):
    """Legal search query with optional filters and pagination."""

    query: str = Field(..., min_length=1, max_length=2000, description="Arama sorgusu metni")
    case_id: str | None = Field(None, description="Opsiyonel case baglami")
    official_only: bool = Field(False, description="Sadece resmi kaynaklarda ara")
    source_types: list[str] = Field(default_factory=list, description="Kaynak turleri filtresi (yargitay, danistay, aym, mevzuat, resmi_gazete)")
    date_range: tuple[str, str] | None = Field(None, description="Tarih araligi (baslangic, bitis) YYYY-AA-GG formatinda")
    court: str | None = Field(None, description="Mahkeme adi filtresi")
    limit: int = Field(20, ge=1, le=100, description="Sayfa basina sonuc sayisi")
    cursor: str | None = Field(None, description="Sayfalama imleci")


# ── Response models ───────────────────────────────────────────────────────────

class LegalSearchResult(BaseModel):
    """A single legal search result with full provenance."""

    result_id: str = Field(..., description="Sonuc benzersiz kimligi")
    source_id: str = Field(..., description="Kaynak kaydinin ID'si")
    source_type: str = Field(..., description="Kaynak turu (yargitay, danistay, aym, mevzuat, resmi_gazete)")
    canonical_key: str = Field(..., description="Kaynak kanonik anahtari")
    title: str = Field("", description="Kaynak basligi")
    court: str = Field("", description="Mahkeme adi")
    chamber: str = Field("", description="Daire/bolum")
    case_number: str = Field("", description="Dosya/Esas numarasi")
    decision_number: str = Field("", description="Karar numarasi")
    decision_date: str = Field("", description="Karar tarihi")
    publication_date: str = Field("", description="Yayin tarihi")
    effective_date: str = Field("", description="Yururluk tarihi")
    issuing_authority: str = Field("", description="Yayinlayan kurum")
    jurisdiction: str = Field("", description="Yargi alani (TR)")
    verification_status: str = Field("", description="Dogrulama durumu")
    temporal_status: str = Field("", description="Zamansal durum (guncel/mulga)")
    paragraph_id: str | None = Field(None, description="Eslesen paragraf ID'si")
    paragraph_text: str | None = Field(None, description="Eslesen paragraf metni")
    snippet: str = Field("", description="Eslesen metin parcasi (highlight icin)")
    relevance_score: float = Field(0.0, description="Alaka puani (0-1)")
    semantic_score: float | None = Field(None, description="Semantik benzerlik puani (0-1)")
    lexical_score: float | None = Field(None, description="Sozluksel eslesme puani (0-1)")
    match_reasons: list[str] = Field(default_factory=list, description="Eslesme nedenleri (Turkce)")


class LegalSearchResponse(BaseModel):
    """Paginated legal search response."""

    results: list[LegalSearchResult] = Field(default_factory=list, description="Arama sonuclari listesi")
    total: int = Field(0, description="Toplam eslesen sonuc sayisi")
    has_more: bool = Field(False, description="Daha fazla sonuc var mi")
    next_cursor: str | None = Field(None, description="Sonraki sayfa imleci")
    semantic_available: bool = Field(False, description="Semantik arama kullanilabilir mi")
    degraded_mode: bool = Field(False, description="Dusurulmus modda mi calisiyor")
    query_id: str | None = Field(None, description="Sorgu ID'si (geri bildirim icin)")


# ── Similar search ────────────────────────────────────────────────────────────

class SimilarSearchRequest(BaseModel):
    """Benzer kaynak aramasi istegi."""

    source_id: str = Field(..., description="Referans kaynak ID'si")
    source_paragraph_id: str | None = Field(None, description="Referans paragraf ID'si (opsiyonel)")
    limit: int = Field(10, ge=1, le=50, description="Maksimum benzer sonuc sayisi")
    filters: dict[str, Any] = Field(default_factory=dict, description="Ek filtreler")


class SimilarSearchResponse(BaseModel):
    """Benzer kaynak aramasi yaniti."""

    results: list[LegalSearchResult] = Field(default_factory=list, description="Benzer sonuclar")
    similarity_basis: str = Field("", description="Benzerlik temeli (semantic/title/citation)")


# ── Opposing search ───────────────────────────────────────────────────────────

class OpposingSearchRequest(BaseModel):
    """Aleyhe kaynak aramasi istegi."""

    source_id: str = Field(..., description="Referans kaynak ID'si")
    filters: dict[str, Any] = Field(default_factory=dict, description="Ek filtreler")


class OpposingSearchResponse(BaseModel):
    """Aleyhe kaynak aramasi yaniti."""

    results: list[LegalSearchResult] = Field(default_factory=list, description="Aleyhe sonuclar")
    opposition_basis: str = Field("", description="Aleyhe olma temeli")


# ── Query suggestions ─────────────────────────────────────────────────────────

class SearchSuggestionResponse(BaseModel):
    """Arama sorgusu onerileri yaniti."""

    suggestions: list[str] = Field(default_factory=list, description="Onerilen sorgu metinleri")


# ── Feedback ──────────────────────────────────────────────────────────────────

class SearchFeedbackRequest(BaseModel):
    """Arama sonucu icin geri bildirim."""

    feedback_type: str = Field(..., description="Geri bildirim turu (relevant, not_relevant, authoritative, outdated, incorrect)")
    query_id: str | None = Field(None, description="Ilgili sorgu ID'si")


class SearchFeedbackResponse(BaseModel):
    """Geri bildirim onay yaniti."""

    acknowledged: bool = Field(True, description="Geri bildirim alindi mi")
    feedback_id: str | None = Field(None, description="Olusan geri bildirim ID'si")
