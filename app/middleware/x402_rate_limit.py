"""Per-IP rate limiting for the agent surface (/v1/* + /x402/v1/*).

In-process sliding window (single uvicorn worker; Redis is gone).
Fails open on any error. Protects free endpoints like /v1/estimate and
the 402 gateway from probe floods without throttling legit agents.
"""
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.cache import rate_check

logger = logging.getLogger("cortexcloud.middleware.x402_ratelimit")

X402_IP_LIMIT = 1200          # requests per window
X402_IP_WINDOW = 60           # seconds


class X402RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if not (path.startswith("/v1") or path.startswith("/x402/v1")):
            return await call_next(request)

        client_ip = request.client.host if request.client else "127.0.0.1"
        try:
            ok = rate_check(f"ip:{client_ip}", X402_IP_LIMIT, X402_IP_WINDOW)
        except Exception as e:
            logger.warning(f"x402 rate-limit check failed (fail-open): {e}")
            ok = True
        if not ok:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content={"error": "x402 gateway rate limit exceeded. Slow down and retry."},
            )
        return await call_next(request)