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
    DATA_TTL_S,
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
    other v1 discovery tools parse. The rich v2 manifest stays at x402.json.
    Resources are derived from the pricing table so this surface cannot drift
    from ROUTE_PRICING (it previously hardcoded 10 of the 17 paid routes)."""
    resources = [
        f"https://api.cortexcloud.org{path.split(' ', 1)[1]}"
        for path in public_routes()
    ]
    resources.append("https://api.cortexcloud.org/v1/capabilities")
    return {
        "version": 1,
        "resources": resources,
        "instructions": "Pay-per-call on-chain data + intelligence API over x402 (USDC on Base eip155:8453). Full pricing: https://api.cortexcloud.org/v1/capabilities; rich manifest: https://api.cortexcloud.org/.well-known/x402.json; agent docs: https://api.cortexcloud.org/llms.txt.",
    }


@router.get("/.well-known/agentsearch.txt", tags=["x402 Discovery"])
async def agentsearch_txt():
    """Agent-search discovery file (agentsearch.txt convention): what this
    service is, how agents call it, and where the machine-readable docs live."""
    text = "\n".join([
        "Name: CortexCloud On-Chain Data API - api.cortexcloud.org",
        "Description: Pay-per-call on-chain data API over x402 (USDC on Base, eip155:8453). Token prices, ERC-20 balances, NFT ownership, transaction history, blocks, gas, wallet profiles, token risk, whale alerts, cross-chain comparison, and market snapshots. Every paid call returns evidence-backed JSON with source attribution, checked_at timestamps, and explicit missing-data indicators. No API keys.",
        "Human URL: https://api.cortexcloud.org/",
        "Commands:",
        "- POST /v1/data/token-intel {contract, chain?, coin_id?} for a token intelligence profile (deployment, metadata, price, 24h change, optional age/liquidity/mcap, recent activity). $0.030.",
        "- POST /v1/data/token-price {id|contract, chain?} for spot USD price + 24h change. $0.004.",
        "- POST /v1/data/token-balances {address, chain?, tokens?} for ERC-20 balances. $0.004.",
        "- POST /v1/data/nft-ownership {address, chain?} for NFTs owned by a wallet. $0.004.",
        "- POST /v1/data/token-risk {contract, chain?, coin_id?} for a risk verdict with evidence. $0.020.",
        "- POST /v1/data/wallet-intel {address, chain?, limit?} for a wallet profile (balances, holdings, counterparties). $0.006.",
        "- POST /v1/data/whale-alerts {address?, chain?, min_usd?, limit?} for large-transfer alerts. $0.050.",
        "- POST /v1/data/cross-chain-compare {contract, chains?} to compare one contract across chains. $0.040.",
        "- POST /v1/data/market-snapshot {contract, chain?, address?, coin_id?, min_usd?} for token + whale + risk in one call. $0.070.",
        "- GET /v1/data/block {chain?} for a block by number or 'latest'. $0.004.",
        "- GET /v1/data/gas-oracle {chain?} for base fee + priority fee. $0.004.",
        "- POST /v1/webhooks/whale-alerts {url, address, chain?, min_usd?, secret?} to register an HTTPS whale-alert webhook (HMAC-signed when secret is set). $0.100 registration + $0.020 per delivered alert.",
        "- GET /v1/webhooks/whale-alerts?owner=0x... to list registrations and the delivery amount due (free). DELETE /v1/webhooks/whale-alerts/{id}?token=... to unregister (free).",
        "- POST /v1/aggregate/{balances|nfts|prices|tx-history} for batch reads across many addresses. $0.004.",
        "Discovery: https://api.cortexcloud.org/llms.txt, https://api.cortexcloud.org/.well-known/x402.json, https://api.cortexcloud.org/.well-known/bazaar, https://api.cortexcloud.org/.well-known/agentsearch.txt, https://api.cortexcloud.org/openapi.json",
        "Pricing: https://api.cortexcloud.org/v1/capabilities",
        "# Chains: ethereum, base, arbitrum, polygon, optimism (name or chain id). Providers: Alchemy + CoinGecko. Cached per endpoint (5-60s TTL): identical requests inside the window are served from cache with no additional upstream call (the x402 price is still charged per request).",
    ])
    return PlainTextResponse(text + "\n", media_type="text/plain; charset=utf-8")


@router.get("/llms.txt", tags=["x402 Discovery"])
async def llms_txt():
    paid = [
        f"- {path.split(' ', 1)[0]} {path.split(' ', 1)[1]} — {price}"
        for path, price in sorted(public_routes().items())
        if float(price.lstrip("$")) > 0.0
    ]
    free = [f"- {path} — {desc}" for path, desc in sorted(FREE_ROUTES.items())]
    ttl_rows = "\n".join(
        f"| /v1/data/{name} | {ttl}s |" for name, ttl in sorted(DATA_TTL_S.items())
    )
    solana_section = ""
    if settings.HELIUS_API_KEY and settings.HELIUS_VERIFIED:
        solana_section = """## Solana (Helius)

Solana reads are enabled on this instance for legacy SPL and Token-2022
balances, transaction history, token prices, wallet intelligence, token
intelligence and risk, wallet-scoped priced whale alerts, and cross-chain
comparison. Cross-chain comparison requires the caller to provide both the
EVM contract and the Solana mint; CortexCloud does not assert asset identity.
Solana whale alerts require a wallet address and exclude transfers without a
verified USD price. Payment settlement remains USDC on Base; Solana is the
read chain, not the payment chain.

"""

    text = f"""# CortexCloud On-Chain Data API - api.cortexcloud.org

CortexCloud is an agent-native on-chain data API for AI agents and trading
systems. Use x402 pay-per-call in USDC on Base (eip155:8453) without an API
key, or buy a manual monthly prepaid subscription that issues a wallet-linked
API key and weighted usage credits. Credits are consumed by advertised route
price; after exhaustion, x402 per-call payments remain available. Renewals are
manual — there are no automatic wallet withdrawals. Data sources: Alchemy (primary) + CoinGecko (prices).
Supported EVM chains: ethereum, base, arbitrum, polygon, optimism.

Every paid response is evidence-backed: each fact carries its source, a
checked_at timestamp, and an explicit missing-data indicator when a value
could not be resolved. Nothing is fabricated.

## Workflow (agent-first)

1. Read this file or GET /v1/capabilities (free) — endpoint list, prices,
   configured providers, chain support, and billing plans.
2. For one-off calls, POST the endpoint and answer the 402 x402 challenge.
3. For recurring API use, GET /v1/billing/plans and POST a subscription route;
   the settled response returns a wallet-linked API key once.
4. Send that key as Authorization: Bearer cx_live_…; each successful data
   request deducts weighted credits. When credits are exhausted, use x402
   payment-signature for a per-call overage.
5. For recurring whale alerts, register a webhook and receive signed HTTPS
   deliveries.

Copy-paste buyer (Python, official x402 SDK):

    pip install "x402" eth-account httpx
    TEST_BUYER_KEY=0x... python paid_client.py   # 402 -> sign -> 200

Source: https://raw.githubusercontent.com/jonahthan433/CortexCloud/main/examples/paid_client.py
(overrides: CC_PATH, CC_BODY, CC_URL)

Copy-paste buyer (TypeScript, @x402/fetch + bun):

    bun add @x402/fetch @x402/evm viem
    CC_PRIVATE_KEY=0x... CC_PATH=/v1/data/token-price CC_BODY='{{"id":"ethereum"}}' \\
      bun run paid_client.ts

Source: https://raw.githubusercontent.com/jonahthan433/CortexCloud/main/examples/paid_client.ts
(overrides: CC_PRIVATE_KEY, CC_URL, CC_PATH, CC_BODY)

## Endpoints (advertised product)

{chr(10).join(paid)}

Free:

{chr(10).join(free)}

## Response cache (TTL)

{ttl_rows}

Identical requests inside the TTL window are served from the in-process cache:
the upstream provider call is skipped, so there is no additional upstream cost.
For x402 requests the advertised per-call price still applies; subscription
requests deduct the same weighted credit amount. The cache is not a discount.

## Monthly prepaid subscriptions

    GET  /v1/billing/plans                         free
    POST /v1/billing/subscribe/starter              $19 / month, 19,000 credits
    POST /v1/billing/subscribe/trading-pro          $49 / month, 49,000 credits
    POST /v1/billing/subscribe/agent-fleet          $99 / month, 99,000 credits
    GET  /v1/billing/account                       free (API key required)
    GET  /v1/billing/usage                         free (API key required)
    POST /v1/billing/keys/revoke                    free (API key required)

- One credit represents $0.001 of advertised API price.
- Subscription payments are prepaid manually in USDC on Base. No recurring
  wallet pulls or automatic withdrawals are performed.
- The API key is returned only once after a settled subscription payment;
  only its hash is stored. Save the key securely.
- Data and aggregate requests debit credits. When credits are exhausted, the
  request falls back to the normal x402 per-call challenge.
- API key requests may supply an Idempotency-Key header to prevent duplicate
  credit debits. A reused key returns 409.

## Billing dashboard

Open https://api.cortexcloud.org/billing.html to inspect subscription status,
active API key prefixes, remaining credits, and the latest credit ledger.
The dashboard keeps the entered key in page memory only; it does not persist it.

## Whale-alert webhooks

    POST   /v1/webhooks/whale-alerts        $0.100  register (x402, USDC on Base)
    GET    /v1/webhooks/whale-alerts        free    list by ?owner=0x...
    DELETE /v1/webhooks/whale-alerts/{{id}}   free    ?token=... or X-Webhook-Token

- HTTPS only, public hosts only, no credentials in the URL.
- Registration returns a one-time `management_token`; only its SHA-256 is
  stored. Listing never returns secrets or the token.
- Deliveries are POSTed as JSON (`type: "whale_alert"`, `alert`, `delivered_at`).
  When you supply a `secret`, every delivery carries
  `X-CortexCloud-Signature: sha256=<hex>`, an HMAC-SHA256 over the exact
  request body. Without a secret the delivery is sent unsigned
  (`signed: false`).
- Billing is metered: each successful delivery accrues $0.020 on the
  registration (`deliveries`, `amount_due_usd` in the list response). Outbound
  webhooks cannot answer a 402, so nothing is charged silently.
- A new registration is primed on its first poll: alerts that already exist
  are recorded but not delivered, so you only receive new activity.

## Flagship: token intelligence

POST /v1/data/token-intel with {{"contract": "0x...", "chain": "ethereum",
"coin_id": "usd-coin"}} returns in ONE call: contract deployment check
(eth_getCode), token metadata (symbol/name/decimals), spot USD price +
24h change (CoinGecko), optional age/liquidity/market-cap (only when a
coin_id is supplied — never guessed), and recent activity evidence
(latest transfer hash + block). Each fact ships as
{{value, source, checked_at[, missing]}}; unresolvable fields are null with
a reason. A compact risk verdict + flags summarize the evidence.

POST /v1/data/market-snapshot takes the same contract and fans token-intel,
whale-alerts and token-risk out in parallel, returning them under `token`,
`whale_activity` and `risk` with a `snapshot_at` timestamp. If one section
fails, that key carries an `error` while the rest of the snapshot still
returns (`partial: true`, `errors`, `sections`). One call, $0.070 versus
$0.100 for the three routes separately.

{solana_section}## Honesty

- Provider costs are published; CortexCloud margin is computed transparently.
- Missing data is reported as missing, never estimated silently.
- whale-alerts applies the USD floor to native-asset transfers only;
  erc20 values are raw units (call /token-price for USD).
- Supported EVM chains are ethereum, base, arbitrum, polygon, and optimism
  (name or chain id). Optional Solana routes are described above only when
  Helius is configured on this instance.
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
