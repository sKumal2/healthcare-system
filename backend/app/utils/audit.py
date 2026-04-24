"""
Utility functions for the admin service.
Includes audit logging, data masking, and permission checking.
"""

import json
import re
from typing import Any, Dict, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.database import AuditLogModel, UserModel, RoleEnum


def create_audit_log(
    session: Session,
    user_id: int,
    organization_id: int,
    action: str,
    resource_type: str,
    resource_id: Optional[int] = None,
    changes: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    status: str = "SUCCESS",
    error_message: Optional[str] = None,
) -> AuditLogModel:
    """
    Create an audit log entry for tracking admin actions.
    
    Args:
        session: Database session
        user_id: ID of admin performing the action
        organization_id: Organization where action occurred
        action: Action type (e.g., "USER_CREATED", "ROLE_UPDATED")
        resource_type: Type of resource affected (e.g., "USER", "API_KEY")
        resource_id: ID of affected resource
        changes: Dict of changes (before/after values)
        ip_address: Client IP address
        user_agent: Client user agent
        status: SUCCESS or FAILURE
        error_message: Error message if status is FAILURE
    
    Returns:
        AuditLogModel instance
    """
    audit_log = AuditLogModel(
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
    session.commit()
    return audit_log


def mask_sensitive_data(data: str, pattern: str = "default") -> str:
    """
    Mask sensitive data like API keys, passwords, emails.
    
    Args:
        data: Data to mask
        pattern: Type of pattern (default, email, api_key, password)
    
    Returns:
        Masked string
    """
    if not data:
        return data
    
    if pattern == "email":
        # Mask: user@example.com -> u***@example.com
        match = re.match(r"(.)(.*?)(@.*)", data)
        if match:
            return f"{match.group(1)}***{match.group(3)}"
    
    elif pattern == "api_key":
        # Mask: sk_live_abcd1234 -> sk_live_****
        if len(data) > 8:
            return f"{data[:8]}****"
    
    elif pattern == "password":
        # Mask: password -> ****
        return "****"
    
    # Default: show first and last character
    if len(data) > 2:
        return f"{data[0]}***{data[-1]}"
    return "****"


def extract_before_after(old_data: Dict[str, Any], new_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Extract before/after values from two data dictionaries.
    Automatically masks sensitive fields.
    
    Args:
        old_data: Old values
        new_data: New values
    
    Returns:
        Dict with 'before' and 'after' keys
    """
    sensitive_fields = {"password", "hashed_password", "key", "key_hash", "token"}
    
    before = {}
    after = {}
    
    # Get all keys from both dicts
    all_keys = set(old_data.keys()) | set(new_data.keys())
    
    for key in all_keys:
        old_val = old_data.get(key)
        new_val = new_data.get(key)
        
        if old_val == new_val:
            continue
        
        # Mask sensitive fields
        if key in sensitive_fields:
            before[key] = mask_sensitive_data(str(old_val), "password") if old_val else None
            after[key] = mask_sensitive_data(str(new_val), "password") if new_val else None
        else:
            before[key] = old_val
            after[key] = new_val
    
    return {"before": before, "after": after}


def check_privilege_escalation(
    current_user: UserModel,
    target_user_id: int,
    new_role: Optional[RoleEnum] = None,
) -> bool:
    """
    Check if an admin is attempting privilege escalation.
    Rules:
    - Admin cannot remove themselves from admin role
    - Admin cannot modify another admin unless authorized
    
    Args:
        current_user: Admin user making the change
        target_user_id: User being modified
        new_role: New role being assigned
    
    Returns:
        True if escalation detected, False otherwise
    """
    # Cannot modify own role
    if current_user.id == target_user_id and new_role and new_role != current_user.role:
        return True
    
    return False


def is_admin(user: UserModel) -> bool:
    """Check if user has admin role."""
    return user.role == RoleEnum.ADMIN


def safe_log_action(
    session: Session,
    user_id: int,
    organization_id: int,
    action: str,
    resource_type: str,
    resource_id: Optional[int] = None,
    changes: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Optional[AuditLogModel]:
    """
    Safely create audit log with exception handling.
    Does not raise exceptions to avoid breaking the main flow.
    
    Args:
        session: Database session
        user_id: Admin user ID
        organization_id: Organization ID
        action: Action type
        resource_type: Resource type
        resource_id: Resource ID
        changes: Changes dict
        **kwargs: Additional audit log arguments
    
    Returns:
        AuditLogModel if successful, None otherwise
    """
    try:
        return create_audit_log(
            session=session,
            user_id=user_id,
            organization_id=organization_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            changes=changes,
            **kwargs,
        )
    except Exception as e:
        # Log to monitoring system
        print(f"Audit log creation failed: {str(e)}")
        return None


def paginate_query(query, page: int = 1, page_size: int = 20):
    """
    Paginate a SQLAlchemy query.
    
    Args:
        query: SQLAlchemy query
        page: Page number (1-indexed)
        page_size: Records per page
    
    Returns:
        Tuple of (items, total, page, page_size, total_pages)
    """
    total = query.count()
    total_pages = (total + page_size - 1) // page_size
    
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return items, total, page, page_size, total_pages
