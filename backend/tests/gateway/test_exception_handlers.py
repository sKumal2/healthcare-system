"""Tests for the global exception handlers."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.gateway.exceptions import (
    InvalidRequestError,
    PermissionDeniedError,
    RateLimitExceededError,
    RequestTooLargeError,
    TokenExpiredError,
    TokenInvalidError,
    TokenRevokedError,
    UnsupportedMediaTypeError,
)
from app.gateway.exceptions.handlers import register_exception_handlers
from app.gateway.middleware.correlation import CorrelationMiddleware


pytestmark = pytest.mark.asyncio


class Body(BaseModel):
    n: int


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(CorrelationMiddleware)

    @app.get("/expired")
    async def expired():
        raise TokenExpiredError()

    @app.get("/invalid")
    async def invalid():
        raise TokenInvalidError()

    @app.get("/revoked")
    async def revoked():
        raise TokenRevokedError()

    @app.get("/forbidden")
    async def forbidden():
        raise PermissionDeniedError()

    @app.get("/rate")
    async def rate():
        raise RateLimitExceededError(retry_after_seconds=42, limit=10)

    @app.get("/too-large")
    async def too_large():
        raise RequestTooLargeError()

    @app.get("/bad-type")
    async def bad_type():
        raise UnsupportedMediaTypeError()

    @app.get("/bad-req")
    async def bad_req():
        raise InvalidRequestError()

    @app.get("/http")
    async def http_err():
        raise HTTPException(status_code=404, detail="missing")

    @app.get("/boom")
    async def boom():
        raise RuntimeError("internal secret value")

    @app.post("/validate")
    async def validate(body: Body):
        return body.dict()

    return app


@pytest.mark.parametrize(
    "path,status,code",
    [
        ("/expired", 401, "TOKEN_EXPIRED"),
        ("/invalid", 401, "TOKEN_INVALID"),
        ("/revoked", 401, "TOKEN_REVOKED"),
        ("/forbidden", 403, "FORBIDDEN"),
        ("/too-large", 413, "REQUEST_TOO_LARGE"),
        ("/bad-type", 415, "UNSUPPORTED_MEDIA_TYPE"),
        ("/bad-req", 400, "INVALID_REQUEST"),
    ],
)
async def test_custom_errors_map_to_status_and_code(path, status, code):
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get(path)
    assert r.status_code == status
    body = r.json()
    assert body["error"]["code"] == code
    assert body["error"]["request_id"]  # always present


async def test_rate_limit_error_includes_retry_after_header():
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/rate")
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "RATE_LIMITED"
    assert r.headers["Retry-After"] == "42"
    assert r.headers["X-RateLimit-Limit"] == "10"
    assert r.headers["X-RateLimit-Remaining"] == "0"


async def test_http_exception_passthrough():
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/http")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert r.json()["error"]["message"] == "missing"


async def test_validation_error_returns_422_with_fields():
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/validate", json={"n": "not-an-int"})
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "fields" in body["error"]


async def test_unhandled_exception_does_not_leak_internals():
    app = _build_app()
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as c:
        r = await c.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    # The raw exception text must never reach the client.
    assert "internal secret value" not in r.text
    assert "RuntimeError" not in r.text


async def test_response_includes_request_id_header():
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/forbidden")
    body = r.json()
    # request_id from envelope matches the response header
    assert body["error"]["request_id"]
    assert r.headers["X-Request-ID"] == body["error"]["request_id"]
