# CortexCloud On-Chain Data API - api.cortexcloud.org

CortexCloud On-Chain Data API is a blockchain data and intelligence API at
https://api.cortexcloud.org for AI agents and trading systems. Use x402
pay-per-call in USDC on Base (eip155:8453) without an API key, or choose a
manual monthly prepaid subscription with a wallet-linked API key and weighted
usage credits. Renewals are manual; there are no automatic wallet withdrawals.

Every paid response is evidence-backed JSON: each fact carries its source, a
checked_at timestamp, and an explicit missing-data indicator when a value
could not be resolved.

Data sources: Alchemy (primary) and CoinGecko (prices). Supported EVM chains:
ethereum, base, arbitrum, polygon, optimism (name or chain id). Solana remains
gated and is not advertised until Helius is configured and verified.

## Quick start (free, no wallet)

```bash
curl https://api.cortexcloud.org/v1/capabilities
```

Returns the endpoint list, live prices, chains, providers, and payment terms.

## Endpoints

| Method | Path | Price |
|---|---|---|
| GET | /v1/data/block | $0.004 |
| GET | /v1/data/gas-oracle | $0.004 |
| POST | /v1/data/token-price | $0.004 |
| POST | /v1/data/token-balances | $0.004 |
| POST | /v1/data/nft-ownership | $0.004 |
| POST | /v1/data/tx-history | $0.004 |
| POST | /v1/data/wallet-intel | $0.006 |
| POST | /v1/data/token-risk | $0.020 |
| POST | /v1/data/token-intel | $0.030 |
| POST | /v1/data/cross-chain-compare | $0.040 |
| POST | /v1/data/whale-alerts | $0.050 |
| POST | /v1/data/market-snapshot | $0.070 |
| POST | /v1/webhooks/whale-alerts | $0.100 + $0.020/delivery |
| POST | /v1/aggregate/balances | $0.004 per address |
| POST | /v1/aggregate/nfts | $0.004 per address |
| POST | /v1/aggregate/prices | $0.004 per asset |
| POST | /v1/aggregate/tx-history | $0.004 per address |
| POST | /v1/billing/subscribe/starter | $19/month · 19,000 credits |
| POST | /v1/billing/subscribe/trading-pro | $49/month · 49,000 credits |
| POST | /v1/billing/subscribe/agent-fleet | $99/month · 99,000 credits |

Free: `GET /v1/capabilities`; `GET /v1/billing/plans`;
`GET /v1/billing/account`, `GET /v1/billing/usage`, and
`POST /v1/billing/keys/revoke` (subscription API key required);
`GET /v1/webhooks/whale-alerts` (list by `?owner=0x...`);
`DELETE /v1/webhooks/whale-alerts/{id}`.

Prices are per call in USDC on Base and match `app/x402/pricing.py`.

## Flagship: token intelligence

`POST /v1/data/token-intel` with `{"contract": "0x...", "chain": "ethereum",
"coin_id": "usd-coin"}` returns in one call: contract deployment check
(eth_getCode), token metadata (symbol/name/decimals), spot USD price + 24h
change (CoinGecko), optional age/liquidity/market-cap (only when a `coin_id`
is supplied — never guessed), and recent activity evidence (latest transfer
hash + block). Each fact ships as `{value, source, checked_at[, missing]}`;
unresolvable fields are null with a reason.

`POST /v1/data/market-snapshot` takes the same contract and fans token-intel,
whale-alerts, and token-risk out in parallel, returning them under `token`,
`whale_activity`, and `risk` with a `snapshot_at` timestamp. If one section
fails, that key carries an `error` while the rest of the snapshot still
returns (`partial: true`). One call, $0.070 versus $0.100 for the three routes
separately.

## Whale-alert webhooks

`POST /v1/webhooks/whale-alerts` registers an HTTPS endpoint for whale-alert
deliveries ($0.100). Each delivered alert accrues $0.020 on the registration.
When a `secret` is supplied, deliveries carry
`X-CortexCloud-Signature: sha256=<hex>` (HMAC-SHA256 over the exact request
body). `GET` (list by `?owner=`) and `DELETE` (by `?token=` or
`X-Webhook-Token`) are free.

## Payment model

For one-off requests, paid endpoints return an x402 `402 Payment Required`
with USDC terms on Base. An x402 client settles the per-call price and retries
with `PAYMENT-SIGNATURE`; no API key or account is needed.

For monthly prepaid use, call `GET /v1/billing/plans`, then pay one of the
`POST /v1/billing/subscribe/{plan}` routes through x402. The response returns
a `cx_live_` API key once. Send it as `Authorization: Bearer cx_live_…`;
data and aggregate requests debit weighted credits. When credits are exhausted,
the normal x402 per-call challenge is used for overages. The billing dashboard
is at `/billing.html`.

## Paid client examples (copy-paste)

Two reference buyers, both do the whole 402 -> sign -> replay loop:

- `examples/paid_client.py` — official Python SDK (`x402` + `eth-account` + `httpx`)
- `examples/paid_client.ts` — TypeScript / Bun (`@x402/fetch` + `@x402/evm` + `viem`)

```bash
pip install "x402" eth-account httpx
TEST_BUYER_KEY=0x... python examples/paid_client.py

bun add @x402/fetch @x402/evm viem
CC_PRIVATE_KEY=0x... \
CC_PATH=/v1/data/token-price \
CC_BODY='{"id":"ethereum"}' \
  bun run examples/paid_client.ts
```

Both default to `POST /v1/data/token-price` ($0.004) and accept `CC_URL`,
`CC_PATH`, `CC_BODY` overrides. The npm package `x402-fetch` is the deprecated
v1 client (it sends `X-PAYMENT`); this API settles x402 v2
(`PAYMENT-SIGNATURE`), so the TypeScript example uses its successor
`@x402/fetch`.

## Response cache (TTL)

Identical requests inside the TTL window are served from the in-process cache.
x402 requests still pay per call; subscription requests debit the same weighted
credit amount. TTLs: token-price 10s,
token-balances 15s, nft-ownership 15s, tx-history 15s, gas-oracle 5s, block 5s,
wallet-intel 30s, whale-alerts 20s, token-risk 60s, cross-chain-compare 60s,
token-intel 60s, market-snapshot 20s.

## MCP

MCP server (Streamable HTTP): https://api.cortexcloud.org/mcp — tool catalog at
https://api.cortexcloud.org/.well-known/bazaar.

## Discovery

- Agent terms: `/.well-known/x402.json`
- LLM docs: `/llms.txt`
- Agent search: `/.well-known/agentsearch.txt`
- Bazaar: `/.well-known/bazaar`
- OpenAPI: `/openapi.json`

Base URL: https://api.cortexcloud.org
