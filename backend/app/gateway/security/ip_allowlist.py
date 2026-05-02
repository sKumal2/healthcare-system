"""IP allowlist middleware for `/api/v1/admin/...` routes.

If `ADMIN_IP_ALLOWLIST` is empty (the default) the middleware is a no-op.
Otherwise we parse the comma-separated CIDRs once at startup and check
the client IP on every admin request, denying with 403 if it does not
match any listed network.

Blocked attempts are logged at WARNING level — IP, path, timestamp only;
no PHI, no headers, no request body.
"""

from __future__ import annotations

import ipaddress
import logging
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.gateway.exceptions import GatewayError, PermissionDeniedError
from app.gateway.exceptions.handlers import gateway_error_to_response

logger = logging.getLogger("app")


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return "unknown"


class IPAllowlistMiddleware(BaseHTTPMiddleware):
    """Restrict `/api/v1/admin/...` traffic to configured CIDRs."""

    def __init__(self, app, *, admin_prefix: str | None = None) -> None:
        super().__init__(app)
        self._admin_prefix = admin_prefix or f"{settings.API_V1_STR}/admin"
        self._networks = self._parse_networks(settings.admin_ip_allowlist_cidrs)

    @staticmethod
    def _parse_networks(cidrs: list[str]) -> list[ipaddress._BaseNetwork]:
        nets: list[ipaddress._BaseNetwork] = []
        for cidr in cidrs:
            try:
                nets.append(ipaddress.ip_network(cidr, strict=False))
            except ValueError:
                logger.warning("invalid_cidr_in_admin_ip_allowlist", extra={"cidr": cidr})
        return nets

    def _is_allowed(self, ip_str: str) -> bool:
        if not self._networks:
            return True
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        return any(ip in net for net in self._networks)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            return await self._dispatch(request, call_next)
        except GatewayError as exc:
            return gateway_error_to_response(exc)

    async def _dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not self._networks:
            return await call_next(request)
        if not request.url.path.startswith(self._admin_prefix):
            return await call_next(request)

        ip = _client_ip(request)
        if not self._is_allowed(ip):
            logger.warning(
                "admin_ip_blocked",
                extra={
                    "ip": ip,
                    "path": request.url.path,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            raise PermissionDeniedError("Source IP is not permitted for admin endpoints.")
        return await call_next(request)
