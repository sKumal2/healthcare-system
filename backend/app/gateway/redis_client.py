"""Lazy, fail-tolerant Redis client used by the gateway.

We share a single async client across rate limiter, JWT revocation,
and refresh token storage. Callers must handle `redis.exceptions.RedisError`
explicitly — the gateway's policy is **fail open** for rate limiting but
**fail closed** for token revocation/refresh (security over availability).
"""

from __future__ import annotations

import logging
from typing import Optional

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger("app")

_client: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    """Return the process-wide async Redis client, creating it on first use."""
    global _client
    if _client is None:
        _client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _client


async def close_redis() -> None:
    """Close the shared client at app shutdown."""
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:  # noqa: BLE001
            logger.warning("redis_close_failed", exc_info=True)
        _client = None


def set_redis_client(client: aioredis.Redis) -> None:
    """Replace the shared client (used by tests to inject fakes)."""
    global _client
    _client = client
