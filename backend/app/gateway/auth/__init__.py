"""Authentication primitives for the API gateway.

Exports:
- JWT handler functions (create_access_token, decode_token, ...)
- FastAPI dependencies (get_current_user, require_role, ...)
- Pydantic models (TokenPayload, UserIdentity)
"""

from app.gateway.auth.dependencies import (
    get_current_user,
    get_optional_user,
    oauth2_scheme,
    require_role,
)
from app.gateway.auth.jwt_handler import (
    create_access_token,
    create_refresh_token,
    decode_token,
    revoke_refresh_token,
    revoke_token,
    validate_refresh_token,
)
from app.gateway.auth.models import TokenPayload, UserIdentity

__all__ = [
    "TokenPayload",
    "UserIdentity",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "get_current_user",
    "get_optional_user",
    "oauth2_scheme",
    "require_role",
    "revoke_refresh_token",
    "revoke_token",
    "validate_refresh_token",
]
