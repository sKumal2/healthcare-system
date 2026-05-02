"""JWT signing, decoding, and revocation.

- Access tokens are short-lived (`ACCESS_TOKEN_EXPIRE_MINUTES`) and carry
  a unique `jti` so individual tokens can be revoked by adding the jti
  to a Redis set.
- Refresh tokens are long-lived (`REFRESH_TOKEN_EXPIRE_DAYS`) and rotated
  on every refresh — only the *hash* of the active refresh token is stored
  in Redis, keyed by user_id, so a leaked refresh token at rest cannot be
  reused once rotated.
- Raw token strings are never logged.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError

from app.core.config import settings
from app.gateway.auth.models import TokenPayload
from app.gateway.exceptions import (
    TokenExpiredError,
    TokenInvalidError,
    TokenRevokedError,
)
from app.gateway.redis_client import get_redis

logger = logging.getLogger("app")

_REVOKED_KEY = "healthcare:revoked_tokens:{jti}"
_REFRESH_KEY = "healthcare:refresh_tokens:{user_id}"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    """SHA-256 hash a token for at-rest comparison without storing it raw."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """Sign an access token. `data` must include `sub` and `role`.

    Always injects `exp`, `iat`, `jti`, and `token_type=access`.
    """
    if "sub" not in data:
        raise ValueError("access token data must include 'sub' (user_id)")
    if "role" not in data:
        raise ValueError("access token data must include 'role'")

    now = _now_utc()
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    payload = {
        **data,
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
        "jti": str(uuid.uuid4()),
        "token_type": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(user_id: str, role: str = "") -> str:
    """Sign a refresh token bound to user_id.

    Caller is expected to also call `store_refresh_token` to persist the
    hash for later validation/rotation.
    """
    now = _now_utc()
    expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": user_id,
        "role": role,
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
        "jti": str(uuid.uuid4()),
        "token_type": "refresh",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def store_refresh_token(user_id: str, token: str) -> None:
    """Store the hash of the refresh token in Redis, keyed by user_id.

    Only one active refresh token per user — calling this overwrites any
    prior refresh token, effectively rotating it.
    """
    ttl = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    await get_redis().set(
        _REFRESH_KEY.format(user_id=user_id),
        _hash_token(token),
        ex=ttl,
    )


async def validate_refresh_token(user_id: str, token: str) -> bool:
    """Check that the supplied refresh token matches the stored hash for user_id."""
    stored = await get_redis().get(_REFRESH_KEY.format(user_id=user_id))
    if not stored:
        return False
    return stored == _hash_token(token)


async def revoke_refresh_token(user_id: str) -> None:
    """Delete the user's refresh-token hash from Redis (used on logout)."""
    await get_redis().delete(_REFRESH_KEY.format(user_id=user_id))


async def revoke_token(jti: str, ttl: int) -> None:
    """Mark `jti` as revoked. TTL should match the access token's remaining lifetime."""
    if ttl <= 0:
        return  # already expired naturally
    await get_redis().set(_REVOKED_KEY.format(jti=jti), "1", ex=ttl)


async def _is_revoked(jti: str) -> bool:
    """Return True if `jti` has been revoked. Fails closed on Redis errors."""
    try:
        return bool(await get_redis().exists(_REVOKED_KEY.format(jti=jti)))
    except Exception:  # noqa: BLE001 — we want to fail closed
        logger.warning("redis_revocation_check_failed", exc_info=True)
        # Security-critical path: if we can't check revocation, deny.
        raise TokenRevokedError("Unable to verify token state.")


async def decode_token(token: str) -> TokenPayload:
    """Decode and validate a JWT, raising the appropriate gateway error on failure."""
    try:
        raw = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except ExpiredSignatureError as e:
        raise TokenExpiredError() from e
    except JWTError as e:
        raise TokenInvalidError() from e

    try:
        payload = TokenPayload(**raw)
    except Exception as e:  # noqa: BLE001 — pydantic validation
        raise TokenInvalidError("Token payload is malformed.") from e

    if await _is_revoked(payload.jti):
        raise TokenRevokedError()

    return payload
