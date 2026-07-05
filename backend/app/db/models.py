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
