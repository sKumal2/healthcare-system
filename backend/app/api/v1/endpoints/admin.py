"""
Admin API endpoints for healthcare RAG system.
All endpoints require admin role and implement full audit logging.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.gateway.auth.dependencies import get_current_user
from app.gateway.auth.models import UserIdentity
from app.models.database import Organization, User
from app.models.enums import RoleEnum
from app.models.admin_schemas import (
    UserCreate, UserUpdate, UserResponse, AuditLogFilters,
    ApiKeyCreate, RateLimitUpdate,
)
from app.services.admin_service import AdminService


router = APIRouter(prefix="/admin", tags=["Admin"])


# ============ DEPENDENCIES ============

def require_admin(current_user: UserIdentity = Depends(get_current_user)) -> UserIdentity:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


async def get_admin_service(
    db: AsyncSession = Depends(get_db),
    admin: UserIdentity = Depends(require_admin),
) -> AdminService:
    result = await db.execute(select(User).where(User.id == admin.user_id))
    admin_user = result.scalar_one_or_none()
    if not admin_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin user not found"
        )
    return AdminService(session=db, current_admin=admin_user)


# ============ USER MANAGEMENT ENDPOINTS ============

@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    service: AdminService = Depends(get_admin_service),
    x_forwarded_for: Optional[str] = Header(None),
):
    try:
        return await service.create_user(user_data)
    except HTTPException:
        raise
    except Exception:
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
    return await service.get_users(
        organization_id=organization_id,
        role=role,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    service: AdminService = Depends(get_admin_service),
):
    return await service.get_user_by_id(user_id)


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    service: AdminService = Depends(get_admin_service),
):
    return await service.update_user(user_id, user_data)


@router.delete("/users/{user_id}", response_model=UserResponse)
async def deactivate_user(
    user_id: int,
    service: AdminService = Depends(get_admin_service),
):
    return await service.deactivate_user(user_id)


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
    filters = AuditLogFilters(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        start_date=start_date,
        end_date=end_date,
    )
    return await service.get_audit_logs(filters, page, page_size)


# ============ API KEY MANAGEMENT ENDPOINTS ============

@router.post("/api-keys/{user_id}", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    user_id: int,
    key_data: ApiKeyCreate,
    service: AdminService = Depends(get_admin_service),
):
    return await service.create_api_key(user_id, key_data)


@router.delete("/api-keys/{api_key_id}", response_model=dict)
async def revoke_api_key(
    api_key_id: int,
    service: AdminService = Depends(get_admin_service),
):
    return await service.revoke_api_key(api_key_id)


# ============ ANALYTICS ENDPOINTS ============

@router.get("/analytics", response_model=dict)
async def get_analytics(
    days: int = Query(30, ge=1, le=365),
    service: AdminService = Depends(get_admin_service),
):
    return await service.get_analytics(days)


# ============ RATE LIMIT ENDPOINTS ============

@router.patch("/rate-limits/{user_id}", response_model=dict)
async def update_rate_limits(
    user_id: int,
    limits: RateLimitUpdate,
    service: AdminService = Depends(get_admin_service),
):
    return await service.update_rate_limits(user_id, limits)


# ============ ORG INVITE CODE ============

@router.get("/org/invite-code", response_model=dict)
async def get_invite_code(
    db: AsyncSession = Depends(get_db),
    admin: UserIdentity = Depends(require_admin),
):
    """Get the organization's invite code to share with new users."""
    import secrets

    result = await db.execute(select(User).where(User.id == admin.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    org_result = await db.execute(
        select(Organization).where(Organization.id == user.organization_id)
    )
    org = org_result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if not org.invite_code:
        org.invite_code = secrets.token_hex(4).upper()
        await db.commit()
        await db.refresh(org)

    return {
        "invite_code": org.invite_code,
        "org_name": org.name,
        "share_message": f"Join {org.name} on HealthRAG using code: {org.invite_code}",
    }


@router.post("/org/regenerate-invite-code", response_model=dict)
async def regenerate_invite_code(
    db: AsyncSession = Depends(get_db),
    admin: UserIdentity = Depends(require_admin),
):
    """Generate a new invite code (invalidates old one)."""
    import secrets

    result = await db.execute(select(User).where(User.id == admin.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    org_result = await db.execute(
        select(Organization).where(Organization.id == user.organization_id)
    )
    org = org_result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    org.invite_code = secrets.token_hex(4).upper()
    await db.commit()
    await db.refresh(org)

    return {
        "invite_code": org.invite_code,
        "message": "Invite code regenerated. Old code is no longer valid.",
    }


# ============ HEALTH CHECK ============

@router.get("/health", response_model=dict)
async def admin_health(admin: UserIdentity = Depends(require_admin)):
    return {
        "status": "healthy",
        "admin_id": admin.user_id,
    }
