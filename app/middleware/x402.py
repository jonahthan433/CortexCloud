import base64
import hashlib
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


async def _record_payment(path: str, payer: str, amount_atomic: int, body_str: str | None, nonce: str | None = None) -> None:
    """Record a settled payment in PostgreSQL. Telemetry never blocks a payment."""
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
}


def _input_schema(path: str) -> dict:
    return INPUT_SCHEMAS.get(path, {"type": "object", "properties": {}})


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

        # Dynamic pricing for /v1/optimize: price follows the requested
        # mode (classical 0.05 / hybrid 0.10 / quantum 0.85). Body is read
        # once and cached on the request — downstream routes reuse it.
        # Do NOT re-inject request._receive here (starlette 1.x state
        # machine rejects a second http.request; see SSE comment below).
        body_str = None
        if method == "POST" and path == "/v1/optimize":
            try:
                body = await request.body()
                data = json.loads(body) if body else {}
                body_str = body.decode("utf-8", errors="replace") if body else None
                price_str = price_for_mode((data.get("mode") or "auto"))
            except (json.JSONDecodeError, AttributeError, TypeError) as e:
                logger.warning(f"Failed to parse request body for dynamic pricing: {e}")

        required = usd_to_usdc_atomic(price_str)

        # Check for payment headers
        payment_signature = request.headers.get("payment-signature")
        x_payment = request.headers.get("x-payment")
        x_correlation_id = request.headers.get("x-correlation-id")
        mpp = await _get_mpp()
        authorization = request.headers.get("authorization")

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
                await _record_payment(path, payer, int(required), body_str)
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
                    "url": settings.X402_RESOURCE_BASE.rstrip("/") + path,
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
                    {
                        "scheme": "exact",
                        "network": settings.X402_NETWORK,
                        "asset": USDC_ON_BASE,
                        "amount": str(required),
                        "payTo": settings.WALLET_ADDRESS_2 or settings.WALLET_ADDRESS,
                        "maxTimeoutSeconds": 60,
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
        await _record_payment(path, _payer, int(required), request.state.x402_body, _auth0.get("nonce"))
    
        # Payment verified and settled, proceed to request
        limited = await _rate_limit(request)
        if limited:
            return limited
        response = await call_next(request)
        success_payload = json.dumps({"success": True, "details": settle_data})
        response.headers["X-PAYMENT-RESPONSE"] = base64.b64encode(success_payload.encode()).decode()
        _log_request(request, response, request.state.x402_start)
        return response
