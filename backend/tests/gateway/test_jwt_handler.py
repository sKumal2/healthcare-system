"""Tests for JWT creation, decoding, and revocation."""

from __future__ import annotations

import time
from datetime import timedelta

import pytest
from jose import jwt

from app.core.config import settings
from app.gateway.auth.jwt_handler import (
    create_access_token,
    create_refresh_token,
    decode_token,
    revoke_token,
    store_refresh_token,
    validate_refresh_token,
)
from app.gateway.exceptions import (
    TokenExpiredError,
    TokenInvalidError,
    TokenRevokedError,
)


pytestmark = pytest.mark.asyncio


async def test_create_and_decode_round_trip(fake_redis):
    token = create_access_token({"sub": "user-1", "role": "patient"})
    payload = await decode_token(token)
    assert payload.sub == "user-1"
    assert payload.role == "patient"
    assert payload.token_type == "access"
    assert payload.jti  # uuid is present


async def test_expired_token_raises(fake_redis):
    token = create_access_token(
        {"sub": "user-1", "role": "patient"},
        expires_delta=timedelta(seconds=-1),
    )
    with pytest.raises(TokenExpiredError):
        await decode_token(token)


async def test_tampered_signature_raises(fake_redis):
    token = create_access_token({"sub": "user-1", "role": "patient"})
    # Flip the last char of the signature segment
    head, payload, sig = token.split(".")
    tampered = ".".join([head, payload, sig[:-1] + ("A" if sig[-1] != "A" else "B")])
    with pytest.raises(TokenInvalidError):
        await decode_token(tampered)


async def test_malformed_payload_raises(fake_redis):
    bad = jwt.encode({"foo": "bar"}, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    with pytest.raises(TokenInvalidError):
        await decode_token(bad)


async def test_revoked_jti_raises(fake_redis):
    token = create_access_token({"sub": "user-1", "role": "patient"})
    payload = await decode_token(token)
    await revoke_token(payload.jti, ttl=60)
    with pytest.raises(TokenRevokedError):
        await decode_token(token)


async def test_token_does_not_contain_password_or_pii(fake_redis):
    token = create_access_token({"sub": "user-1", "role": "patient"})
    decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    forbidden = {"password", "hashed_password", "ssn", "dob", "email"}
    assert not (decoded.keys() & forbidden)


async def test_create_access_token_requires_sub_and_role(fake_redis):
    with pytest.raises(ValueError):
        create_access_token({"role": "patient"})
    with pytest.raises(ValueError):
        create_access_token({"sub": "u"})


async def test_refresh_token_round_trip(fake_redis):
    token = create_refresh_token("user-2", role="clinician")
    await store_refresh_token("user-2", token)
    assert await validate_refresh_token("user-2", token) is True

    # Wrong token for the user fails
    other = create_refresh_token("user-2", role="clinician")
    assert await validate_refresh_token("user-2", other) is False


async def test_refresh_token_rotation(fake_redis):
    a = create_refresh_token("user-3")
    await store_refresh_token("user-3", a)
    b = create_refresh_token("user-3")
    await store_refresh_token("user-3", b)
    assert await validate_refresh_token("user-3", a) is False
    assert await validate_refresh_token("user-3", b) is True


async def test_revoke_token_with_zero_ttl_is_noop(fake_redis):
    # A token whose ttl is already in the past shouldn't be added to Redis.
    await revoke_token("nonexistent-jti", ttl=0)
    assert await fake_redis.exists("healthcare:revoked_tokens:nonexistent-jti") == 0
