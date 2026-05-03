from enum import Enum


class RoleEnum(str, Enum):
    """User roles in the system."""
    ADMIN = "admin"
    CLINICIAN = "clinician"
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
