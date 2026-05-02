"""API Gateway layer.

Single entry point for all client traffic — handles auth, rate limiting,
HIPAA-compliant audit logging, request validation, security headers,
CORS, and IP allowlisting before requests reach the service routers.
"""
