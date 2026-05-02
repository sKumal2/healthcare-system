"""Gateway-specific exception types.

These are caught by the global handlers in `handlers.py` and translated
into the standard JSON error envelope with a stable `code` for clients.
"""

from __future__ import annotations


class GatewayError(Exception):
    """Base class for all gateway-layer errors."""

    code: str = "GATEWAY_ERROR"
    status_code: int = 500
    default_message: str = "An error occurred."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


# ---------- Token errors (401) ----------


class TokenExpiredError(GatewayError):
    code = "TOKEN_EXPIRED"
    status_code = 401
    default_message = "Token has expired."


class TokenInvalidError(GatewayError):
    code = "TOKEN_INVALID"
    status_code = 401
    default_message = "Token is invalid."


class TokenRevokedError(GatewayError):
    code = "TOKEN_REVOKED"
    status_code = 401
    default_message = "Token has been revoked."


# ---------- AuthZ ----------


class PermissionDeniedError(GatewayError):
    code = "FORBIDDEN"
    status_code = 403
    default_message = "You do not have permission to access this resource."


# ---------- Rate limiting ----------


class RateLimitExceededError(GatewayError):
    code = "RATE_LIMITED"
    status_code = 429
    default_message = "Too many requests."

    def __init__(
        self,
        message: str | None = None,
        retry_after_seconds: int = 60,
        limit: int | None = None,
    ) -> None:
        self.retry_after_seconds = retry_after_seconds
        self.limit = limit
        super().__init__(message)


# ---------- Request validation (413/415/400) ----------


class RequestTooLargeError(GatewayError):
    code = "REQUEST_TOO_LARGE"
    status_code = 413
    default_message = "Request body exceeds maximum allowed size."


class UnsupportedMediaTypeError(GatewayError):
    code = "UNSUPPORTED_MEDIA_TYPE"
    status_code = 415
    default_message = "Unsupported Content-Type."


class InvalidRequestError(GatewayError):
    code = "INVALID_REQUEST"
    status_code = 400
    default_message = "Invalid request."
