"""FastAPI entrypoint.

The middleware stack is layered (last added = first executed) such that:

    request → IPAllowlist → RateLimiter → RequestValidator → CORS
            → SecurityHeaders → HIPAALogger → Correlation → app

In other words: correlation runs first (so every later log line carries
a request_id), the audit logger wraps the whole thing, and the IP
allowlist sits just inside the network boundary for admin routes.
"""

from __future__ import annotations

from dotenv import load_dotenv
from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import settings
from app.gateway.exceptions.handlers import register_exception_handlers
from app.gateway.middleware.correlation import CorrelationMiddleware
from app.gateway.middleware.hipaa_logger import HIPAALoggerMiddleware
from app.gateway.middleware.rate_limiter import RateLimiterMiddleware
from app.gateway.middleware.request_validator import RequestValidatorMiddleware
from app.gateway.security.cors import add_cors_middleware
from app.gateway.security.headers import SecurityHeadersMiddleware
from app.gateway.security.ip_allowlist import IPAllowlistMiddleware

load_dotenv()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    debug=settings.DEBUG,
)

# Middleware order matters: in Starlette the last `add_middleware` call is the
# outermost layer (executed first on the way in, last on the way out). Add them
# in *inside-out* order so the resulting stack reads naturally from outside-in.

# 1. Correlation ID — first thing every log line needs
app.add_middleware(CorrelationMiddleware)

# 2. HIPAA audit logger — must wrap auth so failures are still audited
app.add_middleware(HIPAALoggerMiddleware)

# 3. Security headers
app.add_middleware(SecurityHeadersMiddleware)

# 4. CORS — must be before auth so OPTIONS preflight passes
add_cors_middleware(app)

# 5. Request validator
app.add_middleware(RequestValidatorMiddleware)

# 6. Rate limiter
app.add_middleware(RateLimiterMiddleware)

# 7. IP allowlist — last added = outermost; admin-path-only
app.add_middleware(IPAllowlistMiddleware)

# Global exception handlers
register_exception_handlers(app)

# Routers
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Liveness probe — exempt from rate limiting and audit context restrictions."""
    return {"status": "ok"}
