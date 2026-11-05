# MARKETPLACE_LISTINGS.md — Submission Kit & Status Tracker

Copy corrected 2026-11-05 for the on-chain data API. Listings marked LIVE below were previously submitted, but external status
has not been re-verified during this implementation. Treat each as historical
until checked directly. Re-submit or refresh descriptions using this file.

## Canonical listing facts

- Service: CortexCloud On-Chain Data API - api.cortexcloud.org
- Base URL: `https://api.cortexcloud.org`
- Paid routes (x402, USDC on Base, eip155:8453, 6-dec): 12 `/v1/data/*` routes,
  4 `/v1/aggregate/*` routes, `POST /v1/webhooks/whale-alerts`, and 3 manual
  prepaid subscription purchase routes.
- Prices: $0.004 (block, gas-oracle, token-price, token-balances,
  nft-ownership, tx-history, all four aggregate routes) · $0.006 wallet-intel ·
  $0.020 token-risk · $0.030 token-intel · $0.040 cross-chain-compare ·
  $0.050 whale-alerts · $0.070 market-snapshot · $0.100 webhook registration
  + $0.020 per delivered alert
- Free: `GET /v1/capabilities`, `GET /v1/webhooks/whale-alerts`,
  `GET /v1/billing/plans`, and API-key-authenticated billing account/usage/key
  management endpoints.
- Payee wallet: `0x5a0353bc9c75b893a9b5735d3e79f1bd988ea143`
- MCP: `https://api.cortexcloud.org/mcp` (Streamable HTTP; 18 tools catalogued
  at `/.well-known/bazaar`; server version 0.5.0)
- Discovery: `/llms.txt` · `/.well-known/x402.json` · `/.well-known/bazaar` ·
  `/.well-known/agentsearch.txt` · `/openapi.json`

### Descriptions (reuse everywhere)
- Short: `CortexCloud On-Chain Data API - api.cortexcloud.org: evidence-backed on-chain data and intelligence for AI agents and trading systems. Pay per call over x402 in USDC on Base without an API key, or use manual prepaid monthly plans ($19/$49/$99) with wallet-linked API keys and weighted credits. Token prices, ERC-20 balances, NFT ownership, transaction history, blocks, gas, wallet profiles, token risk, whale alerts, cross-chain comparison, and market snapshots. $0.004-$0.070 per data call.`
- Long: `CortexCloud On-Chain Data API serves evidence-backed blockchain data to AI agents and trading systems at api.cortexcloud.org. Paid routes cover token prices, ERC-20 balances, NFT ownership, transaction history, blocks, gas oracle, wallet profiles, token risk, whale alerts, cross-chain comparison, and a combined market snapshot; batch reads cover balances, NFTs, prices, and transaction history. Whale-alert webhooks register for $0.100 and accrue $0.020 per delivered alert. One-off requests settle over x402 in USDC on Base (eip155:8453) without an API key. Optional manual monthly prepaid plans cost $19, $49, or $99 and issue wallet-linked API keys with weighted credits; after credits run out, x402 per-call overages remain available. Renewals are manual with no automatic wallet withdrawals. Responses are evidence-backed: each fact carries its source, a checked_at timestamp, and an explicit missing-data indicator when a value could not be resolved. Data sources are Alchemy and CoinGecko; supported public chains are ethereum, base, arbitrum, polygon, and optimism (name or chain id). Solana is intentionally not advertised until Helius is configured and verified.`

## Submission tracker

| # | Platform | Historical status | Listing URL | Date | Needs |
|---|---|---|---|---|---|
| 0a | x402scan | ✅ LIVE | x402scan.com → resources?origin=api.cortexcloud.org | 2026-07 | price refresh via x402scan-MCP or browser |
| 0b | mppscan | ✅ LIVE | mppscan.com → search `api.cortexcloud.org` | 2026-07 | none |
| 0c | Poncho AI | ✅ LIVE | https://tryponcho.com/m/api.cortexcloud.org | 2026-07 | none |
| 0d | AgentCash dir | ⚠️ AUTO | agentcash.dev/apis (fed by x402scan/mppscan) | — | verify presence |
| 0e | x402-list | ✅ LIVE | x402-list submission 5bc566a8-622f-43b2-9509-3e0cf0281117 | 2026-08 | re-submit with data-API copy |
| 0f | x402-index | 🚀 SUBMITTED | github.com/x402-index/x402-discovery-index/issues/36 | 2026-08 | awaiting merge; refresh copy on merge |
| 1 | Smithery | ✅ LIVE | https://smithery.ai/servers/ampwerajonathan50/cortexcloud-mcp | 2026-08-08 | update description |
| 2 | Glama | 🧰 PREPARED | glama.ai/mcp/servers/… (est.) | — | Jonathan: account + submit URL |
| 3 | mcp.so | 🧰 PREPARED | mcp.so/servers/cortexcloud (est.) | — | Jonathan: submit form |
| 4 | PulseMCP | 🧰 PREPARED | pulsemcp.com (est.) | — | Jonathan: submit form |
| 5 | awesome-mcp-servers | 🚀 SUBMITTED | PR https://github.com/punkpeye/awesome-mcp-servers/pull/11752 | 2026-08-08 | update line if merged |
| 6 | apis.guru | 🚀 SUBMITTED | issue https://github.com/APIs-guru/openapi-directory/issues/2992 | 2026-08-08 | awaiting maintainer review |
| 7 | Official MCP Registry | ✅ LIVE | registry.modelcontextprotocol.io → io.github.jonahthan433/cortexcloud | 2026-08-08 | refresh description |

## Kit 1 — Smithery
```bash
npm i -g @smithery/cli
smithery login          # GitHub OAuth (Jonathan)
smithery mcp publish https://api.cortexcloud.org/mcp -n cortexcloud/cortexcloud
# metadata prompts: description = short desc above; categories: data, web3, crypto, api; tags: x402, usdc, agent, blockchain, on-chain-data, web3
```
Verify after publish: `https://smithery.ai/server/cortexcloud/cortexcloud`.

## Kit 2 — Glama (glama.ai/mcp)
1. Create account (GitHub OAuth) → glama.ai/mcp/servers → "Submit server".
2. Server URL: `https://api.cortexcloud.org/mcp` (remote HTTP — Glama probes it).
3. Name `CortexCloud On-Chain Data API` · description = short · category
   `AI / Developer Tools / Data / Web3`.
Verify: `https://glama.ai/mcp/servers/cortexcloud-cortexcloud` (or search
"cortexcloud").

## Kit 3 — mcp.so
Form at `https://mcp.so/submit`: name `CortexCloud On-Chain Data API`, server
URL `https://api.cortexcloud.org/mcp`, description = short, category
`AI / Agent / Data / Web3`. Verify: `https://mcp.so/servers/cortexcloud`.

## Kit 4 — PulseMCP
Form at `https://pulsemcp.com` → Submit a server: URL
`https://api.cortexcloud.org/mcp`, name `CortexCloud On-Chain Data API`,
description = short. Verify: pulsemcp.com search "cortexcloud". (Site is
Cloudflare-fronted; 403 to bots — form only.)

## Kit 5 — awesome-mcp-servers (punkpeye/awesome-mcp-servers)
PR body / README addition:
```
- [CortexCloud On-Chain Data API](https://api.cortexcloud.org/mcp) - Pay-per-call on-chain data over x402 (USDC on Base): token prices, balances, NFTs, transactions, wallet intel, whale alerts, market snapshots. $0.004-$0.070 per call, no API keys.
```
`gh` is authenticated as jonahthan433 — PR command ready:
```bash
gh repo clone punkpeye/awesome-mcp-servers /tmp/awesome-mcp && cd /tmp/awesome-mcp
# add line to README.md under relevant section, then:
git checkout -b add-cortexcloud && git add README.md && git commit -m "add CortexCloud MCP server"
gh pr create --title "Add CortexCloud MCP server" --body "Remote Streamable-HTTP MCP server: pay-per-call on-chain data via x402 (USDC on Base)."
```
(Requires Jonathan's approval before opening.)

## Kit 6 — apis.guru (APIs-guru/openapi-directory)
Submit via `https://apis.guru/add-api` — OpenAPI URL:
`https://api.cortexcloud.org/openapi.json` (the API is machine-readable;
apis.guru fetches + validates it). Prepared issue/PR text:
```
Add CortexCloud On-Chain Data API — pay-per-call on-chain data over x402 (USDC on Base). Token prices, balances, NFTs, transactions, wallet intel, whale alerts, market snapshots. $0.004-$0.070 per call.
OpenAPI: https://api.cortexcloud.org/openapi.json
```
Verify: apis.guru → search "cortexcloud".

## Kit 7 — Official MCP Registry (registry.modelcontextprotocol.io)
Server metadata (server.json) — verify exact schema in the registry UI at
submission time:
```json
{
  "name": "github.jonahthan433/cortexcloud",
  "description": "CortexCloud On-Chain Data API - api.cortexcloud.org: pay-per-call on-chain data over x402 (USDC on Base). Token prices, ERC-20 balances, NFT ownership, transaction history, wallet profiles, token risk, whale alerts, cross-chain comparison, and market snapshots. $0.004-$0.070 per call; no API keys. Evidence-backed JSON with source attribution and checked_at timestamps.",
  "version": "0.5.0",
  "remotes": {
    "https://api.cortexcloud.org/mcp": {}
  }
}
```
Publish path (both need Jonathan): (a) npm `@cortexcloud/mcp-server` — publish
blocked headless (passkey-only 2FA; run from Lenovo/iPhone), then register via
registry website (GitHub auth); or (b) attach server.json to a GitHub release
of jonahthan433/CortexCloudAPI and register via the registry website. Verify:
registry.modelcontextprotocol.io → search "cortexcloud".

## Kit 8 — x402 discovery directories
Paste-ready blurbs for x402-list, x402-index, 402index, awesome-x402, and
claw402 live in `listing-*.md` alongside this file.

## Paid-call watchdog (live 08-08)
- `cc-paid-call-watch` cron (every 30m, silent unless a new settled payment
  lands) reads `scripts/paid_metrics.py` (read-only settled-payment counters)
  on CT105 → alerts with total/10 + revenue + per-endpoint breakdown. Target:
  first 10 real external paid calls.
- Note: `INTERNAL_TOKEN` is unset in prod → `/internal/metrics` returns 503.
  The watchdog uses the DB read path instead.

## Next actions (Jonathan only)
1. Smithery description update (2 min) → highest-value MCP listing
2. Glama + mcp.so + PulseMCP forms (~5 min each) with the short description
3. Re-submit x402-list / x402-index with the data-API blurbs
4. Official registry: refresh description (npm publish from Lenovo/iPhone, or
   GitHub-release path)
