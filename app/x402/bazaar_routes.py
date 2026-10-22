"""Bazaar discovery root (agent index of the x402-wrapped /v1/* surface).

- /.well-known/bazaar — human/agent index: endpoints, prices, MCP tool
  registry (mcp.tools) and payment terms.

The MCP gateway itself is a separate host service (zero-dependency relay,
exposed by the tunnel at https://api.cortexcloud.org/mcp). It holds no
payment logic: it relays HTTP + payment headers to /v1/* and returns
whatever the API says, 402 challenge included.
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
