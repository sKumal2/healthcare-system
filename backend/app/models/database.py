"""
SQLAlchemy database models for the healthcare system.
Includes User, Organization, AuditLog, ApiKey, and RateLimit models.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Float, ForeignKey, Index, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()


class OrganizationModel(Base):
    """Organization model for multi-tenant support."""
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    users = relationship("UserModel", back_populates="organization")
    api_keys = relationship("ApiKeyModel", back_populates="organization")


class RoleEnum(str, enum.Enum):
    """Available roles in the system."""
    ADMIN = "admin"
    HEALTHCARE_PROVIDER = "healthcare_provider"
    PATIENT = "patient"
    RESEARCHER = "researcher"


class UserModel(Base):
    """User model with role-based access control."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    email = Column(String(255), nullable=False, unique=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(Enum(RoleEnum), default=RoleEnum.PATIENT, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    organization = relationship("OrganizationModel", back_populates="users")
    audit_logs = relationship("AuditLogModel", back_populates="user")
    api_keys = relationship("ApiKeyModel", back_populates="user")

    __table_args__ = (
        Index("ix_user_org", "organization_id", "email"),
    )


class AuditLogModel(Base):
    """Audit log model for tracking admin actions (HIPAA compliance)."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    action = Column(String(255), nullable=False)  # e.g., "USER_CREATED", "USER_ROLE_UPDATED"
    resource_type = Column(String(255), nullable=False)  # e.g., "USER", "ORGANIZATION", "API_KEY"
    resource_id = Column(Integer, nullable=True)
    changes = Column(Text, nullable=True)  # JSON string of before/after values
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(String(255), nullable=True)
    status = Column(String(50), default="SUCCESS")  # SUCCESS, FAILURE
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("UserModel", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_org_action", "organization_id", "action"),
        Index("ix_audit_created", "created_at"),
    )


class ApiKeyModel(Base):
    """API key model for programmatic access."""
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    name = Column(String(255), nullable=False)
    key_hash = Column(String(255), nullable=False, unique=True)  # Never store plaintext
    last_used_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("UserModel", back_populates="api_keys")
    organization = relationship("OrganizationModel", back_populates="api_keys")

    __table_args__ = (
        Index("ix_api_key_org_user", "organization_id", "user_id"),
    )


class RateLimitModel(Base):
    """Rate limit model for tracking and enforcing limits."""
    __tablename__ = "rate_limits"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    requests_per_minute = Column(Integer, default=60)
    requests_per_hour = Column(Integer, default=1000)
    requests_per_day = Column(Integer, default=10000)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_rate_limit_org_user", "organization_id", "user_id"),
    )


class DocumentModel(Base):
    """Document model for healthcare documents."""
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    title = Column(String(255), nullable=False)
    content_hash = Column(String(64), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class QueryAnalyticsModel(Base):
    """Query analytics model for tracking user queries and system performance."""
    __tablename__ = "query_analytics"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    query_text = Column(Text, nullable=False)
    response_time_ms = Column(Float, nullable=False)
    status_code = Column(Integer, nullable=False)
    feedback_score = Column(Integer, nullable=True)  # Rating 1-5
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_analytics_org_user", "organization_id", "user_id"),
        Index("ix_analytics_created", "created_at"),
    )
