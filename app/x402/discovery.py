"""Root discovery endpoints — /.well-known/x402.json and /llms.txt.

Both are generated at request time from live config (app.x402.pricing
ROUTE_PRICING + the model registry) so they never describe a stale surface.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import get_db
from app.services.models import ModelRegistryService
from app.x402.pricing import ROUTE_PRICING, ROUTE_DESCRIPTIONS

router = APIRouter()


def _usd_atomic(price_str: str) -> str:
    """'$0.005' -> '5000' (USDC 6-decimal atomic units)."""
    try:
        return str(int(float(price_str.lstrip("$")) * 1_000_000))
    except ValueError:
        return "0"


def build_manifest(active: bool = True) -> dict:
    if not active:
        return {"x402": False, "message": "x402 payment gateway is not enabled on this instance."}

    endpoints = [
        {
            "path": path.split(" ", 1)[1],
            "method": path.split(" ", 1)[0],
            "price": price,
            "price_atomic_usdc": _usd_atomic(price),
            "description": ROUTE_DESCRIPTIONS.get(path, ""),
        }
        for path, price in ROUTE_PRICING.items()
        if float(price.lstrip("$")) > 0.0  # paid routes only
    ]

    return {
        "x402": True,
        "version": 2,
        "facilitator": settings.X402_FACILITATOR_URL,
        "merchant_wallet": settings.WALLET_ADDRESS,
        "pricing_currency": "USDC",
        "pricing_decimals": 6,
        "network": {"chainId": 8453, "eip155": "eip155:8453", "name": "Base"},
        "endpoints": endpoints,
    }


@router.get("/llms.txt", tags=["x402 Discovery"])
async def llms_txt(db: AsyncSession = Depends(get_db)):
    """AI-optimized documentation index. Factual, generated from live config."""
    models = await ModelRegistryService.get_active_models(db)
    model_lines = "\n".join(
        f"- {m.name} ({m.provider}: {m.provider_model_name}, context {m.context_length}, "
        f"${m.prompt_token_price:.6f}/in, ${m.completion_token_price:.6f}/out, "
        f"capabilities: {', '.join(m.capabilities.keys())})"
        for m in models
    ) if models else "- (no models registered)"

    endpoints = [
        f"- {path.split(' ', 1)[0]} {path.split(' ', 1)[1]} — {price}"
        for path, price in sorted(ROUTE_PRICING.items())
        if float(price.lstrip("$")) > 0.0
    ]

    text = f"""# CortexCloud

CortexCloud is an OpenAI-compatible AI and data gateway for agents. Pay per
call in USDC on Base via the x402 payment protocol (eip155:8453) — no API keys,
no subscriptions, no lock-in. Maker opens a session; settlement is
permissionless.

## Authentication

Two ways:

1. x402 (recommended for agents): No API key. Call a /x402/v1/* endpoint, receive
   a 402 Payment Required challenge containing an acceptEVM authorization,
   sign it from your wallet, submit the payment-signature, and stream the
   result. Bazaar input/output schemas are in each 402 challenge's
   extensions.bazaar.
2. Classic API key: Send `Authorization: Bearer <api-key>` to /v1/* endpoints
   (platform-style account).

## OpenAI-compatible surface

- POST /v1/chat/completions
- POST /v1/responses
- POST /v1/embeddings
- GET  /v1/models

## Models

{model_lines}

## Paid x402 endpoints (pricing, USDC on Base)

{chr(10).join(endpoints)}

## Reference

- GitHub: https://github.com/jonahthan433/CortexCloudAPI
"""
    return PlainTextResponse(text, media_type="text/plain; charset=utf-8")