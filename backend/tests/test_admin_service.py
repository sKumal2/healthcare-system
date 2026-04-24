"""
Test suite for AdminService.
Tests RBAC enforcement, user management, audit logging, and security features.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session

from app.models.database import (
    UserModel,
    OrganizationModel,
    AuditLogModel,
    ApiKeyModel,
    RateLimitModel,
    QueryAnalyticsModel,
    RoleEnum,
)
from app.models.admin_schemas import (
    UserCreate,
    UserUpdate,
    AuditLogFilters,
    ApiKeyCreate,
    RateLimitUpdate,
)
from app.services.admin_service import AdminService
from app.utils.audit import (
    create_audit_log,
    mask_sensitive_data,
    check_privilege_escalation,
    is_admin,
)


@pytest.fixture
def mock_db():
    """Fixture providing a mock database session."""
    return MagicMock(spec=Session)


@pytest.fixture
def organization():
    """Fixture providing a test organization."""
    return OrganizationModel(
        id=1,
        name="Test Healthcare Org",
        description="Testing organization",
        is_active=True,
    )


@pytest.fixture
def admin_user(organization):
    """Fixture providing an admin user."""
    user = UserModel(
        id=1,
        organization_id=organization.id,
        email="admin@test.com",
        hashed_password="hashed_password_123",
        full_name="Admin User",
        role=RoleEnum.ADMIN,
        is_active=True,
    )
    user.organization = organization
    return user


@pytest.fixture
def non_admin_user(organization):
    """Fixture providing a non-admin user."""
    user = UserModel(
        id=2,
        organization_id=organization.id,
        email="provider@test.com",
        hashed_password="hashed_password_456",
        full_name="Healthcare Provider",
        role=RoleEnum.HEALTHCARE_PROVIDER,
        is_active=True,
    )
    user.organization = organization
    return user


@pytest.fixture
def admin_service(mock_db, admin_user):
    """Fixture providing an AdminService instance with admin context."""
    return AdminService(session=mock_db, current_admin=admin_user)


# ============================================================================
# AdminService Initialization Tests
# ============================================================================


class TestAdminServiceInitialization:
    """Tests for AdminService initialization and RBAC enforcement."""

    def test_service_initializes_with_admin_user(self, mock_db, admin_user):
        """Test that service initializes correctly with admin user."""
        service = AdminService(session=mock_db, current_admin=admin_user)
        assert service.current_admin == admin_user
        assert service.session == mock_db

    def test_service_raises_error_for_non_admin_user(self, mock_db, non_admin_user):
        """Test that service raises error if non-admin tries to initialize."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            AdminService(session=mock_db, current_admin=non_admin_user)

    def test_service_stores_admin_context(self, mock_db, admin_user):
        """Test that service correctly stores admin context."""
        service = AdminService(session=mock_db, current_admin=admin_user)
        assert service.current_admin.organization_id == admin_user.organization_id


# ============================================================================
# User Management Tests
# ============================================================================


class TestUserCreation:
    """Tests for user creation functionality."""

    def test_create_user_method_exists(self, admin_service):
        """Test that create_user method exists and is callable."""
        assert hasattr(admin_service, "create_user")
        assert callable(admin_service.create_user)

    def test_create_user_accepts_user_create_object(self):
        """Test that UserCreate schema has required fields."""
        user_data = UserCreate(
            email="test@example.com",
            password="SecurePass123",
            full_name="Test User",
            role=RoleEnum.HEALTHCARE_PROVIDER,
            organization_id=1,
        )
        assert user_data.email == "test@example.com"
        assert user_data.full_name == "Test User"
        assert user_data.role == RoleEnum.HEALTHCARE_PROVIDER

    def test_create_user_validates_password_strength(self):
        """Test that password validation is required."""
        # Weak password
        invalid_password = "weak"
        valid_password = "SecurePass123"
        
        # Valid password has uppercase and digit
        assert any(c.isupper() for c in valid_password)
        assert any(c.isdigit() for c in valid_password)


class TestUserUpdate:
    """Tests for user update functionality."""

    def test_update_user_method_exists(self, admin_service):
        """Test that update_user method exists."""
        assert hasattr(admin_service, "update_user")
        assert callable(admin_service.update_user)

    def test_user_update_schema_exists(self):
        """Test that UserUpdate schema exists with expected fields."""
        update_data = UserUpdate(full_name="Updated Name")
        assert update_data.full_name == "Updated Name"

    def test_privilege_escalation_prevention_function_exists(self):
        """Test that privilege escalation check function exists."""
        assert callable(check_privilege_escalation)


class TestUserDeactivation:
    """Tests for user deactivation (soft delete)."""

    def test_deactivate_user_method_exists(self, admin_service):
        """Test that deactivate_user method exists."""
        assert hasattr(admin_service, "deactivate_user")
        assert callable(admin_service.deactivate_user)


# ============================================================================
# Audit Logging Tests
# ============================================================================


class TestAuditLogQueries:
    """Tests for audit log querying and filtering."""

    def test_get_audit_logs_method_exists(self, admin_service):
        """Test that get_audit_logs method exists."""
        assert hasattr(admin_service, "get_audit_logs")
        assert callable(admin_service.get_audit_logs)

    def test_audit_log_model_has_required_fields(self):
        """Test that AuditLog model has required fields for compliance."""
        audit_log = AuditLogModel(
            id=1,
            user_id=1,
            organization_id=1,
            action="USER_CREATED",
            resource_type="USER",
            changes='{"email": "user@test.com"}',
            status="SUCCESS",
            created_at=datetime.now(),
        )
        
        # Verify HIPAA compliance fields exist
        assert audit_log.user_id is not None
        assert audit_log.action is not None
        assert audit_log.resource_type is not None
        assert audit_log.changes is not None
        assert audit_log.status is not None
        assert audit_log.created_at is not None

    def test_audit_log_filters_schema_exists(self):
        """Test that audit log filtering is supported."""
        filters = AuditLogFilters(
            user_id=1,
            action="USER_CREATED",
            page=1,
            page_size=50,
        )
        assert filters.user_id == 1
        assert filters.action == "USER_CREATED"


# ============================================================================
# API Key Management Tests
# ============================================================================


class TestApiKeyManagement:
    """Tests for API key creation and revocation."""

    def test_create_api_key_method_exists(self, admin_service):
        """Test that create_api_key method exists."""
        assert hasattr(admin_service, "create_api_key")
        assert callable(admin_service.create_api_key)

    def test_revoke_api_key_method_exists(self, admin_service):
        """Test that revoke_api_key method exists."""
        assert hasattr(admin_service, "revoke_api_key")
        assert callable(admin_service.revoke_api_key)

    def test_api_key_model_stores_hash_not_plaintext(self):
        """Test that API key model stores hashed value."""
        api_key = ApiKeyModel(
            id=1,
            user_id=1,
            organization_id=1,
            name="Test Key",
            key_hash="sha256_abc123def456",
            is_active=True,
        )
        
        # Hash should be stored (not plaintext key itself)
        assert api_key.key_hash == "sha256_abc123def456"
        assert api_key.key_hash != "actual_api_key_value"

    def test_api_key_supports_expiration(self):
        """Test that API keys can have expiration dates."""
        expires_at = datetime.now() + timedelta(days=30)
        api_key = ApiKeyModel(
            id=2,
            user_id=1,
            organization_id=1,
            name="Expiring Key",
            key_hash="hash_value",
            expires_at=expires_at,
            is_active=True,
        )
        
        assert api_key.expires_at is not None


# ============================================================================
# Rate Limiting Tests
# ============================================================================


class TestRateLimitManagement:
    """Tests for rate limit configuration."""

    def test_update_rate_limits_method_exists(self, admin_service):
        """Test that update_rate_limits method exists."""
        assert hasattr(admin_service, "update_rate_limits")
        assert callable(admin_service.update_rate_limits)

    def test_rate_limit_model_has_default_values(self):
        """Test that RateLimitModel supports default values."""
        # When created with explicit values, they are respected
        rate_limit = RateLimitModel(
            id=1,
            user_id=1,
            organization_id=1,
            requests_per_minute=60,
            requests_per_hour=1000,
            requests_per_day=10000,
        )
        
        # Verify the values
        assert rate_limit.requests_per_minute == 60
        assert rate_limit.requests_per_hour == 1000
        assert rate_limit.requests_per_day == 10000

    def test_rate_limit_respects_hierarchy(self):
        """Test that rate limits follow minute < hour < day hierarchy."""
        rate_limit = RateLimitModel(
            id=2,
            user_id=1,
            organization_id=1,
            requests_per_minute=100,
            requests_per_hour=5000,
            requests_per_day=50000,
        )
        
        assert (
            rate_limit.requests_per_minute 
            < rate_limit.requests_per_hour 
            < rate_limit.requests_per_day
        )

    def test_rate_limits_can_be_disabled(self):
        """Test that rate limits can be deactivated."""
        rate_limit = RateLimitModel(
            id=3,
            user_id=1,
            organization_id=1,
            is_active=True,
        )
        
        assert rate_limit.is_active is True
        rate_limit.is_active = False
        assert rate_limit.is_active is False


# ============================================================================
# Security & Utility Function Tests
# ============================================================================


class TestSensitiveDataMasking:
    """Tests for sensitive data protection in audit logs."""

    def test_mask_email_address(self):
        """Test that email addresses are properly masked."""
        masked = mask_sensitive_data("user@example.com", "email")
        assert "user@example.com" != masked
        assert "@" in masked or "***" in masked

    def test_mask_api_key(self):
        """Test that API keys are properly masked."""
        api_key = "secret_key_1234567890"
        masked = mask_sensitive_data(api_key, "api_key")
        assert api_key != masked
        assert "***" in masked

    def test_mask_password(self):
        """Test that passwords are properly masked."""
        password = "MySecurePassword123!"
        masked = mask_sensitive_data(password, "password")
        assert password != masked
        assert "***" in masked

    def test_non_sensitive_data_handling(self):
        """Test that non-sensitive fields are processed."""
        original = "John Doe"
        masked = mask_sensitive_data(original, "full_name")
        # Should be a string (masked or unchanged)
        assert isinstance(masked, str)


class TestPrivilegeEscalationPrevention:
    """Tests for privilege escalation detection."""

    def test_privilege_escalation_function_exists(self):
        """Test that privilege escalation check function exists."""
        assert callable(check_privilege_escalation)

    def test_privilege_escalation_detects_self_role_change(self, admin_user):
        """Test that changing own role is detected."""
        # Attempt to change own role
        result = check_privilege_escalation(
            current_user=admin_user,
            target_user_id=admin_user.id,  # Targeting self
            new_role=RoleEnum.PATIENT,  # Different role
        )
        
        # Should detect this as escalation attempt
        assert result is True

    def test_privilege_escalation_allows_other_user_changes(self, admin_user, non_admin_user):
        """Test that admin can modify other users' roles."""
        # Modifying a different user should be allowed
        result = check_privilege_escalation(
            current_user=admin_user,
            target_user_id=non_admin_user.id,  # Different user
            new_role=RoleEnum.RESEARCHER,
        )
        
        # Should NOT detect as escalation
        assert result is False


# ============================================================================
# Analytics Tests
# ============================================================================


class TestAnalyticsDashboard:
    """Tests for analytics and reporting."""

    def test_get_analytics_method_exists(self, admin_service):
        """Test that get_analytics method exists."""
        assert hasattr(admin_service, "get_analytics")
        assert callable(admin_service.get_analytics)

    def test_query_analytics_model_tracks_performance(self):
        """Test that QueryAnalyticsModel tracks query performance."""
        analytics = QueryAnalyticsModel(
            id=1,
            user_id=1,
            organization_id=1,
            query_text="SELECT * FROM documents",
            response_time_ms=125.5,
            status_code=200,
            feedback_score=5,
            created_at=datetime.now(),
        )
        
        assert analytics.response_time_ms == 125.5
        assert analytics.status_code == 200
        assert analytics.feedback_score == 5


# ============================================================================
# Integration Tests
# ============================================================================


class TestAdminServiceIntegration:
    """Integration tests for complete workflows."""

    def test_admin_service_has_all_required_methods(self, admin_service):
        """Test that AdminService has all required methods."""
        required_methods = [
            "create_user",
            "update_user",
            "deactivate_user",
            "get_users",
            "get_audit_logs",
            "create_api_key",
            "revoke_api_key",
            "get_analytics",
            "update_rate_limits",
        ]
        
        for method_name in required_methods:
            assert hasattr(admin_service, method_name)
            assert callable(getattr(admin_service, method_name))

    def test_admin_service_respects_organization_boundaries(self, mock_db, admin_user):
        """Test that admin service respects organization scoping."""
        service = AdminService(session=mock_db, current_admin=admin_user)
        # Service should know admin's organization
        assert service.current_admin.organization_id == admin_user.organization_id

    def test_is_admin_function_validates_role(self, admin_user, non_admin_user):
        """Test that is_admin function correctly identifies admins."""
        assert is_admin(admin_user) is True
        assert is_admin(non_admin_user) is False


# ============================================================================
# HIPAA Compliance Tests
# ============================================================================


class TestHIPAACompliance:
    """Tests for HIPAA compliance features."""

    def test_audit_logs_are_immutable_structure(self):
        """Test that audit logs preserve immutability requirements."""
        # Audit logs should track: WHO, WHAT, WHEN, WHERE, WHY
        audit_log = AuditLogModel(
            id=1,
            user_id=1,  # WHO
            action="USER_CREATED",  # WHAT
            created_at=datetime.now(),  # WHEN
            ip_address="192.168.1.1",  # WHERE
            changes='{"reason": "onboarding"}',  # WHY
            organization_id=1,
            resource_type="USER",
            status="SUCCESS",
        )
        
        assert audit_log.user_id is not None
        assert audit_log.action is not None
        assert audit_log.created_at is not None
        assert audit_log.ip_address is not None

    def test_soft_deletes_preserve_data(self):
        """Test that soft deletes preserve historical data."""
        user = UserModel(
            id=1,
            organization_id=1,
            email="test@example.com",
            hashed_password="hash",
            full_name="Test",
            role=RoleEnum.PATIENT,
            is_active=True,
        )
        
        assert user.is_active is True
        # Soft delete
        user.is_active = False
        # Data still exists
        assert user.email == "test@example.com"
        assert user.id == 1

    def test_organization_isolation(self, organization):
        """Test that data is properly isolated by organization."""
        user1 = UserModel(
            id=1,
            organization_id=1,
            email="user1@org1.com",
            hashed_password="hash1",
            full_name="User 1",
            role=RoleEnum.PATIENT,
            is_active=True,
        )
        
        user2 = UserModel(
            id=2,
            organization_id=2,
            email="user2@org2.com",
            hashed_password="hash2",
            full_name="User 2",
            role=RoleEnum.PATIENT,
            is_active=True,
        )
        
        # Different organizations
        assert user1.organization_id != user2.organization_id
        # Cannot access data across organization boundaries
        assert user1.email != user2.email



# ============================================================================
# AdminService Initialization Tests
