"""
Admin Service - Core business logic for admin operations.
Includes user management, organization management, audit logs, analytics, etc.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.database import (
    UserModel, OrganizationModel, AuditLogModel, ApiKeyModel,
    RateLimitModel, QueryAnalyticsModel, RoleEnum
)
from app.models.admin_schemas import (
    UserCreate, UserUpdate, UserResponse, AuditLogFilters,
    ApiKeyCreate, RateLimitUpdate
)
from app.utils.audit import (
    create_audit_log, check_privilege_escalation, is_admin,
    extract_before_after, paginate_query
)
import hashlib
import secrets


class AdminService:
    """Service for admin operations with full audit logging."""
    
    def __init__(self, session: Session, current_admin: UserModel):
        """
        Initialize admin service.
        
        Args:
            session: Database session
            current_admin: Currently authenticated admin user
        """
        self.session = session
        self.current_admin = current_admin
        
        # Verify current user is admin
        if not is_admin(self.current_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can access admin service"
            )
    
    # ============ USER MANAGEMENT ============
    
    def create_user(self, user_data: UserCreate) -> UserResponse:
        """
        Create a new user (admin only).
        
        Args:
            user_data: User creation data
        
        Returns:
            UserResponse with new user data
        
        Raises:
            HTTPException if user already exists or validation fails
        """
        # Check if user already exists
        existing_user = self.session.query(UserModel).filter(
            UserModel.email == user_data.email
        ).first()
        
        if existing_user:
            create_audit_log(
                session=self.session,
                user_id=self.current_admin.id,
                organization_id=self.current_admin.organization_id,
                action="USER_CREATE_FAILED",
                resource_type="USER",
                status="FAILURE",
                error_message=f"User with email {user_data.email} already exists"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )
        
        # Hash password
        hashed_password = self._hash_password(user_data.password)
        
        # Create new user
        new_user = UserModel(
            organization_id=user_data.organization_id,
            email=user_data.email,
            full_name=user_data.full_name,
            hashed_password=hashed_password,
            role=user_data.role,
            is_active=True
        )
        
        self.session.add(new_user)
        self.session.flush()  # Get the ID
        
        # Log the action
        create_audit_log(
            session=self.session,
            user_id=self.current_admin.id,
            organization_id=self.current_admin.organization_id,
            action="USER_CREATED",
            resource_type="USER",
            resource_id=new_user.id,
            changes={
                "email": user_data.email,
                "role": user_data.role.value,
            }
        )
        
        self.session.commit()
        return UserResponse.from_orm(new_user)
    
    def update_user(self, user_id: int, user_data: UserUpdate) -> UserResponse:
        """
        Update user (admin only).
        
        Args:
            user_id: ID of user to update
            user_data: Updated user data
        
        Returns:
            Updated UserResponse
        
        Raises:
            HTTPException if user not found or privilege escalation detected
        """
        user = self.session.query(UserModel).filter(
            UserModel.id == user_id
        ).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Check for privilege escalation
        if user_data.role and check_privilege_escalation(
            self.current_admin, user_id, user_data.role
        ):
            create_audit_log(
                session=self.session,
                user_id=self.current_admin.id,
                organization_id=self.current_admin.organization_id,
                action="USER_UPDATE_FAILED",
                resource_type="USER",
                resource_id=user_id,
                status="FAILURE",
                error_message="Privilege escalation attempt detected"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot modify your own role"
            )
        
        # Track changes
        old_data = {
            "full_name": user.full_name,
            "role": user.role.value,
            "is_active": user.is_active,
        }
        
        # Update fields
        if user_data.full_name is not None:
            user.full_name = user_data.full_name
        if user_data.role is not None:
            user.role = user_data.role
        if user_data.is_active is not None:
            user.is_active = user_data.is_active
        
        user.updated_at = datetime.utcnow()
        
        new_data = {
            "full_name": user.full_name,
            "role": user.role.value,
            "is_active": user.is_active,
        }
        
        # Log the action
        changes = extract_before_after(old_data, new_data)
        create_audit_log(
            session=self.session,
            user_id=self.current_admin.id,
            organization_id=self.current_admin.organization_id,
            action="USER_UPDATED",
            resource_type="USER",
            resource_id=user_id,
            changes=changes
        )
        
        self.session.commit()
        return UserResponse.from_orm(user)
    
    def deactivate_user(self, user_id: int) -> UserResponse:
        """
        Deactivate a user (soft delete).
        
        Args:
            user_id: ID of user to deactivate
        
        Returns:
            Updated UserResponse
        
        Raises:
            HTTPException if user not found
        """
        if user_id == self.current_admin.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot deactivate yourself"
            )
        
        user = self.session.query(UserModel).filter(
            UserModel.id == user_id
        ).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        user.is_active = False
        user.updated_at = datetime.utcnow()
        
        create_audit_log(
            session=self.session,
            user_id=self.current_admin.id,
            organization_id=self.current_admin.organization_id,
            action="USER_DEACTIVATED",
            resource_type="USER",
            resource_id=user_id,
        )
        
        self.session.commit()
        return UserResponse.from_orm(user)
    
    def get_users(
        self,
        organization_id: Optional[int] = None,
        role: Optional[RoleEnum] = None,
        is_active: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        Get users with filtering and pagination.
        
        Args:
            organization_id: Filter by organization
            role: Filter by role
            is_active: Filter by active status
            page: Page number
            page_size: Records per page
        
        Returns:
            Dict with items, pagination info
        """
        query = self.session.query(UserModel)
        
        # Apply filters
        if organization_id:
            query = query.filter(UserModel.organization_id == organization_id)
        if role:
            query = query.filter(UserModel.role == role)
        if is_active is not None:
            query = query.filter(UserModel.is_active == is_active)
        
        # Order by created_at descending
        query = query.order_by(desc(UserModel.created_at))
        
        # Paginate
        items, total, page, page_size, total_pages = paginate_query(query, page, page_size)
        
        return {
            "items": [UserResponse.from_orm(u) for u in items],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
    
    # ============ AUDIT LOG MANAGEMENT ============
    
    def get_audit_logs(
        self,
        filters: AuditLogFilters,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """
        Get audit logs with filtering and pagination.
        
        Args:
            filters: AuditLogFilters for filtering
            page: Page number
            page_size: Records per page
        
        Returns:
            Dict with audit logs and pagination info
        """
        query = self.session.query(AuditLogModel).filter(
            AuditLogModel.organization_id == self.current_admin.organization_id
        )
        
        # Apply filters
        if filters.user_id:
            query = query.filter(AuditLogModel.user_id == filters.user_id)
        if filters.action:
            query = query.filter(AuditLogModel.action.ilike(f"%{filters.action}%"))
        if filters.resource_type:
            query = query.filter(AuditLogModel.resource_type == filters.resource_type)
        if filters.resource_id:
            query = query.filter(AuditLogModel.resource_id == filters.resource_id)
        if filters.status:
            query = query.filter(AuditLogModel.status == filters.status)
        if filters.start_date:
            query = query.filter(AuditLogModel.created_at >= filters.start_date)
        if filters.end_date:
            query = query.filter(AuditLogModel.created_at <= filters.end_date)
        
        # Order by created_at descending
        query = query.order_by(desc(AuditLogModel.created_at))
        
        # Paginate
        items, total, page, page_size, total_pages = paginate_query(query, page, page_size)
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }
    
    # ============ API KEY MANAGEMENT ============
    
    def create_api_key(self, user_id: int, key_data: ApiKeyCreate) -> Dict[str, str]:
        """
        Create a new API key for a user.
        
        Args:
            user_id: User ID
            key_data: API key creation data
        
        Returns:
            Dict with {key, id, name} - key only shown on creation
        
        Raises:
            HTTPException if user not found
        """
        user = self.session.query(UserModel).filter(
            UserModel.id == user_id
        ).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Generate API key
        plaintext_key = f"api_key_{secrets.token_urlsafe(32)}"
        key_hash = self._hash_api_key(plaintext_key)
        
        # Calculate expiration
        expires_at = None
        if key_data.expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=key_data.expires_in_days)
        
        # Create API key record
        api_key = ApiKeyModel(
            user_id=user_id,
            organization_id=user.organization_id,
            name=key_data.name,
            key_hash=key_hash,
            expires_at=expires_at,
            is_active=True,
        )
        
        self.session.add(api_key)
        self.session.flush()
        
        # Log the action
        create_audit_log(
            session=self.session,
            user_id=self.current_admin.id,
            organization_id=self.current_admin.organization_id,
            action="API_KEY_CREATED",
            resource_type="API_KEY",
            resource_id=api_key.id,
            changes={"name": key_data.name}
        )
        
        self.session.commit()
        
        # Return key details (plaintext key only shown once)
        return {
            "id": str(api_key.id),
            "key": plaintext_key,
            "name": api_key.name,
        }
    
    def revoke_api_key(self, api_key_id: int) -> Dict[str, str]:
        """
        Revoke an API key.
        
        Args:
            api_key_id: API key ID
        
        Returns:
            Success message
        
        Raises:
            HTTPException if key not found
        """
        api_key = self.session.query(ApiKeyModel).filter(
            ApiKeyModel.id == api_key_id,
            ApiKeyModel.organization_id == self.current_admin.organization_id
        ).first()
        
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="API key not found"
            )
        
        api_key.is_active = False
        
        create_audit_log(
            session=self.session,
            user_id=self.current_admin.id,
            organization_id=self.current_admin.organization_id,
            action="API_KEY_REVOKED",
            resource_type="API_KEY",
            resource_id=api_key_id,
        )
        
        self.session.commit()
        return {"detail": "API key revoked successfully"}
    
    # ============ ANALYTICS ============
    
    def get_analytics(self, days: int = 30) -> Dict[str, Any]:
        """
        Get analytics for the organization.
        
        Args:
            days: Number of days to look back
        
        Returns:
            Analytics data including metrics, top users, usage trend
        """
        org_id = self.current_admin.organization_id
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Total queries
        total_queries = self.session.query(func.count(QueryAnalyticsModel.id)).filter(
            QueryAnalyticsModel.organization_id == org_id
        ).scalar() or 0
        
        # Average response time
        avg_response_time = self.session.query(
            func.avg(QueryAnalyticsModel.response_time_ms)
        ).filter(
            QueryAnalyticsModel.organization_id == org_id
        ).scalar() or 0.0
        
        # Total active users
        total_users = self.session.query(func.count(UserModel.id)).filter(
            UserModel.organization_id == org_id,
            UserModel.is_active == True
        ).scalar() or 0
        
        # Queries in last 24 hours
        queries_24h = self.session.query(func.count(QueryAnalyticsModel.id)).filter(
            QueryAnalyticsModel.organization_id == org_id,
            QueryAnalyticsModel.created_at >= datetime.utcnow() - timedelta(hours=24)
        ).scalar() or 0
        
        # Average feedback score
        avg_feedback = self.session.query(
            func.avg(QueryAnalyticsModel.feedback_score)
        ).filter(
            QueryAnalyticsModel.organization_id == org_id,
            QueryAnalyticsModel.feedback_score.isnot(None)
        ).scalar()
        
        # Peak usage hour (0-23)
        peak_hour = self.session.query(
            func.extract("hour", QueryAnalyticsModel.created_at).label("hour"),
            func.count(QueryAnalyticsModel.id).label("count")
        ).filter(
            QueryAnalyticsModel.organization_id == org_id
        ).group_by("hour").order_by(desc(func.count(QueryAnalyticsModel.id))).first()
        
        peak_usage_hour = peak_hour[0] if peak_hour else None
        
        # Top users
        top_users_query = self.session.query(
            UserModel.id,
            UserModel.email,
            func.count(QueryAnalyticsModel.id).label("query_count"),
            func.avg(QueryAnalyticsModel.response_time_ms).label("avg_time"),
            func.max(QueryAnalyticsModel.created_at).label("last_query")
        ).join(
            QueryAnalyticsModel
        ).filter(
            UserModel.organization_id == org_id
        ).group_by(
            UserModel.id, UserModel.email
        ).order_by(
            desc(func.count(QueryAnalyticsModel.id))
        ).limit(10)
        
        top_users = [
            {
                "user_id": u[0],
                "email": u[1],
                "total_queries": u[2],
                "avg_response_time_ms": float(u[3]) if u[3] else 0.0,
                "last_query_at": u[4],
            }
            for u in top_users_query
        ]
        
        # Usage trend by date
        usage_trend_query = self.session.query(
            func.date(QueryAnalyticsModel.created_at).label("date"),
            func.count(QueryAnalyticsModel.id).label("query_count"),
            func.count(func.distinct(QueryAnalyticsModel.user_id)).label("unique_users"),
            func.avg(QueryAnalyticsModel.response_time_ms).label("avg_time")
        ).filter(
            QueryAnalyticsModel.organization_id == org_id,
            QueryAnalyticsModel.created_at >= start_date
        ).group_by(
            func.date(QueryAnalyticsModel.created_at)
        ).order_by(
            func.date(QueryAnalyticsModel.created_at)
        )
        
        usage_trend = [
            {
                "date": str(u[0]),
                "query_count": u[1],
                "unique_users": u[2],
                "avg_response_time_ms": float(u[3]) if u[3] else 0.0,
            }
            for u in usage_trend_query
        ]
        
        return {
            "metrics": {
                "total_queries": total_queries,
                "avg_response_time_ms": float(avg_response_time),
                "total_users": total_users,
                "queries_last_24h": queries_24h,
                "avg_feedback_score": float(avg_feedback) if avg_feedback else None,
                "peak_usage_hour": int(peak_usage_hour) if peak_usage_hour else None,
            },
            "top_users": top_users,
            "usage_trend": usage_trend,
        }
    
    # ============ RATE LIMITS ============
    
    def update_rate_limits(self, user_id: int, limits: RateLimitUpdate) -> Dict[str, Any]:
        """
        Update rate limits for a user.
        
        Args:
            user_id: User ID
            limits: New rate limit values
        
        Returns:
            Updated rate limit data
        
        Raises:
            HTTPException if user not found
        """
        user = self.session.query(UserModel).filter(
            UserModel.id == user_id
        ).first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        rate_limit = self.session.query(RateLimitModel).filter(
            RateLimitModel.user_id == user_id
        ).first()
        
        if not rate_limit:
            # Create default rate limit
            rate_limit = RateLimitModel(
                user_id=user_id,
                organization_id=user.organization_id,
            )
            self.session.add(rate_limit)
        
        # Track changes
        old_data = {
            "requests_per_minute": rate_limit.requests_per_minute,
            "requests_per_hour": rate_limit.requests_per_hour,
            "requests_per_day": rate_limit.requests_per_day,
        }
        
        # Update fields
        if limits.requests_per_minute is not None:
            rate_limit.requests_per_minute = limits.requests_per_minute
        if limits.requests_per_hour is not None:
            rate_limit.requests_per_hour = limits.requests_per_hour
        if limits.requests_per_day is not None:
            rate_limit.requests_per_day = limits.requests_per_day
        
        rate_limit.updated_at = datetime.utcnow()
        
        new_data = {
            "requests_per_minute": rate_limit.requests_per_minute,
            "requests_per_hour": rate_limit.requests_per_hour,
            "requests_per_day": rate_limit.requests_per_day,
        }
        
        self.session.flush()
        
        changes = extract_before_after(old_data, new_data)
        create_audit_log(
            session=self.session,
            user_id=self.current_admin.id,
            organization_id=self.current_admin.organization_id,
            action="RATE_LIMIT_UPDATED",
            resource_type="RATE_LIMIT",
            resource_id=user_id,
            changes=changes
        )
        
        self.session.commit()
        
        return {
            "user_id": user_id,
            "requests_per_minute": rate_limit.requests_per_minute,
            "requests_per_hour": rate_limit.requests_per_hour,
            "requests_per_day": rate_limit.requests_per_day,
        }
    
    # ============ UTILITY METHODS ============
    
    @staticmethod
    def _hash_password(password: str) -> str:
        """Hash a password using SHA-256 (use bcrypt in production)."""
        return hashlib.sha256(password.encode()).hexdigest()
    
    @staticmethod
    def _hash_api_key(key: str) -> str:
        """Hash an API key."""
        return hashlib.sha256(key.encode()).hexdigest()

