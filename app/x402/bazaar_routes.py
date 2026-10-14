"""Bazaar discovery root + MCP gateway (x402-wrapped /v1/* surface).

- /.well-known/bazaar   — human/agent index of what this service offers
- /x402/v1/mcp          — MCP (Streamable HTTP style) gateway: tools/list,
                          tools/call; paid tools forward the signed payment
                          challenge/verification to the REST layer.

The MCP layer never implements payment logic — it relays HTTP + payment
headers to /v1/* and returns whatever the gateway says, 402 included.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.http import shared_client
from app.x402.bazaar import list_tools, tool_entry
from app.x402.pricing import FREE_ROUTES, ROUTE_DESCRIPTIONS, ROUTE_PRICING, public_routes

logger = logging.getLogger("cortexcloud.x402.bazaar")

router = APIRouter()


def _endpoint_catalog() -> list[dict]:
    # Advertised product only (PUBLIC_PRODUCT_ROUTES); legacy routes stay
    # paywalled for existing callers but are not advertised.
    paid = [
        {
            "method": path.split(" ", 1)[0],
            "path": path.split(" ", 1)[1],
            "price": price,
            "description": ROUTE_DESCRIPTIONS.get(path, ""),
        }
        for path, price in public_routes().items()
        if float(price.lstrip("$")) > 0.0
    ]
    free = [
        {"method": "GET", "path": "/v1/capabilities", "price": "free", "description": FREE_ROUTES["GET /v1/capabilities"]},
    ]
    return paid + free


@router.get("/.well-known/bazaar", tags=["x402 Discovery"])
async def bazaar_root():
    return {
        "name": "CortexCloud On-Chain Data API",
        "description": "Pay-per-call on-chain data and intelligence over x402 (USDC on Base). Token, wallet, contract/liquidity risk, prices, whale activity, transaction history, balances, and cross-chain comparison. Evidence-backed JSON: source attribution, checked_at timestamps, explicit missing-data indicators. Providers: Alchemy + CoinGecko.",
        "endpoints": _endpoint_catalog(),
        "mcp": {
            "transport": "streamable-http",
            "endpoint": "https://api.cortexcloud.org/mcp",
            "tools": list_tools(),
        },
        "payment": {
            "scheme": "x402",
            "network": settings.X402_NETWORK,
            "asset": "USDC",
            "facilitator": settings.X402_FACILITATOR_URL,
            "merchant_wallet": settings.WALLET_ADDRESS,
        },
        "discovery": ["/.well-known/x402.json", "/llms.txt", "/openapi.json"],
    }
