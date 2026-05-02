"""FastAPI dependencies wrapping JWT auth.

`get_current_user` is the standard dependency for protected routes;
`require_role(...)` is a factory for role-gated routes; `get_optional_user`
is for endpoints that work both authenticated and anonymously.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer

from app.core.config import settings
from app.gateway.auth.jwt_handler import decode_token
from app.gateway.auth.models import UserIdentity
from app.gateway.exceptions import (
    PermissionDeniedError,
    TokenInvalidError,
)

logger = logging.getLogger("app")

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    auto_error=False,
)


async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> UserIdentity:
    """Resolve a Bearer token to a UserIdentity, raising 401 on any failure."""
    if not token:
        raise TokenInvalidError("Missing bearer token.")
    payload = await decode_token(token)
    if payload.token_type != "access":
        raise TokenInvalidError("Refresh token cannot be used as access token.")
    return UserIdentity(user_id=payload.sub, role=payload.role, jti=payload.jti)


async def get_optional_user(
    token: Optional[str] = Depends(oauth2_scheme),
) -> Optional[UserIdentity]:
    """Same as get_current_user, but returns None when no token is supplied.

    Token errors (expired/invalid/revoked) still raise — supplying a *bad*
    token is treated as a real auth failure, not as anonymous access.
    """
    if not token:
        return None
    payload = await decode_token(token)
    if payload.token_type != "access":
        return None
    return UserIdentity(user_id=payload.sub, role=payload.role, jti=payload.jti)


def require_role(*roles: str):
    """Build a dependency that admits only the given roles.

    Usage::

        admin_only = require_role("admin")

        @router.get("/x", dependencies=[Depends(admin_only)])
        def x(): ...
    """
    allowed = set(roles)

    async def _checker(user: UserIdentity = Depends(get_current_user)) -> UserIdentity:
        if user.role not in allowed:
            raise PermissionDeniedError(
                f"Role '{user.role}' is not permitted on this endpoint."
            )
        return user

    return _checker


def get_request_user(request: Request) -> Optional[UserIdentity]:
    """Read the resolved user off `request.state` if any middleware put it there.

    Used by the rate limiter and HIPAA logger to discover the caller without
    re-decoding the JWT. They cannot use FastAPI dependencies because they
    run as Starlette middleware, not as route handlers.
    """
    return getattr(request.state, "user", None)
