"""
DEVELOPER QUICK REFERENCE: Admin Service Code Patterns & Extension Guide

Use this guide to add new admin features while maintaining production quality.
"""

# ============ PATTERN 1: ADD A NEW ADMIN ENDPOINT ============

"""
REQUIREMENT: Add a new endpoint to suspend all queries for a user

STEPS:

1. Add schema (app/models/admin_schemas.py):
"""

from pydantic import BaseModel, Field

class UserSuspensionRequest(BaseModel):
    """Request to suspend a user's queries."""
    reason: str = Field(..., min_length=1, max_length=500)
    duration_hours: int = Field(24, ge=1, le=168)  # Max 7 days


class UserSuspensionResponse(BaseModel):
    """Response after user suspension."""
    user_id: int
    reason: str
    suspended_at: datetime
    resume_at: datetime


"""
2. Add service method (app/services/admin_service.py):
"""

def suspend_user_queries(self, user_id: int, suspension: UserSuspensionRequest) -> UserSuspensionResponse:
    """
    Suspend a user's query capability temporarily.
    
    Args:
        user_id: User ID to suspend
        suspension: Suspension details
    
    Returns:
        Suspension info
    """
    user = self.session.query(UserModel).filter(UserModel.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    
    # Calculate resume time
    resume_at = datetime.utcnow() + timedelta(hours=suspension.duration_hours)
    
    # Create suspension record (would need new model)
    suspension_record = UserSuspensionModel(
        user_id=user_id,
        organization_id=self.current_admin.organization_id,
        reason=suspension.reason,
        suspended_at=datetime.utcnow(),
        resume_at=resume_at,
        is_active=True
    )
    
    self.session.add(suspension_record)
    self.session.flush()
    
    # 🔐 LOG THE ACTION
    create_audit_log(
        session=self.session,
        user_id=self.current_admin.id,
        organization_id=self.current_admin.organization_id,
        action="USER_QUERIES_SUSPENDED",
        resource_type="USER",
        resource_id=user_id,
        changes={
            "reason": suspension.reason,
            "duration_hours": suspension.duration_hours,
            "resume_at": resume_at.isoformat()
        }
    )
    
    self.session.commit()
    
    return UserSuspensionResponse(
        user_id=user_id,
        reason=suspension.reason,
        suspended_at=suspension_record.suspended_at,
        resume_at=resume_at
    )


"""
3. Add endpoint (app/api/v1/endpoints/admin.py):
"""

@router.post("/users/{user_id}/suspend-queries", response_model=UserSuspensionResponse)
async def suspend_user_queries(
    user_id: int,
    suspension: UserSuspensionRequest,
    service: AdminService = Depends(get_admin_service),
):
    """Suspend user's query capability temporarily."""
    return service.suspend_user_queries(user_id, suspension)


"""
KEY PATTERNS TO FOLLOW:

✅ 1. Validate input with Pydantic schema
✅ 2. Check admin role (automatically via dependency injection)
✅ 3. Verify resource exists before modifying
✅ 4. Track changes in before/after format
✅ 5. ALWAYS CALL create_audit_log() after mutation
✅ 6. Use self.session.flush() before logging (to get IDs)
✅ 7. Commit entire transaction atomically
✅ 8. Return structured response
"""

# ============ PATTERN 2: ADD FILTERING & PAGINATION ============

"""
REQUIREMENT: Add list endpoint for suspended users

STEP 1: Add schema with filters
"""

class UserSuspensionFilter(BaseModel):
    """Filters for suspended users list."""
    user_id: Optional[int] = None
    is_active: Optional[bool] = True
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class UserSuspensionListResponse(BaseModel):
    """Paginated suspension list."""
    items: List[UserSuspensionResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


"""
STEP 2: Add service method with filtering
"""

def list_suspended_users(
    self,
    filters: UserSuspensionFilter,
    page: int = 1,
    page_size: int = 20,
) -> UserSuspensionListResponse:
    """
    List suspended users with filtering and pagination.
    
    Key: Use paginate_query utility for consistent pagination!
    """
    query = self.session.query(UserSuspensionModel).filter(
        UserSuspensionModel.organization_id == self.current_admin.organization_id
    )
    
    # Apply filters
    if filters.user_id:
        query = query.filter(UserSuspensionModel.user_id == filters.user_id)
    if filters.is_active is not None:
        query = query.filter(UserSuspensionModel.is_active == filters.is_active)
    if filters.start_date:
        query = query.filter(UserSuspensionModel.suspended_at >= filters.start_date)
    if filters.end_date:
        query = query.filter(UserSuspensionModel.suspended_at <= filters.end_date)
    
    # Order and paginate
    query = query.order_by(desc(UserSuspensionModel.suspended_at))
    items, total, page, page_size, total_pages = paginate_query(query, page, page_size)
    
    return UserSuspensionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


"""
STEP 3: Add endpoint with Query parameters
"""

@router.get("/users/suspensions", response_model=UserSuspensionListResponse)
async def list_suspended_users(
    user_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(True),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: AdminService = Depends(get_admin_service),
):
    """List suspended users with filtering."""
    filters = UserSuspensionFilter(
        user_id=user_id,
        is_active=is_active,
        start_date=start_date,
        end_date=end_date,
    )
    return service.list_suspended_users(filters, page, page_size)


"""
FILTERING PATTERN SUMMARY:

1. Create filter schema with Optional fields
2. Create query in service method
3. Apply each filter with conditional query.filter()
4. Order by most recent first (ORDER BY created_at DESC)
5. Use paginate_query() utility for consistency
6. Return paginated response with total/page_count
"""

# ============ PATTERN 3: PREVENT COMMON SECURITY MISTAKES ============

# ❌ WRONG: Business logic in endpoint
@router.post("/users/wrong")
async def wrong_pattern(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    admin: UserModel = Depends(require_admin)
):
    # ❌ Logic here is hard to test and not audited
    existing = db.query(UserModel).filter(...).first()
    if existing:
        db.query(AuditLogModel).insert(...)  # ❌ Inconsistent logging
        raise HTTPException(400, "exists")
    # ... more logic ...


# ✅ CORRECT: All logic in service layer
@router.post("/users", response_model=UserResponse)
async def create_user(
    user_data: UserCreate,
    service: AdminService = Depends(get_admin_service)
):
    return service.create_user(user_data)  # ✅ All logic in service
    # ✅ Consistent audit logging
    # ✅ Easy to test
    # ✅ RBAC already enforced by dependency


# ❌ WRONG: Forgetting to audit log
def bad_user_update(self, user_id: int, updates: dict):
    user = self.session.query(UserModel).filter(...).first()
    for key, value in updates.items():
        setattr(user, key, value)
    self.session.commit()
    # ❌ NO AUDIT LOG! HIPAA violation!
    return user


# ✅ CORRECT: Always log mutations
def good_user_update(self, user_id: int, user_data: UserUpdate):
    user = self.session.query(UserModel).filter(...).first()
    
    old_data = {k: getattr(user, k) for k in ["full_name", "role"]}
    
    if user_data.full_name:
        user.full_name = user_data.full_name
    if user_data.role:
        user.role = user_data.role
    
    self.session.flush()
    
    new_data = {k: getattr(user, k) for k in ["full_name", "role"]}
    
    # ✅ LOG BEFORE COMMIT
    create_audit_log(
        session=self.session,
        user_id=self.current_admin.id,
        organization_id=self.current_admin.organization_id,
        action="USER_UPDATED",
        resource_type="USER",
        resource_id=user_id,
        changes=extract_before_after(old_data, new_data)
    )
    
    self.session.commit()  # ✅ Atomic with audit log
    return user


# ❌ WRONG: Storing plaintext sensitive data
def bad_api_key_storage(self, user_id: int):
    key = secrets.token_urlsafe(32)
    # ❌ NEVER store plaintext!
    api_key = ApiKeyModel(key_hash=key)
    self.session.add(api_key)


# ✅ CORRECT: Always hash sensitive data
def good_api_key_storage(self, user_id: int):
    plaintext_key = f"sk_live_{secrets.token_urlsafe(32)}"
    # ✅ Hash before storing
    key_hash = hashlib.sha256(plaintext_key.encode()).hexdigest()
    api_key = ApiKeyModel(key_hash=key_hash)
    self.session.add(api_key)
    # ✅ Return plaintext ONLY on creation
    return {"key": plaintext_key, ...}


"""
SECURITY ANTI-PATTERNS TABLE:

❌ WRONG                                  | ✅ CORRECT
--------------------------------------|---------------------
Logic in endpoint                    | Logic in service layer
No audit logging                     | Audit log for every mutation
Plaintext sensitive data             | Hash everything before storing
Forgetting error handling            | Explicit try/catch with logging
No RBAC checks                       | RBAC at multiple layers
Returning full user objects          | Mask sensitive fields
SQL injection via f-strings          | Use SQLAlchemy ORM
No transaction management            | Atomic commits with logging
"""

# ============ PATTERN 4: TEST YOUR NEW FEATURE ============

"""
TESTING PATTERN:
"""

import pytest
from unittest.mock import Mock, patch

def test_suspend_user_queries_creates_audit_log():
    """Suspended user queries should be logged."""
    admin = UserModel(id=1, role=RoleEnum.ADMIN, organization_id=1)
    user = UserModel(id=2, organization_id=1)
    db = Mock()
    
    db.query(UserModel).filter(...).first.return_value = user
    db.flush = Mock()
    db.commit = Mock()
    
    service = AdminService(session=db, current_admin=admin)
    
    suspension_request = UserSuspensionRequest(
        reason="Abuse of service",
        duration_hours=24
    )
    
    # Call the method
    result = service.suspend_user_queries(2, suspension_request)
    
    # Verify audit log was created
    create_audit_log_calls = [call for call in db.add.call_args_list 
                              if isinstance(call[0][0], AuditLogModel)]
    assert len(create_audit_log_calls) > 0
    
    # Verify response
    assert result.user_id == 2
    assert result.reason == "Abuse of service"


def test_suspend_user_queries_fails_for_non_admin():
    """Non-admin should not be able to suspend users."""
    non_admin = UserModel(id=3, role=RoleEnum.PATIENT, organization_id=1)
    db = Mock()
    
    with pytest.raises(HTTPException) as exc_info:
        service = AdminService(session=db, current_admin=non_admin)
    
    assert exc_info.value.status_code == 403


def test_list_suspended_users_with_filters():
    """Suspended users list should respect filters."""
    admin = UserModel(id=1, role=RoleEnum.ADMIN, organization_id=1)
    db = Mock()
    
    service = AdminService(session=db, current_admin=admin)
    
    filters = UserSuspensionFilter(
        user_id=2,
        is_active=True,
        start_date=datetime(2026, 4, 20)
    )
    
    result = service.list_suspended_users(filters, page=1, page_size=20)
    
    # Verify pagination
    assert result.page == 1
    assert result.page_size == 20


"""
CHECKLIST FOR NEW ADMIN FEATURE:

□ Create Pydantic schema with validation
□ Add service method with all business logic
□ Create audit log for every mutation
□ Add endpoint with proper dependencies
□ Handle errors with specific HTTP status codes
□ Add pagination for list endpoints
□ Write unit tests for service method
□ Test error cases (404, 403, 400)
□ Test privilege escalation prevention
□ Document endpoint in API docs
□ Update ADMIN_SERVICE_DESIGN.md
"""

# ============ PATTERN 5: DATABASE MIGRATION FOR NEW FEATURE ============

"""
When adding new tables/columns, use Alembic migrations:

$ alembic revision --autogenerate -m "Add user suspension table"

This creates: alembic/versions/xxxx_add_user_suspension_table.py
"""

from alembic import op
import sqlalchemy as sa

def upgrade():
    """Add new user suspension table."""
    op.create_table(
        'user_suspensions',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('organization_id', sa.Integer, sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('reason', sa.String(500), nullable=False),
        sa.Column('suspended_at', sa.DateTime, default=sa.func.now()),
        sa.Column('resume_at', sa.DateTime, nullable=False),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime, default=sa.func.now()),
    )
    
    # Add indexes
    op.create_index('ix_suspension_org_user', 'user_suspensions', ['organization_id', 'user_id'])
    op.create_index('ix_suspension_resume', 'user_suspensions', ['resume_at'])


def downgrade():
    """Rollback user suspension table."""
    op.drop_table('user_suspensions')


"""
Run migration:
$ alembic upgrade head

Rollback migration:
$ alembic downgrade -1
"""
