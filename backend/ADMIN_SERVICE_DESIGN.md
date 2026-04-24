# Production-Grade Admin Service for Healthcare RAG System

## Architecture & Design Overview

### System Design Principles

This Admin Service implements **enterprise-grade security and compliance** with HIPAA requirements while maintaining scalability and clean code architecture. The design follows Three-Layer Architecture:

1. **API Layer** (FastAPI endpoints) - HTTP concerns, input validation, authentication
2. **Service Layer** (AdminService class) - All business logic, security policies, audit logging
3. **Data Layer** (SQLAlchemy ORM) - Database persistence, transactions, relationships

**Key security philosophy**: "Defense in Depth" - Multiple layers of validation and security checks ensure that no single point of failure compromises the system. Every admin action is immutably logged with complete context (user, organization, IP, action, changes).

---

## Component Breakdown

### 1. Database Models (`app/models/database.py`)

**Design Decisions:**

- **Soft Deletes**: Users are deactivated via `is_active` flag rather than deleted. This maintains historical data for audit purposes and complies with HIPAA retention requirements.
- **Audit Logs Table**: Every admin action is recorded with:
  - WHO (user_id) - Admin performing action
  - WHAT (action, resource_type, resource_id) - Action type and target
  - WHEN (created_at) - Timestamp
  - SOURCE (ip_address, user_agent) - Request context
  - RESULT (status, error_message) - Success/failure
  - CHANGES (before/after JSON) - Data modifications
  
- **Indexing Strategy**: Composite indexes on common filter combinations:
  - `(organization_id, action)` - Fast audit log queries
  - `(organization_id, user_id)` - Rate limit lookups
  
- **Role Enum**: Type-safe role management prevents string-based attacks

**Example Models:**
```sql
-- Users are never deleted, just deactivated
UPDATE users SET is_active = FALSE WHERE id = 123;

-- Every action logged immutably
INSERT INTO audit_logs (user_id, action, resource_type, changes, ...)
VALUES (1, 'USER_ROLE_UPDATED', 'USER', '{"before": {"role": "doctor"}, "after": {"role": "admin"}}', ...);
```

---

### 2. Pydantic Schemas (`app/models/admin_schemas.py`)

**Design Decisions:**

- **Request/Response Separation**: Different schemas for input and output:
  - `UserCreate` for POST requests (includes password)
  - `UserResponse` for API responses (excludes hashed_password)
  - `UserDetailResponse` for admin views
  
- **Validation at Boundary**: Pydantic validates all inputs before reaching service layer:
  - Email format validation
  - Password strength rules (uppercase, digits)
  - Field length constraints
  - Enum validation for roles
  
- **No Sensitive Data in Responses**: 
  - API keys shown only on creation (plaintext)
  - Subsequent responses only show masked keys
  - Passwords never exposed
  
**Example:**
```python
class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    
    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v):
        # Enforce strong passwords at input boundary
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain uppercase")
```

---

### 3. Utility Functions (`app/utils/audit.py`)

**Design Decisions:**

- **Audit Logging Abstraction**: `create_audit_log()` centralizes all logging logic
  - Prevents accidental audit gaps
  - Enforces consistent error handling
  - Can be easily extended with external logging (e.g., CloudWatch, Datadog)
  
- **Sensitive Data Masking**: Separate function handles masking based on field type:
  ```python
  mask_sensitive_data("user@example.com", "email") → "u***@example.com"
  mask_sensitive_data("api_key_abc123xyz", "api_key") → "api_key_****"
  ```
  - Used when logging changes involving sensitive fields
  - Prevents accidental data leaks in audit logs
  
- **Before/After Change Tracking**: `extract_before_after()` creates structured change records:
  ```python
  {
      "before": {"role": "doctor", "is_active": true},
      "after": {"role": "admin", "is_active": true}
  }
  ```
  - Essential for compliance audits ("who changed what when")
  
- **Privilege Escalation Prevention**: `check_privilege_escalation()` detects:
  - Admin attempting to modify own role
  - Admin attempting to remove self from admin group
  - Returns True only when tampering detected

---

### 4. Admin Service (`app/services/admin_service.py`)

**Design Decisions:**

**RBAC Enforcement at Construction:**
```python
def __init__(self, session: Session, current_admin: UserModel):
    if not is_admin(self.current_admin):
        raise HTTPException(status_code=403, detail="Admin access required")
```
- Fails fast if non-admin somehow reaches service
- Prevents privilege escalation bugs propagating through business logic

**Transactional Consistency:**
- Database writes only happen AFTER all validation passes
- Audit logs created in same transaction as data changes
- If audit logging fails, entire transaction rolled back (fail-secure)

**Method Structure Examples:**

```python
def create_user(self, user_data: UserCreate) -> UserResponse:
    # 1. Validate user doesn't exist
    existing_user = self.session.query(UserModel).filter(...).first()
    if existing_user:
        # 2. Log failure for compliance
        create_audit_log(..., status="FAILURE", error_message="...")
        # 3. Raise exception to client
        raise HttpException(400, "User exists")
    
    # 4. Create user
    new_user = UserModel(...)
    self.session.add(new_user)
    self.session.flush()  # Get ID for audit log
    
    # 5. Log success
    create_audit_log(..., action="USER_CREATED", resource_id=new_user.id)
    
    # 6. Commit all changes atomically
    self.session.commit()
    
    # 7. Return response
    return UserResponse.from_orm(new_user)
```

**Advanced Features:**

1. **Privilege Escalation Prevention** (in `update_user`):
```python
if check_privilege_escalation(self.current_admin, user_id, new_role):
    create_audit_log(..., status="FAILURE", error_message="Privilege escalation")
    raise HTTPException(403, "Cannot modify own role")
```

2. **Soft Deletes** (in `deactivate_user`):
```python
user.is_active = False  # Never delete, just deactivate
create_audit_log(..., action="USER_DEACTIVATED")
```

3. **Analytics with Advanced SQL** (in `get_analytics`):
```python
# Uses GROUP BY, aggregate functions, date extraction for comprehensive metrics
top_users = session.query(
    UserModel.id,
    func.count(QueryAnalyticsModel.id).label("query_count"),
    func.avg(QueryAnalyticsModel.response_time_ms).label("avg_time")
).join(QueryAnalyticsModel).group_by(UserModel.id).order_by(...)
```

---

### 5. API Endpoints (`app/api/v1/endpoints/admin.py`)

**Design Decisions:**

**Dependency Injection for Security:**
```python
def require_admin(current_user: UserModel = Depends(get_current_user)):
    if current_user.role != RoleEnum.ADMIN:
        raise HTTPException(403, "Admin required")
    return current_user

def get_admin_service(admin: UserModel = Depends(require_admin)):
    return AdminService(session=db, current_admin=admin)

@router.post("/users")
def create_user(service: AdminService = Depends(get_admin_service)):
    # Service is guaranteed admin and properly authenticated
```

- RBAC enforcement at route level (decorators pattern)
- AdminService receives authenticated admin automatically
- No way to bypass auth by directly calling service

**Pagination & Filtering:**
```python
@router.get("/users")
def list_users(
    organization_id: Optional[int] = Query(None),
    role: Optional[RoleEnum] = Query(None),
    is_active: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),  # Max 100 to prevent DoS
    ...
):
```
- Query parameters for flexible filtering
- Type validation via FastAPI
- Max page_size prevents resource exhaustion attacks

**Audit Log Filtering for Compliance:**
```python
@router.get("/audit-logs")
def get_audit_logs(
    user_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    ...
):
```
- Rich filtering supports forensic investigations
- Date range filtering for compliance reports
- Audit data accessed only by admins in same org

---

## Security Features Implemented

### 1. **RBAC (Role-Based Access Control)**
- ✅ Admin role gating at multiple levels (decorator, service constructor, endpoints)
- ✅ Role enums prevent typos
- ✅ Privilege escalation detection

### 2. **Audit Logging (HIPAA)**
- ✅ Every mutation logged with before/after state
- ✅ Immutable audit logs (append-only)
- ✅ Context captured (user, IP, timestamp, user agent)
- ✅ Soft deletes maintain history

### 3. **Input Validation**
- ✅ Pydantic schemas validate all requests
- ✅ Email format validation
- ✅ Password strength rules
- ✅ Enum-based roles prevent injection

### 4. **Sensitive Data Protection**
- ✅ Passwords never logged in plain text
- ✅ API keys hashed (SHA-256, use bcrypt in production)
- ✅ Sensitive data masked in audit logs
- ✅ Plaintext API keys only shown on creation

### 5. **Privilege Escalation Prevention**
- ✅ Admins cannot modify their own roles
- ✅ Admins cannot deactivate themselves
- ✅ All operations validated before mutation

### 6. **Error Handling**
- ✅ Specific HTTP status codes (400, 403, 404, 500)
- ✅ ✂️ Limited error details (no stack traces to client)
- ✅ Failure logged to audit trail

---

## API Endpoint Summary

### User Management
| Method | Endpoint | Purpose | Notes |
|--------|----------|---------|-------|
| POST | `/admin/users` | Create user | Admin only, logs to audit trail |
| GET | `/admin/users` | List users | Pagination, filters, audit log only |
| PATCH | `/admin/users/{id}` | Update user | Role/status changes logged |
| DELETE | `/admin/users/{id}` | Deactivate user | Soft delete (is_active=false) |

### Audit Logs (HIPAA)
| Method | Endpoint | Purpose | Notes |
|--------|----------|---------|-------|
| GET | `/admin/audit-logs` | View audit trail | Filter by user/action/date/resource |

### API Keys
| Method | Endpoint | Purpose | Notes |
|--------|----------|---------|-------|
| POST | `/admin/api-keys/{user_id}` | Create key | Plaintext only shown once |
| DELETE | `/admin/api-keys/{key_id}` | Revoke key | Immediate revocation, logged |

### Analytics
| Method | Endpoint | Purpose | Notes |
|--------|----------|---------|-------|
| GET | `/admin/analytics` | Dashboard | Top users, usage trends, KPIs |

### Rate Limits
| Method | Endpoint | Purpose | Notes |
|--------|----------|---------|-------|
| PATCH | `/admin/rate-limits/{user_id}` | Update limits | Per-user rate limit config |

---

## Production Readiness Checklist

- ✅ **Database Indexing**: Composite indexes on common queries
- ✅ **Pagination**: All list endpoints paginated with max page sizes
- ✅ **SQL Injection Prevention**: SQLAlchemy ORM (no raw SQL)
- ✅ **Soft Deletes**: Historical data preserved for compliance
- ✅ **Audit Logging**: Every mutation logged immutably
- ✅ **Error Handling**: Specific HTTP status codes, safe error messages
- ✅ **Validation**: Pydantic schemas at boundary
- ✅ **RBAC**: Multi-layer admin verification
- ⚠️ **Password Hashing**: Currently SHA-256, should use bcrypt/argon2 in production
- ⚠️ **API Key Hashing**: Currently SHA-256, should use bcrypt in production
- ⚠️ **Rate Limiting**: Schema defined but enforcement middleware needed
- ⚠️ **CORS**: Should be configured in main app
- ⚠️ **TLS/HTTPS**: Required for production deployment

---

## Future Enhancements

1. **Multi-Factor Authentication** for admin accounts
2. **IP Whitelisting** for admin endpoints
3. **Real-time Alerts** on suspicious admin activity
4. **Anonymization** of audit logs after retention period
5. **Backup & Recovery** procedures for audit logs
6. **Rate Limiting Middleware** enforcement
7. **OAuth2/OpenID** support
8. **Organization Isolation** enforcement (tenant security)

---

## Testing Strategy (WIP)

```python
# Test privilege escalation prevention
def test_admin_cannot_remove_own_role():
    """Admins cannot modify their own roles"""
    admin = UserModel(role=RoleEnum.ADMIN)
    with pytest.raises(HTTPException) as exc_info:
        service.update_user(admin.id, UserUpdate(role=RoleEnum.DOCTOR))
    assert exc_info.value.status_code == 403

# Test audit logging
def test_user_creation_logged():
    """Every user creation recorded in audit trail"""
    service.create_user(UserCreate(...))
    audit_logs = session.query(AuditLogModel).filter(
        AuditLogModel.action == "USER_CREATED"
    ).all()
    assert len(audit_logs) > 0

# Test soft deletes
def test_deactivated_user_not_deleted():
    """Deactivation uses soft delete"""
    user = UserModel(is_active=True)
    service.deactivate_user(user.id)
    assert session.query(UserModel).filter(...).first() is not None  # User still in DB
```

---

## Deployment Notes

1. **Environment Variables**: Set in production:
   - `DATABASE_URL` - PostgreSQL connection string
   - `REDIS_URL` - Redis connection (for caching)
   - `SECRET_KEY` - JWT signing key (strong random value)

2. **Database Migrations**: Run before deployment:
   ```bash
   alembic upgrade head
   ```

3. **Monitoring**:
   - Track failed admin operations
   - Alert on privilege escalation attempts
   - Monitor audit log table growth
   - Check API response times for performance issues

4. **Backup Strategy**:
   - Daily backups of entire database
   - Separate backup for audit logs (cannot be modified)
   - Test restore procedures monthly
