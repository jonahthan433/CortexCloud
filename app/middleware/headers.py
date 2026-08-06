"""S3 + S6: emit X-Cortex-* headers and ECDSA-sign every response.

Runs after the x402 payment middleware so it sees the final Response. Reads
request_id and upstream metadata from request.state (set by the router). Signs
SHA256(request_id + response_body) for non-streaming responses and attaches
X-Cortex-Signature. Public key at /x402/v1/pubkey.

Also enforces Section 5: HTTP security headers + strips server identity.
"""
import logging
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import StreamingResponse

from app.x402.trust import sign_payload  # noqa: F401

logger = logging.getLogger("cortexcloud.middleware.headers")

# Section 5: security headers emitted on every response.
_SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'none'",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}
# Remove any header that leaks server/framework identity.
_IDENTITY_HEADERS = ("server", "x-powered-by", "x-aspnet-version")


class CortexHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-correlation-id") or (getattr(request.state, "request_id", None) or "")
        resp = await call_next(request)

        # Always attach the request id header.
        if request_id and "X-Cortex-Request-Id" not in resp.headers:
            resp.headers["X-Cortex-Request-Id"] = request_id
        if "X-Request-Id" not in resp.headers:
            resp.headers["X-Request-Id"] = request_id or uuid.uuid4().hex
        # Provider chosen by smart routing (only set for routed requests).
        prov = getattr(request.state, "upstream_provider", None)
        if "X-Cortex-Provider" not in resp.headers and prov:
            resp.headers["X-Cortex-Provider"] = prov
        lat = getattr(request.state, "upstream_latency_ms", None)
        if "X-Cortex-Latency-Ms" not in resp.headers and lat:
            resp.headers["X-Cortex-Latency-Ms"] = str(int(lat))

        # Section 5: set security headers on every response.
        for k, v in _SECURITY_HEADERS.items():
            if k not in resp.headers:
                resp.headers[k] = v
        # Strip server/framework identity headers.
        for k in _IDENTITY_HEADERS:
            try:
                del resp.headers[k]  # MutableHeaders: no .pop(), use __delitem__
            except (KeyError, AttributeError):
                pass

        # Sign buffered JSON responses: SHA256(request_id + body).
        if isinstance(resp, StreamingResponse):
            return resp
        body = getattr(resp, "body", b"")
        if isinstance(body, (bytes, bytearray, memoryview)):
            payload = f"{request_id}".encode() + bytes(body)
            resp.headers["X-Cortex-Signature"] = sign_payload(payload)
        return resp