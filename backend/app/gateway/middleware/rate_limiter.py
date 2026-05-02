"""Sliding-window rate limiter backed by a Redis sorted set.

For each request we apply two limits:

1. **Per-IP** — always evaluated. Protects unauthenticated endpoints and
   stops one bad actor from exhausting the whole user pool.
2. **Per-user** — evaluated when a JWT is present. Admin endpoints
   (`/api/v1/admin/...`) get a higher per-user limit.

The sorted-set algorithm is the textbook sliding-window approach:
    ZREMRANGEBYSCORE → drop entries older than `now - window`
    ZADD             → record the current request at score=now
    ZCARD            → count requests still in the window
    EXPIRE           → idle key expires when no traffic arrives

If any of those operations fail (Redis down), we **fail open**: log a
warning and let the request through. A rate limiter should never be the
reason an emergency clinical query gets blocked.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from jose import JWTError, jwt
from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.gateway.exceptions import GatewayError, RateLimitExceededError
from app.gateway.exceptions.handlers import gateway_error_to_response
from app.gateway.redis_client import get_redis

logger = logging.getLogger("app")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return "unknown"


def _peek_user_id(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": False},
        )
    except JWTError:
        return None
    return payload.get("sub")


def _is_admin_path(path: str) -> bool:
    return path.startswith(f"{settings.API_V1_STR}/admin")


def _exempt_path(path: str) -> bool:
    """Don't rate-limit health probes."""
    return path in ("/", "/health", "/healthz", "/ready")


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Apply per-IP and (when authenticated) per-user sliding-window limits."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            return await self._dispatch(request, call_next)
        except GatewayError as exc:
            return gateway_error_to_response(exc)

    async def _dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path
        if _exempt_path(path):
            return await call_next(request)

        user_id = _peek_user_id(request)
        ip = _client_ip(request)
        is_admin = _is_admin_path(path)

        # Determine the user-scoped limit — admins get a higher ceiling.
        user_limit = (
            settings.RATE_LIMIT_ADMIN_REQUESTS
            if is_admin
            else settings.RATE_LIMIT_USER_REQUESTS
        )
        user_window = settings.RATE_LIMIT_USER_WINDOW_SECONDS
        ip_limit = settings.RATE_LIMIT_IP_REQUESTS
        ip_window = settings.RATE_LIMIT_IP_WINDOW_SECONDS

        applied_limit = ip_limit
        applied_window = ip_window
        remaining = ip_limit
        reset_in = ip_window

        # Per-IP check (always)
        try:
            count = await self._record_and_count(
                f"healthcare:ratelimit:ip:{ip}", ip_window
            )
        except RedisError:
            logger.warning("rate_limiter_redis_unavailable", exc_info=True)
            return await call_next(request)  # fail open

        if count > ip_limit:
            raise RateLimitExceededError(
                f"IP rate limit exceeded ({ip_limit}/{ip_window}s).",
                retry_after_seconds=ip_window,
                limit=ip_limit,
            )
        remaining = max(0, ip_limit - count)
        reset_in = ip_window

        # Per-user check (when authenticated)
        if user_id:
            try:
                u_count = await self._record_and_count(
                    f"healthcare:ratelimit:user:{user_id}", user_window
                )
            except RedisError:
                logger.warning("rate_limiter_redis_unavailable", exc_info=True)
                return await call_next(request)

            if u_count > user_limit:
                raise RateLimitExceededError(
                    f"User rate limit exceeded ({user_limit}/{user_window}s).",
                    retry_after_seconds=user_window,
                    limit=user_limit,
                )
            applied_limit = user_limit
            applied_window = user_window
            remaining = max(0, user_limit - u_count)
            reset_in = user_window

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(applied_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_in)
        return response

    @staticmethod
    async def _record_and_count(key: str, window_seconds: int) -> int:
        """Record the current request and return the count within the window."""
        now = _now_ms()
        window_ms = window_seconds * 1000
        cutoff = now - window_ms
        client = get_redis()

        pipe = client.pipeline()
        pipe.zremrangebyscore(key, 0, cutoff)
        # Use "<ms>:<random>" as member to avoid collisions when multiple
        # requests land in the same millisecond. Score stays as `now`.
        pipe.zadd(key, {f"{now}:{id(pipe)}": now})
        pipe.zcard(key)
        pipe.expire(key, window_seconds)
        results = await pipe.execute()
        # results = [removed, added, count, expire_ok]
        return int(results[2])
