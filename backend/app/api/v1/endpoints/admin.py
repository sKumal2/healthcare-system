from fastapi import APIRouter, Depends
from typing import List
from app.services.admin_service import AdminService
from app.models.schemas import UserData, AnalyticsData, AuditLog

router = APIRouter(prefix="/admin", tags=["admin"])


def get_admin_service() -> AdminService:
    """Dependency injection for AdminService."""
    return AdminService()


@router.get("/users", response_model=List[UserData])
async def get_users(
    service: AdminService = Depends(get_admin_service)
) -> List[UserData]:
    """
    Get list of all users.

    Returns:
        List of users with their details
    """
    return service.get_users()


@router.get("/analytics", response_model=AnalyticsData)
async def get_analytics(
    service: AdminService = Depends(get_admin_service)
) -> AnalyticsData:
    """
    Get system analytics data.

    Returns:
        Analytics including total users, documents, and queries
    """
    return service.get_analytics()


@router.get("/audit-logs", response_model=List[AuditLog])
async def get_audit_logs(
    limit: int = 10,
    service: AdminService = Depends(get_admin_service)
) -> List[AuditLog]:
    """
    Get audit logs.

    Args:
        limit: Maximum number of logs to return (default: 10)

    Returns:
        List of audit log entries
    """
    return service.get_audit_logs(limit=limit)
