"""Correlation-ID middleware.

Reads the inbound `X-Request-ID` header (or generates a new uuid4 if absent
or invalid), stashes it on a `ContextVar`, and writes it back on the response.
Downstream loggers read the value via `get_request_id()` to stamp every log
line for a single request with the same id.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)

REQUEST_ID_HEADER = "X-Request-ID"


def get_request_id() -> Optional[str]:
    """Return the current request's correlation id, or None if not in a request."""
    return _request_id_ctx.get()


def _set_request_id(value: str) -> None:
    _request_id_ctx.set(value)


def _is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Inject a correlation id into every request/response cycle."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming if incoming and _is_valid_uuid(incoming) else str(uuid.uuid4())

        token = _request_id_ctx.set(request_id)
        request.state.request_id = request_id
        try:
            response = await call_next(request)
        finally:
            _request_id_ctx.reset(token)

        response.headers[REQUEST_ID_HEADER] = request_id
        return response
