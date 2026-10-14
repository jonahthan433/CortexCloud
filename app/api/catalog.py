"""Agent capability catalog — the data-only view of the service.

Split out of the optimization router when the solver surface was removed;
kept mounted at /v1/capabilities because discovery (llms.txt, agentsearch,
bazaar, homepage) links agents to it as the live pricing/catalog endpoint.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.core.config import settings
from app.x402.pricing import DATA_CHAINS, FREE_ROUTES

router = APIRouter(tags=["catalog"])


@router.get("/v1/capabilities", summary="Agent capability catalog")
async def capabilities() -> dict:
    return {
        "service": "CortexCloud On-Chain Data API",
        "version": "v1",
        "description": FREE_ROUTES,
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
        "providers": ["alchemy", "coingecko"],
        "supported_chains": sorted(set(DATA_CHAINS.keys()) - {"1", "8453", "42161", "137", "10"}),
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
                ],
                "providers": ["alchemy", "coingecko"],
                "supported_chains": sorted(set(DATA_CHAINS.keys()) - {"1", "8453", "42161", "137", "10"}),
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
