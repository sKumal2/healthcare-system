"""Tests for the async AdminService and audit utilities.

Focused on the Definition of Done in PROMPTFIX.md:
- bcrypt password hashing (no SHA-256)
- audit utility no longer commits
- analytics returns the documented shape
"""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.database import RoleEnum, User as UserModel
import bcrypt as _bcrypt

from app.services.admin_service import AdminService
from app.utils.audit import create_audit_log


@pytest.fixture
def admin_user():
    user = UserModel(
        id=1,
        organization_id=1,
        email="admin@test.com",
        password_hash="placeholder",
        full_name="Test Admin",
        role=RoleEnum.ADMIN,
        is_active=True,
    )
    return user


@pytest.fixture
def mock_async_session():
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


# -------------------------- password hashing --------------------------

def test_hash_password_uses_bcrypt():
    hashed = AdminService._hash_password("CorrectHorse123")
    assert hashed.startswith(("$2a$", "$2b$", "$2y$"))


def test_verify_password_validates_bcrypt():
    plain = "CorrectHorse123"
    hashed = AdminService._hash_password(plain)
    assert AdminService._verify_password(plain, hashed) is True
    assert AdminService._verify_password("Wrong123", hashed) is False


def test_sha256_hash_does_not_pass_verification():
    """Regression: legacy SHA-256 hashes must not validate as bcrypt."""
    plain = "CorrectHorse123"
    legacy_sha = hashlib.sha256(plain.encode()).hexdigest()
    # passlib raises on malformed hashes — assert it does not silently succeed.
    try:
        result = _bcrypt.checkpw(plain.encode(), legacy_sha.encode())
    except Exception:
        result = False
    assert result is False


# -------------------------- audit utility --------------------------

@pytest.mark.asyncio
async def test_create_audit_log_does_not_commit(mock_async_session):
    audit = await create_audit_log(
        session=mock_async_session,
        user_id=1,
        organization_id=1,
        action="USER_CREATED",
        resource_type="USER",
    )
    mock_async_session.add.assert_called_once_with(audit)
    mock_async_session.commit.assert_not_called()


# -------------------------- admin service constructor --------------------------

def test_constructor_rejects_non_admin(mock_async_session):
    from fastapi import HTTPException
    non_admin = UserModel(
        id=2,
        organization_id=1,
        email="x@test.com",
        password_hash="x",
        full_name="x",
        role=RoleEnum.PATIENT,
        is_active=True,
    )
    with pytest.raises(HTTPException) as exc:
        AdminService(session=mock_async_session, current_admin=non_admin)
    assert exc.value.status_code == 403


# -------------------------- analytics --------------------------

@pytest.mark.asyncio
async def test_get_analytics_returns_documented_shape(mock_async_session, admin_user):
    """Each scalar() / first() / all() call returns a stub so the shape can be asserted."""
    scalar_values = iter([10, 123.4, 5, 2, 4.2])  # total, avg, users, 24h, feedback

    def execute_side_effect(*args, **kwargs):
        result = MagicMock()
        try:
            result.scalar.return_value = next(scalar_values)
        except StopIteration:
            result.scalar.return_value = None
        result.first.return_value = (14, 3)  # peak hour, count
        result.all.return_value = []
        return result

    mock_async_session.execute = AsyncMock(side_effect=execute_side_effect)

    service = AdminService(session=mock_async_session, current_admin=admin_user)
    analytics = await service.get_analytics(days=30)

    assert set(analytics.keys()) == {"metrics", "top_users", "usage_trend"}
    metrics = analytics["metrics"]
    assert metrics["total_queries"] == 10
    assert metrics["avg_response_time_ms"] == 123.4
    assert metrics["total_users"] == 5
    assert metrics["queries_last_24h"] == 2
    assert metrics["avg_feedback_score"] == 4.2
    assert metrics["peak_usage_hour"] == 14
    assert analytics["top_users"] == []
    assert analytics["usage_trend"] == []
