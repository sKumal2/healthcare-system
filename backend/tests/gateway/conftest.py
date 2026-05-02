"""Shared fixtures for gateway tests.

Two patterns matter here:

1. We swap the gateway's Redis client with `fakeredis.aioredis.FakeRedis`
   so tests run hermetically — no real Redis needed.
2. We auto-reset the correlation ContextVar between tests so request_id
   bleed-through can't make a test depend on its predecessors.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator

import fakeredis.aioredis
import pytest
import pytest_asyncio

from app.gateway import redis_client
from app.gateway.middleware.correlation import _request_id_ctx


@pytest_asyncio.fixture
async def fake_redis() -> AsyncGenerator[fakeredis.aioredis.FakeRedis, None]:
    """Swap the shared gateway Redis client with an in-memory fake."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    redis_client.set_redis_client(client)
    try:
        yield client
    finally:
        await client.aclose()
        redis_client.set_redis_client(None)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def reset_request_id_ctx():
    """Don't leak X-Request-ID context across tests."""
    token = _request_id_ctx.set(None)
    try:
        yield
    finally:
        _request_id_ctx.reset(token)


@pytest.fixture
def caplog_audit(caplog):
    """Caplog fixture preset to the `audit` logger at INFO level."""
    caplog.set_level(logging.INFO, logger="audit")
    return caplog
