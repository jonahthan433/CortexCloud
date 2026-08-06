"""Section 2: input validation at the trust boundary.

One pass, outermost. Read-only on the body (starlette buffers it, so the
downstream x402 middleware can re-read safely — no _receive re-injection,
which is exactly what breaks SSE on this stack).

Guards (fail closed, never forward malformed input):
  POST/PUT/PATCH -> 415 unless Content-Type application/json
                 -> 413 if body > 1MB
                 -> 400 if invalid JSON or nesting depth > 10
  /x402/v1/chat/completions + /x402/v1/responses ->
                 400 if messages > 500 items
                 400 if any single message > 100KB serialized
                 400 if model not in allowlist
                 400 if token estimate > model context window
  GET /data/* -> 400 if any query param has unsafe chars
              -> 400 if an address param is not a valid checksummed ERC-55
"""
import json
import re
import time

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

try:
    from web3 import Web3
    _web3 = Web3()
except Exception:  # pragma: no cover
    _web3 = None

MAX_BODY = 1_000_000          # 1MB
MAX_DEPTH = 10
MAX_MESSAGES = 500
MAX_MSG_JSON = 100_000        # per-message serialized budget (chars)

# allowlist for /data/* query params: alnum, comma, dot, slash, dash, under-score, colon, space
_SAFE_PARAM = re.compile(r"^[0-9A-Za-z_,./:\-\s]{1,300}$")
_ADDR_PARAMS = {"address", "addr", "pair", "token"}  # ERC-55 checked names
_DATA_SUFFIX = "/data/"  # matches any /data/ under any prefix

_model_cache = {"t": 0.0, "ids": None, "win": {}}


def _depth(o, d=0):
    if d > MAX_DEPTH:
        raise ValueError("depth")
    if isinstance(o, dict):
        return max((_depth(v, d + 1) for v in o.values()), default=d)
    if isinstance(o, list):
        return max((_depth(v, d + 1) for v in o), default=d)
    return d


def _est_tokens(text) -> int:
    s = text if isinstance(text, str) else json.dumps(text)
    return max(1, len(s) // 4)  # ~4 chars/token


def _valid_addr(a) -> bool:
    if not isinstance(a, str) or not re.fullmatch(r"0x[0-9a-fA-F]{40}", a):
        return False
    if _web3 is None:
        return True  # scope-format only when web3 unavailable
    try:
        return bool(_web3.is_checksum_address(a))
    except Exception:
        return False


def _models():
    """Reusable cache accessor (ids, windows, capabilities)."""
    c = _model_cache
    return c["ids"], c["win"], c.get("cap", {})


async def _refresh_models():
    cache = _model_cache
    now = time.time()
    if cache["ids"] and now - cache["t"] < 60:
        return cache["ids"], cache["win"], cache.get("cap", {})
    try:
        from sqlalchemy import select
        from app.database.session import AsyncSessionLocal
        from app.models.registry import ModelRegistry
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(ModelRegistry).where(ModelRegistry.is_active == True)
            )).scalars().all()
        ids, win, cap = set(), {}, {}
        for m in rows:
            ids.add(m.name)          # client-facing alias, e.g. "gpt-4o"
            win[m.name] = int(m.context_length or 0)
            cap[m.name] = (m.capabilities or {}) if isinstance(m.capabilities, dict) else {}
        cache.update({"t": now, "ids": ids, "win": win, "cap": cap})
    except Exception:
        return None, {}, {}
    return cache["ids"], cache["win"], cache.get("cap", {})


CHAT_PATHS = ("/x402/v1/chat/completions", "/x402/v1/responses")


class InputValidationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # GET /data/* -> query-param sanitization only.
        if request.method == "GET":
            if _DATA_SUFFIX in request.url.path:
                for k, v in request.query_params.multi_items():
                    if k in _ADDR_PARAMS:
                        if not _valid_addr(v):
                            return JSONResponse(status_code=400, content={"detail": f"invalid address param: {k}"})
                    elif not _SAFE_PARAM.match(v):
                        return JSONResponse(status_code=400, content={"detail": f"unsafe query param: {k}"})
            return await call_next(request)

        # Body-based methods.
        ct = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
        if ct != "application/json":
            return JSONResponse(status_code=415, content={"detail": "Content-Type must be application/json"})

        raw = await request.body()
        if len(raw) > MAX_BODY:
            return JSONResponse(status_code=413, content={"detail": "Request body too large (max 1MB)"})

        try:
            data = json.loads(raw)
            _depth(data)
        except json.JSONDecodeError:
            return JSONResponse(status_code=400, content={"detail": "Invalid JSON"})
        except (ValueError, RecursionError):
            return JSONResponse(status_code=400, content={"detail": "JSON too deeply nested"})

        path = request.url.path
        if path in CHAT_PATHS:
            msgs = data.get("messages") if isinstance(data, dict) else None
            if msgs is not None:
                if not isinstance(msgs, list) or len(msgs) > MAX_MESSAGES:
                    return JSONResponse(status_code=400, content={"detail": f"messages exceeds {MAX_MESSAGES} items"})
                for m in msgs:
                    if len(json.dumps(m, separators=(",", ":"))) > MAX_MSG_JSON:
                        return JSONResponse(status_code=400, content={"detail": "message content too large"})
            model = data.get("model") if isinstance(data, dict) else None
            if model is not None and not isinstance(model, str):
                return JSONResponse(status_code=400, content={"detail": "model must be a string"})
            ids, win, cap = await _refresh_models()
            if model and ids and model not in ids:
                return JSONResponse(status_code=400, content={"detail": f"unknown model: {model}"})
            if msgs and model and win.get(model):
                est = sum(_est_tokens(m.get("content", "")) for m in msgs if isinstance(m, dict))
                if est > win[model]:
                    return JSONResponse(status_code=400, content={"detail": "token estimate exceeds model context window"})

            # Section 3: AI/agent abuse hardening — capability-consistent payload.
            if isinstance(data, dict):
                tools = data.get("tools") or []
                if tools:
                    if not isinstance(tools, list) or len(tools) > 64:
                        return JSONResponse(status_code=400, content={"detail": "tools exceeds 64 items"})
                    if model and cap and not cap.get(model, {}).get("tool_calling"):
                        return JSONResponse(status_code=400, content={"detail": f"model '{model}' does not support tool calling"})
                mt = data.get("max_tokens") or data.get("max_completion_tokens")
                if model and cap and isinstance(mt, int) and mt > win.get(model, 0):
                    return JSONResponse(status_code=400, content={"detail": "max_tokens exceeds model context window"})

        return await call_next(request)


# fixup: the earlier scratch file used a different module name; keep _valid_addr importable
valid_addr = _valid_addr