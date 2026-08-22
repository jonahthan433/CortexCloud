import base64
import hashlib
import hmac
import json
import logging
import time

import httpx
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import settings
from app.core.cache import cache_proof, proof_is_cached, rate_allow
from app.core.http import shared_client
from app.core.nonce import nonce_seen
from app.middleware.audit import audit, alert
from app.core.reqlog import CACHE_HITS, LATENCY, get_req
from app.x402.pricing import ROUTE_PRICING, ROUTE_DESCRIPTIONS, usd_to_usdc_atomic, price_for_mode

logger = logging.getLogger("cortexcloud.middleware.x402")


def _resource_url(request, path: str) -> str:
    """Resource URL for the x402 challenge.

    Prefer the URL the caller actually hit (request.scheme+host) so the
    signed payment matches the endpoint an agent is calling — correct for
    both the public domain and any staging host. Fall back to the configured
    X402_RESOURCE_BASE when the request context is unavailable.
    """
    try:
        if getattr(request, "url", None) is not None:
            # Honour upstream TLS termination (Cloudflare sets X-Forwarded-Proto).
            scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
            base = f"{scheme}://{request.url.netloc}"
            return base.rstrip("/") + path
    except Exception:
        pass
    return settings.X402_RESOURCE_BASE.rstrip("/") + path


def _log_request(request, response, start_ns: float) -> None:
    """S6: one JSON log line per paid request + latency histogram."""
    ctx = get_req()
    total_ms = (time.perf_counter() - start_ns) * 1000.0
    model = None
    try:
        model = (json.loads(getattr(request.state, "x402_body", "{}") or "{}")).get("model")
    except Exception:
        pass
    logger.info(json.dumps({
        "event": "request",
        "endpoint": request.url.path,
        "model": model,
        "upstream_provider": getattr(request.state, "upstream_provider", None) or ctx.get("upstream_provider"),
        "payment_verified_from_cache": getattr(request.state, "x402_cache", False),
        "upstream_latency_ms": getattr(request.state, "upstream_latency_ms", None) or ctx.get("upstream_latency_ms"),
        "total_latency_ms": int(total_ms),
        "status_code": response.status_code,
        "payer_address": getattr(request.state, "x402_payer", None),
    }))
    LATENCY.labels(request.url.path).observe(total_ms / 1000.0)


async def _rate_limit(request) -> JSONResponse | None:
    """S5: 60 req/min per payer wallet; 429 + Retry-After when exceeded."""
    payer = getattr(request.state, "x402_payer", None)
    if not payer:
        return None
    count = await rate_allow(payer)
    if count > settings.X402_RATE_LIMIT:
        log = json.dumps({"event": "rate_limited", "payer": payer, "count": count})
        audit("rate_limited", payer=payer, count=count)
        await alert("rate_limit", 300, 200, "rate_limit_dos", payer=payer)
        logger.warning(log)
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"error": "rate limit exceeded", "retry_after": 60},
            headers={"Retry-After": "60"},
        )
    return None

try:  # cdp-sdk present on CT; absent elsewhere -> facilitator auth disabled
    from cdp.x402.x402 import create_cdp_auth_headers as _cdp_auth_headers_fn
except Exception:
    _cdp_auth_headers_fn = None


def _cdp_auth_headers() -> dict:
    """Per-endpoint CDP facilitator auth ({verify, settle, supported, list}).
    Empty dict when the SDK or key material is unavailable."""
    if not _cdp_auth_headers_fn:
        return {}
    kid = getattr(settings, "X402_FACILITATOR_API_KEY_ID", None)
    secret = getattr(settings, "X402_FACILITATOR_API_KEY_SECRET", None)
    if not kid or not secret:
        return {}
    try:
        return _cdp_auth_headers_fn(kid, secret)()
    except Exception as e:
        logger.warning(f"cdp auth header generation failed: {e}")
        return {}

# x402scan probes HEAD/GET/POST/OPTIONS (plus a HEAD status-capture). Match
# paid routes by PATH only: ANY method on a paid path -> 402. Method-scoped
# keys ("GET /x402/v1/data/prices") let other methods fall through to FastAPI
# routing, which 405s them -> "No valid x402 response found (HTTP 405)".
_PATH_PRICING = {
    (k.split(" ", 1)[1] if " " in k else k): v for k, v in ROUTE_PRICING.items()
}
_PATH_DESCRIPTIONS = {
    (k.split(" ", 1)[1] if " " in k else k): v for k, v in ROUTE_DESCRIPTIONS.items()
}

# USDC on Base mainnet (canonical contract, 6 decimals).
USDC_ON_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

# ---- MPP (Machine Payments Protocol) via pympp (official Python SDK) ----
# Server side needs NO private key: pympp verifies credentials on-chain via
# Tempo RPC; recipient is our public WALLET_ADDRESS. MPP_SECRET_KEY is the
# HMAC secret for stateless challenge IDs (persist across restarts).
try:
    from mpp import Challenge as _MppChallenge
    from mpp.server import Mpp as _Mpp
    from mpp.methods.tempo import ChargeIntent as _ChargeIntent, tempo as _tempo
    from mpp.stores.sqlite import SQLiteStore as _SQLiteStore
    _MPP_AVAILABLE = True
except Exception:
    _MPP_AVAILABLE = False

# Tempo USDC (TIP-20, chain 4217) — canonical address from pympp defaults.
TEMPO_USDC = "0x20C000000000000000000000b9537d11c60E8b50"

_mpp_instance = None
_mpp_init_attempted = False


async def _get_mpp():
    """Lazily build the Mpp server singleton. None when disabled/unconfigured."""
    global _mpp_instance, _mpp_init_attempted
    if _mpp_init_attempted:
        return _mpp_instance
    _mpp_init_attempted = True
    if not (_MPP_AVAILABLE and settings.MPP_ENABLED and settings.MPP_SECRET_KEY and settings.WALLET_ADDRESS):
        return None
    try:
        store = await _SQLiteStore.create(settings.MPP_STORE_PATH)
        _mpp_instance = _Mpp.create(
            method=_tempo(
                currency=TEMPO_USDC,
                intents={"charge": _ChargeIntent()},
                recipient=settings.WALLET_ADDRESS,
            ),
            realm=settings.MPP_REALM,
            secret_key=settings.MPP_SECRET_KEY,
            store=store,
        )
        logger.info(f"MPP enabled: realm={settings.MPP_REALM} recipient={settings.WALLET_ADDRESS}")
    except Exception as e:
        logger.error(f"MPP init failed (MPP disabled): {e}")
        _mpp_instance = None
    return _mpp_instance


async def _record_payment(path: str, payer: str, amount_atomic: int, body_str: str | None,
                          nonce: str | None = None, provider_cost_usd: float | None = None,
                          margin_usd: float | None = None, category: str | None = None) -> None:
    """Record a settled payment in PostgreSQL. Telemetry never blocks a payment.
    AI/Research routes pass provider_cost/margin/category (read from
    request.state at the call site) so the usage ledger reports CortexCloud
    revenue + margin per call. Cost is never hardcoded — it is computed in the
    route from the advertised rate table."""
    try:
        if not payer:
            return
        from app.database.session import AsyncSessionLocal
        from app.models import Payment

        mode = n_vars = None
        try:
            _b = json.loads(body_str or "{}")
            mode = _b.get("mode")
            n_vars = (_b.get("problem") or {}).get("n")
        except Exception:
            pass
        if margin_usd is None and provider_cost_usd is not None:
            margin_usd = round(int(amount_atomic) / 1_000_000 - provider_cost_usd, 6)
        async with AsyncSessionLocal() as _db:
            _db.add(
                Payment(
                    endpoint=path,
                    payer=payer,
                    amount_atomic=int(amount_atomic),
                    amount_usd=int(amount_atomic) / 1_000_000,
                    mode=mode,
                    n_vars=n_vars,
                    nonce=nonce,
                    status="settled",
                    provider_cost_usd=round(provider_cost_usd, 6) if provider_cost_usd is not None else None,
                    margin_usd=margin_usd,
                    category=category,
                )
            )
            await _db.commit()
    except Exception:
        pass

# GET routes take query params instead of a JSON body.
# The only paid route is POST /v1/optimize (body), so this stays empty.
QUERY_ROUTES: set[str] = set()

# Per-route request schemas, surfaced in the 402 challenge via the bazaar
# extension. x402scan's validator hard-errors SCHEMA_INPUT_MISSING without one.
INPUT_SCHEMAS = {
    "/v1/optimize": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["auto", "classical", "hybrid", "quantum"],
                "default": "auto",
            },
            "problem": {
                "type": "object",
                "properties": {
                    "problem_type": {"type": "string", "enum": ["qubo", "ising"], "default": "qubo"},
                    "n": {"type": "integer", "minimum": 2, "maximum": 5000},
                    "data": {
                        "type": "object",
                        "properties": {
                            "linear": {"type": "array", "items": {"type": "number"}},
                            "quadratic": {
                                "type": "object",
                                "additionalProperties": {"type": "number"},
                                "description": "\"i,j\" -> coefficient",
                            },
                        },
                    },
                },
                "required": ["n", "data"],
            },
        },
        "required": ["problem"],
    },
}

# Sample response objects for the bazaar output schema (WARN-level if absent).
# S1: per-route example request bodies so the facilitator's discovery-extension
# validation (example must satisfy the input schema) passes for every route.
INPUT_EXAMPLES = {
    "/v1/optimize": {
        "mode": "auto",
        "problem": {
            "problem_type": "qubo",
            "n": 4,
            "data": {
                "linear": [1.0, -2.0, 3.0, -4.0],
                "quadratic": {"0,1": -1.5, "1,2": 0.5, "2,3": -2.0},
            },
        },
    },
}
OUTPUT_EXAMPLES = {
    "/v1/optimize": {
        "job_id": "3f5c2e6a-9a0b-4c8d-9e7f-1a2b3c4d5e6f",
        "status": "queued",
        "mode": "auto",
        "price_usd": 0.05,
        "poll": "/v1/jobs/3f5c2e6a-9a0b-4c8d-9e7f-1a2b3c4d5e6f",
    },
    "/v1/ai/chat": {
        "id": "chatcmpl-...", "model": "openrouter/gemini-2.5-flash",
        "choices": [{"message": {"role": "assistant", "content": "..."}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 48}, "price_usd": 0.0082,
    },
    "/v1/ai/embed": {"model": "openrouter/google/text-embedding-004", "data": [{"embedding": [0.01, 0.02, -0.03]}], "price_usd": 0.0001},
    "/v1/ai/transcribe": {"text": "...", "price_usd": 0.002},
    "/v1/research/search": {"query": "quantum annealing", "results": [{"title": "...", "url": "...", "source": "..."}], "price_usd": 0.006},
    "/v1/research/answer": {"query": "...", "sources": [{"title": "...", "url": "..."}], "price_usd": 0.012},
}

# Per-route request schemas for the 402 challenge bazaar extension + the
# money-path validation guard. Each must satisfy its own example (x402scan
# hard-errors SCHEMA_INPUT_MISSING / example-must-satisfy-schema).
INPUT_SCHEMAS = {
    **INPUT_SCHEMAS,
    "/v1/ai/chat": {
        "type": "object",
        "properties": {
            "messages": {"type": "array", "items": {"type": "object"}, "minItems": 1},
            "model": {"type": "string", "enum": ["gemini-2.5-flash", "gemini-2.0-flash", "gpt-4o-mini"], "default": "gemini-2.5-flash"},
            "max_tokens": {"type": "integer", "minimum": 1, "maximum": 8192, "default": 512},
            "temperature": {"type": "number", "minimum": 0.0, "maximum": 2.0, "default": 0.7},
        },
        "required": ["messages"],
    },
    "/v1/ai/embed": {
        "type": "object",
        "properties": {
            "input": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 128},
            "model": {"type": "string", "default": "text-embedding-004"},
        },
        "required": ["input"],
    },
    "/v1/ai/transcribe": {
        "type": "object",
        "properties": {
            "audio_b64": {"type": "string"},
            "mime": {"type": "string", "default": "audio/wav"},
        },
        "required": ["audio_b64"],
    },
    "/v1/research/search": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 400},
            "count": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
            "freshness": {"type": "string", "default": "pw"},
        },
        "required": ["query"],
    },
    "/v1/research/answer": {
        "type": "object",
        "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 400}},
        "required": ["query"],
    },
}
INPUT_EXAMPLES = {
    **INPUT_EXAMPLES,
    "/v1/ai/chat": {"messages": [{"role": "user", "content": "Summarize quantum annealing in one sentence."}], "model": "gemini-2.5-flash", "max_tokens": 128},
    "/v1/ai/embed": {"input": ["CortexCloud agent-native API"], "model": "text-embedding-004"},
    "/v1/ai/transcribe": {"audio_b64": "UklGRg...", "mime": "audio/wav"},
    "/v1/research/search": {"query": "latest quantum error correction results", "count": 5, "freshness": "pw"},
    "/v1/research/answer": {"query": "What advances in topological qubits happened in 2026?"},
}


def _validate_optimize_body(data) -> list | None:
    """Money-path guard: reject bodies the endpoint would reject, BEFORE
    any x402/MPP settlement. Returns a FastAPI-style 422 detail list."""
    if not isinstance(data, dict):
        return [{"type": "missing", "loc": ["body"], "msg": "Request body must be a JSON object", "input": None}]
    prob = data.get("problem")
    if not isinstance(prob, dict):
        return [{"type": "missing", "loc": ["body", "problem"], "msg": "Field required", "input": None}]
    if prob.get("problem_type") not in ("qubo", "ising"):
        return [{"type": "value_error", "loc": ["body", "problem", "problem_type"],
                 "msg": "problem_type must be 'qubo' or 'ising'", "input": prob.get("problem_type")}]
    if not isinstance(prob.get("n"), int):
        return [{"type": "missing", "loc": ["body", "problem", "n"], "msg": "Field required", "input": None}]
    if not isinstance(prob.get("data"), dict):
        return [{"type": "missing", "loc": ["body", "problem", "data"], "msg": "Field required", "input": None}]
    mode = data.get("mode")
    if mode is not None and mode not in ("auto", "classical", "hybrid", "quantum"):
        return [{"type": "value_error", "loc": ["body", "mode"],
                 "msg": "mode must be one of auto, classical, hybrid, quantum", "input": mode}]
    return None


def _input_schema(path: str) -> dict:
    return INPUT_SCHEMAS.get(path, {"type": "object", "properties": {}})


class X402Middleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Enterprise single-tenant gate: a configured PRIVATE_API_KEY replaces
        # blockchain settlement entirely. Constant-time compare; /health stays
        # open for load-balancer probes.
        if settings.PRIVATE_API_KEY:
            if request.url.path != "/health":
                supplied = request.headers.get("x-api-key", "")
                if not hmac.compare_digest(supplied, settings.PRIVATE_API_KEY):
                    return JSONResponse(status_code=401, content={"error": "invalid or missing API key"})

        # Skip if x402 is disabled
        if not settings.X402_ENABLED:
            return await call_next(request)

        method = request.method
        path = request.url.path

        # Path-only lookup: any method on a paid path gets the paywall.
        price_str = _PATH_PRICING.get(path)
        if price_str is None or price_str == "$0.00":
            return await call_next(request)

        # Feature-flag gate: a disabled category is NEVER billable. Return 503
        # before any payment challenge so agents discover-but-don't-pay a
        # service that is offline (honest disable, matches route behavior).
        if path.startswith("/v1/ai/") and not settings.AI_ENABLED:
            return JSONResponse(status_code=503, content={"error": "ai_disabled", "detail": "AI category is disabled on this instance."})
        if path.startswith("/v1/research/") and not (settings.RESEARCH_ENABLED and settings.BRAVE_API_KEY):
            return JSONResponse(status_code=503, content={"error": "research_disabled", "detail": "Research category is disabled (set RESEARCH_ENABLED + BRAVE_API_KEY)."})

        # Dynamic pricing: read the POST body once (cached on request) for
        # routes whose price depends on the payload. /v1/optimize keys off
        # mode+n; AI routes key off token counts. The body is read ONCE here
        # and reused downstream — never re-inject request._receive (starlette
        # 1.x state machine rejects a second http.request; see SSE comment).
        body_str = None
        if method == "POST":
            try:
                body = await request.body()
                data = json.loads(body) if body else {}
                body_str = body.decode("utf-8", errors="replace") if body else None
            except (json.JSONDecodeError, AttributeError, TypeError) as e:
                logger.warning(f"Failed to parse request body for dynamic pricing: {e}")
                data = {}
            if path == "/v1/optimize":
                price_str = price_for_mode((data.get("mode") or "auto"), n=((data.get("problem") or {}).get("n") if isinstance(data, dict) else None))
            elif path == "/v1/ai/chat":
                from app.x402.pricing import ai_chat_price_usd, AI_PROVIDERS
                _m = (data.get("model") if isinstance(data, dict) else None)
                _in = sum(len(str(m.get("content", ""))) for m in (data.get("messages") or []) if isinstance(m, dict)) // 4 or 1
                _out = int((data.get("max_tokens") if isinstance(data, dict) else None) or 512)
                price_str = f"${ai_chat_price_usd(_m, _in, _out):.6f}"
                request.state.provider_cost_usd = round(AI_PROVIDERS["chat"].estimate_cost(_m, _in, _out).provider_cost_usd, 6)
                request.state.category = "ai"
            elif path == "/v1/ai/embed":
                from app.x402.pricing import ai_embed_price_usd, AI_PROVIDERS
                _in = sum(len(t) // 4 for t in (data.get("input") or []) if isinstance(t, str)) or 1
                price_str = f"${ai_embed_price_usd(_in):.6f}"
                request.state.provider_cost_usd = round(AI_PROVIDERS["embed"].estimate_cost(input_tokens=_in).provider_cost_usd, 6)
                request.state.category = "ai"
            elif path == "/v1/ai/transcribe":
                from app.x402.pricing import ai_transcribe_price_usd, AI_PROVIDERS
                price_str = f"${ai_transcribe_price_usd():.6f}"
                request.state.provider_cost_usd = round(AI_PROVIDERS["transcribe"].estimate_cost().provider_cost_usd, 6)
                request.state.category = "ai"
            elif path == "/v1/research/search":
                from app.x402.pricing import research_price_usd, RESEARCH_PROVIDERS
                price_str = f"${research_price_usd('web'):.6f}"
                request.state.provider_cost_usd = round(RESEARCH_PROVIDERS["search"].estimate_cost("web").provider_cost_usd, 6)
                request.state.category = "research"
            elif path == "/v1/research/answer":
                from app.x402.pricing import research_price_usd, RESEARCH_PROVIDERS
                price_str = f"${research_price_usd('answer'):.6f}"
                request.state.provider_cost_usd = round(RESEARCH_PROVIDERS["answer"].estimate_cost("answer").provider_cost_usd, 6)
                request.state.category = "research"

        required = usd_to_usdc_atomic(price_str)

        # Check for payment headers
        payment_signature = request.headers.get("payment-signature")
        x_payment = request.headers.get("x-payment")
        x_correlation_id = request.headers.get("x-correlation-id")
        mpp = await _get_mpp()
        authorization = request.headers.get("authorization")

        # Money-path guard: never settle a request the endpoint would reject.
        # Validate the paid body BEFORE either settle branch (x402 or MPP).
        _ai_paths = {"/v1/ai/chat", "/v1/ai/embed", "/v1/ai/transcribe"}
        if (path == "/v1/optimize" or path in _ai_paths) and (payment_signature or (mpp and authorization)):
            if path == "/v1/optimize":
                _v_err = _validate_optimize_body(data)
                if _v_err:
                    return JSONResponse(status_code=422, content={"detail": _v_err})
                # Availability pre-check: refuse BEFORE settling when the requested
                # mode has no executable backend (e.g. quantum with all QPUs
                # offline). 409 = retry later or pick another mode.
                from app.solvers.registry import mode_has_available_solver
                _mode = (data.get("mode") or "auto") if isinstance(data, dict) else "auto"
                if not mode_has_available_solver(_mode):
                    return JSONResponse(
                        status_code=409,
                        content={"error": "no available solver for requested mode", "mode": _mode},
                    )
            else:
                # AI routes: reject missing required fields + bad enum BEFORE
                # settling. The full Pydantic check runs in the route after
                # payment; this just stops billing an obviously-invalid body.
                _schema = INPUT_SCHEMAS.get(path, {})
                _req = _schema.get("required", [])
                _bad = [k for k in _req if not isinstance(data, dict) or k not in data or data.get(k) in (None, "", [])]
                if _bad:
                    return JSONResponse(
                        status_code=422,
                        content={"detail": [{"loc": ["body", b], "msg": "field required", "type": "missing"} for b in _bad]},
                    )
                if path == "/v1/ai/chat":
                    _m = data.get("model")
                    if _m is not None and _m not in ("gemini-2.5-flash", "gemini-2.0-flash", "gpt-4o-mini"):
                        return JSONResponse(status_code=422, content={"error": "bad_model", "detail": "model not supported"})

        if not payment_signature:
            if mpp and authorization:
                # MPP credential path: client answered a challenge with
                # `Authorization: <credential>`. pympp verifies on-chain.
                try:
                    result = await mpp.charge(
                        authorization=authorization, amount=price_str.lstrip("$")
                    )
                except Exception as e:
                    logger.warning(f"MPP charge error: {e}")
                    return JSONResponse(
                        status_code=status.HTTP_402_PAYMENT_REQUIRED,
                        content={"error": "Payment verification failed", "details": str(e)},
                    )
                if isinstance(result, _MppChallenge):
                    return JSONResponse(
                        status_code=status.HTTP_402_PAYMENT_REQUIRED,
                        content={"error": "Payment required"},
                        headers={
                            "WWW-Authenticate": result.to_www_authenticate(mpp.realm),
                            "x-payment-protocol": "mpp",
                        },
                    )
                credential, receipt = result
                payer = getattr(credential, "source", None) or ""
                request.state.x402_payer = payer
                request.state.x402_start = time.perf_counter()
                await _record_payment(
                    path, payer, int(required), body_str,
                    provider_cost_usd=getattr(request.state, "provider_cost_usd", None),
                    category=getattr(request.state, "category", None),
                )
                limited = await _rate_limit(request)
                if limited:
                    return limited
                response = await call_next(request)
                success_payload = json.dumps({"success": True, "details": {"protocol": "mpp"}})
                response.headers["X-PAYMENT-RESPONSE"] = base64.b64encode(success_payload.encode()).decode()
                _log_request(request, response, request.state.x402_start)
                return response

            # x402 v2 PaymentRequirements challenge (validated by x402scan's
            # validatePaymentRequiredDetailed: x402Version, accepts[] fields,
            # resource object, bazaar input schema all mandatory).
            schema_input = _input_schema(path)
            input_key = "queryParams" if path in QUERY_ROUTES else "body"
            challenge = {
                "x402Version": 2,
                "resource": {
                "url": _resource_url(request, path),
                    "description": _PATH_DESCRIPTIONS.get(path, "Access to this resource"),
                    "mimeType": "application/json",
                },
                "accepts": [
                    {
                        "scheme": "exact",
                        "network": settings.X402_NETWORK,
                        "asset": USDC_ON_BASE,
                        "amount": str(required),
                        "payTo": settings.WALLET_ADDRESS,
                        "maxTimeoutSeconds": 60,
                        # EIP-712 domain for the asset — client requires extra.name/version
                        # to sign the EIP-3009 authorization (matches DEFAULT_STABLECOINS
                        # "USD Coin" / "2" on eip155:8453).
                        # ponytail: hardcoded to Base USDC; make a per-asset map when
                        # more assets are accepted.
                        "extra": {"name": "USD Coin", "version": "2"},
                    },
                    # ponytail: only advertise a second payee when it exists;
                    # duplicate identical accepts entries fail x402scan L3 validation.
                    *([
                        {
                            "scheme": "exact",
                            "network": settings.X402_NETWORK,
                            "asset": USDC_ON_BASE,
                            "amount": str(required),
                            "payTo": settings.WALLET_ADDRESS_2,
                            "maxTimeoutSeconds": 60,
                            "extra": {"name": "USD Coin", "version": "2"},
                        }
                    ] if settings.WALLET_ADDRESS_2 and settings.WALLET_ADDRESS_2 != settings.WALLET_ADDRESS else []),
                ],
                "extensions": {
                    "bazaar": {
                        "discoverable": True,
                        "info": {
                            "input": {
                                "type": "http",
                                "method": method,
                                "bodyType": "json",
                                "body": INPUT_EXAMPLES.get(path, {"mode": "auto", "problem": {"problem_type": "qubo", "n": 2, "data": {"linear": [0.0, 0.0]}}}),
                            },
                            "output": {
                                "type": "object",
                                "format": "application/json",
                                "example": OUTPUT_EXAMPLES.get(path, {}),
                            },
                        },
                        "schema": {
                            "properties": {
                                "input": {"properties": {input_key: schema_input}},
                                "output": {"properties": {"example": OUTPUT_EXAMPLES.get(path, {})}},
                            }
                        }
                    }
                },
            }
            _headers = {
                "Accept": "application/json",
                # x402 v2 contract = JSON body + payment-required header.
                # x-payment-protocol keeps protocol detection honest when MPP
                # is also advertised.
                "x-payment-protocol": "x402, mpp" if mpp else "x402",
                # @agentcash/discovery parses v2 challenges ONLY from this
                # base64 header; its body parser is v1-only. Without it the
                # probe drops the challenge -> "No valid x402 response found".
                "payment-required": base64.b64encode(json.dumps(challenge).encode()).decode(),
            }
            if mpp:
                try:
                    ch = await mpp.charge(authorization=None, amount=price_str.lstrip("$"))
                    _headers["WWW-Authenticate"] = ch.to_www_authenticate(mpp.realm)
                except Exception as e:
                    logger.warning(f"MPP challenge generation failed: {e}")
            return JSONResponse(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                content=challenge,
                headers=_headers,
            )

        # Payment headers present, verify and settle via CDP facilitator
        facilitator_url = settings.X402_FACILITATOR_URL
        if not facilitator_url:
            logger.error("X402_FACILITATOR_URL not configured")
            return JSONResponse(
                status_code=status.HTTP_502_BAD_GATEWAY,
                content={"error": "Payment processor not configured"},
            )

        # Read body once; re-inject so the route can still read it downstream.
        try:
            body_bytes = await request.body()
        except Exception:
            body_bytes = b""
        # Note: `await request.body()` above already cached the body on the
        # request object (FastAPI caches in request._body), so the route
        # handler re-reads it without another receive() call. We must NOT
        # re-inject request._receive here — starlette 1.x BaseHTTPMiddleware
        # wraps receive in a strict state machine (one http.request only) and
        # a replacement closure makes paid SSE streams die with
        # "RuntimeError: Unexpected message received: http.request".
        body_str = body_bytes.decode("utf-8", errors="replace") if body_bytes else None
        request.state.x402_body = body_str
        request.state.x402_start = time.perf_counter()

        # x402 v2: client sends the whole signed payload in one PAYMENT-SIGNATURE
        # header. CDP facilitator schema = TOP-LEVEL resource/method/headers/body
        # (a {payload: {...}} wrapper is rejected: "property resource is missing").
        validation_body = {
            "resource": _resource_url(request, path),
            "method": method,
            "headers": {
                "payment-signature": payment_signature,
                **( {"x-payment": x_payment} if x_payment else {} ),
                **( {"x-correlation-id": x_correlation_id} if x_correlation_id else {} ),
            },
            "body": body_str,
        }

        # Decode the signed payload once; used for the nonce/payer gates, the
        # proof cache, and the CDP settle envelope below.
        try:
            _sig_payload = json.loads(base64.b64decode(payment_signature).decode())
        except Exception:
            _sig_payload = {}
        _auth0 = (_sig_payload.get("payload") or {}).get("authorization") or {}
        request.state.x402_payer = _auth0.get("from")
        request.state.x402_cache = False

        # S1: payment-proof cache — the same proof verified+settled within the
        # last 60s skips CDP entirely (fast retries/timeouts). Fail-open if
        # Redis is down: cached-only optimizations must never block payments.
        if await proof_is_cached(payment_signature):
            settle_data = {"success": True, "cached": True}
            request.state.x402_cache = True
            CACHE_HITS.inc()
            limited = await _rate_limit(request)
            if limited:
                return limited
            response = await call_next(request)
            success_payload = json.dumps({"success": True, "details": settle_data})
            response.headers["X-PAYMENT-RESPONSE"] = base64.b64encode(success_payload.encode()).decode()
            _log_request(request, response, request.state.x402_start)
            return response

        # S1: nonce dedup — an EIP-3009 nonce may only be used once. TTL tracks
        # validBefore (the x402 validUntil timestamp). Verified BEFORE CDP so a
        # double-spend attempt never reaches the facilitator.
        if _auth0.get("nonce") and await nonce_seen(_auth0["nonce"], _auth0.get("validBefore")):
            audit("nonce_replay", payer=_auth0.get("from") or "?", nonce=_auth0["nonce"])
            logger.warning(f"x402 nonce replay rejected: {_auth0['nonce']}")
            return JSONResponse(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                content={"error": "Payment nonce already used"},
            )

        # S1 (hardening): in-process proof verification — ECDSA signer recovery,
        # amount >= required, chainId==8453, asset==USDC, payTo==our wallet,
        # validBefore expiry window. Fail closed: ANY failure is a 402.
        from app.middleware.payverify import verify_proof
        ok, reason, _auth_verified = verify_proof(payment_signature, price_str, path)
        if not ok:
            ip = request.client.host if request.client else "?"
            audit("proof_rejected", payer=_auth0.get("from") or "?", reason=reason, ip=ip)
            await alert("proof_reject", 60, 10, "proof_rejected_alert",
                        payer=_auth0.get("from") or "", reason=reason, ip=ip)
            logger.warning(json.dumps({"event": "proof_rejected", "payer": _auth0.get("from"), "reason": reason}))
            return JSONResponse(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                content={"error": "Payment verification failed", "details": reason},
            )

        # S2: shared pooled CDP client (2 calls per payment — pooling pays).
        cdp_client = shared_client("cdp", 30.0)
        try:
            cdp_headers = _cdp_auth_headers()
            auth_headers = {"Content-Type": "application/json", **cdp_headers.get("verify", {})}
            validate_res = await cdp_client.post(
                f"{facilitator_url}/validate",
                json=validation_body,
                headers=auth_headers,
            )
            if validate_res.status_code != 200:
                logger.warning(f"x402 validation failed: {validate_res.text}")
                return JSONResponse(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    content={"error": "Payment validation failed", "details": validate_res.text},
                )
            validate_data = validate_res.json()
            if not validate_data.get("valid", validate_data.get("success", False)):
                logger.warning(f"x402 validation unsuccessful: {validate_data}")
                return JSONResponse(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    content={"error": "Payment validation unsuccessful", "details": validate_data},
                )

            # /settle uses the protocol shape, not the /validate envelope:
            # {x402Version, paymentPayload, paymentRequirements}. The v2
            # paymentPayload is the decoded PAYMENT-SIGNATURE header itself.
            _accepted = _sig_payload.get("accepted") or (_sig_payload.get("accepts") or [{}])[0]
            settle_body = {
                "x402Version": _sig_payload.get("x402Version", 2),
                "paymentPayload": _sig_payload,
                "paymentRequirements": {
                    "x402Version": _sig_payload.get("x402Version", 2),
                    **_accepted,  # scheme, network, asset, amount, payTo, maxTimeoutSeconds, extra
                    "resource": _sig_payload.get("resource"),
                    "extensions": _sig_payload.get("extensions"),
                },
            }
            settle_res = await cdp_client.post(
                f"{facilitator_url}/settle",
                json=settle_body,
                headers={"Content-Type": "application/json", **cdp_headers.get("settle", {})},
            )
            if settle_res.status_code != 200:
                logger.warning(f"x402 settlement failed: {settle_res.text}")
                return JSONResponse(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    content={"error": "Payment settlement failed", "details": settle_res.text},
                )
            settle_data = settle_res.json()
            if not settle_data.get("success", False):
                logger.warning(f"x402 settlement unsuccessful: {settle_data}")
                return JSONResponse(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    content={"error": "Payment settlement unsuccessful", "details": settle_data},
                )
        except Exception as e:
            logger.error(f"x402 facilitator communication error: {e}")
            return JSONResponse(
                status_code=status.HTTP_502_BAD_GATEWAY,
                content={"error": "Payment processor communication error"},
            )
    
        # S1: remember this proof so retries within 60s skip CDP.
        await cache_proof(payment_signature)

        # Record the settled payment in PostgreSQL (jobs/payments ledger).
        # Telemetry never blocks a settled payment.
        _payer = getattr(request.state, "x402_payer", None) or (_sig_payload.get("payload") or {}).get("authorization", {}).get("from", "")
        await _record_payment(
            path, _payer, int(required), request.state.x402_body, _auth0.get("nonce"),
            provider_cost_usd=getattr(request.state, "provider_cost_usd", None),
            category=getattr(request.state, "category", None),
        )
    
        # Payment verified and settled, proceed to request
        limited = await _rate_limit(request)
        if limited:
            return limited
        response = await call_next(request)
        success_payload = json.dumps({"success": True, "details": settle_data})
        response.headers["X-PAYMENT-RESPONSE"] = base64.b64encode(success_payload.encode()).decode()
        _log_request(request, response, request.state.x402_start)
        return response
