"""Agent capability catalog — the data-only view of the service.

Split out of the optimization router when the solver surface was removed;
kept mounted at /v1/capabilities because discovery (llms.txt, agentsearch,
bazaar, homepage) links agents to it as the live pricing/catalog endpoint.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.x402.pricing import (
    DATA_CHAINS,
    FREE_ROUTES,
    HELIUS_ENDPOINTS,
)

router = APIRouter(tags=["catalog"])


@router.get("/v1/capabilities", summary="Agent capability catalog")
async def capabilities() -> dict:
    helius_configured = bool(settings.HELIUS_API_KEY)
    providers = ["alchemy", "coingecko"] + (["helius"] if helius_configured else [])
    solana_endpoints = [f"/v1/data/{e}" for e in HELIUS_ENDPOINTS] if helius_configured else []
    return {
        "service": "CortexCloud On-Chain Data API",
        "version": "v1",
        "description": FREE_ROUTES["GET /v1/capabilities"],
        "payments": {
            "scheme": "x402",
            "network": "eip155:8453",
            "asset": "USDC (Base)",
            "challenge": "POST any paid route without payment-signature returns 402 with the challenge",
        },
        "discovery": [
            "/.well-known/x402.json",
            "/.well-known/bazaar",
            "/llms.txt",
            "/openapi.json",
            "/mcp",
        ],
        "providers": providers,
        "supported_chains": sorted(set(DATA_CHAINS.keys()) - {"1", "8453", "42161", "137", "10"}),
        "solana": {
            "aliases": ["solana", "sol"],
            "provider": "helius" if settings.HELIUS_API_KEY else "not_configured",
            "endpoints": solana_endpoints,
            "status": "available" if helius_configured else "not_configured",
            "note": ("Solana is supported on token-balances, tx-history, token-price, wallet-intel and token-intel; "
                    "every other route returns chain_not_supported.") if helius_configured
                    else "Solana is not enabled on this instance; configure and verify HELIUS_API_KEY before use.",
            "settlement": "x402 (USDC on Base) — Solana is the READ chain, not the payment chain.",
        },
        "categories": {
            "data": {
                "status": "available" if settings.DATA_ENABLED else "disabled",
                "note": "Onchain data via Alchemy (Token/NFT/Transfers/Node) + CoinGecko price. Tier 1 at the $0.004 floor; Tier 2 intelligence routes fan out to multiple upstreams and are priced accordingly.",
                "endpoints": [
                    "/v1/data/token-intel",
                    "/v1/data/token-balances",
                    "/v1/data/token-price",
                    "/v1/data/nft-ownership",
                    "/v1/data/tx-history",
                    "/v1/data/gas-oracle",
                    "/v1/data/block",
                    "/v1/data/token-risk",
                    "/v1/data/wallet-intel",
                    "/v1/data/whale-alerts",
                    "/v1/data/cross-chain-compare",
                    "/v1/data/market-snapshot",
                ],
                "providers": providers,
                "supported_chains": sorted(set(DATA_CHAINS.keys()) - {"1", "8453", "42161", "137", "10"}),
            },
            "webhooks": {
                "status": "available" if (settings.DATA_ENABLED and settings.WEBHOOKS_ENABLED) else "disabled",
                "note": "Whale-alert webhook registrations (HTTPS only). Registration is paid; "
                        "each delivered alert accrues a metered delivery fee on the registration.",
                "endpoints": [
                    "POST /v1/webhooks/whale-alerts",
                    "GET /v1/webhooks/whale-alerts?owner=0x...",
                    "DELETE /v1/webhooks/whale-alerts/{id}?token=...",
                ],
                "registration_price_usd": 0.10,
                "delivery_price_usd": settings.WEBHOOK_DELIVERY_PRICE_USD,
                "signing": "HMAC-SHA256 over the exact body in X-CortexCloud-Signature: sha256=<hex> when a secret is supplied",
                "constraints": ["https:// only", "public hosts only", "no credentials in the URL"],
            },
            "aggregate": {
                "status": "available" if settings.DATA_ENABLED else "disabled",
                "note": "Batch onchain data across addresses/tokens in one paid call (Alchemy + CoinGecko).",
                "endpoints": [
                    "/v1/aggregate/balances",
                    "/v1/aggregate/prices",
                    "/v1/aggregate/nfts",
                    "/v1/aggregate/tx-history",
                ],
            },
        },
    }
