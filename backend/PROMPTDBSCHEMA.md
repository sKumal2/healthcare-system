# Database Schema (ORM Models) — Claude Code Prompt

## Context

This is a Healthcare RAG System built with FastAPI (Python 3.11+). Before implementing the
async database layer, you need the complete ORM schema that defines all tables, relationships,
constraints, and indexes.

The backend uses **SQLAlchemy 2.0+ with async support** and **PostgreSQL**. All models will
inherit from the `Base` and mixins defined in `backend/app/db/base.py` (created in the DB
layer prompt).

### What exists already (do not change):
```
backend/app/db/base.py          # Defines Base, TimestampMixin, UUIDMixin, BaseModel
backend/app/core/config.py      # Pydantic settings with DB config
```

### What to create:
```
backend/app/models/
├── __init__.py
├── database.py          # All ORM models in a single file
└── enums.py            # All enum types (RoleEnum, QueryIntentEnum, etc.)
```

---

## File: `backend/app/models/enums.py`

Define all enums as Python `Enum` classes. These will be used as column types in the models.

```python
from enum import Enum

class RoleEnum(str, Enum):
    """User roles in the system."""
    ADMIN = "admin"
    CLINICIAN = "clinician"           # Healthcare professional
    PATIENT = "patient"
    ORGANIZATION_OWNER = "org_owner"


class QueryIntentEnum(str, Enum):
    """Intent classification for a query."""
    DIAGNOSIS = "diagnosis"
    TREATMENT = "treatment"
    DRUG_INFO = "drug_info"
    SYMPTOM_CHECK = "symptom_check"
    GENERAL = "general"


class AuditActionEnum(str, Enum):
    """Types of admin actions tracked in audit log."""
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"
    USER_ROLE_CHANGED = "user_role_changed"
    API_KEY_CREATED = "api_key_created"
    API_KEY_REVOKED = "api_key_revoked"
    RATE_LIMIT_UPDATED = "rate_limit_updated"
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_DELETED = "document_deleted"
    ORGANIZATION_UPDATED = "organization_updated"


class QueryFeedbackEnum(str, Enum):
    """User feedback on query results."""
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"
    PARTIALLY_HELPFUL = "partially_helpful"
    MISLEADING = "misleading"
    OUTDATED = "outdated"
```

---

## File: `backend/app/models/database.py`

### 1. **Organization Model**

```python
class Organization(BaseModel):
    """
    Represents a healthcare organization (hospital, clinic, research facility).
    Multi-tenancy is enforced at the organization level.
    """
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Contact info
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Address
    address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Settings & status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    max_users: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    max_api_keys: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    
    # Relationships
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
```

### 2. **User Model**

```python
class User(BaseModel):
    """
    Represents a user in the system (admin, clinician, patient).
    Users belong to exactly one organization.
    """
    __tablename__ = "users"

    # Basic info
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Role & organization
    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum), nullable=False, index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    
    # Status & auth
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Security
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
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
```

### 3. **Document Model**

```python
class Document(BaseModel):
    """
    Represents an uploaded healthcare document (PDF, text, research paper, etc.).
    Documents are chunked and embedded into the vector database.
    """
    __tablename__ = "documents"

    # Basic info
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Content metadata
    source_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)  # S3 path or local path
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Authorship & sourcing
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    published_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Processing status
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    chunks_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Trust & authority
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    verification_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    authority_score: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)  # 0.0 to 1.0
    
    # Organization & status
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_doc_organization_id", "organization_id"),
        Index("idx_doc_verified_active", "is_verified", "is_active"),
        Index("idx_doc_processed", "is_processed"),
    )
```

### 4. **DocumentChunk Model**

```python
class DocumentChunk(BaseModel):
    """
    Represents a chunk of a document (after splitting into smaller pieces).
    Each chunk has a vector embedding stored in the vector DB.
    This table stores metadata only; embeddings live in Pinecone/Weaviate.
    """
    __tablename__ = "document_chunks"

    # Content
    content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 0, 1, 2, ... within document
    
    # Vector DB reference
    vector_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)  # ID in Pinecone/Weaviate
    embedding_model: Mapped[str] = mapped_column(String(100), default="all-MiniLM-L6-v2", nullable=False)
    
    # Metadata
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Organization & document reference
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="chunks")

    __table_args__ = (
        Index("idx_chunk_document_id", "document_id"),
        Index("idx_chunk_organization_id", "organization_id"),
        Index("idx_chunk_vector_id", "vector_id"),
    )
```

### 5. **Query Model**

```python
class Query(BaseModel):
    """
    Represents a user's question answered via RAG.
    Stores the question, answer, sources, and metadata for auditing & analytics.
    """
    __tablename__ = "queries"

    # Question & answer
    question: Mapped[str] = mapped_column(String(2000), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Processing metadata
    query_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)  # UUID string for external reference
    session_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)  # Groups multiple queries in a session
    intent: Mapped[Optional[QueryIntentEnum]] = mapped_column(Enum(QueryIntentEnum), nullable=True)
    
    # RAG pipeline metadata
    top_k_retrieved: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    sources_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0 to 1.0
    processing_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Token usage
    input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # User & organization
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    
    # Feedback (optional, added later by user)
    feedback: Mapped[Optional["QueryFeedback"]] = relationship(back_populates="query", cascade="all, delete-orphan", uselist=False)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="queries")
    organization: Mapped["Organization"] = relationship(back_populates="queries")
    sources: Mapped[list["QuerySource"]] = relationship(back_populates="query", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_query_user_id", "user_id"),
        Index("idx_query_organization_id", "organization_id"),
        Index("idx_query_session_id", "session_id"),
        Index("idx_query_query_id", "query_id"),
    )
```

### 6. **QuerySource Model**

```python
class QuerySource(BaseModel):
    """
    Represents a document chunk used as a source in answering a query.
    Links a query to the documents that were cited.
    """
    __tablename__ = "query_sources"

    # References
    query_id: Mapped[UUID] = mapped_column(ForeignKey("queries.id"), nullable=False, index=True)
    chunk_id: Mapped[UUID] = mapped_column(ForeignKey("document_chunks.id"), nullable=False, index=True)
    
    # Ranking
    rank: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3, ... in order of relevance
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)  # Final reranker score

    # Relationships
    query: Mapped["Query"] = relationship(back_populates="sources")

    __table_args__ = (
        Index("idx_source_query_id", "query_id"),
        Index("idx_source_chunk_id", "chunk_id"),
        UniqueConstraint("query_id", "chunk_id", name="uq_query_chunk"),
    )
```

### 7. **QueryFeedback Model**

```python
class QueryFeedback(BaseModel):
    """
    Captures user feedback on query results for quality monitoring & model improvement.
    One-to-one with Query — a user gives zero or one feedback per query.
    """
    __tablename__ = "query_feedback"

    # Question response
    feedback_type: Mapped[QueryFeedbackEnum] = mapped_column(Enum(QueryFeedbackEnum), nullable=False, index=True)
    feedback_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-5 star rating
    
    # References
    query_id: Mapped[UUID] = mapped_column(ForeignKey("queries.id"), nullable=False, unique=True, index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    
    # Metadata
    was_helpful: Mapped[bool] = mapped_column(Boolean, nullable=True)

    # Relationships
    query: Mapped["Query"] = relationship(back_populates="feedback")
    user: Mapped["User"] = relationship(back_populates="query_feedback")

    __table_args__ = (
        Index("idx_feedback_query_id", "query_id"),
        Index("idx_feedback_user_id", "user_id"),
        Index("idx_feedback_type", "feedback_type"),
    )
```

### 8. **ApiKey Model**

```python
class ApiKey(BaseModel):
    """
    API key for programmatic access to the system.
    Keys are hashed before storage (plaintext shown only on creation).
    """
    __tablename__ = "api_keys"

    # Key data
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)  # SHA-256 hash
    
    # Status & expiry
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # References
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="api_keys")
    organization: Mapped["Organization"] = relationship(back_populates="api_keys")

    __table_args__ = (
        Index("idx_apikey_user_id", "user_id"),
        Index("idx_apikey_organization_id", "organization_id"),
        Index("idx_apikey_active", "is_active"),
        Index("idx_apikey_expires", "expires_at"),
    )
```

### 9. **RateLimit Model**

```python
class RateLimit(BaseModel):
    """
    Custom rate limits per user (overrides organization defaults).
    If not present, system defaults apply.
    """
    __tablename__ = "rate_limits"

    # Limits
    requests_per_minute: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    requests_per_hour: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    requests_per_day: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    
    # References
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, unique=True, index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="rate_limit")
    organization: Mapped["Organization"] = relationship(back_populates="rate_limits")

    __table_args__ = (
        Index("idx_ratelimit_user_id", "user_id"),
        Index("idx_ratelimit_organization_id", "organization_id"),
    )
```

### 10. **AuditLog Model**

```python
class AuditLog(BaseModel):
    """
    Immutable audit trail of all admin actions.
    HIPAA-compliant logging for compliance & forensics.
    """
    __tablename__ = "audit_logs"

    # Action details
    action: Mapped[AuditActionEnum] = mapped_column(Enum(AuditActionEnum), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # "USER", "API_KEY", etc.
    resource_id: Mapped[Optional[UUID]] = mapped_column(nullable=True, index=True)
    
    # Changes (JSON for flexibility)
    changes: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)  # {before: {...}, after: {...}}
    
    # Request context
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Result
    status: Mapped[str] = mapped_column(String(20), default="SUCCESS", nullable=False, index=True)  # SUCCESS, FAILURE
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # References
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)  # Admin performing action
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)

    # Relationships
    user: Mapped["User"] = relationship(foreign_keys=[user_id])  # Admin who did the action
    organization: Mapped["Organization"] = relationship(back_populates="audit_logs")

    __table_args__ = (
        Index("idx_audit_user_id", "user_id"),
        Index("idx_audit_organization_id", "organization_id"),
        Index("idx_audit_action", "action"),
        Index("idx_audit_resource", "resource_type", "resource_id"),
        Index("idx_audit_created_at", "created_at"),  # For time-range queries
    )
```

### 11. **QueryAnalytics Model** (optional, for analytics endpoint)

```python
class QueryAnalytics(BaseModel):
    """
    Denormalized analytics table for fast aggregations.
    Periodically populated from Query & QueryFeedback tables.
    Used for dashboards, reporting, and system monitoring.
    """
    __tablename__ = "query_analytics"

    # Denormalized query data
    question: Mapped[str] = mapped_column(String(2000), nullable=False)
    answer_length: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Metrics
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    response_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    sources_count: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Feedback
    feedback_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-5 or None if no feedback
    
    # References (denormalized for fast querying)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    organization_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)

    __table_args__ = (
        Index("idx_analytics_organization_id_created", "organization_id", "created_at"),
        Index("idx_analytics_user_id_created", "user_id", "created_at"),
        Index("idx_analytics_created_at", "created_at"),
    )
```

---

## Import Structure in `backend/app/models/__init__.py`

```python
from app.models.enums import (
    RoleEnum,
    QueryIntentEnum,
    AuditActionEnum,
    QueryFeedbackEnum,
)

from app.models.database import (
    Organization,
    User,
    Document,
    DocumentChunk,
    Query,
    QuerySource,
    QueryFeedback,
    ApiKey,
    RateLimit,
    AuditLog,
    QueryAnalytics,
)

__all__ = [
    # Enums
    "RoleEnum",
    "QueryIntentEnum",
    "AuditActionEnum",
    "QueryFeedbackEnum",
    # Models
    "Organization",
    "User",
    "Document",
    "DocumentChunk",
    "Query",
    "QuerySource",
    "QueryFeedback",
    "ApiKey",
    "RateLimit",
    "AuditLog",
    "QueryAnalytics",
]
```

---

## Schema Design Decisions Explained

### Multi-tenancy
Every model that stores user data has `organization_id`. This enforces complete isolation
— queries from one org can never touch data from another org. No shared tables.

### UUIDs for primary keys
All `id` fields are UUID, not auto-increment integers. Benefits:
- Prevents leaking record counts via sequential IDs
- Supports distributed systems where multiple servers generate IDs
- Better for security (harder to guess resource IDs)

### Relationships & cascades
`cascade="all, delete-orphan"` on parent→child relationships means deleting an org
automatically deletes all its users, documents, queries, etc. No orphaned data.

### Audit immutability
`AuditLog` has no cascade deletes and no update constraints — once an audit entry is
written, it cannot be modified. This is HIPAA requirement.

### Vector DB separation
`DocumentChunk` stores only metadata; embeddings live in Pinecone/Weaviate. This keeps
the SQL DB small and lets you swap vector providers without migrating the schema.

### Analytics denormalization
`QueryAnalytics` is a denormalized read-only table populated from `Query` + `QueryFeedback`.
This allows fast aggregations for dashboards without expensive joins on the operational table.

---

## Required Imports at Top of `database.py`

```python
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
from app.db.base import Base, BaseModel
from app.models.enums import RoleEnum, QueryIntentEnum, AuditActionEnum, QueryFeedbackEnum

if TYPE_CHECKING:
    # Forward references for type hints
    pass
```

---

## Code Quality Standards

- **Column constraints**: `nullable=False` on required fields, `unique=True` + `index=True` on unique columns
- **Relationships**: Always define bidirectional relationships with `back_populates`
- **Indexes**: Create indexes on foreign keys, high-cardinality columns, and filter columns (e.g., `is_active`)
- **Composite indexes**: For common filter+sort patterns (e.g., `idx_query_organization_id_created_at`)
- **Docstrings**: Every model class and major relationship has a one-line docstring
- **Type hints**: Use `Mapped[...]` with the exact type (not `Optional` in the string, use `Optional[T]` in Mapped)
- **No business logic**: These are data models only — no methods beyond `__repr__` if needed

---

## Definition of Done

- [ ] `backend/app/models/enums.py` created with all 4 enum classes
- [ ] `backend/app/models/database.py` created with all 11 models
- [ ] `backend/app/models/__init__.py` created with proper imports
- [ ] All models inherit from `BaseModel` (which inherits from `UUIDMixin`, `TimestampMixin`, `Base`)
- [ ] All relationships are bidirectional (use `back_populates`)
- [ ] All FK columns have matching indexes
- [ ] All Enum columns use `Enum(EnumClass)` type
- [ ] All models have docstrings
- [ ] No circular imports (use `TYPE_CHECKING` + string forward refs if needed)
- [ ] Can import all models from `app.models` without errors: `from app.models import User, Query, etc.`