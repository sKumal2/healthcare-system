from datetime import datetime
from typing import Optional, TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    String,
    Text,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    Enum,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel
from app.models.enums import RoleEnum, QueryIntentEnum, AuditActionEnum, QueryFeedbackEnum


class Organization(BaseModel):
    """Represents a healthcare organization (hospital, clinic, research facility)."""
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    max_users: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    max_api_keys: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    invite_code: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        unique=True,
        index=True,
    )

    users: Mapped[list["User"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    documents: Mapped[list["Document"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    queries: Mapped[list["Query"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    rate_limits: Mapped[list["RateLimit"]] = relationship(back_populates="organization", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_org_is_active", "is_active"),
        Index("idx_org_email", "email"),
    )


class User(BaseModel):
    """Represents a user in the system (admin, clinician, patient)."""
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum), nullable=False, index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="users")
    queries: Mapped[list["Query"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    rate_limit: Mapped[Optional["RateLimit"]] = relationship(back_populates="user", cascade="all, delete-orphan", uselist=False)
    query_feedback: Mapped[list["QueryFeedback"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_user_organization_id", "organization_id"),
        Index("idx_user_email_active", "email", "is_active"),
        UniqueConstraint("organization_id", "email", name="uq_org_email"),
    )


class Document(BaseModel):
    """Represents an uploaded healthcare document chunked into the vector DB."""
    __tablename__ = "documents"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    source_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    published_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    is_processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    chunks_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    verification_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    authority_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)

    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    organization: Mapped["Organization"] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_doc_organization_id", "organization_id"),
        Index("idx_doc_verified_active", "is_verified", "is_active"),
        Index("idx_doc_processed", "is_processed"),
    )


class DocumentChunk(BaseModel):
    """Chunk of a document with metadata; embeddings live in the vector DB."""
    __tablename__ = "document_chunks"

    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    vector_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    embedding_model: Mapped[str] = mapped_column(String(100), default="all-MiniLM-L6-v2", nullable=False)

    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)

    document: Mapped["Document"] = relationship(back_populates="chunks")

    __table_args__ = (
        Index("idx_chunk_document_id", "document_id"),
        Index("idx_chunk_organization_id", "organization_id"),
        Index("idx_chunk_vector_id", "vector_id"),
    )


class Query(BaseModel):
    """Represents a user's RAG question and its answer, with full audit metadata."""
    __tablename__ = "queries"

    question: Mapped[str] = mapped_column(String(2000), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)

    query_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    intent: Mapped[Optional[QueryIntentEnum]] = mapped_column(Enum(QueryIntentEnum), nullable=True)

    top_k_retrieved: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    sources_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    processing_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)

    feedback: Mapped[Optional["QueryFeedback"]] = relationship(back_populates="query", cascade="all, delete-orphan", uselist=False)
    user: Mapped["User"] = relationship(back_populates="queries")
    organization: Mapped["Organization"] = relationship(back_populates="queries")
    sources: Mapped[list["QuerySource"]] = relationship(back_populates="query", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_query_user_id", "user_id"),
        Index("idx_query_organization_id", "organization_id"),
        Index("idx_query_session_id", "session_id"),
        Index("idx_query_query_id", "query_id"),
    )


class QuerySource(BaseModel):
    """Links a query to the document chunks cited as sources."""
    __tablename__ = "query_sources"

    query_id: Mapped[UUID] = mapped_column(ForeignKey("queries.id"), nullable=False, index=True)
    chunk_id: Mapped[UUID] = mapped_column(ForeignKey("document_chunks.id"), nullable=False, index=True)

    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)

    query: Mapped["Query"] = relationship(back_populates="sources")

    __table_args__ = (
        Index("idx_source_query_id", "query_id"),
        Index("idx_source_chunk_id", "chunk_id"),
        UniqueConstraint("query_id", "chunk_id", name="uq_query_chunk"),
    )


class QueryFeedback(BaseModel):
    """User feedback on a query result; one-to-one with Query."""
    __tablename__ = "query_feedback"

    feedback_type: Mapped[QueryFeedbackEnum] = mapped_column(Enum(QueryFeedbackEnum), nullable=False, index=True)
    feedback_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    query_id: Mapped[UUID] = mapped_column(ForeignKey("queries.id"), nullable=False, unique=True, index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    was_helpful: Mapped[bool] = mapped_column(Boolean, nullable=True)

    query: Mapped["Query"] = relationship(back_populates="feedback")
    user: Mapped["User"] = relationship(back_populates="query_feedback")

    __table_args__ = (
        Index("idx_feedback_query_id", "query_id"),
        Index("idx_feedback_user_id", "user_id"),
        Index("idx_feedback_type", "feedback_type"),
    )


class ApiKey(BaseModel):
    """API key for programmatic access; key is hashed before storage."""
    __tablename__ = "api_keys"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)

    user: Mapped["User"] = relationship(back_populates="api_keys")
    organization: Mapped["Organization"] = relationship(back_populates="api_keys")

    __table_args__ = (
        Index("idx_apikey_user_id", "user_id"),
        Index("idx_apikey_organization_id", "organization_id"),
        Index("idx_apikey_active", "is_active"),
        Index("idx_apikey_expires", "expires_at"),
    )


class RateLimit(BaseModel):
    """Custom rate limits per user; overrides organization defaults when present."""
    __tablename__ = "rate_limits"

    requests_per_minute: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    requests_per_hour: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    requests_per_day: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, unique=True, index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)

    user: Mapped["User"] = relationship(back_populates="rate_limit")
    organization: Mapped["Organization"] = relationship(back_populates="rate_limits")

    __table_args__ = (
        Index("idx_ratelimit_user_id", "user_id"),
        Index("idx_ratelimit_organization_id", "organization_id"),
    )


class AuditLog(BaseModel):
    """Immutable audit trail of all admin actions (HIPAA-compliant)."""
    __tablename__ = "audit_logs"

    action: Mapped[AuditActionEnum] = mapped_column(Enum(AuditActionEnum), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_id: Mapped[Optional[UUID]] = mapped_column(nullable=True, index=True)

    changes: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)

    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="SUCCESS", nullable=False, index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)

    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    organization: Mapped["Organization"] = relationship(back_populates="audit_logs")

    __table_args__ = (
        Index("idx_audit_user_id", "user_id"),
        Index("idx_audit_organization_id", "organization_id"),
        Index("idx_audit_action", "action"),
        Index("idx_audit_resource", "resource_type", "resource_id"),
        Index("idx_audit_created_at", "created_at"),
    )


class QueryAnalytics(BaseModel):
    """Denormalized analytics table for fast dashboard aggregations."""
    __tablename__ = "query_analytics"

    question: Mapped[str] = mapped_column(String(2000), nullable=False)
    answer_length: Mapped[int] = mapped_column(Integer, nullable=False)

    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    response_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    sources_count: Mapped[int] = mapped_column(Integer, nullable=False)

    feedback_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)

    __table_args__ = (
        Index("idx_analytics_organization_id_created", "organization_id", "created_at"),
        Index("idx_analytics_user_id_created", "user_id", "created_at"),
        Index("idx_analytics_created_at", "created_at"),
    )
