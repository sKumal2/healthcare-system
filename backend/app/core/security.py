"""Compatibility shim — re-exports gateway auth primitives.

The existing admin/queries routers were written against
`app.core.security.get_current_user` before the gateway was introduced.
This module wires those imports through to the new gateway-managed
auth dependency without forcing changes to the routers themselves.
"""

from app.gateway.auth.dependencies import (  # noqa: F401
    get_current_user,
    get_optional_user,
    oauth2_scheme,
    require_role,
)
from app.gateway.auth.models import UserIdentity  # noqa: F401
