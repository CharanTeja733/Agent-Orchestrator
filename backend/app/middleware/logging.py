"""Request logging middleware for the HR Q&A Agent.

Captures every HTTP request with method, path, status code, duration, and a
unique ``X-Request-ID`` for end-to-end tracing.
"""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.middleware.logging")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with a unique request ID for tracing."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        start = time.time()

        response: Response = await call_next(request)

        duration_ms = round((time.time() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id

        # Determine user identity if available
        user_id = None
        if hasattr(request, "state"):
            user = getattr(request.state, "user", None)
            if user is not None and hasattr(user, "id"):
                user_id = str(user.id)

        # Pick log level based on status
        if response.status_code >= 500:
            log_level = logging.ERROR
        elif response.status_code >= 400:
            log_level = logging.WARNING
        else:
            log_level = logging.INFO

        logger.log(
            log_level,
            "%s %s → %d [%s] (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            request_id,
            duration_ms,
            extra={
                "component": "http",
                "event": "request",
                "details": {
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "request_id": request_id,
                    "duration_ms": duration_ms,
                    "user_id": user_id,
                },
            },
        )

        return response
