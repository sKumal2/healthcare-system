"""Authentication endpoints: login, refresh, logout, me.

These endpoints front the JWT handler and the Redis refresh-token store.
The login endpoint validates credentials against the `users` table via
SQLAlchemy; password hashes are checked with passlib's bcrypt context.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8)
    full_name: str = Field(..., min_length=2)
    invite_code: Optional[str] = Field(None, max_length=20)


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:  # noqa: BLE001
        return False


async def _lookup_user(db: AsyncSession, username: str):
    """Look up a user record by email or username.

    Returns a tuple `(user_id, role, hashed_password, is_active)` or `None`.
    The healthcare DB stores users by email, so we treat the form's
    `username` field as an email.
    """
    try:
        from app.models.database import User
    except Exception:  # noqa: BLE001
        return None
    result = await db.execute(select(User).where(User.email == username))
    user = result.scalar_one_or_none()
    if user is None:
        return None
    role_value = user.role.value if hasattr(user.role, "value") else str(user.role)
    return str(user.id), role_value, user.password_hash, bool(user.is_active)


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """Register a new user.

    If invite_code is provided → join existing org as PATIENT.
    If no invite_code → create new org, user becomes ORG_OWNER.
    """
    from app.models.database import User, Organization
    from app.models.enums import RoleEnum

    email_normalized = payload.email.lower().strip()

    existing = await db.execute(select(User).where(User.email == email_normalized))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists."
        )

    if payload.invite_code:
        code = payload.invite_code.upper().strip()
        org_result = await db.execute(
            select(Organization).where(
                Organization.invite_code == code,
                Organization.is_active == True,
            )
        )
        org = org_result.scalar_one_or_none()

        if not org:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid organization code. Please check with your administrator."
            )

        role = RoleEnum.PATIENT
        logger.info("User %s joining org '%s' via invite code", email_normalized, org.name)

    else:
        invite_code = secrets.token_hex(4).upper()
        org = Organization(
            name=f"{payload.full_name.split()[0]}'s Organization",
            email=email_normalized,
            is_active=True,
            invite_code=invite_code,
        )
        db.add(org)
        await db.flush()

        role = RoleEnum.ORGANIZATION_OWNER
        logger.info("New org created with invite code: %s", invite_code)

    user = User(
        email=email_normalized,
        full_name=payload.full_name.strip(),
        password_hash=pwd_context.hash(payload.password),
        role=role,
        organization_id=org.id,
        is_active=True,
        is_email_verified=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    user_id = str(user.id)
    role_value = user.role.value
    access = create_access_token({"sub": user_id, "role": role_value})
    refresh = create_refresh_token(user_id, role=role_value)
    await store_refresh_token(user_id, refresh)
    return TokenPair(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=TokenPair)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> TokenPair:
    """Validate credentials, issue a fresh access + refresh token pair."""
    record = await _lookup_user(db, form_data.username)
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
