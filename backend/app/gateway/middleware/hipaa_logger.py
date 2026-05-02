"""HIPAA-compliant audit logging middleware.

Every request produces exactly one structured JSON entry on the dedicated
`audit` logger. The entry contains *only* metadata — never request bodies,
response bodies, raw tokens, or unapproved headers/query params — because
patient questions and answers may contain PHI (names, DOBs, conditions).

Audit log entries are guaranteed to be emitted even on 5xx errors via
try/finally: the auditor must log first, then re-raise.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings

audit_logger = logging.getLogger("audit")

# Headers we are willing to copy into the audit log. Everything else is dropped.
SAFE_HEADERS = {"content-type", "accept", "x-request-id"}

# Query parameter names that are safe to record. We keep the *names* but not
# the values unless the name is in this allowlist.
SAFE_QUERY_PARAMS = {"page", "limit", "offset", "sort", "order"}


def _classify_resource(path: str) -> str:
    if path.startswith(f"{settings.API_V1_STR}/query") or path.startswith(
        f"{settings.API_V1_STR}/conversations"
    ):
        return "query"
    if path.startswith(f"{settings.API_V1_STR}/document"):
        return "document"
    if path.startswith(f"{settings.API_V1_STR}/admin"):
        return "admin"
    if path.startswith(f"{settings.API_V1_STR}/auth"):
        return "auth"
    if path in ("/", "/health", "/healthz", "/ready"):
        return "health"
    return "other"


def _client_ip(request: Request) -> str:
    """Resolve the client's real IP, honoring `X-Forwarded-For` for proxied requests."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        # Leftmost address in XFF is the originating client.
        return xff.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return "unknown"


def _peek_user(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Best-effort extraction of (user_id, role) from the Authorization header.

    We *do not* fully validate the token here — the auth dependency handles
    that. We just want to record who the caller claimed to be, even if their
    request later 401s. Decoding errors silently yield (None, None).
    """
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None, None
    token = auth.split(" ", 1)[1].strip()
    if not token:
        return None, None
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": False},
        )
    except JWTError:
        return None, None
    return payload.get("sub"), payload.get("role")


def _safe_headers(request: Request) -> dict[str, str]:
    return {k: v for k, v in request.headers.items() if k.lower() in SAFE_HEADERS}


def _safe_query(request: Request) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in request.query_params.multi_items():
        if k in SAFE_QUERY_PARAMS:
            out[k] = v
        else:
            out[k] = "<redacted>"
    return out


class HIPAALoggerMiddleware(BaseHTTPMiddleware):
    """Audit-log every request as structured JSON on the `audit` logger."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.perf_counter()
        status_code = 500
        response: Optional[Response] = None
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception:
            # Let the exception propagate — but record it in the audit log.
            status_code = 500
            raise
        finally:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            user_id, user_role = _peek_user(request)
            user_agent = (request.headers.get("user-agent") or "")[:200]

            entry = {
                "event": "api_request",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "request_id": getattr(request.state, "request_id", None),
                "method": request.method,
                "path": request.url.path,
                "user_id": user_id,
                "user_role": user_role,
                "client_ip": _client_ip(request),
                "user_agent": user_agent,
                "status_code": status_code,
                "response_time_ms": elapsed_ms,
                "resource_type": _classify_resource(request.url.path),
                "headers": _safe_headers(request),
                "query": _safe_query(request),
            }
            # Emit a single JSON line so downstream SIEMs can parse trivially.
            audit_logger.info(json.dumps(entry, default=str))
