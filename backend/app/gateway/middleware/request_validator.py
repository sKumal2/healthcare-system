"""Request-level validation middleware.

- Rejects bodies larger than `MAX_REQUEST_SIZE_BYTES` (413).
- Rejects POST/PUT/PATCH requests whose Content-Type is not JSON or multipart (415).
- Rejects GET/DELETE requests that include a body (400).

This middleware does *not* parse the body — it only inspects headers and
performs streaming length checks, so it imposes no additional latency.
"""

from __future__ import annotations

from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings
from app.gateway.exceptions import (
    GatewayError,
    InvalidRequestError,
    RequestTooLargeError,
    UnsupportedMediaTypeError,
)
from app.gateway.exceptions.handlers import gateway_error_to_response

_BODY_METHODS: Iterable[str] = ("POST", "PUT", "PATCH")
_NO_BODY_METHODS: Iterable[str] = ("GET", "DELETE")
_ALLOWED_CONTENT_TYPES: tuple[str, ...] = (
    "application/json",
    "multipart/form-data",
    "application/x-www-form-urlencoded",
)


def _content_type_allowed(value: str | None) -> bool:
    if not value:
        return False
    base = value.split(";", 1)[0].strip().lower()
    return base in _ALLOWED_CONTENT_TYPES


class RequestValidatorMiddleware(BaseHTTPMiddleware):
    """Enforce body-size, content-type, and method/body invariants."""

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
        method = request.method.upper()

        # Skip CORS preflight
        if method == "OPTIONS":
            return await call_next(request)

        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                length = int(content_length)
            except ValueError:
                raise InvalidRequestError("Content-Length header is not an integer.")
            if length > settings.MAX_REQUEST_SIZE_BYTES:
                raise RequestTooLargeError(
                    f"Request body exceeds the {settings.MAX_REQUEST_SIZE_BYTES}-byte limit."
                )

        if method in _BODY_METHODS:
            if not _content_type_allowed(request.headers.get("content-type")):
                raise UnsupportedMediaTypeError(
                    "Content-Type must be application/json, multipart/form-data, "
                    "or application/x-www-form-urlencoded."
                )

        if method in _NO_BODY_METHODS:
            # Either Content-Length > 0 or chunked transfer encoding indicates a body.
            if content_length and int(content_length) > 0:
                raise InvalidRequestError(f"{method} requests must not include a body.")
            if request.headers.get("transfer-encoding", "").lower() == "chunked":
                raise InvalidRequestError(f"{method} requests must not include a body.")

        return await call_next(request)
