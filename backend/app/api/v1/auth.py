"""Authentication endpoints: login, refresh, logout, me.

These endpoints front the JWT handler and the Redis refresh-token store.
The login endpoint validates credentials against the `users` table via
SQLAlchemy; password hashes are checked with passlib's bcrypt context.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.gateway.auth import (
    UserIdentity,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    revoke_refresh_token,
    revoke_token,
    validate_refresh_token,
)
from app.gateway.auth.jwt_handler import store_refresh_token
from app.gateway.exceptions import (
    PermissionDeniedError,
    TokenInvalidError,
)

logger = logging.getLogger("app")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
router = APIRouter(prefix="/auth", tags=["auth"])


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:  # noqa: BLE001
        return False


def _lookup_user(db: Session, username: str):
    """Look up a user record by email or username.

    Returns a tuple `(user_id, role, hashed_password, is_active)` or `None`.
    The healthcare DB stores users by email, so we treat the form's
    `username` field as an email.
    """
    try:
        from app.models.database import UserModel
    except Exception:  # noqa: BLE001
        return None
    user = db.query(UserModel).filter(UserModel.email == username).first()
    if user is None:
        return None
    role_value = user.role.value if hasattr(user.role, "value") else str(user.role)
    return str(user.id), role_value, user.hashed_password, bool(user.is_active)


@router.post("/login", response_model=TokenPair)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> TokenPair:
    """Validate credentials, issue a fresh access + refresh token pair."""
    record = _lookup_user(db, form_data.username)
    if record is None:
        raise PermissionDeniedError("Invalid credentials.")
    user_id, role, hashed_password, is_active = record
    if not is_active:
        raise PermissionDeniedError("User account is disabled.")
    if not _verify_password(form_data.password, hashed_password):
        raise PermissionDeniedError("Invalid credentials.")

    access = create_access_token({"sub": user_id, "role": role})
    refresh = create_refresh_token(user_id, role=role)
    await store_refresh_token(user_id, refresh)
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(payload: RefreshRequest = Body(...)) -> AccessTokenResponse:
    """Rotate the refresh token and issue a new access token."""
    decoded = await decode_token(payload.refresh_token)
    if decoded.token_type != "refresh":
        raise TokenInvalidError("Token is not a refresh token.")
    if not await validate_refresh_token(decoded.sub, payload.refresh_token):
        raise TokenInvalidError("Refresh token is no longer valid.")

    # Rotate: invalidate the old refresh token and issue a fresh one.
    new_refresh = create_refresh_token(decoded.sub, role=decoded.role)
    await store_refresh_token(decoded.sub, new_refresh)
    new_access = create_access_token({"sub": decoded.sub, "role": decoded.role})
    return AccessTokenResponse(access_token=new_access)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def logout(user: UserIdentity = Depends(get_current_user)) -> Response:
    """Revoke both the access token (by jti) and the refresh token (by user)."""
    # Best-effort: remaining lifetime of the access token = exp - now, but we
    # don't have exp on UserIdentity. Use the configured max lifetime as TTL.
    ttl = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    await revoke_token(user.jti, ttl)
    await revoke_refresh_token(user.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserIdentity)
async def me(user: UserIdentity = Depends(get_current_user)) -> UserIdentity:
    """Return the currently authenticated caller's identity."""
    return user
