"""
Utility functions for the admin service.
Includes audit logging, data masking, and permission checking.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import AuditLog, User
from app.models.enums import RoleEnum

UTC = timezone.utc

logger = logging.getLogger("audit")


async def create_audit_log(
    session: AsyncSession,
    user_id,
    organization_id,
    action: str,
    resource_type: str,
    resource_id=None,
    changes: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    status: str = "SUCCESS",
    error_message: Optional[str] = None,
) -> AuditLog:
    """Add an audit log row to the session. The caller is responsible for commit.

    Utility helpers must never commit on their own — doing so breaks the
    atomicity of any wrapping transaction the caller has set up.
    """
    audit_log = AuditLog(
        user_id=user_id,
        organization_id=organization_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        changes=json.dumps(changes) if changes else None,
        ip_address=ip_address,
        user_agent=user_agent,
        status=status,
        error_message=error_message,
    )
    session.add(audit_log)
    return audit_log


def mask_sensitive_data(data: str, pattern: str = "default") -> str:
    """Mask sensitive data like API keys, passwords, emails."""
    if not data:
        return data

    if pattern == "email":
        match = re.match(r"(.)(.*?)(@.*)", data)
        if match:
            return f"{match.group(1)}***{match.group(3)}"

    elif pattern == "api_key":
        if len(data) > 8:
            return f"{data[:8]}****"

    elif pattern == "password":
        return "****"

    if len(data) > 2:
        return f"{data[0]}***{data[-1]}"
    return "****"


def extract_before_after(
    old_data: Dict[str, Any], new_data: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    """Extract before/after values, automatically masking sensitive fields."""
    sensitive_fields = {"password", "hashed_password", "key", "key_hash", "token"}

    before: Dict[str, Any] = {}
    after: Dict[str, Any] = {}

    all_keys = set(old_data.keys()) | set(new_data.keys())

    for key in all_keys:
        old_val = old_data.get(key)
        new_val = new_data.get(key)

        if old_val == new_val:
            continue

        if key in sensitive_fields:
            before[key] = mask_sensitive_data(str(old_val), "password") if old_val else None
            after[key] = mask_sensitive_data(str(new_val), "password") if new_val else None
        else:
            before[key] = old_val
            after[key] = new_val

    return {"before": before, "after": after}


def check_privilege_escalation(
    current_user: User,
    target_user_id,
    new_role: Optional[RoleEnum] = None,
) -> bool:
    """Detect attempts to modify one's own role."""
    if current_user.id == target_user_id and new_role and new_role != current_user.role:
        return True
    return False


def is_admin(user: User) -> bool:
    """Check if user has admin role."""
    return user.role == RoleEnum.ADMIN


async def safe_log_action(
    session: AsyncSession,
    user_id,
    organization_id,
    action: str,
    resource_type: str,
    resource_id=None,
    changes: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Optional[AuditLog]:
    """Safely create an audit log entry, swallowing exceptions.

    Logs failures via the audit logger without exposing the exception text,
    which can carry PHI / query parameters.
    """
    try:
        return await create_audit_log(
            session=session,
            user_id=user_id,
            organization_id=organization_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            changes=changes,
            **kwargs,
        )
    except Exception:
        logger.error("Audit log creation failed", exc_info=True)
        return None


async def paginate_query(
    session: AsyncSession, query, page: int = 1, page_size: int = 20
):
    """Paginate an async SQLAlchemy ``select()`` statement.

    Returns ``(items, total, page, page_size, total_pages)``.
    """
    total_result = await session.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = total_result.scalar() or 0
    total_pages = (total + page_size - 1) // page_size

    result = await session.execute(
        query.offset((page - 1) * page_size).limit(page_size)
    )
    items = result.scalars().all()

    return items, total, page, page_size, total_pages
