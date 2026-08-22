"""AI category — agent-native inference via OpenRouter (chat/embed) + Gemini STT.

All paid routes inherit x402 v2 + MPP, rate-limit, input validation, observability
and bazaar discovery from the shared middleware by being listed in
app.x402.pricing (ROUTE_PRICING + INPUT_SCHEMAS). This router only runs the
upstream call and returns structured output — it never touches payments.

Provider abstraction (app.x402.pricing.AI_PROVIDERS) keeps the public API stable
if a vendor is swapped. Costs are NEVER hardcoded here; the middleware computes
price + margin from the advertised rate table at request time.

Feature flag: AI_ENABLED (default False). When off, every route 503s honestly so
the surface can ship to staging before the flag is flipped on in production.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app.core.config import settings
from app.x402.pricing import (
    AI_PROVIDERS,
    ai_chat_price_usd,
    ai_embed_price_usd,
    ai_transcribe_price_usd,
)

logger = logging.getLogger("cortexcloud.api.ai")

router = APIRouter(prefix="/v1", tags=["ai"])

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

_OPENROUTER_MODELS = {
    "gemini-2.5-flash": "google/gemini-2.5-flash",
    "gemini-2.0-flash": "google/gemini-2.0-flash",
    "gpt-4o-mini": "openai/gpt-4o-mini",
}

_CHAT_MODELS = set(_OPENROUTER_MODELS.keys())


class ChatRequest(BaseModel):
    messages: list[dict] = Field(min_length=1, description="Chat messages (role/content).")
    model: str = Field(default="gemini-2.5-flash", description="One of: gemini-2.5-flash, gemini-2.0-flash, gpt-4o-mini")
    max_tokens: int = Field(default=512, ge=1, le=8192, description="Max output tokens (drives price quote).")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    def est_input_tokens(self) -> int:
        # Conservative estimate: ~4 chars/token over all message text.
        chars = sum(len(str(m.get("content", ""))) for m in self.messages)
        return max(1, chars // 4)


class EmbedRequest(BaseModel):
    input: list[str] = Field(min_length=1, max_length=128, description="Texts to embed.")
    model: str = Field(default="text-embedding-004", description="Embedding model id.")


class TranscribeRequest(BaseModel):
    audio_b64: str = Field(description="Base64-encoded audio (WAV/FLAC/MP3).")
    mime: str = Field(default="audio/wav")


def _disabled() -> JSONResponse | None:
    if not settings.AI_ENABLED:
        return JSONResponse(
            status_code=503,
            content={"error": "ai_disabled", "detail": "AI category not enabled on this instance (AI_ENABLED=false)"},
        )
    return None


def _need(key: str | None, name: str, prefix: str | None = None) -> JSONResponse | None:
    if not key or (prefix and not key.startswith(prefix)):
        return JSONResponse(
            status_code=503,
            content={"error": "provider_unconfigured", "detail": f"{name} key not configured on gateway"},
        )
    return None


@router.post("/ai/estimate", include_in_schema=True)
async def ai_estimate(req: ChatRequest):
    """Free: return predicted token cost + USDC price for a chat request."""
    if d := _disabled():
        return d
    price = ai_chat_price_usd(req.model, req.est_input_tokens(), req.max_tokens)
    return {
        "category": "ai",
        "model": req.model,
        "estimated_input_tokens": req.est_input_tokens(),
        "max_output_tokens": req.max_tokens,
        "provider_cost_usd": round(
            AI_PROVIDERS["chat"].estimate_cost(req.model, req.est_input_tokens(), req.max_tokens).provider_cost_usd, 6
        ),
        "price_usd": price,
        "currency": "USDC",
        "payment": "x402 (USDC on Base, eip155:8453)",
    }


@router.post("/ai/chat", include_in_schema=True)
async def ai_chat(req: ChatRequest, request: Request):
    if d := _disabled():
        return d
    if req.model not in _CHAT_MODELS:
        return JSONResponse(status_code=422, content={"error": "bad_model", "detail": f"model must be one of {sorted(_CHAT_MODELS)}"})
    if e := _need(settings.OPENROUTER_API_KEY, "OpenRouter", "sk-or-"):
        return e
    provider_cost = AI_PROVIDERS["chat"].estimate_cost(req.model, req.est_input_tokens(), req.max_tokens).provider_cost_usd
    # Stash cost/margin context for the middleware to record (set on request.state).
    request.state.provider_cost_usd = round(provider_cost, 6)
    request.state.category = "ai"
    async with httpx.AsyncClient(timeout=120.0) as c:
        r = await c.post(
            f"{OPENROUTER_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                      "HTTP-Referer": "https://cortexcloud.org", "X-Title": "CortexCloud"},
            json={"model": _OPENROUTER_MODELS.get(req.model, req.model),
                  "messages": req.messages, "max_tokens": req.max_tokens, "temperature": req.temperature},
        )
        if r.status_code != 200:
            return JSONResponse(status_code=r.status_code, content=r.json() if r.content else {"error": "upstream", "detail": r.text[:500]})
        data = r.json()
    # Extract usage so the client gets structured cost info.
    usage = data.get("usage", {})
    return {
        "id": data.get("id"),
        "model": data.get("model"),
        "choices": data.get("choices"),
        "usage": usage,
        "price_usd": ai_chat_price_usd(req.model, req.est_input_tokens(), req.max_tokens),
        "provider_cost_usd": round(provider_cost, 6),
    }


@router.post("/ai/embed", include_in_schema=True)
async def ai_embed(req: EmbedRequest, request: Request):
    if d := _disabled():
        return d
    if e := _need(settings.OPENROUTER_API_KEY, "OpenRouter", "sk-or-"):
        return e
    input_tokens = sum(max(1, len(t) // 4) for t in req.input)
    provider_cost = AI_PROVIDERS["embed"].estimate_cost(input_tokens=input_tokens).provider_cost_usd
    request.state.provider_cost_usd = round(provider_cost, 6)
    request.state.category = "ai"
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.post(
            f"{OPENROUTER_BASE}/embeddings",
            headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                      "HTTP-Referer": "https://cortexcloud.org", "X-Title": "CortexCloud"},
            json={"model": "openrouter/google/text-embedding-004", "input": req.input},
        )
        if r.status_code != 200:
            return JSONResponse(status_code=r.status_code, content=r.json() if r.content else {"error": "upstream", "detail": r.text[:500]})
        data = r.json()
    return {
        "model": data.get("model"),
        "data": data.get("data"),
        "usage": data.get("usage", {"prompt_tokens": input_tokens}),
        "price_usd": ai_embed_price_usd(input_tokens),
        "provider_cost_usd": round(provider_cost, 6),
    }


@router.post("/ai/transcribe", include_in_schema=True)
async def ai_transcribe(req: TranscribeRequest, request: Request):
    if d := _disabled():
        return d
    if e := _need(settings.GEMINI_API_KEY, "Gemini"):
        return e
    provider_cost = AI_PROVIDERS["transcribe"].estimate_cost().provider_cost_usd
    request.state.provider_cost_usd = round(provider_cost, 6)
    request.state.category = "ai"
    payload = {
        "contents": [{"parts": [{"text": "Transcribe this audio exactly."},
                                {"inline_data": {"mime_type": req.mime, "data": req.audio_b64}}]}]
    }
    async with httpx.AsyncClient(timeout=120.0) as c:
        r = await c.post(
            f"{GEMINI_BASE}/models/gemini-2.5-flash:generateContent",
            params={"key": settings.GEMINI_API_KEY}, json=payload,
        )
        if r.status_code != 200:
            return JSONResponse(status_code=r.status_code, content=r.json() if r.content else {"error": "upstream", "detail": r.text[:500]})
        data = r.json()
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": "parse_stt", "detail": str(e)[:200]})
    return {
        "text": text,
        "price_usd": ai_transcribe_price_usd(),
        "provider_cost_usd": round(provider_cost, 6),
    }
