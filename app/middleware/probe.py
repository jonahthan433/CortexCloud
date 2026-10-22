"""Probe-friendly middleware: x402scan crawls every route with HEAD/OPTIONS
(method-aware status capture). FastAPI GET routes 405 on those, failing
discovery for non-paid endpoints. Rewrite HEAD->GET (then strip body) and
answer OPTIONS, whole app.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class ProbeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method
        if method in ("HEAD", "OPTIONS"):
            # Re-drive as GET: mutate scope in place (BaseHTTPMiddleware
            # forwards the same request object to call_next).
            request.scope["method"] = "GET"
            try:
                resp = await call_next(request)
            except Exception:
                return Response(status_code=204)
            if method == "HEAD":
                # H2: strip body-describing headers before answering with an
                # empty body. Copying the GET response's Content-Length onto
                # an empty body made uvicorn raise "Response content shorter
                # than Content-Length" and abort the connection on every HEAD
                # to a GET route without a payment header.
                _drop = {"content-length", "content-encoding", "transfer-encoding"}
                headers = {k: v for k, v in resp.headers.items() if k.lower() not in _drop}
                return Response(status_code=resp.status_code,
                                headers=headers, content=b"")
            return Response(status_code=200,
                            headers={"allow": "GET,POST,PUT,PATCH,DELETE,HEAD,OPTIONS"},
                            content=b"")
        return await call_next(request)