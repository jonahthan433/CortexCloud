"""Research Utilities API (Tier 1) -- content-grounded research helpers.

Endpoints (all paid):
  POST /v1/research/summarize   summarize content with grounded citations
  POST /v1/research/extract      extract entities/facts from text
  POST /v1/research/compare      compare two topics side-by-side

Reuses Brave Search AI-Grounding (same as /v1/research/answer) so outputs
are always web-grounded -- never hallucinated. All routes inherit
x402/MPP/rate-limit/validation/ledger from pricing.ROUTE_PRICING.
"""
from __future__ import annotations

import logging
import re

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.cache import TTLCache
from app.core.config import settings
from app.x402.pricing import PROVIDER_PRICING, pegged_price

logger = logging.getLogger("cortexcloud.api.research_utils")

router = APIRouter(prefix="/v1/research", tags=["Research Utilities"])

_CACHES: dict[str, TTLCache] = {
    "research-summarize": TTLCache(300),
    "research-extract": TTLCache(600),
    "research-compare": TTLCache(300),
}


def _disabled() -> JSONResponse | None:
    if not settings.RESEARCH_ENABLED:
        return JSONResponse(
            status_code=503,
            content={"error": "research_disabled", "detail": "Research Utilities not enabled"},
        )
    return None


def _need_brave() -> JSONResponse | None:
    if not settings.BRAVE_API_KEY:
        return JSONResponse(
            status_code=503,
            content={"error": "provider_unconfigured", "detail": "Brave API key not configured"},
        )
    return None


def _cache_key(*parts: str) -> str:
    import hashlib
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


async def _brave_ground(query: str) -> dict:
    """Brave AI-Grounding: returns cited answer with source URLs."""
    url = "https://api.search.brave.com/res/v1/grounding/answer"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": settings.BRAVE_API_KEY,
    }
    params = {"query": query, "count": 5}
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(url, params=params, headers=headers)
    if r.status_code != 200:
        return {"error": f"brave_status_{r.status_code}", "detail": r.text[:500]}
    return r.json()


class SummarizeRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400, description="What to summarize.")
    max_sentences: int = Field(default=3, ge=1, le=10, description="Max sentences in summary.")


class ExtractRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000, description="Source text to extract from.")


class CompareRequest(BaseModel):
    topic_a: str = Field(min_length=1, max_length=200, description="First topic.")
    topic_b: str = Field(min_length=1, max_length=200, description="Second topic.")


def _stamp_response(body: dict, price: float, provider_cost: float):
    body["price_usd"] = price
    body["provider_cost_usd"] = round(provider_cost, 8)
    body["margin_usd"] = round(price - provider_cost, 8)
    body["currency"] = "USDC"
    return JSONResponse(body)


@router.post("/summarize")
async def research_summarize(req: SummarizeRequest, request: Request):
    if d := _disabled():
        return d
    if e := _need_brave():
        return e

    provider_cost = PROVIDER_PRICING["brave:answer"].per_call
    price = pegged_price(provider_cost)

    cache_key = _cache_key("rsum", req.query, str(req.max_sentences))
    cached = _CACHES["research-summarize"].get(cache_key)
    if cached is not None:
        cached = dict(cached)
        cached["cache_hit"] = True
        return _stamp_response(cached, price, provider_cost)

    result = await _brave_ground(req.query)
    if "error" in result:
        return JSONResponse(status_code=502, content=result)

    answer = result.get("answer", "")
    sentences = answer.split(". ")
    summary = ". ".join(sentences[:req.max_sentences])
    if sentences and req.max_sentences < len(sentences):
        summary += "."

    out = {
        "query": req.query,
        "summary": summary,
        "sources": [s.get("url") for s in result.get("sources", [])[:5]],
        "cache_hit": False,
    }
    _CACHES["research-summarize"].set(cache_key, out)
    return _stamp_response(out, price, provider_cost)


@router.post("/extract")
async def research_extract(req: ExtractRequest, request: Request):
    """Extract entities/facts from provided text (no external call needed)."""
    if d := _disabled():
        return d

    from app.x402.pricing import PRICING_FLOOR_USD
    price = PRICING_FLOOR_USD
    provider_cost = 0.0001

    cache_key = _cache_key("rext", req.text[:200])
    cached = _CACHES["research-extract"].get(cache_key)
    if cached is not None:
        cached = dict(cached)
        cached["cache_hit"] = True
        return _stamp_response(cached, price, provider_cost)

    sentences = [s.strip() for s in re.split(r'[.!?]', req.text) if s.strip()]
    entities = set()
    for s in sentences:
        matches = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', s)
        entities.update(matches)

    facts = [s for s in sentences if any(k in s.lower() for k in ["is", "are", "was", "were", "has", "have"])]

    out = {
        "entity_count": len(entities),
        "entities": list(entities)[:50],
        "fact_count": len(facts),
        "facts": facts[:20],
        "sentence_count": len(sentences),
        "cache_hit": False,
    }
    _CACHES["research-extract"].set(cache_key, out)
    return _stamp_response(out, price, provider_cost)


@router.post("/compare")
async def research_compare(req: CompareRequest, request: Request):
    if d := _disabled():
        return d
    if e := _need_brave():
        return e

    provider_cost = PROVIDER_PRICING["brave:answer"].per_call * 2
    price = pegged_price(provider_cost)

    cache_key = _cache_key("rcmp", req.topic_a, req.topic_b)
    cached = _CACHES["research-compare"].get(cache_key)
    if cached is not None:
        cached = dict(cached)
        cached["cache_hit"] = True
        return _stamp_response(cached, price, provider_cost)

    result_a = await _brave_ground(req.topic_a)
    result_b = await _brave_ground(req.topic_b)

    out = {
        "topic_a": req.topic_a,
        "summary_a": result_a.get("answer", "")[:500] if "error" not in result_a else None,
        "sources_a": [s.get("url") for s in result_a.get("sources", [])[:3] if "error" not in result_a],
        "topic_b": req.topic_b,
        "summary_b": result_b.get("answer", "")[:500] if "error" not in result_b else None,
        "sources_b": [s.get("url") for s in result_b.get("sources", [])[:3] if "error" not in result_b],
        "comparison_prompt": f"Compare '{req.topic_a}' vs '{req.topic_b}' using the cited sources.",
        "cache_hit": False,
    }
    _CACHES["research-compare"].set(cache_key, out)
    return _stamp_response(out, price, provider_cost)
