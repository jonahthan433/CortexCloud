"""ML API (Tier 1) — agent-native ML inference.

Three endpoints:
  POST /v1/ml/image-generate   (fal.ai primary, Replicate fallback; SDXL/Flux)
  POST /v1/ml/image-understand (Gemini vision via OpenRouter)
  POST /v1/ml/rerank           (Cohere primary, Jina fallback)

All paid routes inherit the full x402/MPP/rate-limit/validation/ledger stack
by being registered in app.x402.pricing.ROUTE_PRICING — this router only calls
the upstream provider and returns normalized JSON. It NEVER touches payments.

Provider economics are data, not logic: app.x402.pricing.ML_PROVIDERS /
ml_provider_cost_usd / ml_price_usd. The charged price (and ledger margin)
auto-derive from the advertised provider rate table, so a provider reprice is
a one-line table edit, not a code change.

Provider abstraction: each endpoint declares (Primary, Fallback) provider
objects implementing estimate_cost(); the route tries primary, falls back on
transport/auth failure, and records which provider actually served the call.

Caching: image-generate is uncacheable (unique per request). image-understand
and rerank are deterministic on (input, params) -> short TTL via the in-process
TTLCache (single-worker; see app.core.cache).

Feature flag: ML_ENABLED (default False). When off, every route 503s honestly,
exactly like AI/Research/Data. Discovery still advertises the surface.
"""
from __future__ import annotations

import base64
import hashlib
import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from app.core.cache import TTLCache
from app.core.config import settings
from app.x402.pricing import (
    ML_PROVIDERS,
    ML_TTL_S,
    ml_price_usd,
    ml_provider_cost_usd,
)

logger = logging.getLogger("cortexcloud.api.ml")

router = APIRouter(prefix="/v1/ml", tags=["ml"])

# ponytail: in-process cache (single worker). Swap to Redis by pointing TTLCache
# at a redis-backed store — same .get/.set API. No route changes needed.
_CACHES: dict[str, TTLCache] = {ep: TTLCache(ttl_s) for ep, ttl_s in ML_TTL_S.items() if ttl_s > 0}

# Hard request-size ceiling (trust boundary): 8 MB of base64 image input / audio.
_MAX_B64 = 11_000_000  # ~8 MB decoded
_HTTPX_TIMEOUT = 120.0


# ---------------------------------------------------------------------------
# Input models (validated before any settlement by the shared money-path
# guard; re-validated here too).
# ---------------------------------------------------------------------------
class ImageGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000, description="Text prompt.")
    model: str = Field(default="sdxl", description="sdxl | flux")
    n: int = Field(default=1, ge=1, le=4, description="Images to generate.")
    size: str = Field(default="1024x1024", description="WxH, e.g. 1024x1024.")

    @field_validator("model")
    @classmethod
    def _model(cls, v):
        if v not in ("sdxl", "flux"):
            raise ValueError("model must be 'sdxl' or 'flux'")
        return v


class ImageUnderstandRequest(BaseModel):
    image_b64: str | None = Field(default=None, description="Base64 image (png/jpg/webp).")
    image_url: str | None = Field(default=None, description="Public image URL (http/https).")
    prompt: str = Field(default="Describe this image in detail.", max_length=1000)

    @field_validator("image_b64")
    @classmethod
    def _b64(cls, v):
        if v is None:
            return v
        if len(v) > _MAX_B64:
            raise ValueError("image_b64 too large (max ~8 MB)")
        try:
            base64.b64decode(v, validate=True)
        except Exception:
            raise ValueError("image_b64 must be valid base64")
        return v


class RerankRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    documents: list[str] = Field(min_length=1, max_length=256, description="Candidate strings to rank.")
    model: str = Field(default="rerank-v3", description="rerank-v3 (cohere) | rerank (jina)")
    top_n: int | None = Field(default=None, ge=1, le=256, description="Return only top N.")


def _disabled() -> JSONResponse | None:
    if not settings.ML_ENABLED:
        return JSONResponse(
            status_code=503,
            content={"error": "ml_disabled", "detail": "ML API not enabled on this instance (ML_ENABLED=false)"},
        )
    return None


def _need(key: str | None, name: str, prefix: str | None = None) -> JSONResponse | None:
    if not key or (prefix and not key.startswith(prefix)):
        return JSONResponse(
            status_code=503,
            content={"error": "provider_unconfigured", "detail": f"{name} key not configured on gateway"},
        )
    return None


def _cache_key(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _cached_get(endpoint: str, key: str):
    return _CACHES[endpoint].get(key)


def _cached_set(endpoint: str, key: str, value: dict) -> None:
    _CACHES[endpoint].set(key, value)


def _stamp(body: dict, endpoint: str, provider_cost: float, provider_used: str) -> dict:
    price = ml_price_usd(endpoint)
    body["price_usd"] = price
    body["provider_cost_usd"] = round(provider_cost, 8)
    body["margin_usd"] = round(price - provider_cost, 8)
    body["provider"] = provider_used
    body["currency"] = "USDC"
    return body


# ---------------------------------------------------------------------------
# Provider transport (primary -> fallback). Each returns (status, data, used).
# ---------------------------------------------------------------------------
async def _fal_generate(req: ImageGenerateRequest, api_key: str):
    url = f"https://fal.run/fal-ai/{req.model}"
    headers = {"Authorization": f"Key {api_key}", "Content-Type": "application/json"}
    payload = {"prompt": req.prompt, "num_images": req.n, "image_size": req.size}
    async with httpx.AsyncClient(timeout=_HTTPX_TIMEOUT) as c:
        r = await c.post(url, headers=headers, json=payload)
    if r.status_code != 200:
        return r.status_code, (r.json() if r.content else {"error": r.text[:300]}), "fal"
    data = r.json()
    images = [i.get("url") for i in data.get("images", []) if i.get("url")]
    return 200, {"images": images, "raw": data}, "fal"


async def _replicate_generate(req: ImageGenerateRequest, api_key: str):
    # Replicate REST: POST model version-less via /v1/models/{owner}/{name}/predictions
    model_path = "stability-ai/sdxl" if req.model == "sdxl" else "black-forest-labs/flux-schnell"
    url = f"https://api.replicate.com/v1/models/{model_path}/predictions"
    headers = {"Authorization": f"Token {api_key}", "Content-Type": "application/json", "Prefer": "wait"}
    payload = {"input": {"prompt": req.prompt, "num_outputs": req.n}}
    async with httpx.AsyncClient(timeout=_HTTPX_TIMEOUT) as c:
        r = await c.post(url, headers=headers, json=payload)
    if r.status_code != 201:
        return r.status_code, (r.json() if r.content else {"error": r.text[:300]}), "replicate"
    data = r.json()
    output = data.get("output") or []
    images = [o for o in output if isinstance(o, str)]
    return 200, {"images": images, "raw": data}, "replicate"


async def _openrouter_vision(req: ImageUnderstandRequest, api_key: str, input_tokens: int, output_tokens: int):
    """Image understanding via OpenRouter vision (Gemini 2.5 Flash)."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
               "HTTP-Referer": "https://cortexcloud.org", "X-Title": "CortexCloud"}
    content = [{"type": "text", "text": req.prompt}]
    if req.image_url:
        content.append({"type": "image_url", "image_url": {"url": req.image_url}})
    elif req.image_b64:
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{req.image_b64}"}})
    payload = {"model": "google/gemini-2.5-flash", "messages": [{"role": "user", "content": content}]}
    async with httpx.AsyncClient(timeout=_HTTPX_TIMEOUT) as c:
        r = await c.post(url, headers=headers, json=payload)
    if r.status_code != 200:
        return r.status_code, (r.json() if r.content else {"error": r.text[:300]}), "openrouter"
    data = r.json()
    try:
        text = data["choices"][0]["message"]["content"]
    except Exception as e:
        return 502, {"error": "parse_vision", "detail": str(e)[:200]}, "openrouter"
    provider_cost = ml_provider_cost_usd("image-understand", input_tokens=input_tokens, output_tokens=output_tokens)
    return 200, {"text": text}, "openrouter", provider_cost


async def _cohere_rerank(req: RerankRequest, api_key: str):
    url = "https://api.cohere.com/v2/rerank"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": "rerank-v3.5", "query": req.query, "documents": req.documents, "top_n": req.top_n or len(req.documents)}
    async with httpx.AsyncClient(timeout=_HTTPX_TIMEOUT) as c:
        r = await c.post(url, headers=headers, json=payload)
    if r.status_code != 200:
        return r.status_code, (r.json() if r.content else {"error": r.text[:300]}), "cohere"
    data = r.json()
    results = [{"index": i["index"], "document": req.documents[i["index"]], "relevance_score": i.get("relevance_score")} for i in data.get("results", [])]
    return 200, {"results": results}, "cohere"


async def _jina_rerank(req: RerankRequest, api_key: str):
    url = "https://api.jina.ai/v1/rerank"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": "jina-reranker-v2-base-multilingual", "query": req.query, "documents": req.documents, "top_n": req.top_n or len(req.documents)}
    async with httpx.AsyncClient(timeout=_HTTPX_TIMEOUT) as c:
        r = await c.post(url, headers=headers, json=payload)
    if r.status_code != 200:
        return r.status_code, (r.json() if r.content else {"error": r.text[:300]}), "jina"
    data = r.json()
    results = [{"index": i["index"], "document": req.documents[i["index"]], "relevance_score": i.get("relevance_score")} for i in data.get("results", [])]
    return 200, {"results": results}, "jina"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.post("/estimate")
async def ml_estimate(req: ImageGenerateRequest | ImageUnderstandRequest | RerankRequest, request: Request):
    """Free: predicted USDC price for an ML request before paying."""
    if d := _disabled():
        return d
    # Determine endpoint from payload shape.
    if getattr(req, "prompt", None) and getattr(req, "documents", None) is not None and isinstance(getattr(req, "documents", None), list):
        endpoint = "rerank"
    elif getattr(req, "image_b64", None) is not None or getattr(req, "image_url", None) is not None:
        endpoint = "image-understand"
    else:
        endpoint = "image-generate"
    price = ml_price_usd(endpoint, getattr(req, "model", None))
    return {
        "category": "ml",
        "endpoint": endpoint,
        "price_usd": price,
        "provider_cost_usd": round(ml_provider_cost_usd(endpoint, getattr(req, "model", None)), 6),
        "currency": "USDC",
        "payment": "x402 (USDC on Base, eip155:8453)",
    }


@router.post("/image-generate")
async def image_generate(req: ImageGenerateRequest, request: Request):
    if d := _disabled():
        return d
    if e := _need(settings.FAL_KEY, "fal.ai", "fal-"):
        # If fal key absent, allow Replicate-only path.
        if not settings.REPLICATE_API_KEY:
            return e
    endpoint = "image-generate"
    provider_cost = ml_provider_cost_usd(endpoint, req.model)
    request.state.provider_cost_usd = round(provider_cost, 6)
    request.state.category = "ml"

    last_err = None
    # Primary: fal
    if settings.FAL_KEY:
        status, data, used = await _fal_generate(req, settings.FAL_KEY)
        if status == 200:
            body = {"images": data.get("images", []), "cache_hit": False}
            return _stamp(body, endpoint, provider_cost, used)
        last_err = data
    # Fallback: replicate
    if settings.REPLICATE_API_KEY:
        status, data, used = await _replicate_generate(req, settings.REPLICATE_API_KEY)
        if status == 200:
            body = {"images": data.get("images", []), "cache_hit": False}
            return _stamp(body, endpoint, provider_cost, used)
        last_err = data
    return JSONResponse(status_code=502, content={"error": "upstream_ml", "detail": str(last_err)[:500]})


@router.post("/image-understand")
async def image_understand(req: ImageUnderstandRequest, request: Request):
    if d := _disabled():
        return d
    if not req.image_b64 and not req.image_url:
        return JSONResponse(status_code=400, content={"error": "bad_request", "detail": "provide image_b64 or image_url"})
    if e := _need(settings.OPENROUTER_API_KEY, "OpenRouter", "sk-or-"):
        return e
    endpoint = "image-understand"
    input_tokens = (len(req.image_b64 or "") // 4) + (len(req.prompt) // 4)
    provider_cost = ml_provider_cost_usd(endpoint, input_tokens=input_tokens, output_tokens=128)
    # Cache deterministic understand calls (same image + prompt).
    cache_key = _cache_key(endpoint, req.image_url or req.image_b64 or "", req.prompt)
    hit = _cached_get(endpoint, cache_key)
    if hit is not None:
        hit = dict(hit)
        hit["cache_hit"] = True
        return _stamp(hit, endpoint, provider_cost, hit.get("provider", "openrouter"))
    status, data, used, *rest = await _openrouter_vision(req, settings.OPENROUTER_API_KEY, input_tokens, 128)
    if status != 200:
        detail = data if isinstance(data, dict) else {"error": str(data)[:300]}
        return JSONResponse(status_code=status or 502, content={"error": "upstream_ml", "detail": str(detail)[:500]})
    provider_cost = rest[0] if rest else provider_cost
    body = {"text": data.get("text", ""), "cache_hit": False}
    _cached_set(endpoint, cache_key, body)
    request.state.provider_cost_usd = round(provider_cost, 6)
    request.state.category = "ml"
    return _stamp(body, endpoint, provider_cost, used)


@router.post("/rerank")
async def rerank(req: RerankRequest, request: Request):
    if d := _disabled():
        return d
    if e := _need(settings.COHERE_API_KEY, "Cohere", "co-"):
        if not settings.JINA_API_KEY:
            return e
    endpoint = "rerank"
    provider_cost = ml_provider_cost_usd(endpoint, docs=len(req.documents))
    cache_key = _cache_key(endpoint, req.query, "|".join(req.documents), req.model, str(req.top_n))
    hit = _cached_get(endpoint, cache_key)
    if hit is not None:
        hit = dict(hit)
        hit["cache_hit"] = True
        return _stamp(hit, endpoint, provider_cost, hit.get("provider", "cohere"))
    last_err = None
    # Primary: cohere
    if settings.COHERE_API_KEY:
        status, data, used = await _cohere_rerank(req, settings.COHERE_API_KEY)
        if status == 200:
            body = {"results": data.get("results", []), "cache_hit": False}
            request.state.provider_cost_usd = round(provider_cost, 6)
            request.state.category = "ml"
            return _stamp(body, endpoint, provider_cost, used)
        last_err = data
    # Fallback: jina
    if settings.JINA_API_KEY:
        status, data, used = await _jina_rerank(req, settings.JINA_API_KEY)
        if status == 200:
            body = {"results": data.get("results", []), "cache_hit": False}
            request.state.provider_cost_usd = round(provider_cost, 6)
            request.state.category = "ml"
            return _stamp(body, endpoint, provider_cost, used)
        last_err = data
    return JSONResponse(status_code=502, content={"error": "upstream_ml", "detail": str(last_err)[:500]})
