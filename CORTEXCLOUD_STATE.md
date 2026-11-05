# CORTEXCLOUD_STATE.md — Authoritative Project State

Service: CortexCloud On-Chain Data API - api.cortexcloud.org

Single source of truth for what the service IS, what it charges, what is
enabled, and what the commercialization backlog is. Code is
always the final truth (`app/x402/pricing.py` for prices;
`PUBLIC_PRODUCT_ROUTES` is the advertised subset).

## What this is
Pay-per-call on-chain data + intelligence API over x402 (USDC on Base,
eip155:8453). The advertised product is 17 paid data/aggregate/webhook routes
plus 2 free discovery routes. Data sources: Alchemy (primary), CoinGecko
(prices). Every paid response is evidence-backed (source, checked_at,
explicit missing-data indicators).

## Live surface
- API: `cortexcloud.service` (uvicorn :8000)
  - Paid (x402, USDC on Base): 12 `/v1/data/*` routes, 4 `/v1/aggregate/*`
    routes, `POST /v1/webhooks/whale-alerts`
  - Free: `GET /v1/capabilities`, `GET /v1/webhooks/whale-alerts`
- Discovery: `/llms.txt`, `/.well-known/x402.json`, `/.well-known/x402`,
  `/.well-known/agentsearch.txt`, `/.well-known/bazaar`,
  `/.well-known/x402list.txt`, `/openapi.json`
- MCP: `cortexcloud-mcp.service` (Streamable HTTP :3100 + stdio) — 18 tools
  catalogued at `/.well-known/bazaar` (17 paid routes + free capabilities)
- Gateway: `cortexcloud-gateway.service` (Node)
- Internal: `/internal/metrics` (X-Internal-Token) — revenue aggregates only,
  never public

## Pricing policy
| Route group | Price |
|---|---|
| Tier 1 data: block, gas-oracle, token-price, token-balances, nft-ownership, tx-history | $0.004 |
| Aggregate batch routes: balances, nfts, prices, tx-history | $0.004 per constituent call |
| wallet-intel | $0.006 |
| token-risk | $0.020 |
| token-intel | $0.030 |
| cross-chain-compare | $0.040 |
| whale-alerts | $0.050 |
| market-snapshot | $0.070 |
| webhooks/whale-alerts registration | $0.100 + $0.020 per delivered alert |

- Prices are the advertised floors in `ROUTE_PRICING`; provider cost is far
  below the floor on data routes (Alchemy ~$0.000011/call, CoinGecko free
  tier).
- Cache TTLs per route (5–60s): identical requests inside the window are
  served from cache; the x402 price is still charged per request.
- `ROUTE_PRICING` contains legacy optimization/AI/research entries only as
  code paths; the advertised product is filtered by `PUBLIC_PRODUCT_ROUTES`.

## Chains
- EVM: ethereum, base, arbitrum, polygon, optimism (name or chain id)
- Solana: implemented in code but NOT enabled — no `HELIUS_API_KEY` is
  configured, and `/v1/capabilities` reports `solana.status: not_configured`.
  Do not advertise Solana until the key is set and verified. Once configured,
  the gated Solana surface includes token balances (legacy SPL + Token-2022),
  transaction history, token price, wallet intelligence, token intelligence,
  token risk, wallet-scoped whale alerts, and cross-chain comparison.
  Solana whale alerts require a wallet address and exclude unpriced transfers.
  Cross-chain comparison requires both an EVM contract and an explicit Solana
  mint; the service does not assert that caller-supplied addresses represent
  the same asset.

## Evidence / honesty
- Every paid fact ships as `{value, source, checked_at[, missing]}`
- Missing data is reported as missing, never estimated silently
- whale-alerts applies the USD floor to native-asset transfers only; erc20
  values are raw units

## Revenue posture
- Every settled x402 request records a Payment row (payer, endpoint,
  amount_usd, referer, user_agent)
- `/internal/metrics`: token-gated revenue aggregates (503 when
  INTERNAL_TOKEN unset)

## Deploy & test (CT105 /opt/CortexCloudAPI)
```bash
/opt/cortexcloud-venv/bin/python -m pytest tests/ -q          # must be green
/opt/cortexcloud-venv/bin/python update_openapi_v2.py          # regen OpenAPI
systemctl restart cortexcloud.service                          # deploy API
systemctl restart cortexcloud-mcp.service                      # deploy MCP
curl -s localhost:8000/v1/capabilities                         # verify pricing + routes
curl -s -X POST localhost:8000/v1/data/token-price \
  -H 'Content-Type: application/json' -d '{"id":"ethereum"}'   # expect 402 + amount
curl -s localhost:8000/.well-known/agentsearch.txt             # verify discovery
```
MCP rebuild (from the source repo on the Hermes host):
`npx tsc --noEmit && npx --no-install esbuild src/http.ts --bundle --format=cjs --platform=node --outfile=dist/mcp-bundle.cjs` then push the bundle to CT105 `/opt/cortexcloud-mcp/mcp-bundle.cjs`.

## Commercialization backlog (hand-maintained — next moves)
1. Recurring external paid calls: directory listings, demo funnel, referrals
2. Discovery copy sync: `llms.txt`/`agentsearch.txt` are generated from
   `app/x402/pricing.py` — verify after any route/price change; the TypeScript
   install line in the generator still names the deprecated `x402-fetch`
   package and must be corrected to `@x402/fetch`
3. Agent discovery: re-submit stale directory listings (optimization-era
   copy) with the on-chain data blurbs in `MARKETPLACE_LISTINGS.md`
4. MCP registry: refresh listing; keep tool descriptions in sync with the API

## Live snapshot
Regenerate after deploy. Note: `scripts/update_state.py` still emits the
legacy optimization price table (`MODE_PRICE_USD`/Benchmark rows) and must be
rewritten for the data surface before its output is trusted.

## Phase completion status (feature branch, 2026-11-05)

### Phase 1 — production readiness
- Added PostgreSQL-backed GitHub Actions CI and deterministic test configuration.
- Solana discovery is gated: Helius is omitted from provider lists and Solana routes are hidden until `HELIUS_API_KEY` is configured.
- Aggregate pricing now scales by batch size; cache hits report zero upstream provider cost.
- The CI suite has not yet been certified green. The first run exposed 29 failures caused by x402 being disabled and missing provider test configuration; fixtures and validation are being corrected.

### Phase 2 — multi-chain intelligence
- Implemented Token-2022-aware Solana balances, wallet intelligence, token intelligence, token risk, wallet-scoped priced whale alerts, and EVM/Solana cross-chain comparison.
- Cross-chain comparison requires a caller-supplied EVM contract and Solana mint; the API does not claim those addresses identify the same asset.
- Solana whale alerts require a wallet address. Transfers without a verified USD price are excluded rather than estimated.
- Helius is still unconfigured in the deployment environment. Solana must remain hidden until the provider key is configured and live checks pass.

### Phase 3 — monetization
- Added manual monthly prepaid USDC plans on Base: Starter $19/19,000 credits; Trading Pro $49/49,000; Agent Fleet $99/99,000.
- One credit equals $0.001 of advertised API price. Subscription purchases are x402-settled, issue a wallet-linked API key once, and create a credit ledger.
- API-key requests debit credits; exhausted balances fall back to ordinary x402 per-call overages. Failed upstream 5xx responses refund credits. Idempotency keys prevent duplicate debits.
- Added authenticated billing account/usage endpoints, API-key revocation, a browser billing dashboard, Python SDK support, and purchase/trading-bot examples.
- Renewals are manual. There are no automatic wallet withdrawals or recurring wallet pulls.

### Phase 4 — commercial launch preparation
- Updated the public README, website pricing section, llms.txt discovery, SDK documentation and examples.
- External directory submissions/listing status still require re-verification; no external listing is claimed live solely from repository changes.
- Production migration, Helius configuration, provider verification, green CI, and an explicit production deployment approval remain launch gates.
- No production deployment has been performed, and `main` has not been modified.
