"""CORS configuration.

Reads `BACKEND_CORS_ORIGINS` from settings. In `DEBUG` mode we additionally
permit localhost-style origins via a regex so frontend dev servers running
on arbitrary ports work without manual config. In non-DEBUG, the `*`
wildcard is never used.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings


def add_cors_middleware(app: FastAPI) -> None:
    """Install FastAPI's CORSMiddleware with project policy."""
    origins = [str(o).rstrip("/") for o in settings.BACKEND_CORS_ORIGINS] if settings.BACKEND_CORS_ORIGINS else []

    kwargs = {
        "allow_origins": origins,
        "allow_credentials": True,
        "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Authorization", "Content-Type", "X-Request-ID"],
        "expose_headers": [
            "X-Request-ID",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "Retry-After",
        ],
    }

    if settings.DEBUG:
        # Allow any localhost origin in dev — never `*`, never in prod.
        kwargs["allow_origin_regex"] = r"https?://localhost(:\d+)?"

    app.add_middleware(CORSMiddleware, **kwargs)
