"""Global FastAPI exception handlers.

Every error response from the API gateway flows through one of these
handlers and is normalized to the shape:

    {
      "error": {
        "code": "<STABLE_CODE>",
        "message": "...",
        "request_id": "<uuid>"
      }
    }

The catch-all `Exception` handler intentionally hides internal details
from the client — full traceback is logged to the application logger
under the request's correlation ID.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.gateway.exceptions import (
    GatewayError,
    InvalidRequestError,
    PermissionDeniedError,
    RateLimitExceededError,
    RequestTooLargeError,
    TokenExpiredError,
    TokenInvalidError,
    TokenRevokedError,
    UnsupportedMediaTypeError,
)
from app.gateway.middleware.correlation import get_request_id

logger = logging.getLogger("app")


def _envelope(code: str, message: str, request_id: str, **extra: Any) -> dict[str, Any]:
    """Build the standard error JSON envelope."""
    body: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        }
    }
    if extra:
        body["error"].update(extra)
    return body


def gateway_error_to_response(exc: GatewayError) -> JSONResponse:
    """Build a JSONResponse for a gateway error.

    Used by middleware that needs to convert raised gateway errors into a
    response directly — Starlette doesn't route middleware-raised errors
    through the FastAPI exception handler chain, so we do it ourselves.
    """
    request_id = get_request_id() or ""
    headers: dict[str, str] = {}
    if isinstance(exc, RateLimitExceededError):
        headers["Retry-After"] = str(exc.retry_after_seconds)
        if exc.limit is not None:
            headers["X-RateLimit-Limit"] = str(exc.limit)
            headers["X-RateLimit-Remaining"] = "0"
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(exc.code, exc.message, request_id),
        headers=headers,
    )


async def gateway_error_handler(request: Request, exc: GatewayError) -> JSONResponse:
    """Handle all custom GatewayError subclasses with their declared status & code."""
    request_id = get_request_id() or ""
    headers: dict[str, str] = {}
    extra: dict[str, Any] = {}

    if isinstance(exc, RateLimitExceededError):
        headers["Retry-After"] = str(exc.retry_after_seconds)
        if exc.limit is not None:
            headers["X-RateLimit-Limit"] = str(exc.limit)
            headers["X-RateLimit-Remaining"] = "0"

    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(exc.code, exc.message, request_id, **extra),
        headers=headers,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Convert FastAPI body/query validation errors to the standard envelope."""
    request_id = get_request_id() or ""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_envelope(
            "VALIDATION_ERROR",
            "Request validation failed.",
            request_id,
            fields=exc.errors(),
        ),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Pass through FastAPI HTTPException status codes; normalize the body."""
    request_id = get_request_id() or ""
    code = _status_to_code(exc.status_code)
    message = exc.detail if isinstance(exc.detail, str) else "HTTP error."
    return JSONResponse(
        status_code=exc.status_code,
        content=_envelope(code, message, request_id),
        headers=getattr(exc, "headers", None) or {},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all 500 handler. Never exposes internal details to clients."""
    request_id = get_request_id() or ""
    logger.exception(
        "unhandled_exception",
        extra={"request_id": request_id, "path": request.url.path},
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_envelope(
            "INTERNAL_ERROR",
            "An internal error occurred. Please try again later.",
            request_id,
        ),
    )


def _status_to_code(status_code: int) -> str:
    """Map common HTTP status codes to stable error codes for the envelope."""
    return {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        413: "REQUEST_TOO_LARGE",
        415: "UNSUPPORTED_MEDIA_TYPE",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
        500: "INTERNAL_ERROR",
        502: "BAD_GATEWAY",
        503: "SERVICE_UNAVAILABLE",
        504: "GATEWAY_TIMEOUT",
    }.get(status_code, "ERROR")


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all gateway exception handlers to a FastAPI app."""
    # All custom gateway errors funnel through one handler.
    for exc_type in (
        TokenExpiredError,
        TokenInvalidError,
        TokenRevokedError,
        PermissionDeniedError,
        RateLimitExceededError,
        RequestTooLargeError,
        UnsupportedMediaTypeError,
        InvalidRequestError,
        GatewayError,
    ):
        app.add_exception_handler(exc_type, gateway_error_handler)

    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
