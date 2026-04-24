"""
Admin API endpoints for healthcare RAG system.
All endpoints require admin role and implement full audit logging.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from app.services.admin_service import AdminService
from app.models.database import UserModel, RoleEnum
from app.models.admin_schemas import (
    UserCreate, UserUpdate, UserResponse, AuditLogFilters,
    AuditLogResponse, ApiKeyCreate, RateLimitUpdate, PaginationParams
)
from app.core.security import get_current_user  # Assuming auth is already set up


router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# ============ DEPENDENCIES ============

def get_db():
    """Database session dependency."""
    # TODO: Implement database session manager
    pass


def require_admin(current_user: UserModel = Depends(get_current_user)) -> UserModel:
    """Verify current user is admin."""
    if current_user.role != RoleEnum.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


def get_admin_service(
    db: Session = Depends(get_db),
    admin: UserModel = Depends(require_admin)
) -> AdminService:
    """Get admin service instance."""
    return AdminService(session=db, current_admin=admin)


# ============ USER MANAGEMENT ENDPOINTS ============

@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    service: AdminService = Depends(get_admin_service),
    x_forwarded_for: Optional[str] = Header(None),
):
    """
    Create a new user (admin only).
    
    Args:
        user_data: User creation data
        service: Admin service instance
        x_forwarded_for: Client IP from headers
    
    Returns:
        Created user response
    """
    try:
        return service.create_user(user_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user"
        )


@router.get("/users", response_model=dict)
async def list_users(
    organization_id: Optional[int] = Query(None),
    role: Optional[RoleEnum] = Query(None),
    is_active: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: AdminService = Depends(get_admin_service),
):
    """
    List users with filtering and pagination.
    
    Query Parameters:
        organization_id: Filter by organization
        role: Filter by role
        is_active: Filter by active status
        page: Page number (default 1)
        page_size: Records per page (default 20, max 100)
    
    Returns:
        Paginated user list
    """
    return service.get_users(
        organization_id=organization_id,
        role=role,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    service: AdminService = Depends(get_admin_service),
):
    """
    Get a specific user by ID.
    
    Args:
        user_id: User ID
        service: Admin service
    
    Returns:
        User response
    """
    users = service.get_users(page=1, page_size=1)  # Minimal approach
    # In production, add a direct get_user method
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Use /users endpoint with filters"
    )


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    service: AdminService = Depends(get_admin_service),
):
    """
    Update user (admin only).
    
    Args:
        user_id: User ID to update
        user_data: Updated user data
        service: Admin service
    
    Returns:
        Updated user response
    """
    return service.update_user(user_id, user_data)


@router.delete("/users/{user_id}", response_model=UserResponse)
async def deactivate_user(
    user_id: int,
    service: AdminService = Depends(get_admin_service),
):
    """
    Deactivate a user (soft delete).
    
    Args:
        user_id: User ID to deactivate
        service: Admin service
    
    Returns:
        Deactivated user response
    """
    return service.deactivate_user(user_id)


# ============ AUDIT LOG ENDPOINTS ============

@router.get("/audit-logs", response_model=dict)
async def get_audit_logs(
    user_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    resource_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    service: AdminService = Depends(get_admin_service),
):
    """
    Get audit logs with advanced filtering (HIPAA compliance).
    
    Query Parameters:
        user_id: Filter by user ID
        action: Filter by action type (e.g., USER_CREATED, ROLE_UPDATED)
        resource_type: Filter by resource type (e.g., USER, API_KEY)
        resource_id: Filter by resource ID
        status: Filter by status (SUCCESS, FAILURE)
        start_date: Filter by start date
        end_date: Filter by end date
        page: Page number
        page_size: Records per page
    
    Returns:
        Paginated audit logs
    """
    filters = AuditLogFilters(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )
    
    return service.get_audit_logs(filters, page, page_size)


# ============ API KEY MANAGEMENT ENDPOINTS ============

@router.post("/api-keys/{user_id}", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    user_id: int,
    key_data: ApiKeyCreate,
    service: AdminService = Depends(get_admin_service),
):
    """
    Create a new API key for a user.
    
    NOTE: The plaintext key is only shown on creation and cannot be recovered.
    
    Args:
        user_id: User ID
        key_data: API key creation data
        service: Admin service
    
    Returns:
        API key details with plaintext key (only shown once)
    """
    return service.create_api_key(user_id, key_data)


@router.delete("/api-keys/{api_key_id}", response_model=dict)
async def revoke_api_key(
    api_key_id: int,
    service: AdminService = Depends(get_admin_service),
):
    """
    Revoke an API key (cannot be recovered, can be reset by creating new).
    
    Args:
        api_key_id: API key ID
        service: Admin service
    
    Returns:
        Success message
    """
    return service.revoke_api_key(api_key_id)


# ============ ANALYTICS ENDPOINTS ============

@router.get("/analytics", response_model=dict)
async def get_analytics(
    days: int = Query(30, ge=1, le=365),
    service: AdminService = Depends(get_admin_service),
):
    """
    Get organization analytics dashboard.
    
    Query Parameters:
        days: Number of days to look back (default 30, max 365)
    
    Returns:
        Analytics data including:
        - metrics: Overall KPIs (total queries, avg response time, etc.)
        - top_users: Top performing users
        - usage_trend: Daily usage trend
    """
    return service.get_analytics(days)


# ============ RATE LIMIT ENDPOINTS ============

@router.patch("/rate-limits/{user_id}", response_model=dict)
async def update_rate_limits(
    user_id: int,
    limits: RateLimitUpdate,
    service: AdminService = Depends(get_admin_service),
):
    """
    Update rate limits for a user.
    
    Args:
        user_id: User ID
        limits: New rate limit values
        service: Admin service
    
    Returns:
        Updated rate limit configuration
    """
    return service.update_rate_limits(user_id, limits)


# ============ HEALTH CHECK ============

@router.get("/health", response_model=dict)
async def admin_health(admin: UserModel = Depends(require_admin)):
    """
    Health check endpoint (admin only).
    
    Returns:
        Health status
    """
    return {
        "status": "healthy",
        "admin_id": admin.id,
        "organization_id": admin.organization_id,
    }
