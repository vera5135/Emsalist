"""P1.4 — SQLAlchemy database models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Float, ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint, Index, text
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
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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


# -- Conversations (P2.3) --
class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index("ix_conversations_tenant_case", "tenant_id", "case_id"),
    )


# -- Messages (P2.3) --
class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(32), ForeignKey("conversations.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user")
    content: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(20), default="completed")
    parent_message_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    client_request_id: Mapped[str] = mapped_column(String(64), default="")
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint("conversation_id", "client_request_id", name="uq_messages_conv_client_req"),
        Index("ix_messages_conv_created", "conversation_id", "created_at"),
        Index("ix_messages_tenant_case", "tenant_id", "case_id"),
    )


# -- Documents --
class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), default="")
    safe_filename: Mapped[str] = mapped_column(String(500), default="")
    storage_key: Mapped[str] = mapped_column(String(500), default="")
    mime_type: Mapped[str] = mapped_column(String(100), default="")
    extension: Mapped[str] = mapped_column(String(16), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    document_type: Mapped[str] = mapped_column(String(100), default="")
    document_type_source: Mapped[str] = mapped_column(String(20), default="suggested")
    status: Mapped[str] = mapped_column(String(30), default="active")
    analysis_status: Mapped[str] = mapped_column(String(30), default="pending")
    support_level: Mapped[str] = mapped_column(String(30), default="")
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    extracted_text_available: Mapped[bool] = mapped_column(Boolean, default=False)
    failure_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    uploaded_by: Mapped[str] = mapped_column(String(32), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index("ix_documents_case_sha256", "case_id", "sha256"),
        Index("ix_documents_tenant_case", "tenant_id", "case_id"),
    )


# -- Document Pages (P2.5) --
class DocumentPage(Base):
    __tablename__ = "document_pages"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    document_id: Mapped[str] = mapped_column(String(32), ForeignKey("documents.id"), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text, default="")
    text_hash: Mapped[str] = mapped_column(String(64), default="")
    extraction_status: Mapped[str] = mapped_column(String(20), default="extracted")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        Index("ix_document_pages_doc", "document_id", "page_number"),
    )


# -- Document Extractions (P2.5) --
class DocumentExtraction(Base):
    __tablename__ = "document_extractions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    document_id: Mapped[str] = mapped_column(String(32), ForeignKey("documents.id"), nullable=False)
    extraction_type: Mapped[str] = mapped_column(String(40), default="")
    field_key: Mapped[str] = mapped_column(String(80), default="")
    value: Mapped[str] = mapped_column(Text, default="")
    normalized_value: Mapped[str] = mapped_column(String(1000), default="")
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text_span: Mapped[str] = mapped_column(String(80), default="")
    source_quote: Mapped[str] = mapped_column(Text, default="")
    source_quote_hash: Mapped[str] = mapped_column(String(64), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    verification_status: Mapped[str] = mapped_column(String(30), default="detected")
    provider_name: Mapped[str] = mapped_column(String(40), default="")
    provider_model: Mapped[str] = mapped_column(String(80), default="")
    analysis_run_id: Mapped[str] = mapped_column(String(32), default="")
    memory_fact_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        Index("ix_doc_extractions_document", "document_id"),
        Index("ix_doc_extractions_tenant_case", "tenant_id", "case_id"),
    )


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


# -- P1.7 Legal Issue Graph Nodes --
class LegalIssueNode(Base):
    __tablename__ = "legal_issue_nodes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    node_type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="proposed")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="system")
    source_id: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(32), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index("ix_lgn_tenant_case", "tenant_id", "case_id"),
        Index("ix_lgn_case_type", "case_id", "node_type"),
        Index("ix_lgn_source", "source_type", "source_id"),
    )


class LegalIssueEdge(Base):
    __tablename__ = "legal_issue_edges"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    source_node_id: Mapped[str] = mapped_column(String(32), nullable=False)
    target_node_id: Mapped[str] = mapped_column(String(32), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(32), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index("ix_lge_tenant_case", "tenant_id", "case_id"),
        Index("ix_lge_source", "source_node_id"),
        Index("ix_lge_target", "target_node_id"),
    )


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


# -- Legal Grounds (P0.4 normalize edilmiş hukuki dayanaklar) --
class LegalGroundOrm(Base):
    __tablename__ = "legal_grounds"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    graph_id: Mapped[str] = mapped_column(String(32), default="")
    normalized_citation: Mapped[str] = mapped_column(String(200), default="")
    legislation_code: Mapped[str] = mapped_column(String(20), default="")
    legislation_name: Mapped[str] = mapped_column(String(200), default="")
    article: Mapped[str] = mapped_column(String(20), default="")
    verification_status: Mapped[str] = mapped_column(String(20), default="unverified")
    applicability_status: Mapped[str] = mapped_column(String(30), default="potentially_applicable")
    temporal_status: Mapped[str] = mapped_column(String(20), default="uncertain")
    source_refs: Mapped[dict] = mapped_column(JSON, default=dict)
    data_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("case_id", "normalized_citation", name="uq_grounds_case_citation"),)


# -- Claim Grounding Snapshots --
class ClaimGroundingOrm(Base):
    __tablename__ = "claim_grounding_snapshots"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    petition_hash: Mapped[str] = mapped_column(String(64), default="")
    source_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    grounding_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (Index("ix_grounding_case_hash", "case_id", "petition_hash", "source_fingerprint"),)


# -- Auth Sessions (P1.5) --
class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    token_family_id: Mapped[str] = mapped_column(String(64), default="")
    user_agent_hash: Mapped[str] = mapped_column(String(64), default="")
    ip_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str] = mapped_column(String(50), default="")
    replaced_by_session_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    __table_args__ = (
        Index("ix_auth_user_revoked", "user_id", "revoked_at"),
        Index("ix_auth_family", "token_family_id"),
        Index("ix_auth_expires", "expires_at"),
    )


# -- AuthIdentity (P2.2B2A) --
class AuthIdentity(Base):
    __tablename__ = "auth_identities"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    provider: Mapped[str] = mapped_column(String(20), nullable=False, default="apple")
    provider_subject_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_audience: Mapped[str] = mapped_column(String(255), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        UniqueConstraint("provider", "provider_audience", "provider_subject_hash", name="uq_auth_identity_provider_subject"),
        UniqueConstraint("provider", "user_id", name="uq_auth_identity_provider_user"),
        Index("ix_auth_identity_provider_lookup", "provider", "provider_audience", "provider_subject_hash"),
        Index("ix_auth_identity_user", "user_id"),
        Index("ix_auth_identity_tenant_user", "tenant_id", "user_id"),
    )


# -- AuthLinkTicket (P2.2B2A) --
class AuthLinkTicket(Base):
    __tablename__ = "auth_link_tickets"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    ticket_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False, default="apple")
    provider_subject_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_audience: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index("ix_auth_link_ticket_hash", "ticket_hash"),
        Index("ix_auth_link_ticket_expires", "expires_at"),
    )


# -- Case Members (P1.5) --
class CaseMember(Base):
    __tablename__ = "case_members"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), nullable=False)
    membership_role: Mapped[str] = mapped_column(String(20), default="viewer")
    permissions_override: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index("ix_case_member_case", "case_id", "user_id"),
        Index("ix_case_member_tenant", "tenant_id", "user_id"),
    )


# -- P1.6: Lifecycle Models --
class RetentionPolicy(Base):
    __tablename__ = "retention_policies"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    soft_delete_days: Mapped[int] = mapped_column(Integer, default=30)
    purge_after_days: Mapped[int] = mapped_column(Integer, default=365)
    audit_retention_days: Mapped[int] = mapped_column(Integer, default=3650)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class DeletionRequest(Base):
    __tablename__ = "deletion_requests"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(32), default="")
    resource_type: Mapped[str] = mapped_column(String(50), default="")
    resource_id: Mapped[str] = mapped_column(String(32), default="")
    reason_code: Mapped[str] = mapped_column(String(50), default="")
    status: Mapped[str] = mapped_column(String(20), default="requested")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    restore_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    safe_metadata: Mapped[dict] = mapped_column(JSON, default=dict)


class LegalHold(Base):
    __tablename__ = "legal_holds"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(50), default="")
    created_by: Mapped[str] = mapped_column(String(32), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    safe_metadata: Mapped[dict] = mapped_column(JSON, default=dict)


class PurgeRun(Base):
    __tablename__ = "purge_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True)
    scanned_count: Mapped[int] = mapped_column(Integer, default=0)
    purged_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    safe_summary: Mapped[dict] = mapped_column(JSON, default=dict)


class PurgeItem(Base):
    __tablename__ = "purge_items"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    purge_run_id: Mapped[str] = mapped_column(String(32), ForeignKey("purge_runs.id"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(32), default="")
    resource_type: Mapped[str] = mapped_column(String(50), default="")
    resource_id: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    failure_code: Mapped[str] = mapped_column(String(50), default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# -- P1.8: Background Jobs --
class BackgroundJob(Base):
    __tablename__ = "background_jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("cases.id"), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    priority: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(64), default="")
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    safe_payload_hash: Mapped[str] = mapped_column(String(64), default="")
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    safe_error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    progress_stage: Mapped[str] = mapped_column(String(50), default="")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300)
    worker_id_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parent_job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(32), default="")
    request_id: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        Index("ix_bg_jobs_tenant", "tenant_id"),
        Index("ix_bg_jobs_case", "case_id"),
        Index("ix_bg_jobs_status", "status"),
        Index("ix_bg_jobs_tenant_status", "tenant_id", "status"),
        Index("ix_bg_jobs_lease", "status", "lease_expires_at"),
        Index("ix_bg_jobs_idem", "tenant_id", "idempotency_key"),
    )


class BackgroundJobAttempt(Base):
    __tablename__ = "background_job_attempts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(String(32), ForeignKey("background_jobs.id"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="started")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_id_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    safe_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (Index("ix_bg_attempts_job", "job_id"),)


class BackgroundJobEvent(Base):
    __tablename__ = "background_job_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(String(32), ForeignKey("background_jobs.id"), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, default=0)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    progress_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    safe_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    safe_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (Index("ix_bg_events_job_seq", "job_id", "sequence_number"),)


class BackgroundJobArtifact(Base):
    __tablename__ = "background_job_artifacts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    job_id: Mapped[str] = mapped_column(String(32), ForeignKey("background_jobs.id"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("cases.id"), nullable=True)
    artifact_type: Mapped[str] = mapped_column(String(30), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index("ix_bg_artifacts_job", "job_id"),
        Index("ix_bg_artifacts_tenant", "tenant_id", "case_id"),
    )


# -- P1.9: Backup & Restore --
class BackupRun(Base):
    __tablename__ = "backup_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    backup_type: Mapped[str] = mapped_column(String(30), default="full")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    scope: Mapped[str] = mapped_column(String(20), default="full")
    storage_backend: Mapped[str] = mapped_column(String(30), default="local")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(32), default="")
    schema_revision: Mapped[str] = mapped_column(String(32), default="")
    application_version: Mapped[str] = mapped_column(String(20), default="")
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), default="")
    total_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    safe_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (
        Index("ix_backup_runs_status_time", "status", "created_at"),
        Index("ix_backup_runs_retention", "retention_until"),
    )


class BackupItem(Base):
    __tablename__ = "backup_items"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    backup_run_id: Mapped[str] = mapped_column(String(32), ForeignKey("backup_runs.id"), nullable=False)
    item_type: Mapped[str] = mapped_column(String(30), nullable=False)
    logical_name: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), default="")
    encrypted_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    failure_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    safe_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        Index("ix_backup_items_run_type", "backup_run_id", "item_type"),
    )


class RestoreRun(Base):
    __tablename__ = "restore_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    backup_run_id: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    target_environment: Mapped[str] = mapped_column(String(20), default="test")
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_only: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    initiated_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pre_restore_backup_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    schema_revision_before: Mapped[str] = mapped_column(String(32), default="")
    schema_revision_after: Mapped[str] = mapped_column(String(32), default="")
    restored_item_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_item_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_item_count: Mapped[int] = mapped_column(Integer, default=0)
    safe_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (
        Index("ix_restore_runs_backup", "backup_run_id"),
    )


class RestoreItem(Base):
    __tablename__ = "restore_items"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    restore_run_id: Mapped[str] = mapped_column(String(32), ForeignKey("restore_runs.id"), nullable=False)
    backup_item_id: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    failure_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    safe_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        Index("ix_restore_items_run", "restore_run_id"),
    )


class BackupLock(Base):
    __tablename__ = "backup_locks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    lock_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    owner_id_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# P2.4 — Structured Case Memory
# ---------------------------------------------------------------------------
class CaseFact(Base):
    __tablename__ = "case_facts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    fact_type: Mapped[str] = mapped_column(String(80), default="")
    value: Mapped[str] = mapped_column(Text, default="")
    normalized_value: Mapped[str] = mapped_column(String(1000), default="")
    unit: Mapped[str] = mapped_column(String(40), default="")
    source_type: Mapped[str] = mapped_column(String(40), default="user_message")
    source_id: Mapped[str] = mapped_column(String(64), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    verification_status: Mapped[str] = mapped_column(String(30), default="suggested")
    importance: Mapped[str] = mapped_column(String(20), default="medium")
    supersedes_fact_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        UniqueConstraint("tenant_id", "case_id", "id", name="uq_case_facts_tenant_case_id"),
        Index("ix_case_facts_tenant_case", "tenant_id", "case_id"),
        Index("ix_case_facts_case_type", "case_id", "fact_type"),
    )


class TimelineEvent(Base):
    __tablename__ = "timeline_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    event_date: Mapped[str] = mapped_column(String(20), default="")
    event_time: Mapped[str] = mapped_column(String(12), default="")
    is_approximate: Mapped[bool] = mapped_column(Boolean, default=False)
    party_reference: Mapped[str] = mapped_column(String(200), default="")
    legal_significance: Mapped[str] = mapped_column(Text, default="")
    source_type: Mapped[str] = mapped_column(String(40), default="user_message")
    source_id: Mapped[str] = mapped_column(String(64), default="")
    verification_status: Mapped[str] = mapped_column(String(30), default="suggested")
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        Index("ix_timeline_tenant_case", "tenant_id", "case_id"),
        Index("ix_timeline_case_date", "case_id", "event_date"),
    )


class MissingInformation(Base):
    __tablename__ = "missing_information"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    field_key: Mapped[str] = mapped_column(String(80), default="")
    label: Mapped[str] = mapped_column(String(200), default="")
    reason_required: Mapped[str] = mapped_column(Text, default="")
    importance: Mapped[str] = mapped_column(String(20), default="medium")
    related_legal_issue: Mapped[str] = mapped_column(String(200), default="")
    expected_source: Mapped[str] = mapped_column(String(40), default="")
    completion_condition: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="open")
    resolved_by_fact_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_type: Mapped[str] = mapped_column(String(40), default="system_inference")
    source_id: Mapped[str] = mapped_column(String(64), default="")
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        Index("ix_missing_info_tenant_case", "tenant_id", "case_id"),
        UniqueConstraint("case_id", "field_key", name="uq_missing_info_case_field"),
    )


class Contradiction(Base):
    __tablename__ = "contradictions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    contradiction_type: Mapped[str] = mapped_column(String(40), default="")
    subject_key: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    fact_ids: Mapped[list] = mapped_column(JSON, default=list)
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="open")
    resolution_fact_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resolution_note: Mapped[str] = mapped_column(Text, default="")
    resolved_by: Mapped[str] = mapped_column(String(32), default="")
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        Index("ix_contradictions_tenant_case", "tenant_id", "case_id"),
    )


class Risk(Base):
    __tablename__ = "risks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    risk_type: Mapped[str] = mapped_column(String(40), default="procedure")
    severity: Mapped[str] = mapped_column(String(20), default="low")
    title: Mapped[str] = mapped_column(String(300), default="")
    rationale: Mapped[str] = mapped_column(Text, default="")
    affected_claim: Mapped[str] = mapped_column(String(200), default="")
    supporting_reference: Mapped[str] = mapped_column(String(200), default="")
    mitigation: Mapped[str] = mapped_column(Text, default="")
    related_missing_information: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    source_type: Mapped[str] = mapped_column(String(40), default="system_inference")
    source_id: Mapped[str] = mapped_column(String(64), default="")
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        UniqueConstraint("tenant_id", "case_id", "id", name="uq_risks_tenant_case_id"),
        Index("ix_risks_tenant_case", "tenant_id", "case_id"),
    )


# ── P2.8 Legal Issue Graph ────────────────────────────────────────────────────

MEMORY_REVISION_TRIGGER_TYPES = frozenset({
    "user_message", "document_analysis", "uyap_sync", "manual_edit", "system_recompute",
})


class MemoryRevision(Base):
    __tablename__ = "memory_revisions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    memory_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(40), nullable=False)
    trigger_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    change_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        UniqueConstraint("tenant_id", "case_id", "id", name="uq_memory_revisions_tenant_case_id"),
        UniqueConstraint("tenant_id", "case_id", "revision_number", name="uq_memory_revisions_case_number"),
        UniqueConstraint("tenant_id", "case_id", "memory_fingerprint", name="uq_memory_revisions_case_fingerprint"),
        Index("ix_memory_revisions_tenant_case", "tenant_id", "case_id"),
        CheckConstraint(
            f"trigger_type IN ({', '.join(repr(s) for s in sorted(MEMORY_REVISION_TRIGGER_TYPES))})",
            name="ck_memory_revisions_trigger_type",
        ),
        CheckConstraint(
            "length(memory_fingerprint) = 64",
            name="ck_memory_revisions_fingerprint_len",
        ),
    )


LEGAL_ISSUE_STATUSES = frozenset({
    "proposed", "accepted", "disputed", "unsupported",
    "satisfied", "failed", "needs_review",
})


class LegalIssue(Base):
    __tablename__ = "legal_issues"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    parent_issue_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    issue_code: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="proposed")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("tenant_id", "case_id", "id", name="uq_legal_issues_tenant_case_id"),
        Index("ix_legal_issues_tenant_case", "tenant_id", "case_id"),
        Index("ix_legal_issues_case_parent", "case_id", "parent_issue_id"),
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in sorted(LEGAL_ISSUE_STATUSES))})",
            name="ck_legal_issues_status",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_legal_issues_confidence",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "case_id", "parent_issue_id"],
            ["legal_issues.tenant_id", "legal_issues.case_id", "legal_issues.id"],
            name="fk_legal_issues_parent_hierarchy",
            ondelete="RESTRICT",
        ),
    )


class LegalIssueDependency(Base):
    __tablename__ = "legal_issue_dependencies"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    issue_id: Mapped[str] = mapped_column(String(32), nullable=False)
    required_issue_id: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "case_id", "issue_id"],
            ["legal_issues.tenant_id", "legal_issues.case_id", "legal_issues.id"],
            name="fk_legal_issue_dependencies_issue",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "case_id", "required_issue_id"],
            ["legal_issues.tenant_id", "legal_issues.case_id", "legal_issues.id"],
            name="fk_legal_issue_dependencies_required_issue",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "issue_id <> required_issue_id",
            name="ck_legal_issue_dependencies_no_self",
        ),
        Index(
            "ix_legal_issue_dependencies_tenant_case",
            "tenant_id", "case_id",
        ),
        Index(
            "ix_legal_issue_dependencies_issue",
            "case_id", "issue_id",
        ),
        Index(
            "ix_legal_issue_dependencies_required_issue",
            "case_id", "required_issue_id",
        ),
        Index(
            "uq_legal_issue_dependencies_active_pair",
            "tenant_id", "case_id", "issue_id", "required_issue_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


LEGAL_ISSUE_FACT_RELATIONS = frozenset({
    "fact_supports_issue", "fact_contradicts_issue",
})


class LegalIssueFactLink(Base):
    __tablename__ = "legal_issue_fact_links"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    issue_id: Mapped[str] = mapped_column(String(32), nullable=False)
    fact_id: Mapped[str] = mapped_column(String(32), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "case_id", "issue_id"],
            ["legal_issues.tenant_id", "legal_issues.case_id", "legal_issues.id"],
            name="fk_legal_issue_fact_links_issue",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "case_id", "fact_id"],
            ["case_facts.tenant_id", "case_facts.case_id", "case_facts.id"],
            name="fk_legal_issue_fact_links_fact",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"relation_type IN ({', '.join(repr(s) for s in sorted(LEGAL_ISSUE_FACT_RELATIONS))})",
            name="ck_legal_issue_fact_links_relation_type",
        ),
        Index(
            "ix_legal_issue_fact_links_tenant_case",
            "tenant_id", "case_id",
        ),
        Index(
            "ix_legal_issue_fact_links_issue",
            "case_id", "issue_id",
        ),
        Index(
            "ix_legal_issue_fact_links_fact",
            "case_id", "fact_id",
        ),
        Index(
            "uq_legal_issue_fact_links_active_relation",
            "tenant_id", "case_id", "issue_id", "fact_id", "relation_type",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )


LEGAL_ISSUE_RISK_RELATIONS = frozenset({
    "issue_affects_risk",
})


class LegalIssueRiskLink(Base):
    __tablename__ = "legal_issue_risk_links"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    issue_id: Mapped[str] = mapped_column(String(32), nullable=False)
    risk_id: Mapped[str] = mapped_column(String(32), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(40), nullable=False, default="issue_affects_risk")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "case_id", "issue_id"],
            ["legal_issues.tenant_id", "legal_issues.case_id", "legal_issues.id"],
            name="fk_legal_issue_risk_links_issue",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "case_id", "risk_id"],
            ["risks.tenant_id", "risks.case_id", "risks.id"],
            name="fk_legal_issue_risk_links_risk",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"relation_type IN ({', '.join(repr(s) for s in sorted(LEGAL_ISSUE_RISK_RELATIONS))})",
            name="ck_legal_issue_risk_links_relation_type",
        ),
        Index(
            "ix_legal_issue_risk_links_tenant_case",
            "tenant_id", "case_id",
        ),
        Index(
            "ix_legal_issue_risk_links_issue",
            "case_id", "issue_id",
        ),
        Index(
            "ix_legal_issue_risk_links_risk",
            "case_id", "risk_id",
        ),
        Index(
            "uq_legal_issue_risk_links_active_relation",
            "tenant_id", "case_id", "issue_id", "risk_id", "relation_type",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )


LEGAL_ISSUE_SOURCE_RELATIONS = frozenset({
    "source_governs_issue",
})


class LegalIssueSourceLink(Base):
    __tablename__ = "legal_issue_source_links"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    issue_id: Mapped[str] = mapped_column(String(32), nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(32), nullable=False)
    source_version_id: Mapped[str] = mapped_column(String(32), nullable=False)
    source_paragraph_id: Mapped[str] = mapped_column(String(32), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(40), nullable=False, default="source_governs_issue")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "case_id", "issue_id"],
            ["legal_issues.tenant_id", "legal_issues.case_id", "legal_issues.id"],
            name="fk_legal_issue_source_links_issue",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_record_id"],
            ["source_records.id"],
            name="fk_legal_issue_source_links_source_record",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_record_id", "source_version_id"],
            ["source_versions.source_record_id", "source_versions.id"],
            name="fk_legal_issue_source_links_source_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["source_version_id", "source_paragraph_id"],
            ["source_paragraphs.source_version_id", "source_paragraphs.id"],
            name="fk_legal_issue_source_links_source_paragraph",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"relation_type IN ({', '.join(repr(s) for s in sorted(LEGAL_ISSUE_SOURCE_RELATIONS))})",
            name="ck_legal_issue_source_links_relation_type",
        ),
        Index(
            "ix_legal_issue_source_links_tenant_case",
            "tenant_id", "case_id",
        ),
        Index(
            "ix_legal_issue_source_links_issue",
            "case_id", "issue_id",
        ),
        Index(
            "ix_legal_issue_source_links_source_provenance",
            "source_record_id", "source_version_id", "source_paragraph_id",
        ),
        Index(
            "uq_legal_issue_source_links_active_relation",
            "tenant_id", "case_id", "issue_id",
            "source_record_id", "source_version_id", "source_paragraph_id",
            "relation_type",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )


BURDEN_OF_PROOF_STATUSES = frozenset({
    "candidate", "review_required", "finalized",
})

EVIDENCE_SUFFICIENCY_STATUSES = frozenset({
    "supported", "partially_supported", "unsupported", "contradicted",
    "inadmissibility_risk", "authenticity_risk",
})


class BurdenOfProof(Base):
    __tablename__ = "burdens_of_proof"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    issue_id: Mapped[str] = mapped_column(String(32), nullable=False)
    burden_party_id: Mapped[str] = mapped_column(String(32), nullable=False)
    burden_type: Mapped[str] = mapped_column(String(40), nullable=False)
    required_standard: Mapped[str] = mapped_column(String(80), nullable=False)
    legal_source_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_status: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="candidate")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "case_id", "issue_id"],
            ["legal_issues.tenant_id", "legal_issues.case_id", "legal_issues.id"],
            name="fk_burdens_of_proof_issue",
            ondelete="RESTRICT",
        ),
        Index("ix_burdens_of_proof_tenant_case", "tenant_id", "case_id"),
        Index("ix_burdens_of_proof_issue", "case_id", "issue_id"),
        Index(
            "uq_burdens_of_proof_active_scope",
            "tenant_id", "case_id", "issue_id", "burden_party_id", "burden_type",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in sorted(BURDEN_OF_PROOF_STATUSES))})",
            name="ck_burdens_of_proof_status",
        ),
        CheckConstraint(
            f"evidence_status IN ({', '.join(repr(s) for s in sorted(EVIDENCE_SUFFICIENCY_STATUSES))})",
            name="ck_burdens_of_proof_evidence_status",
        ),
        CheckConstraint(
            "status <> 'finalized' OR json_array_length(legal_source_refs) > 0",
            name="ck_burdens_of_proof_finalized_requires_sources",
        ),
    )


class EvidenceSufficiencyAssessment(Base):
    __tablename__ = "evidence_sufficiency_assessments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    issue_id: Mapped[str] = mapped_column(String(32), nullable=False)
    claim_id: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_id: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    legal_source_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    fact_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "case_id", "issue_id"],
            ["legal_issues.tenant_id", "legal_issues.case_id", "legal_issues.id"],
            name="fk_evidence_sufficiency_assessments_issue",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "case_id", "claim_id"],
            ["claims.tenant_id", "claims.case_id", "claims.id"],
            name="fk_evidence_sufficiency_assessments_claim",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "case_id", "evidence_id"],
            ["evidence.tenant_id", "evidence.case_id", "evidence.id"],
            name="fk_evidence_sufficiency_assessments_evidence",
            ondelete="RESTRICT",
        ),
        Index("ix_evidence_sufficiency_assessments_tenant_case", "tenant_id", "case_id"),
        Index("ix_evidence_sufficiency_assessments_issue", "case_id", "issue_id"),
        Index("ix_evidence_sufficiency_assessments_claim", "case_id", "claim_id"),
        Index("ix_evidence_sufficiency_assessments_evidence", "case_id", "evidence_id"),
        Index(
            "uq_evidence_sufficiency_assessments_active_scope",
            "tenant_id", "case_id", "issue_id", "claim_id", "evidence_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in sorted(EVIDENCE_SUFFICIENCY_STATUSES))})",
            name="ck_evidence_sufficiency_assessments_status",
        ),
    )


COUNTERARGUMENT_CATEGORIES = frozenset({
    "alternative_fact_interpretation", "missing_evidence",
    "opposing_precedent", "procedural_time_bar", "overbroad_request",
})

COUNTERARGUMENT_STATUSES = frozenset({
    "proposed", "accepted", "rejected", "needs_review",
})


class Counterargument(Base):
    """Concise, user-facing argument against an issue; never hidden reasoning."""

    __tablename__ = "counterarguments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    issue_id: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    basis: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="proposed")
    created_by: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "case_id", "issue_id"],
            ["legal_issues.tenant_id", "legal_issues.case_id", "legal_issues.id"],
            name="fk_counterarguments_issue", ondelete="RESTRICT",
        ),
        Index("ix_counterarguments_tenant_case", "tenant_id", "case_id"),
        Index("ix_counterarguments_issue", "case_id", "issue_id"),
        CheckConstraint(
            f"category IN ({', '.join(repr(s) for s in sorted(COUNTERARGUMENT_CATEGORIES))})",
            name="ck_counterarguments_category",
        ),
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in sorted(COUNTERARGUMENT_STATUSES))})",
            name="ck_counterarguments_status",
        ),
    )


LEGAL_REASONING_RUN_STATUSES = frozenset({
    "started", "succeeded", "failed", "stale",
})


class LegalReasoningRun(Base):
    __tablename__ = "legal_reasoning_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    memory_revision_id: Mapped[str] = mapped_column(String(32), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    output_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    safe_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "case_id", "memory_revision_id"],
            ["memory_revisions.tenant_id", "memory_revisions.case_id", "memory_revisions.id"],
            name="fk_legal_reasoning_runs_memory_revision",
            ondelete="RESTRICT",
        ),
        Index("ix_legal_reasoning_runs_tenant_case", "tenant_id", "case_id"),
        Index("ix_legal_reasoning_runs_case_created", "case_id", "created_at"),
        Index(
            "ix_legal_reasoning_runs_reproducibility",
            "case_id", "memory_revision_id", "source_fingerprint", "prompt_version",
            "provider", "model_version",
        ),
        CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in sorted(LEGAL_REASONING_RUN_STATUSES))})",
            name="ck_legal_reasoning_runs_status",
        ),
        CheckConstraint(
            "length(source_fingerprint) = 64",
            name="ck_legal_reasoning_runs_source_fingerprint_len",
        ),
        CheckConstraint(
            "length(output_hash) = 64",
            name="ck_legal_reasoning_runs_output_hash_len",
        ),
    )


class Claim(Base):
    __tablename__ = "claims"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    claim_type: Mapped[str] = mapped_column(String(40), default="")
    title: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    requested_relief: Mapped[str] = mapped_column(Text, default="")
    amount: Mapped[str] = mapped_column(String(40), default="")
    currency: Mapped[str] = mapped_column(String(8), default="")
    status: Mapped[str] = mapped_column(String(20), default="open")
    source_type: Mapped[str] = mapped_column(String(40), default="user_message")
    source_id: Mapped[str] = mapped_column(String(64), default="")
    verification_status: Mapped[str] = mapped_column(String(30), default="suggested")
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        UniqueConstraint("tenant_id", "case_id", "id", name="uq_claims_tenant_case_id"),
        Index("ix_claims_tenant_case", "tenant_id", "case_id"),
    )


class Defense(Base):
    __tablename__ = "defenses"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    claim_type: Mapped[str] = mapped_column(String(40), default="")
    title: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    responds_to_claim_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    source_type: Mapped[str] = mapped_column(String(40), default="user_message")
    source_id: Mapped[str] = mapped_column(String(64), default="")
    verification_status: Mapped[str] = mapped_column(String(30), default="suggested")
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        Index("ix_defenses_tenant_case", "tenant_id", "case_id"),
    )


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(40), default="")
    title: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    document_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    supports_claim_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    supports_event_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reliability_status: Mapped[str] = mapped_column(String(20), default="unassessed")
    admissibility_status: Mapped[str] = mapped_column(String(20), default="unassessed")
    source_type: Mapped[str] = mapped_column(String(40), default="user_message")
    source_id: Mapped[str] = mapped_column(String(64), default="")
    verification_status: Mapped[str] = mapped_column(String(30), default="suggested")
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        UniqueConstraint("tenant_id", "case_id", "id", name="uq_evidence_tenant_case_id"),
        Index("ix_evidence_tenant_case", "tenant_id", "case_id"),
    )


EVIDENCE_CLAIM_RELATIONS = frozenset({
    "evidence_supports_claim", "evidence_contradicts_claim",
})


class EvidenceClaimLink(Base):
    __tablename__ = "evidence_claim_links"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    claim_id: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_id: Mapped[str] = mapped_column(String(32), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "case_id", "claim_id"],
            ["claims.tenant_id", "claims.case_id", "claims.id"],
            name="fk_evidence_claim_links_claim",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "case_id", "evidence_id"],
            ["evidence.tenant_id", "evidence.case_id", "evidence.id"],
            name="fk_evidence_claim_links_evidence",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            f"relation_type IN ({', '.join(repr(s) for s in sorted(EVIDENCE_CLAIM_RELATIONS))})",
            name="ck_evidence_claim_links_relation_type",
        ),
        Index(
            "ix_evidence_claim_links_tenant_case",
            "tenant_id", "case_id",
        ),
        Index(
            "ix_evidence_claim_links_claim",
            "case_id", "claim_id",
        ),
        Index(
            "ix_evidence_claim_links_evidence",
            "case_id", "evidence_id",
        ),
        Index(
            "uq_evidence_claim_links_active_relation",
            "tenant_id", "case_id", "claim_id", "evidence_id", "relation_type",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )


class Deadline(Base):
    __tablename__ = "deadlines"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    deadline_type: Mapped[str] = mapped_column(String(40), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    trigger_event_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    trigger_date: Mapped[str] = mapped_column(String(20), default="")
    due_at: Mapped[str] = mapped_column(String(20), default="")
    assumptions: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="proposed")
    source_type: Mapped[str] = mapped_column(String(40), default="system_inference")
    source_id: Mapped[str] = mapped_column(String(64), default="")
    verification_status: Mapped[str] = mapped_column(String(30), default="suggested")
    confirmed_by: Mapped[str] = mapped_column(String(32), default="")
    created_by: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        Index("ix_deadlines_tenant_case", "tenant_id", "case_id"),
    )


# ---------------------------------------------------------------------------
# P2.6 — Trusted Legal Source Backbone
# ---------------------------------------------------------------------------
class SourceRecord(Base):
    """Canonical legal-source identity (global, not tenant-scoped)."""

    __tablename__ = "source_records"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    source_type: Mapped[str] = mapped_column(String(50), default="")
    canonical_key: Mapped[str] = mapped_column(String(300), nullable=False)
    title: Mapped[str] = mapped_column(String(1000), default="")
    issuing_authority: Mapped[str] = mapped_column(String(200), default="")
    court: Mapped[str] = mapped_column(String(120), default="")
    chamber: Mapped[str] = mapped_column(String(120), default="")
    case_number: Mapped[str] = mapped_column(String(80), default="")
    decision_number: Mapped[str] = mapped_column(String(80), default="")
    decision_date: Mapped[str] = mapped_column(String(20), default="")
    publication_date: Mapped[str] = mapped_column(String(20), default="")
    effective_date: Mapped[str] = mapped_column(String(20), default="")
    repeal_date: Mapped[str] = mapped_column(String(20), default="")
    official_url: Mapped[str] = mapped_column(String(1000), default="")
    language: Mapped[str] = mapped_column(String(8), default="tr")
    jurisdiction: Mapped[str] = mapped_column(String(20), default="TR")
    verification_status: Mapped[str] = mapped_column(String(30), default="needs_review")
    temporal_status: Mapped[str] = mapped_column(String(20), default="unknown")
    current_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        UniqueConstraint("canonical_key", name="uq_source_records_canonical_key"),
        Index("ix_source_records_type", "source_type"),
        Index("ix_source_records_status", "verification_status"),
    )


class SourceVersion(Base):
    """A specific retrieved/normalized content version of a SourceRecord."""

    __tablename__ = "source_versions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    source_record_id: Mapped[str] = mapped_column(String(32), ForeignKey("source_records.id"), nullable=False)
    version_label: Mapped[str] = mapped_column(String(40), default="")
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    raw_document_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    valid_from: Mapped[str] = mapped_column(String(20), default="")
    valid_to: Mapped[str] = mapped_column(String(20), default="")
    supersedes_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    retrieval_method: Mapped[str] = mapped_column(String(40), default="")
    parser_version: Mapped[str] = mapped_column(String(40), default="")
    normalized_text: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        Index("ix_source_versions_record", "source_record_id"),
        UniqueConstraint("source_record_id", "content_hash", name="uq_source_versions_record_hash"),
        UniqueConstraint("source_record_id", "id", name="uq_source_versions_record_id"),
    )


class SourceParagraph(Base):
    """A citable paragraph/article bound to a specific SourceVersion."""

    __tablename__ = "source_paragraphs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    source_version_id: Mapped[str] = mapped_column(String(32), ForeignKey("source_versions.id"), nullable=False)
    paragraph_index: Mapped[int] = mapped_column(Integer, default=0)
    heading_path: Mapped[str] = mapped_column(String(500), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    text_hash: Mapped[str] = mapped_column(String(64), default="")
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    article_number: Mapped[str] = mapped_column(String(40), default="")
    locator_json: Mapped[dict] = mapped_column(JSON, default=dict)
    embedding_status: Mapped[str] = mapped_column(String(20), default="pending")
    embedding_model: Mapped[str | None] = mapped_column(String(60), nullable=True)
    embedding_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    embedding_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_vector_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        Index("ix_source_paragraphs_version", "source_version_id", "paragraph_index"),
        UniqueConstraint("source_version_id", "id", name="uq_source_paragraphs_version_id"),
    )


class SourceVerification(Base):
    """An immutable verification event with evidence provenance."""

    __tablename__ = "source_verifications"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    source_record_id: Mapped[str] = mapped_column(String(32), ForeignKey("source_records.id"), nullable=False)
    source_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    verification_method: Mapped[str] = mapped_column(String(40), default="")
    verifier_type: Mapped[str] = mapped_column(String(20), default="automated")
    verifier_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    evidence_url: Mapped[str] = mapped_column(String(1000), default="")
    evidence_hash: Mapped[str] = mapped_column(String(64), default="")
    result: Mapped[str] = mapped_column(String(30), default="")
    notes: Mapped[str] = mapped_column(String(500), default="")
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        Index("ix_source_verifications_record", "source_record_id"),
    )


class SourceRelationship(Base):
    """A directed relationship between two SourceRecords."""

    __tablename__ = "source_relationships"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    source_record_id: Mapped[str] = mapped_column(String(32), ForeignKey("source_records.id"), nullable=False)
    related_source_record_id: Mapped[str] = mapped_column(String(32), ForeignKey("source_records.id"), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(30), default="")
    source_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    evidence: Mapped[str] = mapped_column(String(500), default="")
    verification_status: Mapped[str] = mapped_column(String(30), default="needs_review")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (
        UniqueConstraint(
            "source_record_id", "related_source_record_id", "relationship_type",
            name="uq_source_rel_triplet",
        ),
        Index("ix_source_rel_record", "source_record_id"),
    )


class SourceUsage(Base):
    """Traceability of a source's use within a tenant's case."""

    __tablename__ = "source_usages"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(32), ForeignKey("source_records.id"), nullable=False)
    source_version_id: Mapped[str] = mapped_column(String(32), ForeignKey("source_versions.id"), nullable=False)
    source_paragraph_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    usage_type: Mapped[str] = mapped_column(String(30), default="reference")
    target_type: Mapped[str] = mapped_column(String(30), default="case")
    target_id: Mapped[str] = mapped_column(String(32), default="")
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(String(500), default="")
    selected_by: Mapped[str] = mapped_column(String(32), default="")
    used_in_final_draft: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index("ix_source_usages_tenant_case", "tenant_id", "case_id"),
        Index("ix_source_usages_record", "source_record_id"),
    )


# -- P2.7 Hybrid Legal Search --
class SearchQuery(Base):
    __tablename__ = "search_queries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), nullable=False)
    case_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("cases.id"), nullable=True)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    safe_query_summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    filters_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    index_version: Mapped[str] = mapped_column(String(32), nullable=False, default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    tenant = relationship("Tenant", backref="search_queries")
    user = relationship("User", backref="search_queries")
    case = relationship("Case", backref="search_queries")


class SearchFeedback(Base):
    __tablename__ = "search_feedbacks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    search_query_id: Mapped[str] = mapped_column(String(32), ForeignKey("search_queries.id"), nullable=False, index=True)
    result_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False)
    feedback_type: Mapped[str] = mapped_column(String(30), nullable=False)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    search_query = relationship("SearchQuery", backref="feedbacks")
    user = relationship("User", backref="search_feedbacks")


# -- P2.6C Official provider ingestion runs --
class SourceIngestionRun(Base):
    """One controlled provider ingestion run.

    Stores its identifier, provider code, run type/status, bounded durable
    non-query parameters, counters, timestamps, safe error codes, and
    created-by traceability. It never stores raw fetched source content or raw
    provider search query text.
    """

    __tablename__ = "source_ingestion_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    provider_code: Mapped[str] = mapped_column(String(30), nullable=False)
    run_type: Mapped[str] = mapped_column(String(30), nullable=False, default="discover_only")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued")
    cursor_json: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discovered_count: Mapped[int] = mapped_column(Integer, default=0)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    ingested_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    new_version_count: Mapped[int] = mapped_column(Integer, default=0)
    conflict_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    last_safe_error_code: Mapped[str] = mapped_column(String(50), default="")
    created_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (
        Index("ix_source_ingestion_runs_provider", "provider_code", "created_at"),
    )


class SourceIngestionItem(Base):
    """Controlled per-candidate traceability within a provider run.

    Stores its identifier, run/provider references, provider external
    identifier, candidate URL hash, dedupe key, canonical source/version
    references, status, outcome, safe error code, and timestamps. It never
    stores raw fetched source content or raw provider search query text.
    """

    __tablename__ = "source_ingestion_items"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    run_id: Mapped[str] = mapped_column(String(32), ForeignKey("source_ingestion_runs.id"), nullable=False)
    provider_code: Mapped[str] = mapped_column(String(30), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    candidate_url_hash: Mapped[str] = mapped_column(String(64), default="")
    dedupe_key: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(30), default="discovered")
    source_record_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(30), nullable=True)
    safe_error_code: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index("ix_source_ingestion_items_run", "run_id"),
        Index("ix_source_ingestion_items_dedupe", "provider_code", "dedupe_key"),
    )


# -- P2.8 Final case-scoped dynamic precedent pools --
class PrecedentPool(Base):
    __tablename__ = "precedent_pools"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    initiated_by: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), nullable=False)
    profile_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    query_strategies_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    provider_code: Mapped[str] = mapped_column(String(30), nullable=False, default="yargitay")
    candidate_cap: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="running")
    safe_error_code: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    provider_status: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    source_ingestion_run_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    profile_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    stats_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    planner_version: Mapped[str] = mapped_column(String(60), nullable=False, default="p2.8-final-planner-1")
    model_version: Mapped[str] = mapped_column(String(60), nullable=False, default="deterministic_v1")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "case_id", "profile_fingerprint", "provider_code",
            name="uq_precedent_pools_case_profile_provider",
        ),
        CheckConstraint(
            "status IN ('running','completed','completed_with_errors','degraded_existing_corpus','failed')",
            name="ck_precedent_pools_status",
        ),
        Index("ix_precedent_pools_tenant_case", "tenant_id", "case_id", "created_at"),
        Index("ix_precedent_pools_profile", "profile_fingerprint"),
    )


class PrecedentPoolDecision(Base):
    __tablename__ = "precedent_pool_decisions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    pool_id: Mapped[str] = mapped_column(String(32), ForeignKey("precedent_pools.id"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(32), ForeignKey("source_records.id"), nullable=False)
    source_version_id: Mapped[str] = mapped_column(String(32), ForeignKey("source_versions.id"), nullable=False)
    selected_source_paragraph_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    retrieval_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scores_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    selection_state: Mapped[str] = mapped_column(String(30), nullable=False, default="shortlisted")
    duplicate_of_decision_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    match_reasons_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        ForeignKeyConstraint(
            ["source_record_id", "source_version_id"],
            ["source_versions.source_record_id", "source_versions.id"],
            name="fk_pool_decision_exact_source_version",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "pool_id", "source_record_id", "source_version_id",
            name="uq_pool_decision_source_version",
        ),
        CheckConstraint(
            "selection_state IN ('candidate','shortlisted','accepted','rejected','duplicate')",
            name="ck_pool_decision_selection_state",
        ),
        Index("ix_pool_decisions_pool_rank", "pool_id", "retrieval_rank"),
        Index("ix_pool_decisions_tenant_case", "tenant_id", "case_id"),
        Index("ix_pool_decisions_source", "source_record_id", "source_version_id"),
    )


class PrecedentDecisionAnalysis(Base):
    __tablename__ = "precedent_decision_analyses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_uuid)
    pool_id: Mapped[str] = mapped_column(String(32), ForeignKey("precedent_pools.id"), nullable=False)
    pool_decision_id: Mapped[str] = mapped_column(String(32), ForeignKey("precedent_pool_decisions.id"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(32), ForeignKey("tenants.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(32), ForeignKey("cases.id"), nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(32), ForeignKey("source_records.id"), nullable=False)
    source_version_id: Mapped[str] = mapped_column(String(32), ForeignKey("source_versions.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, default="deterministic")
    model_version: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False, default="p2.8-analysis-v1")
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    output_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    analysis_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    provenance_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="current")
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        ForeignKeyConstraint(
            ["source_record_id", "source_version_id"],
            ["source_versions.source_record_id", "source_versions.id"],
            name="fk_decision_analysis_exact_source_version",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "pool_decision_id", "source_version_id", "source_fingerprint", "output_fingerprint",
            name="uq_decision_analysis_exact_output",
        ),
        CheckConstraint(
            "status IN ('current','stale','failed')",
            name="ck_decision_analysis_status",
        ),
        Index("ix_decision_analyses_pool", "pool_id", "created_at"),
        Index("ix_decision_analyses_tenant_case", "tenant_id", "case_id"),
    )
