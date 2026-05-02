"""Pydantic models describing JWT payloads and authenticated callers."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TokenPayload(BaseModel):
    """Decoded JWT payload as we embed it.

    Always carries `sub` (user_id), `role`, `jti` (unique token id),
    and standard `exp`/`iat` claims.
    """

    sub: str
    role: str
    jti: str
    exp: int
    iat: int
    token_type: str = Field(default="access")


class UserIdentity(BaseModel):
    """Lightweight authenticated-caller identity derived from a JWT.

    This is what request handlers see. It deliberately contains no PII
    — request handlers fetch full user records from the DB by `user_id`
    when they actually need to.
    """

    user_id: str
    role: str
    jti: str
