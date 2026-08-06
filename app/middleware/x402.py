import base64
import json
import logging
import time

import httpx
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import settings
from app.core.cache import cache_proof, nonce_seen, proof_is_cached, rate_allow, get_redis
from app.core.http import shared_client
from app.middleware.audit import audit, alert
from app.core.reqlog import CACHE_HITS, LATENCY, get_req
from app.x402.pricing import ROUTE_PRICING, ROUTE_DESCRIPTIONS, usd_to_usdc_atomic

logger = logging.getLogger("cortexcloud.middleware.x402")


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
        await alert(get_redis(), "rate_limit", 300, 200, "rate_limit_dos", payer=payer)
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

# GET routes take query params instead of a JSON body.
QUERY_ROUTES = {
    "/x402/v1/data/prices",
    "/x402/v1/data/coins/search",
    "/x402/v1/data/dex/search",
    "/x402/v1/data/dex/pairs",
    "/x402/v1/data/base/balance",
    "/x402/v1/data/base/token-balance",
    "/x402/v1/data/base/nonce",
    "/x402/v1/defillama/chains",
    "/x402/v1/defillama/protocols",
    "/x402/v1/defillama/protocol",
    "/x402/v1/defillama/prices",
    "/x402/v1/defillama/yields",
    "/x402/v1/crypto/list",
    "/x402/v1/crypto/price",
    "/x402/v1/crypto/history",
    "/x402/v1/fx/list",
    "/x402/v1/fx/price",
    "/x402/v1/fx/history",
    "/x402/v1/data/news",
    "/x402/v1/data/eth/balance",
    "/x402/v1/data/solana/balance",
    "/x402/v1/data/defi/yields",
    "/x402/v1/data/gas",
}

# Per-route request schemas, surfaced in the 402 challenge via the bazaar
# extension. x402scan's validator hard-errors SCHEMA_INPUT_MISSING without one.
INPUT_SCHEMAS = {
    "/x402/v1/chat/completions": {
        "type": "object",
        "properties": {
            "model": {"type": "string", "description": "Model id, e.g. gemini/gemini-2.0-flash"},
            "messages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string", "enum": ["system", "user", "assistant", "tool"]},
                        "content": {"type": "string"},
                    },
                    "required": ["role", "content"],
                },
            },
            "stream": {"type": "boolean"},
            "temperature": {"type": "number"},
            "max_tokens": {"type": "integer"},
        },
        "required": ["model", "messages"],
    },
    "/x402/v1/responses": {
        "type": "object",
        "properties": {
            "model": {"type": "string"},
            "input": {"type": "string"},
            "instructions": {"type": "string"},
            "stream": {"type": "boolean"},
        },
        "required": ["model", "input"],
    },
    "/x402/v1/embeddings": {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "Text to embed"},
            "model": {"type": "string", "description": "Embedding model id, e.g. gemini/text-embedding-004"},
        },
        "required": ["input", "model"],
    },
    "/x402/v1/images/generations": {
        "type": "object",
        "properties": {
            "model": {"type": "string"},
            "prompt": {"type": "string"},
            "n": {"type": "integer"},
            "size": {"type": "string"},
            "response_format": {"type": "string"},
        },
        "required": ["prompt"],
    },
    "/x402/v1/images/image2image": {
        "type": "object",
        "properties": {"model": {"type": "string"}, "image": {"type": "string"}, "prompt": {"type": "string"}},
        "required": ["image", "prompt"],
    },
    "/x402/v1/audio/speech": {
        "type": "object",
        "properties": {"model": {"type": "string"}, "input": {"type": "string"}, "voice": {"type": "string"}},
        "required": ["model", "input"],
    },
    "/x402/v1/audio/transcriptions": {
        "type": "object",
        "properties": {"model": {"type": "string"}, "audio_b64": {"type": "string"}, "mime": {"type": "string"}},
        "required": ["audio_b64"],
    },
    "/x402/v1/messages": {
        "type": "object",
        "properties": {
            "model": {"type": "string"},
            "messages": {"type": "array", "items": {"type": "object"}},
            "max_tokens": {"type": "integer"},
        },
        "required": ["model", "messages"],
    },
    "/x402/v1/videos/generations": {
        "type": "object",
        "properties": {"model": {"type": "string"}, "prompt": {"type": "string"}},
        "required": ["model", "prompt"],
    },
    "/x402/v1/rpc/ethereum": {
        "type": "object",
        "properties": {"method": {"type": "string"}, "params": {"type": "array"}, "id": {"type": "integer"}},
        "required": ["method"],
    },
    "/x402/v1/search": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "numResults": {"type": "integer", "default": 10},
            "useAutoprompt": {"type": "boolean"},
            "type": {"type": "string", "enum": ["neural", "keyword"]},
            "includeDomains": {"type": "array", "items": {"type": "string"}},
            "excludeDomains": {"type": "array", "items": {"type": "string"}},
            "startPublishedDate": {"type": "string"},
            "endPublishedDate": {"type": "string"},
        },
        "required": ["query"],
    },
    "/x402/v1/search/contents": {
        "type": "object",
        "properties": {"ids": {"type": "array", "items": {"type": "string"}}, "text": {"type": "boolean"}},
        "required": ["ids"],
    },
    # ---- GET routes (query params) ----
    "/x402/v1/data/prices": {
        "type": "object",
        "properties": {"ids": {"type": "string", "description": "Comma-separated coin ids, e.g. bitcoin,ethereum"}, "vs": {"type": "string", "default": "usd"}},
        "required": ["ids"],
    },
    "/x402/v1/data/coins/search": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
    "/x402/v1/data/dex/search": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]},
    "/x402/v1/data/dex/pairs": {
        "type": "object",
        "properties": {"chain": {"type": "string"}, "pair": {"type": "string"}},
        "required": ["chain", "pair"],
    },
    "/x402/v1/data/base/balance": {"type": "object", "properties": {"address": {"type": "string"}}, "required": ["address"]},
    "/x402/v1/data/base/token-balance": {
        "type": "object",
        "properties": {"address": {"type": "string"}, "token": {"type": "string", "description": "Token address or symbol (usdc, weth, dai, usdt)"}},
        "required": ["address", "token"],
    },
    "/x402/v1/data/base/nonce": {"type": "object", "properties": {"address": {"type": "string"}}, "required": ["address"]},
    "/x402/v1/defillama/chains": {"type": "object", "properties": {}},
    "/x402/v1/defillama/protocols": {"type": "object", "properties": {}},
    "/x402/v1/defillama/protocol": {"type": "object", "properties": {"slug": {"type": "string"}}, "required": ["slug"]},
    "/x402/v1/defillama/prices": {"type": "object", "properties": {"coins": {"type": "string"}}, "required": ["coins"]},
    "/x402/v1/defillama/yields": {"type": "object", "properties": {}},
    "/x402/v1/crypto/list": {"type": "object", "properties": {}},
    "/x402/v1/crypto/price": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "vs": {"type": "string", "default": "usd"}},
        "required": ["id"],
    },
    "/x402/v1/crypto/history": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "vs": {"type": "string", "default": "usd"}, "days": {"type": "string", "default": "30"}},
        "required": ["id"],
    },
    "/x402/v1/fx/list": {"type": "object", "properties": {}},
    "/x402/v1/fx/price": {
        "type": "object",
        "properties": {"base": {"type": "string", "default": "EUR"}, "quote": {"type": "string", "default": "USD"}},
    },
    "/x402/v1/fx/history": {
        "type": "object",
        "properties": {"base": {"type": "string", "default": "EUR"}, "quote": {"type": "string", "default": "USD"}, "start": {"type": "string"}, "end": {"type": "string"}},
        "required": ["start", "end"],
    },
    # ---- S4: data marketplace (query params) ----
    "/x402/v1/data/news": {
        "type": "object",
        "properties": {"q": {"type": "string", "description": "Search/news query, e.g. AI funding"}, "limit": {"type": "integer", "default": 5, "description": "Max articles to return"}},
        "required": ["q"],
    },
    "/x402/v1/data/eth/balance": {
        "type": "object",
        "properties": {"address": {"type": "string", "description": "Ethereum address to query balance for"}},
        "required": ["address"],
    },
    "/x402/v1/data/solana/balance": {
        "type": "object",
        "properties": {"address": {"type": "string", "description": "Solana address to query balance for"}},
        "required": ["address"],
    },
    "/x402/v1/data/defi/yields": {"type": "object", "properties": {}},
    "/x402/v1/data/gas": {
        "type": "object",
        "properties": {"chain": {"type": "string", "default": "base", "description": "Chain id to fetch gas price for (base|ethereum|arbitrum|polygon)"}},
    },
    # ---- S5: agent-native ----
    "/x402/v1/jobs": {
        "type": "object",
        "properties": {
            "endpoint": {"type": "string", "description": "Relative x402 endpoint to call asynchronously, e.g. /x402/v1/search"},
            "method": {"type": "string", "default": "POST"},
            "payload": {"type": "object", "description": "Request body to send to the endpoint"},
        },
        "required": ["endpoint"],
    },
    "/x402/v1/embeddings/batch": {
        "type": "object",
        "properties": {"input": {"type": "array", "items": {"type": "string"}, "description": "List of texts (max 100) to embed"}, "model": {"type": "string", "description": "Embedding model id"}},
        "required": ["input", "model"],
    },
}

# Sample response objects for the bazaar output schema (WARN-level if absent).
# S1: per-route example request bodies so the facilitator's discovery-extension
# validation (example must satisfy the input schema) passes for every route.
INPUT_EXAMPLES = {
    "/x402/v1/chat/completions": {"model": "gemini-2.0-flash", "messages": [{"role": "user", "content": "Hello"}]},
    "/x402/v1/responses": {"model": "gemini-2.0-flash", "input": "Hello"},
    "/x402/v1/embeddings": {"model": "gemini-text-embedding-004", "input": "Hello world"},
    "/x402/v1/images/generations": {"prompt": "a red cube on a white background"},
    "/x402/v1/images/image2image": {"image": "<base64>", "prompt": "make it blue"},
    "/x402/v1/audio/speech": {"model": "gpt-4o-mini-tts", "input": "Hello from CortexCloud", "voice": "alloy"},
    "/x402/v1/audio/transcriptions": {"audio_b64": "<base64>", "mime": "audio/wav"},
    "/x402/v1/messages": {"model": "claude-sonnet-4-6", "messages": [{"role": "user", "content": "Hello"}]},
    "/x402/v1/videos/generations": {"model": "grok-video-2", "prompt": "a cat walking"},
    "/x402/v1/rpc/ethereum": {"method": "eth_blockNumber", "params": [], "id": 1},
    "/x402/v1/search": {"query": "latest AI news"},
    "/x402/v1/search/contents": {"ids": ["https://example.com/article"]},
    "/x402/v1/data/news": {"q": "AI funding"},
    "/x402/v1/data/eth/balance": {"address": "0x..."},
    "/x402/v1/data/solana/balance": {"address": "..."},
    "/x402/v1/data/gas": {"chain": "base"},
    "/x402/v1/jobs": {"endpoint": "/x402/v1/search", "payload": {"query": "latest AI news"}},
    "/x402/v1/embeddings/batch": {"model": "gemini-text-embedding-004", "input": ["Hello", "world"]},
}
OUTPUT_EXAMPLES = {
    "/x402/v1/chat/completions": {"id": "chatcmpl-abc", "object": "chat.completion", "choices": [], "usage": {"prompt_tokens": 0, "completion_tokens": 0}},
    "/x402/v1/responses": {"id": "resp_abc", "object": "response", "output": []},
    "/x402/v1/embeddings": {"id": "emb_abc", "object": "list", "data": [{"object": "embedding", "embedding": [], "index": 0}], "usage": {"prompt_tokens": 0, "total_tokens": 0}},
    "/x402/v1/data/prices": {"bitcoin": {"usd": 67000.0}},
    "/x402/v1/data/coins/search": {"coins": []},
    "/x402/v1/data/dex/search": {"pairs": []},
    "/x402/v1/data/dex/pairs": {"pairs": []},
    "/x402/v1/data/base/balance": {"address": "0x...", "balance": "0", "network": "base"},
    "/x402/v1/data/base/token-balance": {"address": "0x...", "token": "0x...", "network": "base", "raw": "0"},
    "/x402/v1/data/base/nonce": {"address": "0x...", "nonce": 0},
    "/x402/v1/search": {"results": []},
    "/x402/v1/search/contents": {"results": []},
    "/x402/v1/data/news": {"articles": [{"title": "CortexCloud raises", "url": "https://example.com/news"}]},
    "/x402/v1/data/eth/balance": {"address": "0x...", "balance": "1.234", "network": "ethereum"},
    "/x402/v1/data/solana/balance": {"address": "...", "balance": "1.5", "network": "solana"},
    "/x402/v1/data/gas": {"base": {"standard": "0.001", "fast": "0.002"}},
    "/x402/v1/jobs": {"id": "job_abc", "status": "queued"},
    "/x402/v1/embeddings/batch": {"data": [{"index": 0, "object": "embedding", "embedding": []}], "usage": {"prompt_tokens": 0, "total_tokens": 0}},
}


def _input_schema(path: str) -> dict:
    return INPUT_SCHEMAS.get(path, {"type": "object", "properties": {}})


# Cache for model pricing to avoid hitting the database on every request
from functools import lru_cache

@lru_cache(maxsize=1)
def get_model_pricing():
    """Fetch model pricing from the database and return a dict keyed by model ID."""
    try:
        from app.services.models import get_models
        models = get_models()  # Returns list of model objects
        pricing = {}
        for model in models:
            pricing[model.id] = {
                "input_cost_per_1k_tokens": float(model.input_cost_per_1k_tokens),
                "output_cost_per_1k_tokens": float(model.output_cost_per_1k_tokens),
            }
        return pricing
    except Exception as e:
        logger.warning(f"Failed to load model pricing: {e}")
        return {}


class X402Middleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip if x402 is disabled
        if not settings.X402_ENABLED:
            return await call_next(request)

        method = request.method
        path = request.url.path

        # Path-only lookup: any method on a paid path gets the paywall.
        price_str = _PATH_PRICING.get(path)
        if price_str is None or price_str == "$0.00":
            return await call_next(request)

        # Dynamic pricing for token/image endpoints (POST only; else static).
        if method == "POST" and path in ["/x402/v1/chat/completions", "/x402/v1/responses"]:
            try:
                body = await request.body()
                data = json.loads(body)
                model_id = data.get("model")
                if model_id:
                    model_pricing = get_model_pricing()
                    if model_id in model_pricing:
                        info = model_pricing[model_id]
                        base_cost = info['input_cost_per_1k_tokens'] + info['output_cost_per_1k_tokens']
                        marked_up_cost = base_cost * 1.275
                        price_str = f"${max(marked_up_cost, 0.000001):.6f}"
                    else:
                        price_str = price_str
                # Body is cached on the request (Request.body() sets _body);
                # downstream reads it via the _CachedRequest state-3 branch.
                # Do NOT re-inject request._receive here: the closure returns
                # http.request forever, which starlette's wrapped_receive state-1
                # branch rejects, killing SSE streams with
                # "RuntimeError: Unexpected message received: http.request".
            except (json.JSONDecodeError, KeyError, AttributeError, TypeError) as e:
                logger.warning(f"Failed to parse request body for dynamic pricing: {e}")
        elif method == "POST" and path == "/x402/v1/images/generations":
            try:
                body = await request.body()
                data = json.loads(body)
                n = data.get("n", 1)
                # S1: spec price $0.02 per image (was $0.04).
                price_str = f"${n * 0.02:.6f}"
            except (json.JSONDecodeError, KeyError, AttributeError, TypeError) as e:
                logger.warning(f"Failed to parse request body for image generation pricing: {e}")

        required = usd_to_usdc_atomic(price_str)

        # Check for payment headers
        payment_signature = request.headers.get("payment-signature")
        x_payment = request.headers.get("x-payment")
        x_correlation_id = request.headers.get("x-correlation-id")

        if not payment_signature:
            # x402 v2 PaymentRequirements challenge (validated by x402scan's
            # validatePaymentRequiredDetailed: x402Version, accepts[] fields,
            # resource object, bazaar input schema all mandatory).
            schema_input = _input_schema(path)
            input_key = "queryParams" if path in QUERY_ROUTES else "body"
            challenge = {
                "x402Version": 2,
                "resource": {
                    "url": settings.X402_RESOURCE_BASE.rstrip("/") + path,
                    "description": _PATH_DESCRIPTIONS.get(path, "Access to this resource"),
                    "mimeType": "application/json",
                },
                "accepts": [
                    {
                        "scheme": "exact",
                        "network": settings.X402_NETWORK,
                        "asset": USDC_ON_BASE,
                        "amount": required,
                        "payTo": settings.WALLET_ADDRESS,
                        "maxTimeoutSeconds": 60,
                        # EIP-712 domain for the asset — client requires extra.name/version
                        # to sign the EIP-3009 authorization (matches DEFAULT_STABLECOINS
                        # "USD Coin" / "2" on eip155:8453).
                        # ponytail: hardcoded to Base USDC; make a per-asset map when
                        # more assets are accepted.
                        "extra": {"name": "USD Coin", "version": "2"},
                    }
                ],
                "extensions": {
                    "bazaar": {
                        "discoverable": True,
                        "info": {
                            "input": {
                                "type": "http",
                                "method": method,
                                "bodyType": "json",
                                "body": INPUT_EXAMPLES.get(path, {"model": "gemini-2.0-flash", "messages": [{"role": "user", "content": "Hello"}]}),
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
            return JSONResponse(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                content=challenge,
                headers={
                    "Accept": "application/json",
                    # x402 v2 contract = JSON body + payment-required header.
                    # A WWW-Authenticate header without an MPP `Payment ...`
                    # challenge trips the audit's unconditional MPP check
                    # ("WWW-Authenticate header contains no Payment challenges").
                    # x-payment-protocol keeps protocol detection at ["x402"].
                    "x-payment-protocol": "x402",
                    # @agentcash/discovery parses v2 challenges ONLY from this
                    # base64 header; its body parser is v1-only. Without it the
                    # probe drops the challenge -> "No valid x402 response found".
                    "payment-required": base64.b64encode(json.dumps(challenge).encode()).decode(),
                },
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
            "resource": settings.X402_RESOURCE_BASE.rstrip("/") + path,
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
            await alert(get_redis(), "proof_reject", 60, 10, "proof_rejected_alert",
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
    
        # Payment verified and settled, proceed to request
        limited = await _rate_limit(request)
        if limited:
            return limited
        response = await call_next(request)
        success_payload = json.dumps({"success": True, "details": settle_data})
        response.headers["X-PAYMENT-RESPONSE"] = base64.b64encode(success_payload.encode()).decode()
        _log_request(request, response, request.state.x402_start)
        return response
