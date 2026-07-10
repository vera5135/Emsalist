"""P2.3 — Case & conversation/message API contract models."""
from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------
class CaseCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    legal_topic: str = Field(default="", max_length=200)
    initial_narrative: str = Field(default="", max_length=20000)
    client_request_id: str | None = Field(default=None, max_length=64)


class CaseUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    legal_topic: str | None = Field(default=None, max_length=200)
    event_text: str | None = Field(default=None, max_length=20000)


class CaseResponse(BaseModel):
    id: str
    title: str
    legal_topic: str
    status: str
    version: int
    created_at: str
    updated_at: str
    archived_at: str | None = None


class CaseListResponse(BaseModel):
    items: list[CaseResponse] = Field(default_factory=list)
    total: int = 0
    limit: int = 20
    offset: int = 0
    has_more: bool = False


# ---------------------------------------------------------------------------
# Conversations & messages
# ---------------------------------------------------------------------------
class ConversationResponse(BaseModel):
    id: str
    case_id: str
    title: str
    status: str
    created_at: str


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse] = Field(default_factory=list)


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    case_id: str
    role: str
    content: str
    status: str
    parent_message_id: str | None = None
    client_request_id: str
    created_at: str
    completed_at: str | None = None


class MessageListResponse(BaseModel):
    items: list[MessageResponse] = Field(default_factory=list)
    total: int = 0
    limit: int = 30
    offset: int = 0
    has_more: bool = False


class MessageCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    client_request_id: str | None = Field(default=None, max_length=64)
