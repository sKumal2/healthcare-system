"""Tests for the FastAPI auth dependencies."""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.gateway.auth.dependencies import (
    get_current_user,
    get_optional_user,
    require_role,
)
from app.gateway.auth.jwt_handler import create_access_token
from app.gateway.auth.models import UserIdentity
from app.gateway.exceptions.handlers import register_exception_handlers
from datetime import timedelta


pytestmark = pytest.mark.asyncio


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/me")
    async def me(user: UserIdentity = Depends(get_current_user)) -> dict:
        return {"user_id": user.user_id, "role": user.role}

    @app.get("/admin", dependencies=[Depends(require_role("admin"))])
    async def admin_only() -> dict:
        return {"ok": True}

    @app.get("/optional")
    async def optional(user=Depends(get_optional_user)) -> dict:
        return {"user_id": user.user_id if user else None}

    return app


async def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_get_current_user_returns_identity(fake_redis):
    app = _build_app()
    token = create_access_token({"sub": "u-1", "role": "patient"})
    async with await _client(app) as c:
        r = await c.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {"user_id": "u-1", "role": "patient"}


async def test_get_current_user_missing_token_returns_401(fake_redis):
    app = _build_app()
    async with await _client(app) as c:
        r = await c.get("/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "TOKEN_INVALID"


async def test_get_current_user_expired_token_returns_401(fake_redis):
    app = _build_app()
    token = create_access_token(
        {"sub": "u-1", "role": "patient"}, expires_delta=timedelta(seconds=-1)
    )
    async with await _client(app) as c:
        r = await c.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "TOKEN_EXPIRED"


async def test_require_role_passes_for_admin(fake_redis):
    app = _build_app()
    token = create_access_token({"sub": "u-1", "role": "admin"})
    async with await _client(app) as c:
        r = await c.get("/admin", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


async def test_require_role_blocks_patient(fake_redis):
    app = _build_app()
    token = create_access_token({"sub": "u-1", "role": "patient"})
    async with await _client(app) as c:
        r = await c.get("/admin", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


async def test_optional_user_anonymous_allowed(fake_redis):
    app = _build_app()
    async with await _client(app) as c:
        r = await c.get("/optional")
    assert r.status_code == 200
    assert r.json() == {"user_id": None}


async def test_optional_user_with_token_resolves(fake_redis):
    app = _build_app()
    token = create_access_token({"sub": "u-9", "role": "patient"})
    async with await _client(app) as c:
        r = await c.get("/optional", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {"user_id": "u-9"}
