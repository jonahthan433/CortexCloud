"""Root discovery endpoints — /.well-known/x402.json and /llms.txt.

Generated at request time from live config (app.x402.pricing) so they
never describe a stale surface. CortexCloud's advertised product is the
on-chain data + intelligence API (app.x402.pricing.PUBLIC_PRODUCT_ROUTES);
legacy optimization/AI routes stay mounted + paywalled for existing
callers but are no longer advertised here.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.x402.pricing import (
    FREE_ROUTES,
    MODE_PRICE_USD,
    ROUTE_DESCRIPTIONS,
    ROUTE_PRICING,
    effective_price_usd,
    public_routes,
)

router = APIRouter()


def _usd_atomic(price_str: str) -> str:
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
            "description": ROUTE_DESCRIPTIONS.get(path, "On-chain data endpoint (x402-paid)"),
        }
        for path, price in public_routes().items()
        if float(price.lstrip("$")) > 0.0
    ]

    return {
        "x402": True,
        "version": 2,
        "facilitator": settings.X402_FACILITATOR_URL,
        "merchant_wallet": settings.WALLET_ADDRESS,
        "pricing_currency": "USDC",
        "pricing_decimals": 6,
        "network": {"chainId": 8453, "eip155": settings.X402_NETWORK, "name": "Base"},
        "endpoints": endpoints,
        "free_endpoints": [
            {"path": p.split(" ", 1)[1], "method": p.split(" ", 1)[0], "description": d}
            for p, d in FREE_ROUTES.items()
        ],
    }


@router.get("/.well-known/x402.json", tags=["x402 Discovery"])
async def well_known_x402():
    return build_manifest()


@router.get("/.well-known/x402", tags=["x402 Discovery"])
async def well_known_x402_v1():
    """v1 discovery document (resource URL list) — the shape x402scan-mcp and
    other v1 discovery tools parse. The rich v2 manifest stays at x402.json."""
    return {
        "version": 1,
        "resources": [
            "https://api.cortexcloud.org/v1/data/token-intel",
            "https://api.cortexcloud.org/v1/data/token-price",
            "https://api.cortexcloud.org/v1/data/token-balances",
            "https://api.cortexcloud.org/v1/data/token-risk",
            "https://api.cortexcloud.org/v1/data/wallet-intel",
            "https://api.cortexcloud.org/v1/data/whale-alerts",
            "https://api.cortexcloud.org/v1/data/cross-chain-compare",
            "https://api.cortexcloud.org/v1/capabilities",
        ],
        "instructions": "Pay-per-call on-chain data + intelligence API over x402 (USDC on Base eip155:8453). Full pricing: https://api.cortexcloud.org/v1/capabilities; rich manifest: https://api.cortexcloud.org/.well-known/x402.json; agent docs: https://api.cortexcloud.org/llms.txt.",
    }


@router.get("/.well-known/agentsearch.txt", tags=["x402 Discovery"])
async def agentsearch_txt():
    """Agent-search discovery file (agentsearch.txt convention): what this
    service is, how agents call it, and where the machine-readable docs live."""
    text = "\n".join([
        "Name: CortexCloud On-Chain Data API",
        "Description: Pay-per-call on-chain data and intelligence API over x402 (USDC on Base, eip155:8453). Token, wallet, contract/liquidity risk, prices, whale activity, transaction history, balances, and cross-chain comparison. Every paid call returns evidence-backed JSON with source attribution, checked_at timestamps, and explicit missing-data indicators. No API keys.",
        "Human URL: https://api.cortexcloud.org/",
        "Commands:",
        "- POST /v1/data/token-intel {contract, chain?, coin_id?} for a flagship token intelligence profile (deployment, metadata, price, 24h change, optional age/liquidity/mcap, recent activity). $0.030.",
        "- POST /v1/data/token-price {id|contract, chain?} for spot USD price + 24h change. $0.004.",
        "- POST /v1/data/token-balances {address, chain?, tokens?} for ERC-20 balances. $0.004.",
        "- POST /v1/data/token-risk {contract, chain?, coin_id?} for a risk verdict with evidence. $0.020.",
        "- POST /v1/data/wallet-intel {address, chain?, limit?} for a wallet profile (balances, holdings, counterparties). $0.006.",
        "- POST /v1/data/whale-alerts {address?, chain?, min_usd?, limit?} for large-transfer alerts. $0.030.",
        "- POST /v1/data/cross-chain-compare {contract, chains?} to compare one contract across up to 5 chains. $0.040.",
        "- POST /v1/aggregate/{balances|nfts|prices|tx-history} for batch reads across many addresses. $0.004.",
        "Discovery: https://api.cortexcloud.org/llms.txt, https://api.cortexcloud.org/.well-known/x402.json, https://api.cortexcloud.org/.well-known/bazaar, https://api.cortexcloud.org/.well-known/agentsearch.txt, https://api.cortexcloud.org/openapi.json",
        "Pricing: https://api.cortexcloud.org/v1/capabilities",
        "# Chains: ethereum, base, arbitrum, polygon, optimism (name or chain id). Providers: Alchemy + CoinGecko. Cached per endpoint (5-60s TTL).",
    ])
    return PlainTextResponse(text + "\n", media_type="text/plain; charset=utf-8")


@router.get("/llms.txt", tags=["x402 Discovery"])
async def llms_txt():
    paid = [
        f"- {path.split(' ', 1)[0]} {path.split(' ', 1)[1]} — {price}"
        for path, price in sorted(public_routes().items())
        if float(price.lstrip("$")) > 0.0
    ]
    free = [f"- {path} — {desc}" for path, desc in sorted(FREE_ROUTES.items())
            if path.startswith(("GET /v1/capabilities",))]

    text = f"""# CortexCloud — On-Chain Data & Intelligence API

CortexCloud is an agent-native, pay-per-call on-chain data API. Agents
discover, pay for, and read blockchain data over x402 (USDC on Base,
eip155:8453) — no API keys, no subscriptions. Data sources: Alchemy
(primary) + CoinGecko (prices). Supported chains: ethereum, base,
arbitrum, polygon, optimism (name or chain id).

Every paid response is evidence-backed: each fact carries its source, a
checked_at timestamp, and an explicit missing-data indicator when a value
could not be resolved. Nothing is fabricated.

## Workflow (agent-first)

1. Read this file or GET /v1/capabilities (free) — the full endpoint list,
   live prices, chains, and providers.
2. POST the endpoint — receive a 402 x402 challenge (USDC on Base).
3. Sign the payment (EIP-3009, gasless for the buyer) and resend with the
   payment-signature header. The response is returned immediately
   (short-TTL cache makes repeats cheap).

Copy-paste buyer (official x402 SDK):

    pip install "x402" eth-account httpx
    TEST_BUYER_KEY=0x... python paid_client.py   # 402 -> sign -> 200

Source: https://raw.githubusercontent.com/jonahthan433/CortexCloud/main/examples/paid_client.py
(overrides: CC_PATH, CC_BODY, CC_URL)

## Endpoints (advertised product)

{chr(10).join(paid)}

Free:

{chr(10).join(free)}

## Flagship: token intelligence

POST /v1/data/token-intel with {{"contract": "0x...", "chain": "ethereum",
"coin_id": "usd-coin"}} returns in ONE call: contract deployment check
(eth_getCode), token metadata (symbol/name/decimals), spot USD price +
24h change (CoinGecko), optional age/liquidity/market-cap (only when a
coin_id is supplied — never guessed), and recent activity evidence
(latest transfer hash + block). Each fact ships as
{{value, source, checked_at[, missing]}}; unresolvable fields are null with
a reason. A compact risk verdict + flags summarize the evidence.

## Honesty

- Provider costs are published; CortexCloud margin is computed transparently.
- Missing data is reported as missing, never estimated silently.
- whale-alerts applies the USD floor to native-asset transfers only;
  erc20 values are raw units (call /token-price for USD).
- What is advertised is what runs: every route above is live on this
  instance.

## Discovery

- MCP server (Streamable HTTP): https://api.cortexcloud.org/mcp
- Payment manifest (x402): https://api.cortexcloud.org/.well-known/x402.json
- Bazaar discovery: https://api.cortexcloud.org/.well-known/bazaar
- OpenAPI: https://api.cortexcloud.org/openapi.json

## Reference

- GitHub: https://github.com/jonahthan433/CortexCloudAPI
"""
    return PlainTextResponse(text, media_type="text/plain; charset=utf-8")
