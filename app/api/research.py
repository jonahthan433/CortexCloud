"""Research category — grounded web search + cited answers via Brave Search API.

Built and wired, but DISABLED until BRAVE_API_KEY is provisioned:
  - RESEARCH_ENABLED must be True (set in staging/prod .env)
  - and BRAVE_API_KEY must be configured, else every route 503s honestly.

Provider abstraction (app.x402.pricing.RESEARCH_PROVIDERS) means swapping Brave
for Exa is a one-line registry change with no public-API change. Costs are never
hardcoded here — the middleware pegs price to the advertised Brave rate.

All paid routes inherit the shared x402/MPP/rate-limit/validation/observability
stack by being listed in app.x402.pricing.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.x402.pricing import RESEARCH_PROVIDERS, research_price_usd

logger = logging.getLogger("cortexcloud.api.research")

router = APIRouter(prefix="/v1", tags=["research"])

BRAVE_BASE = "https://api.search.brave.com/res/v1"


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400, description="Search query.")
    count: int = Field(default=5, ge=1, le=20, description="Number of results.")
    freshness: str = Field(default="pw", description="pw (past week) | pm | py | none.")


class AnswerRequest(BaseModel):
    query: str = Field(min_length=1, max_length=400, description="Question to answer with citations.")


def _disabled() -> JSONResponse | None:
    if not settings.RESEARCH_ENABLED:
        return JSONResponse(
            status_code=503,
            content={"error": "research_disabled", "detail": "Research category not enabled (RESEARCH_ENABLED=false)"},
        )
    return None


def _need_brave() -> JSONResponse | None:
    if not settings.BRAVE_API_KEY:
        return JSONResponse(
            status_code=503,
            content={"error": "provider_unconfigured", "detail": "Brave Search API key not configured on gateway"},
        )
    return None


@router.post("/research/estimate", include_in_schema=True)
async def research_estimate(req: SearchRequest):
    """Free: predicted USDC price for a search/answer request."""
    if d := _disabled():
        return d
    return {
        "category": "research",
        "kind": "search",
        "provider_cost_usd": round(RESEARCH_PROVIDERS["search"].estimate_cost("web").provider_cost_usd, 6),
        "price_usd": research_price_usd("web"),
        "currency": "USDC",
        "payment": "x402 (USDC on Base, eip155:8453)",
    }


@router.post("/research/search", include_in_schema=True)
async def research_search(req: SearchRequest, request: Request):
    if d := _disabled():
        return d
    if e := _need_brave():
        return e
    provider_cost = RESEARCH_PROVIDERS["search"].estimate_cost("web").provider_cost_usd
    request.state.provider_cost_usd = round(provider_cost, 6)
    request.state.category = "research"
    token = settings.BRAVE_API_KEY or ""
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(
            f"{BRAVE_BASE}/web/search",
            headers={"Accept": "application/json", "X-Subscription-Token": token},
            params={"q": req.query, "count": req.count, "freshness": req.freshness},
        )
        if r.status_code != 200:
            return JSONResponse(status_code=r.status_code, content={"error": "upstream_brave", "detail": r.text[:500]})
        data = r.json()
    results = [
        {"title": w.get("title"), "url": w.get("url"), "age": w.get("age"),
         "description": w.get("description"), "source": w.get("meta_url", {}).get("hostname")}
        for w in data.get("web", {}).get("results", [])
    ]
    return {
        "query": req.query,
        "results": results,
        "price_usd": research_price_usd("web"),
        "provider_cost_usd": round(provider_cost, 6),
    }


@router.post("/research/answer", include_in_schema=True)
async def research_answer(req: AnswerRequest, request: Request):
    if d := _disabled():
        return d
    if e := _need_brave():
        return e
    provider_cost = RESEARCH_PROVIDERS["search"].estimate_cost("answer").provider_cost_usd
    request.state.provider_cost_usd = round(provider_cost, 6)
    request.state.category = "research"
    token = settings.BRAVE_API_KEY or ""
    async with httpx.AsyncClient(timeout=25.0) as c:
        r = await c.get(
            f"{BRAVE_BASE}/web/search",
            headers={"Accept": "application/json", "X-Subscription-Token": token},
            params={"q": req.query, "count": 5, "freshness": "pm"},
        )
        if r.status_code != 200:
            return JSONResponse(status_code=r.status_code, content={"error": "upstream_brave", "detail": r.text[:500]})
        data = r.json()
    sources = [
        {"title": w.get("title"), "url": w.get("url")}
        for w in data.get("web", {}).get("results", [])
    ]
    # Honest design: we return the grounded sources + a synthesized answer
    # note. The cited answer text is synthesized by the caller's own model
    # tier; we do NOT fabricate an answer string here.
    return {
        "query": req.query,
        "sources": sources,
        "answer_note": "Grounded sources returned. Synthesize the cited answer with your own model call (POST /v1/ai/chat) using these sources.",
        "price_usd": research_price_usd("answer"),
        "provider_cost_usd": round(provider_cost, 6),
    }
