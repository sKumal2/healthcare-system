"""
Pydantic schemas for admin endpoints.
Includes request/response models with validation.
"""

from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import datetime
from typing import Optional, List
from enum import Enum


class RoleEnum(str, Enum):
    """Available roles."""
    ADMIN = "admin"
    HEALTHCARE_PROVIDER = "healthcare_provider"
    PATIENT = "patient"
    RESEARCHER = "researcher"


# ============ Organization Schemas ============

class OrganizationBase(BaseModel):
    """Base organization schema."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)


class OrganizationCreate(OrganizationBase):
    """Create organization request."""
    pass


class OrganizationUpdate(BaseModel):
    """Update organization request."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)


class OrganizationResponse(OrganizationBase):
    """Organization response."""
    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ User Schemas ============

class UserBase(BaseModel):
    """Base user schema."""
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)


class UserCreate(UserBase):
    """Create user request."""
    organization_id: int
    role: RoleEnum = RoleEnum.PATIENT
    password: str = Field(..., min_length=8)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        """Validate password strength."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain digit")
        return v


class UserUpdate(BaseModel):
    """Update user request (admin)."""
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    role: Optional[RoleEnum] = None
    is_active: Optional[bool] = None


class UserResponse(UserBase):
    """User response (sensitive data masked)."""
    id: int
    organization_id: int
    role: RoleEnum
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserDetailResponse(UserResponse):
    """User detail response with additional info."""
    pass


# ============ Audit Log Schemas ============

class AuditLogFilters(BaseModel):
    """Filters for audit log queries."""
    user_id: Optional[int] = None
    action: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[int] = None
    status: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class AuditLogResponse(BaseModel):
    """Audit log response."""
    id: int
    user_id: int
    organization_id: int
    action: str
    resource_type: str
    resource_id: Optional[int]
    changes: Optional[dict]
    ip_address: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogListResponse(BaseModel):
    """Paginated audit logs response."""
    items: List[AuditLogResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============ API Key Schemas ============

class ApiKeyCreate(BaseModel):
    """Create API key request."""
    name: str = Field(..., min_length=1, max_length=255)
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)


class ApiKeyResponse(BaseModel):
    """API key response (masked)."""
    id: int
    name: str
    last_used_at: Optional[datetime]
    is_active: bool
    expires_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class ApiKeyCreateResponse(ApiKeyResponse):
    """API key creation response with plaintext key (only shown once)."""
    key: str  # Only returned on creation


class ApiKeyRotateResponse(BaseModel):
    """Response for rotating API key."""
    new_key: str
    old_key_revoked_at: datetime


# ============ Analytics Schemas ============

class AnalyticsMetrics(BaseModel):
    """Analytics metrics snapshot."""
    total_queries: int
    avg_response_time_ms: float
    total_users: int
    queries_last_24h: int
    avg_feedback_score: Optional[float]
    peak_usage_hour: Optional[int]


class UserAnalytics(BaseModel):
    """Per-user analytics."""
    user_id: int
    email: str
    total_queries: int
    avg_response_time_ms: float
    last_query_at: Optional[datetime]


class UsageByDate(BaseModel):
    """Usage aggregated by date."""
    date: str
    query_count: int
    unique_users: int
    avg_response_time_ms: float


class AnalyticsResponse(BaseModel):
    """Complete analytics response."""
    metrics: AnalyticsMetrics
    top_users: List[UserAnalytics]
    usage_trend: List[UsageByDate]


# ============ Rate Limit Schemas ============

class RateLimitUpdate(BaseModel):
    """Update rate limits."""
    requests_per_minute: Optional[int] = Field(None, ge=1, le=1000)
    requests_per_hour: Optional[int] = Field(None, ge=1, le=10000)
    requests_per_day: Optional[int] = Field(None, ge=1, le=100000)


class RateLimitResponse(BaseModel):
    """Rate limit response."""
    user_id: int
    requests_per_minute: int
    requests_per_hour: int
    requests_per_day: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============ Pagination ============

class PaginationParams(BaseModel):
    """Pagination parameters."""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


# ============ Error Response ============

class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str
    error_code: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
