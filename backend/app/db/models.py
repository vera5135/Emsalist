"""P1.4 — SQLAlchemy database models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def new_uuid() -> str:
    return uuid.uuid4().hex[:16]


def utcnow() -> datetime:
    return datetime.now(UTC)


# -- Tenants --
class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# -- Users --
class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="active")
    role: Mapped[str] = mapped_column(String(20), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (UniqueConstraint("tenant_id", "email_normalized", name="uq_users_tenant_email"),)


# -- Cases --
class Case(Base):
    __tablename__ = "cases"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    legacy_case_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    owner_user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), default="")
    legal_topic: Mapped[str] = mapped_column(String(200), default="")
    profile_id: Mapped[str] = mapped_column(String(50), default="")
    event_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (Index("ix_cases_tenant_owner", "tenant_id", "owner_user_id"),)


# -- Case Sessions (state snapshot) --
class CaseSession(Base):
    __tablename__ = "case_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), unique=True, nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, default=1)
    state_json: Mapped[dict] = mapped_column(JSON, default=dict)
    source_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


# -- Documents --
class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), default="")
    storage_key: Mapped[str] = mapped_column(String(500), default="")
    mime_type: Mapped[str] = mapped_column(String(100), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    document_type: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (Index("ix_documents_case_sha256", "case_id", "sha256"),)


# -- Document Facts --
class DocumentFact(Base):
    __tablename__ = "document_facts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    document_id: Mapped[str] = mapped_column(String(32), ForeignKey("documents.id"), nullable=False)
    fact_key: Mapped[str] = mapped_column(String(200), default="")
    normalized_value: Mapped[str] = mapped_column(String(1000), default="")
    value_hash: Mapped[str] = mapped_column(String(64), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    conflict_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    source_locator: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# -- Legal Issue Graphs --
class LegalIssueGraph(Base):
    __tablename__ = "legal_issue_graphs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    source_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    grounding_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    graph_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (Index("ix_graphs_case_fingerprint", "case_id", "source_fingerprint"),)


# -- Precedents --
class Precedent(Base):
    __tablename__ = "precedents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    canonical_key: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), default="")
    verification_status: Mapped[str] = mapped_column(String(20), default="unverified")
    authority_status: Mapped[str] = mapped_column(String(20), default="persuasive")
    relevance_status: Mapped[str] = mapped_column(String(20), default="partially_relevant")
    selection_status: Mapped[str] = mapped_column(String(20), default="candidate")
    duplicate_of: Mapped[str | None] = mapped_column(String(32), nullable=True)
    record_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint("case_id", "canonical_key", name="uq_precedents_case_key"), Index("ix_precs_case", "case_id"))


# -- AI Runs --
class AIRun(Base):
    __tablename__ = "ai_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(64), default="")
    request_id: Mapped[str] = mapped_column(String(64), default="")
    operation: Mapped[str] = mapped_column(String(50), default="")
    provider: Mapped[str] = mapped_column(String(30), default="deepseek")
    model: Mapped[str] = mapped_column(String(50), default="")
    status: Mapped[str] = mapped_column(String(20), default="started")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    input_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    output_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    safe_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


# -- Workflow Runs --
class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), default="")
    request_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(20), default="")
    response_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (UniqueConstraint("case_id", "request_id", name="uq_wf_case_request"),)


# -- Audit Events --
class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(32), default="")
    case_id: Mapped[str] = mapped_column(String(32), default="")
    action: Mapped[str] = mapped_column(String(50), default="")
    resource_type: Mapped[str] = mapped_column(String(50), default="")
    resource_id: Mapped[str] = mapped_column(String(32), default="")
    outcome: Mapped[str] = mapped_column(String(20), default="")
    request_id: Mapped[str] = mapped_column(String(64), default="")
    safe_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    __table_args__ = (Index("ix_audit_tenant_time", "tenant_id", "created_at"),)
