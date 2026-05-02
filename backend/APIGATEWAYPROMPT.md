# API Gateway Layer — Claude Code Prompt

## Project Context

This is a Healthcare RAG System built with FastAPI (Python 3.11+). The backend lives at `backend/app/`. The API gateway layer is the single entry point for all client traffic — it handles auth, rate limiting, request validation, HIPAA-compliant logging, and CORS before any request reaches the Query, Document, or Admin services.

### Already configured in the project (do not duplicate or change these):
- JWT auth: `SECRET_KEY`, `ALGORITHM=HS256`, `ACCESS_TOKEN_EXPIRE_MINUTES=30` — already in `.env.example`
- CORS: `BACKEND_CORS_ORIGINS` — already in `config.py`
- Redis: `REDIS_URL=redis://localhost:6379/0` — already in `.env.example`
- API prefix: `API_V1_STR=/api/v1` — already set
- Versioned routers already exist under `backend/app/api/v1/` (query, document, admin) — do not remove or replace them, only wire them up

### Existing structure (do not modify these unless explicitly told to):
```
backend/
├── app/
│   ├── core/
│   │   └── config.py              # Pydantic BaseSettings — extend only
│   ├── api/
│   │   └── v1/                    # Existing routers live here — do not touch
│   ├── db/                        # DB layer (built previously)
│   └── main.py                    # FastAPI entry — add middleware here, do not rewrite
├── requirements.txt
└── .env.example
```

---

## What to Build

```
backend/app/gateway/
├── __init__.py
├── auth/
│   ├── __init__.py
│   ├── jwt_handler.py         # Token creation, decoding, refresh
│   ├── dependencies.py        # FastAPI dependencies: get_current_user, require_role
│   └── models.py              # Pydantic models: TokenPayload, UserIdentity
├── middleware/
│   ├── __init__.py
│   ├── rate_limiter.py        # Per-user + per-IP sliding window rate limiting via Redis
│   ├── hipaa_logger.py        # HIPAA-compliant audit logging middleware
│   ├── request_validator.py   # Request size limits, content-type enforcement
│   └── correlation.py         # Injects X-Request-ID into every request/response
├── security/
│   ├── __init__.py
│   ├── cors.py                # CORS setup (reads existing BACKEND_CORS_ORIGINS)
│   ├── headers.py             # Security headers middleware (HSTS, CSP, etc.)
│   └── ip_allowlist.py        # Optional IP allowlist for admin endpoints
└── exceptions/
    ├── __init__.py
    └── handlers.py            # Global exception handlers wired to FastAPI

backend/tests/gateway/
├── __init__.py
├── test_jwt_handler.py
├── test_rate_limiter.py
├── test_hipaa_logger.py
├── test_dependencies.py
└── test_exception_handlers.py
```

---

## Detailed Specifications

### `auth/jwt_handler.py`

- `create_access_token(data: dict, expires_delta: timedelta | None) -> str`
  - Signs with `SECRET_KEY` and `ALGORITHM` from settings (already HS256)
  - Always includes `exp`, `iat`, `jti` (unique token ID via `uuid4`) in the payload
  - `jti` enables token revocation — store revoked JTIs in Redis with TTL matching token expiry
- `create_refresh_token(user_id: str) -> str`
  - Longer-lived token (configurable `REFRESH_TOKEN_EXPIRE_DAYS`, default 7)
  - Store refresh token hash in Redis against `user_id` — only one active refresh token per user
- `decode_token(token: str) -> TokenPayload`
  - Raises `TokenExpiredError` if expired
  - Raises `TokenInvalidError` if signature is bad or payload is malformed
  - Raises `TokenRevokedError` if the `jti` is in the Redis revocation set
- `revoke_token(jti: str, ttl: int) -> None`
  - Adds `jti` to Redis set `healthcare:revoked_tokens:{jti}` with appropriate TTL
- Never log the raw token string anywhere

### `auth/models.py`

```python
class TokenPayload(BaseModel):
    sub: str           # user_id
    role: str          # "patient" | "clinician" | "admin"
    jti: str           # unique token ID
    exp: int
    iat: int

class UserIdentity(BaseModel):
    user_id: str
    role: str
    jti: str
```

### `auth/dependencies.py`

- `get_current_user(token: str = Depends(oauth2_scheme)) -> UserIdentity`
  - Extracts Bearer token from `Authorization` header
  - Calls `decode_token()` — propagates any token errors as HTTP 401
  - Returns `UserIdentity`
- `require_role(*roles: str)` — factory that returns a dependency:
  ```python
  # Usage in routers:
  # admin_only = require_role("admin")
  # @router.get("/admin/...", dependencies=[Depends(admin_only)])
  ```
  - Raises HTTP 403 if current user's role is not in the allowed list
- `get_optional_user()` — same as `get_current_user` but returns `None` instead of raising if no token is present (for public endpoints that optionally personalize)

---

### `middleware/rate_limiter.py`

Implement a **sliding window** rate limiter using Redis sorted sets — more accurate than fixed windows and fairer to users.

- Two separate limiters running on every request:
  - **Per-user**: keyed by `user_id` from the JWT (if authenticated)
  - **Per-IP**: keyed by client IP (always applies, including unauthenticated requests)
- Default limits (all configurable via settings):
  - Authenticated users: `RATE_LIMIT_USER_REQUESTS=100` per `RATE_LIMIT_USER_WINDOW_SECONDS=60`
  - Unauthenticated / per-IP: `RATE_LIMIT_IP_REQUESTS=20` per `RATE_LIMIT_IP_WINDOW_SECONDS=60`
  - Admin endpoints get a separate higher limit: `RATE_LIMIT_ADMIN_REQUESTS=300` per 60s
- Algorithm (sliding window with Redis sorted set):
  ```
  key = f"healthcare:ratelimit:{identifier}"
  now = current timestamp in ms
  window_start = now - window_size_ms
  
  MULTI (pipeline):
    ZREMRANGEBYSCORE key 0 window_start    # remove old entries
    ZADD key now now                        # add current request
    ZCARD key                               # count requests in window
    EXPIRE key window_size_seconds
  EXEC
  
  if count > limit → return 429
  ```
- On 429, return headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining: 0`, `Retry-After: <seconds>`
- On every non-429 response, add: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`
- If Redis is unavailable, **fail open** (allow the request) and log a warning — never block users because the rate limiter is down

### `middleware/hipaa_logger.py`

This is the most critical middleware for compliance. Every request touching patient data must be auditable.

- Implement as a Starlette `BaseHTTPMiddleware`
- On every request, capture and log as structured JSON:
  ```json
  {
    "event": "api_request",
    "timestamp": "ISO8601",
    "request_id": "from X-Request-ID header",
    "method": "POST",
    "path": "/api/v1/query",
    "user_id": "from JWT if present, else null",
    "user_role": "from JWT if present, else null",
    "client_ip": "real IP (handle X-Forwarded-For for proxied requests)",
    "user_agent": "truncated to 200 chars",
    "status_code": 200,
    "response_time_ms": 142,
    "resource_type": "query | document | admin | health | other"
  }
  ```
- **STRICT PHI rules — never log:**
  - Request body contents (may contain patient questions with names, DOBs, etc.)
  - Response body contents
  - Query parameters that are not on a pre-approved safe list
  - Any header value except: `Content-Type`, `Accept`, `X-Request-ID`
  - Raw JWT tokens
- Log to a **separate audit log** (different logger name: `"audit"`) — this must be distinguishable from application logs so it can be shipped to a separate SIEM or log store
- Always log, even if the request fails — wrap the entire middleware in try/finally

### `middleware/correlation.py`

- If the request has an `X-Request-ID` header, use it (validate it is a valid UUID)
- If not, generate a new `uuid4` and attach it
- Add `X-Request-ID` to the response headers
- Store the request ID in a `contextvars.ContextVar` so it can be included in all log lines within the same request without passing it explicitly

### `middleware/request_validator.py`

- Enforce max request body size: `MAX_REQUEST_SIZE_BYTES` (default 1MB) — return 413 if exceeded
- Reject requests with `Content-Type` that is not `application/json` or `multipart/form-data` on POST/PUT endpoints — return 415
- Strip and reject any request containing a body on GET/DELETE endpoints — return 400

---

### `security/cors.py`

- Read `BACKEND_CORS_ORIGINS` from existing settings (already a `list[str]`)
- Apply using FastAPI's `CORSMiddleware`:
  - `allow_credentials=True`
  - `allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]`
  - `allow_headers=["Authorization", "Content-Type", "X-Request-ID"]`
- In `DEBUG=True` mode only: also allow `http://localhost:*` origins
- Never allow `*` as an origin in production (`DEBUG=False`)

### `security/headers.py`

- Add these security headers to every response:
  ```
  Strict-Transport-Security: max-age=31536000; includeSubDomains
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  X-XSS-Protection: 1; mode=block
  Referrer-Policy: strict-origin-when-cross-origin
  Content-Security-Policy: default-src 'self'
  Permissions-Policy: geolocation=(), microphone=(), camera=()
  ```
- Remove `Server` header from all responses (avoid exposing tech stack)

### `security/ip_allowlist.py`

- `IPAllowlistMiddleware`: reads `ADMIN_IP_ALLOWLIST` from settings (comma-separated CIDRs, default empty = disabled)
- Only applies to paths starting with `/api/v1/admin/`
- If allowlist is non-empty and client IP is not in any listed CIDR, return 403
- Use `ipaddress` stdlib module for CIDR matching — no extra dependencies
- Log every blocked IP attempt at WARNING level (include IP, path, timestamp — no PHI)

---

### `exceptions/handlers.py`

Register global exception handlers on the FastAPI app. Each handler must return a consistent JSON shape:

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Too many requests. Please try again in 30 seconds.",
    "request_id": "uuid"
  }
}
```

Handle these explicitly:
- `TokenExpiredError` → 401, code `TOKEN_EXPIRED`
- `TokenInvalidError` → 401, code `TOKEN_INVALID`
- `TokenRevokedError` → 401, code `TOKEN_REVOKED`
- `RateLimitExceededError` → 429, code `RATE_LIMITED`, include `Retry-After` header
- `RequestTooLargeError` → 413, code `REQUEST_TOO_LARGE`
- `PermissionDeniedError` → 403, code `FORBIDDEN`
- `RequestValidationError` (FastAPI built-in) → 422, code `VALIDATION_ERROR`, include field-level errors
- `HTTPException` (FastAPI built-in) → pass through status code, normalize to standard shape
- `Exception` (catch-all) → 500, code `INTERNAL_ERROR`, log full traceback, **never expose internal details to client**

---

## Wiring Everything into `main.py`

Add the following to `main.py` in this exact order (middleware order matters in Starlette — last added = first executed):

```python
# 1. Correlation ID (must be first — sets request_id for all subsequent logs)
app.add_middleware(CorrelationMiddleware)

# 2. HIPAA audit logger (must be early to capture all requests including auth failures)
app.add_middleware(HIPAALoggerMiddleware)

# 3. Security headers
app.add_middleware(SecurityHeadersMiddleware)

# 4. CORS (must be before auth so OPTIONS preflight passes)
app.add_middleware(CORSMiddleware, ...)

# 5. Request validator
app.add_middleware(RequestValidatorMiddleware)

# 6. Rate limiter (after auth context is available via correlation)
app.add_middleware(RateLimiterMiddleware)

# 7. IP allowlist (last — most specific, only hits admin routes)
app.add_middleware(IPAllowlistMiddleware)
```

Also register all exception handlers from `exceptions/handlers.py`.

---

## New Auth Endpoints

Add `backend/app/api/v1/auth.py` router with:

- `POST /api/v1/auth/login` — accepts `username` + `password` (form body), returns `access_token` + `refresh_token`
  - Validate credentials against the user in PostgreSQL (use existing DB session dependency)
  - Never return the user's password hash in any response
- `POST /api/v1/auth/refresh` — accepts `refresh_token` in body, returns new `access_token`
  - Validate refresh token from Redis; rotate it (invalidate old, issue new)
- `POST /api/v1/auth/logout` — requires valid Bearer token, revokes both tokens
- `GET /api/v1/auth/me` — requires auth, returns current `UserIdentity`

---

## Configuration

Extend `backend/app/core/config.py` — the following already exist, **do not add them again**:
- `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REDIS_URL`, `BACKEND_CORS_ORIGINS`, `DEBUG`

Add only these new settings:
```python
# Auth
REFRESH_TOKEN_EXPIRE_DAYS: int = 7

# Rate limiting
RATE_LIMIT_USER_REQUESTS: int = 100
RATE_LIMIT_USER_WINDOW_SECONDS: int = 60
RATE_LIMIT_IP_REQUESTS: int = 20
RATE_LIMIT_IP_WINDOW_SECONDS: int = 60
RATE_LIMIT_ADMIN_REQUESTS: int = 300

# Request validation
MAX_REQUEST_SIZE_BYTES: int = 1_048_576    # 1MB

# Security
ADMIN_IP_ALLOWLIST: str = ""               # e.g. "10.0.0.0/8,192.168.1.0/24"
```

Add new settings to `.env.example` with safe placeholder values.

---

## Dependencies to Add to `requirements.txt`

```
python-jose[cryptography]>=3.3.0    # JWT signing (HS256)
passlib[bcrypt]>=1.7.4              # Password hashing for login endpoint
python-multipart>=0.0.9             # Required for form body (login endpoint)
```

Note: `redis`, `fastapi`, `pydantic` are already in `requirements.txt` — do not duplicate.

---

## Test Requirements

Use **pytest + pytest-asyncio + httpx** (`AsyncClient` for route-level tests). Mock Redis and DB in all tests.

### `test_jwt_handler.py`
- Valid token creation and decoding round-trip
- Expired token raises `TokenExpiredError`
- Tampered signature raises `TokenInvalidError`
- Revoked JTI raises `TokenRevokedError`
- Token never contains sensitive fields (password, raw PII)

### `test_rate_limiter.py`
- First N requests within window succeed
- Request N+1 returns 429 with `Retry-After` header
- Counter resets after window expires
- Redis down → request is allowed (fail open), warning is logged

### `test_hipaa_logger.py`
- Every request produces exactly one audit log entry
- Log entry contains `user_id`, `path`, `method`, `status_code`, `response_time_ms`
- Log entry does **not** contain request body, response body, or raw token
- Failed requests (5xx) still produce audit log entries

### `test_dependencies.py`
- `get_current_user` returns `UserIdentity` for valid token
- `get_current_user` raises 401 for expired token
- `require_role("admin")` raises 403 for a `patient` role user
- `require_role("admin")` passes for an `admin` role user

### `test_exception_handlers.py`
- All custom exceptions map to correct HTTP status codes
- All error responses follow the standard JSON shape with `request_id`
- Catch-all 500 handler does not expose internal error details in response body

---

## Code Quality Standards

- Full type hints (Python 3.11+ style)
- Docstrings on all classes and public methods
- All middleware is async — no blocking calls
- No `print()` — use structured logging with the `"audit"` logger for HIPAA events and `"app"` logger for everything else
- Middleware must never swallow exceptions silently — always re-raise after logging
- No secrets hardcoded — always read from `settings`
- `X-Request-ID` must appear in every log line within a request (use `ContextVar`)

---

## Definition of Done

- [ ] All files in `backend/app/gateway/` created and implemented
- [ ] All middleware registered in `main.py` in the correct order
- [ ] Auth endpoints at `/api/v1/auth/` working (login, refresh, logout, me)
- [ ] All tests in `backend/tests/gateway/` pass with `pytest`
- [ ] `config.py` extended without removing existing settings
- [ ] `requirements.txt` and `.env.example` updated
- [ ] A request to any protected route without a token returns 401 in the standard error shape
- [ ] A request that exceeds rate limit returns 429 with `Retry-After` header
- [ ] Audit log entries never contain request/response bodies