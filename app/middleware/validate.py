"""Trust-boundary input validation: content-type, size, JSON depth.

Generic guards for the whole surface; the optimization schemas
(ProblemInput) do domain validation in the API layer. Audit every
rejection (security log), fail fast with a 4xx, never touch the body
semantics beyond what's needed to size-limit it.
"""

import json
import re
import time

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.middleware.audit import audit

MAX_BODY = 1_000_000   # 1MB max JSON body
MAX_DEPTH = 24         # nested JSON depth
# base58 alphabet (Bitcoin/Solana), no 0OIl — kept for address-param guards
_BASE58 = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

try:
    from web3 import Web3

    _web3 = Web3()
except Exception:  # noqa: BLE001
    _web3 = None


# ponytail: base58 branch is permissive (no checksum) — Solana addresses have no
# EIP-55 equivalent. Sufficient for a sanity guard; swap for on-chain lookup only
# if callers start depending on it as a hard filter.
def _valid_addr(a) -> bool:
    if not isinstance(a, str):
        return False
    if re.fullmatch(r"0x[0-9a-fA-F]{40}", a):
        if _web3 is None:
            return True  # scope-format only when web3 unavailable
        try:
            return bool(_web3.is_checksum_address(a))
        except Exception:
            return False
    return bool(_BASE58.fullmatch(a))


def _depth(v, d=0) -> None:
    if d > MAX_DEPTH:
        raise ValueError("too deep")
    if isinstance(v, dict):
        for x in v.values():
            _depth(x, d + 1)
    elif isinstance(v, list):
        for x in v:
            _depth(x, d + 1)


class InputValidationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        ip = (request.client.host if request.client else "?")

        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return await call_next(request)

        ct = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
        if ct == "application/x-www-form-urlencoded" or ct.startswith("multipart/form-data"):
            return await call_next(request)
        if ct != "application/json":
            audit("rejected", kind="bad_content_type", ip=ip, path=request.url.path)
            return JSONResponse(status_code=415, content={"detail": "Content-Type must be application/json"})

        raw = await request.body()
        if len(raw) > MAX_BODY:
            audit("rejected", kind="oversize", ip=ip, path=request.url.path, bytes=len(raw))
            return JSONResponse(status_code=413, content={"detail": "Request body too large (max 1MB)"})

        try:
            data = json.loads(raw)
            _depth(data)
        except json.JSONDecodeError:
            audit("rejected", kind="bad_json", ip=ip, path=request.url.path)
            return JSONResponse(status_code=400, content={"detail": "Invalid JSON"})
        except (ValueError, RecursionError):
            audit("rejected", kind="json_depth", ip=ip, path=request.url.path)
            return JSONResponse(status_code=400, content={"detail": "JSON too deeply nested"})

        # /v1/optimize: the middleware re-checks content freshness, Pydantic
        # validates the domain model. Nothing else to gate at this layer.
        return await call_next(request)


# module-level alias for tests/legacy callers
valid_addr = _valid_addr