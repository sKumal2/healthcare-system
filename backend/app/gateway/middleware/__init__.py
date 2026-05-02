"""Starlette middleware components for the API gateway.

Submodules are intentionally not re-exported at package level to avoid
circular imports between `middleware.rate_limiter` and `exceptions.handlers`.
Import from the submodule directly, e.g.::

    from app.gateway.middleware.correlation import CorrelationMiddleware
"""
