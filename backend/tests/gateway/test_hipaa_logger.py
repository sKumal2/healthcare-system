"""Tests for the HIPAA audit logger middleware."""

from __future__ import annotations

import json
import logging

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.gateway.auth.jwt_handler import create_access_token
from app.gateway.exceptions.handlers import register_exception_handlers
from app.gateway.middleware.correlation import CorrelationMiddleware
from app.gateway.middleware.hipaa_logger import HIPAALoggerMiddleware


pytestmark = pytest.mark.asyncio


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(HIPAALoggerMiddleware)

    @app.post("/api/v1/query")
    async def q(payload: dict):
        # Echo a "phi" string so we can verify it does NOT show up in logs.
        return {"echo": payload.get("question", "")}

    @app.get("/boom")
    async def boom():
        raise HTTPException(status_code=500, detail="explode")

    return app


def _audit_lines(caplog) -> list[dict]:
    lines: list[dict] = []
    for rec in caplog.records:
        if rec.name != "audit":
            continue
        try:
            lines.append(json.loads(rec.message))
        except json.JSONDecodeError:
            continue
    return lines


async def test_each_request_logs_one_audit_entry(caplog_audit, fake_redis):
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post(
            "/api/v1/query",
            json={"question": "patient John Doe DOB 1980-01-01"},
        )
    entries = _audit_lines(caplog_audit)
    assert len(entries) == 1
    e = entries[0]
    assert e["event"] == "api_request"
    assert e["method"] == "POST"
    assert e["path"] == "/api/v1/query"
    assert e["status_code"] == 200
    assert isinstance(e["response_time_ms"], int)
    assert e["resource_type"] == "query"


async def test_audit_log_does_not_contain_request_body_or_token(caplog_audit, fake_redis):
    app = _build_app()
    token = create_access_token({"sub": "u-secret", "role": "patient"})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post(
            "/api/v1/query",
            json={"question": "patient John Doe DOB 1980-01-01 SSN 123-45-6789"},
            headers={"Authorization": f"Bearer {token}"},
        )

    # Inspect the actual logged audit record string for forbidden contents.
    audit_text = "\n".join(
        rec.message for rec in caplog_audit.records if rec.name == "audit"
    )
    assert "John Doe" not in audit_text
    assert "123-45-6789" not in audit_text
    assert "1980-01-01" not in audit_text
    assert token not in audit_text
    # User id from JWT *should* be present (it's metadata, not PHI).
    assert "u-secret" in audit_text


async def test_failed_request_still_audited(caplog_audit, fake_redis):
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/boom")
    assert r.status_code == 500
    entries = _audit_lines(caplog_audit)
    assert len(entries) == 1
    assert entries[0]["status_code"] == 500


async def test_only_safe_headers_recorded(caplog_audit, fake_redis):
    app = _build_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.post(
            "/api/v1/query",
            json={"question": "x"},
            headers={
                "Cookie": "session=secret-cookie",
                "X-Custom-PHI": "patient-name-here",
                "Content-Type": "application/json",
            },
        )
    entries = _audit_lines(caplog_audit)
    assert len(entries) == 1
    headers = entries[0]["headers"]
    assert "cookie" not in {k.lower() for k in headers}
    assert "x-custom-phi" not in {k.lower() for k in headers}
    # Content-Type is on the safe list
    assert any(k.lower() == "content-type" for k in headers)


async def test_query_params_redacted(caplog_audit, fake_redis):
    app = _build_app()

    @app.get("/api/v1/document/search")
    async def search(q: str = ""):
        return {"q": q}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.get("/api/v1/document/search", params={"q": "patient name", "page": "2"})

    entries = _audit_lines(caplog_audit)
    assert entries
    last = entries[-1]
    assert last["query"]["q"] == "<redacted>"
    assert last["query"]["page"] == "2"
