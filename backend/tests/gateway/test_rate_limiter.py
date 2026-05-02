"""Tests for the sliding-window rate limiter middleware."""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.exceptions import RedisError

from app.core.config import settings
from app.gateway.exceptions.handlers import register_exception_handlers
from app.gateway.middleware.correlation import CorrelationMiddleware
from app.gateway.middleware.rate_limiter import RateLimiterMiddleware


pytestmark = pytest.mark.asyncio


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(RateLimiterMiddleware)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return app


async def test_first_n_requests_succeed_then_blocked(fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_REQUESTS", 3)
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_WINDOW_SECONDS", 60)

    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for _ in range(3):
            r = await c.get("/ping")
            assert r.status_code == 200
            assert "X-RateLimit-Limit" in r.headers
        r = await c.get("/ping")
        assert r.status_code == 429
        assert r.json()["error"]["code"] == "RATE_LIMITED"
        assert r.headers.get("Retry-After") == "60"
        assert r.headers.get("X-RateLimit-Remaining") == "0"


async def test_redis_down_fails_open(fake_redis, caplog):
    caplog.set_level(logging.WARNING, logger="app")

    app = _build_app()

    async def _boom(*args, **kwargs):
        raise RedisError("simulated outage")

    with patch.object(RateLimiterMiddleware, "_record_and_count", side_effect=_boom):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await c.get("/ping")
    assert r.status_code == 200
    assert any(
        "rate_limiter_redis_unavailable" in rec.message for rec in caplog.records
    )


async def test_health_endpoint_is_exempt(fake_redis, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_IP_REQUESTS", 1)
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(RateLimiterMiddleware)

    @app.get("/health")
    async def health():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        for _ in range(5):
            r = await c.get("/health")
            assert r.status_code == 200
