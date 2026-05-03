"""
Admin Service - Core business logic for admin operations.
Includes user management, organization management, audit logs, analytics, etc.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
from fastapi import HTTPException, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin_schemas import (
    ApiKeyCreate,
    AuditLogFilters,
    RateLimitUpdate,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.models.database import (
    ApiKey,
    AuditLog,
    QueryAnalytics,
    RateLimit,
    User,
)
from app.models.enums import RoleEnum
from app.utils.audit import (
    check_privilege_escalation,
    create_audit_log,
    extract_before_after,
    is_admin,
    paginate_query,
)

UTC = timezone.utc


class AdminService:
    """Service for admin operations with full audit logging."""

    def __init__(self, session: AsyncSession, current_admin: User):
        self.session = session
        self.current_admin = current_admin

        if not is_admin(self.current_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can access admin service",
            )

    # ============ USER MANAGEMENT ============

    async def create_user(self, user_data: UserCreate) -> UserResponse:
        result = await self.session.execute(
            select(User).where(User.email == user_data.email)
        )
        existing_user = result.scalar_one_or_none()

        if existing_user:
            await create_audit_log(
                session=self.session,
                user_id=self.current_admin.id,
                organization_id=self.current_admin.organization_id,
                action="USER_CREATE_FAILED",
                resource_type="USER",
                status="FAILURE",
                error_message=f"User with email {user_data.email} already exists",
            )
            await self.session.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists",
            )

        hashed_password = self._hash_password(user_data.password)

        new_user = User(
            organization_id=user_data.organization_id,
            email=user_data.email,
            full_name=user_data.full_name,
            password_hash=hashed_password,
            role=user_data.role,
            is_active=True,
        )

        self.session.add(new_user)
        await self.session.flush()

        await create_audit_log(
            session=self.session,
            user_id=self.current_admin.id,
            organization_id=self.current_admin.organization_id,
            action="USER_CREATED",
            resource_type="USER",
            resource_id=new_user.id,
            changes={"email": user_data.email, "role": user_data.role.value},
        )

        await self.session.commit()
        return UserResponse.from_orm(new_user)

    async def update_user(self, user_id: int, user_data: UserUpdate) -> UserResponse:
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        if user_data.role and check_privilege_escalation(
            self.current_admin, user_id, user_data.role
        ):
            await create_audit_log(
                session=self.session,
                user_id=self.current_admin.id,
                organization_id=self.current_admin.organization_id,
                action="USER_UPDATE_FAILED",
                resource_type="USER",
                resource_id=user_id,
                status="FAILURE",
                error_message="Privilege escalation attempt detected",
            )
            await self.session.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot modify your own role",
            )

        old_data = {
            "full_name": user.full_name,
            "role": user.role.value,
            "is_active": user.is_active,
        }

        if user_data.full_name is not None:
            user.full_name = user_data.full_name
        if user_data.role is not None:
            user.role = user_data.role
        if user_data.is_active is not None:
            user.is_active = user_data.is_active

        user.updated_at = datetime.now(UTC)

        new_data = {
            "full_name": user.full_name,
            "role": user.role.value,
            "is_active": user.is_active,
        }

        changes = extract_before_after(old_data, new_data)
        await create_audit_log(
            session=self.session,
            user_id=self.current_admin.id,
            organization_id=self.current_admin.organization_id,
            action="USER_UPDATED",
            resource_type="USER",
            resource_id=user_id,
            changes=changes,
        )

        await self.session.commit()
        return UserResponse.from_orm(user)

    async def deactivate_user(self, user_id: int) -> UserResponse:
        if user_id == self.current_admin.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot deactivate yourself",
            )

        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        user.is_active = False
        user.updated_at = datetime.now(UTC)

        await create_audit_log(
            session=self.session,
            user_id=self.current_admin.id,
            organization_id=self.current_admin.organization_id,
            action="USER_DEACTIVATED",
            resource_type="USER",
            resource_id=user_id,
        )

        await self.session.commit()
        return UserResponse.from_orm(user)

    async def get_user_by_id(self, user_id: str) -> UserResponse:
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return UserResponse.from_orm(user)

    async def get_users(
        self,
        organization_id: Optional[int] = None,
        role: Optional[RoleEnum] = None,
        is_active: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        query = select(User)

        if organization_id:
            query = query.where(User.organization_id == organization_id)
        if role:
            query = query.where(User.role == role)
        if is_active is not None:
            query = query.where(User.is_active == is_active)

        query = query.order_by(desc(User.created_at))

        items, total, page, page_size, total_pages = await paginate_query(
            self.session, query, page, page_size
        )

        return {
            "items": [UserResponse.from_orm(u) for u in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    # ============ AUDIT LOG MANAGEMENT ============

    async def get_audit_logs(
        self,
        filters: AuditLogFilters,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        query = select(AuditLog).where(
            AuditLog.organization_id == self.current_admin.organization_id
        )

        if filters.user_id:
            query = query.where(AuditLog.user_id == filters.user_id)
        if filters.action:
            query = query.where(AuditLog.action.ilike(f"%{filters.action}%"))
        if filters.resource_type:
            query = query.where(AuditLog.resource_type == filters.resource_type)
        if filters.resource_id:
            query = query.where(AuditLog.resource_id == filters.resource_id)
        if filters.status:
            query = query.where(AuditLog.status == filters.status)
        if filters.start_date:
            query = query.where(AuditLog.created_at >= filters.start_date)
        if filters.end_date:
            query = query.where(AuditLog.created_at <= filters.end_date)

        query = query.order_by(desc(AuditLog.created_at))

        items, total, page, page_size, total_pages = await paginate_query(
            self.session, query, page, page_size
        )

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    # ============ API KEY MANAGEMENT ============

    async def create_api_key(self, user_id: int, key_data: ApiKeyCreate) -> Dict[str, str]:
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        plaintext_key = f"api_key_{secrets.token_urlsafe(32)}"
        key_hash = self._hash_api_key(plaintext_key)

        expires_at = None
        if key_data.expires_in_days:
            expires_at = datetime.now(UTC) + timedelta(days=key_data.expires_in_days)

        api_key = ApiKey(
            user_id=user_id,
            organization_id=user.organization_id,
            name=key_data.name,
            key_hash=key_hash,
            expires_at=expires_at,
            is_active=True,
        )

        self.session.add(api_key)
        await self.session.flush()

        await create_audit_log(
            session=self.session,
            user_id=self.current_admin.id,
            organization_id=self.current_admin.organization_id,
            action="API_KEY_CREATED",
            resource_type="API_KEY",
            resource_id=api_key.id,
            changes={"name": key_data.name},
        )

        await self.session.commit()

        return {
            "id": str(api_key.id),
            "key": plaintext_key,
            "name": api_key.name,
        }

    async def revoke_api_key(self, api_key_id: int) -> Dict[str, str]:
        result = await self.session.execute(
            select(ApiKey).where(
                ApiKey.id == api_key_id,
                ApiKey.organization_id == self.current_admin.organization_id,
            )
        )
        api_key = result.scalar_one_or_none()

        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="API key not found"
            )

        api_key.is_active = False

        await create_audit_log(
            session=self.session,
            user_id=self.current_admin.id,
            organization_id=self.current_admin.organization_id,
            action="API_KEY_REVOKED",
            resource_type="API_KEY",
            resource_id=api_key_id,
        )

        await self.session.commit()
        return {"detail": "API key revoked successfully"}

    # ============ ANALYTICS ============

    async def get_analytics(self, days: int = 30) -> Dict[str, Any]:
        org_id = self.current_admin.organization_id
        now = datetime.now(UTC)
        start_date = now - timedelta(days=days)

        total_queries = (
            await self.session.execute(
                select(func.count(QueryAnalytics.id)).where(
                    QueryAnalytics.organization_id == org_id
                )
            )
        ).scalar() or 0

        avg_response_time = (
            await self.session.execute(
                select(func.avg(QueryAnalytics.response_time_ms)).where(
                    QueryAnalytics.organization_id == org_id
                )
            )
        ).scalar() or 0.0

        total_users = (
            await self.session.execute(
                select(func.count(User.id)).where(
                    User.organization_id == org_id,
                    User.is_active == True,  # noqa: E712 - SA col compare
                )
            )
        ).scalar() or 0

        queries_24h = (
            await self.session.execute(
                select(func.count(QueryAnalytics.id)).where(
                    QueryAnalytics.organization_id == org_id,
                    QueryAnalytics.created_at >= now - timedelta(hours=24),
                )
            )
        ).scalar() or 0

        avg_feedback = (
            await self.session.execute(
                select(func.avg(QueryAnalytics.feedback_score)).where(
                    QueryAnalytics.organization_id == org_id,
                    QueryAnalytics.feedback_score.isnot(None),
                )
            )
        ).scalar()

        # Peak usage hour (0-23) — group by an SQLAlchemy expression, not a string.
        hour_col = func.extract("hour", QueryAnalytics.created_at).label("hour")
        count_col = func.count(QueryAnalytics.id).label("count")
        peak_hour_result = await self.session.execute(
            select(hour_col, count_col)
            .where(QueryAnalytics.organization_id == org_id)
            .group_by(hour_col)
            .order_by(desc(count_col))
            .limit(1)
        )
        peak_hour = peak_hour_result.first()
        peak_usage_hour = int(peak_hour[0]) if peak_hour else None

        # Top users
        top_users_result = await self.session.execute(
            select(
                User.id,
                User.email,
                func.count(QueryAnalytics.id).label("query_count"),
                func.avg(QueryAnalytics.response_time_ms).label("avg_time"),
                func.max(QueryAnalytics.created_at).label("last_query"),
            )
            .join(QueryAnalytics)
            .where(User.organization_id == org_id)
            .group_by(User.id, User.email)
            .order_by(desc(func.count(QueryAnalytics.id)))
            .limit(10)
        )

        top_users = [
            {
                "user_id": row[0],
                "email": row[1],
                "total_queries": row[2],
                "avg_response_time_ms": float(row[3]) if row[3] else 0.0,
                "last_query_at": row[4],
            }
            for row in top_users_result.all()
        ]

        # Usage trend by date
        date_col = func.date(QueryAnalytics.created_at).label("date")
        usage_trend_result = await self.session.execute(
            select(
                date_col,
                func.count(QueryAnalytics.id).label("query_count"),
                func.count(func.distinct(QueryAnalytics.user_id)).label("unique_users"),
                func.avg(QueryAnalytics.response_time_ms).label("avg_time"),
            )
            .where(
                QueryAnalytics.organization_id == org_id,
                QueryAnalytics.created_at >= start_date,
            )
            .group_by(date_col)
            .order_by(date_col)
        )

        usage_trend = [
            {
                "date": str(row[0]),
                "query_count": row[1],
                "unique_users": row[2],
                "avg_response_time_ms": float(row[3]) if row[3] else 0.0,
            }
            for row in usage_trend_result.all()
        ]

        return {
            "metrics": {
                "total_queries": total_queries,
                "avg_response_time_ms": float(avg_response_time),
                "total_users": total_users,
                "queries_last_24h": queries_24h,
                "avg_feedback_score": float(avg_feedback) if avg_feedback else None,
                "peak_usage_hour": peak_usage_hour,
            },
            "top_users": top_users,
            "usage_trend": usage_trend,
        }

    # ============ RATE LIMITS ============

    async def update_rate_limits(
        self, user_id: int, limits: RateLimitUpdate
    ) -> Dict[str, Any]:
        user_result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = user_result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        rl_result = await self.session.execute(
            select(RateLimit).where(RateLimit.user_id == user_id)
        )
        rate_limit = rl_result.scalar_one_or_none()

        if not rate_limit:
            rate_limit = RateLimit(
                user_id=user_id,
                organization_id=user.organization_id,
            )
            self.session.add(rate_limit)

        old_data = {
            "requests_per_minute": rate_limit.requests_per_minute,
            "requests_per_hour": rate_limit.requests_per_hour,
            "requests_per_day": rate_limit.requests_per_day,
        }

        if limits.requests_per_minute is not None:
            rate_limit.requests_per_minute = limits.requests_per_minute
        if limits.requests_per_hour is not None:
            rate_limit.requests_per_hour = limits.requests_per_hour
        if limits.requests_per_day is not None:
            rate_limit.requests_per_day = limits.requests_per_day

        rate_limit.updated_at = datetime.now(UTC)

        new_data = {
            "requests_per_minute": rate_limit.requests_per_minute,
            "requests_per_hour": rate_limit.requests_per_hour,
            "requests_per_day": rate_limit.requests_per_day,
        }

        await self.session.flush()

        changes = extract_before_after(old_data, new_data)
        await create_audit_log(
            session=self.session,
            user_id=self.current_admin.id,
            organization_id=self.current_admin.organization_id,
            action="RATE_LIMIT_UPDATED",
            resource_type="RATE_LIMIT",
            resource_id=user_id,
            changes=changes,
        )

        await self.session.commit()

        return {
            "user_id": user_id,
            "requests_per_minute": rate_limit.requests_per_minute,
            "requests_per_hour": rate_limit.requests_per_hour,
            "requests_per_day": rate_limit.requests_per_day,
        }

    # ============ UTILITY METHODS ============

    @staticmethod
    def _hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    @staticmethod
    def _verify_password(plain: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(plain.encode(), hashed.encode())
        except Exception:
            return False

    @staticmethod
    def _hash_api_key(key: str) -> str:
        # API keys are high-entropy random tokens, so a fast hash is acceptable.
        return hashlib.sha256(key.encode()).hexdigest()
