# CortexCloud On-Chain Data API - api.cortexcloud.org — GTM Plan

Status: 2026-11-05. Customer-acquisition mode. No fabricated metrics; every
experiment measured against real API traffic and settled payments.

## Value Proposition (canonical, use everywhere)
> **On-chain data infrastructure for AI agents — token, wallet, transaction,
> whale-activity, and market data delivered per call over x402.**

One-liner: "Pay-per-call on-chain data for AI agents. Token prices, balances,
wallets, whale alerts, and market snapshots from $0.004. No API keys — x402
USDC on Base."

## Funnel (no signups exist — x402 IS the onboarding)
visit → free `/v1/capabilities` → paid data call (402 → sign → 200) → repeat
(same wallet)

## Channels, prioritized by (buyer density × conversion ease)
### Tier 1 — agents discover us programmatically (highest leverage)
1. **Official MCP Registry** — LIVE (io.github.jonahthan433/cortexcloud). Keep
   the description on the data-API copy.
2. **x402 scan ecosystem** (x402scan, mppscan, Poncho, AgentCash, x402-list,
   x402-index, 402index, claw402) — LIVE/pending. Keep prices and the manifest
   fresh; re-submit stale optimization-era descriptions.
3. **Glama / mcp.so / PulseMCP** — resubmit with data-API copy.
4. **smithery.ai** — LIVE; update the description.

### Tier 2 — developers building on-chain tooling
5. **GitHub**: README + examples pack with copy-paste token-intel / whale-alert
   demos. The repo is public — the README is the ad.
6. **awesome-mcp-servers** — update the listing line to the data-API copy.
7. **apis.guru** — OpenAPI directory (agents + devtools read it).

### Tier 3 — communities where on-chain data buyers post
8. r/ethereum, r/ethfinance, r/cryptodevs, r/web3, r/defi, r/algotrading;
   X #x402 / agent dev circles; Ethers.js/viem and crypto-agent GitHub
   discussions.
9. **Reference integrations**: agent tool markets (LangChain/Composio),
   crypto-agent GitHub discussions — as issues/PRs only if genuinely useful,
   no spam.

### Tier 4 — paid/partner (only with Jonathan's approval, no budget committed)
10. Cloudflare AI/agent marketplaces, x402 ecosystem grants. Requires money or
    commitments → ask first.

## Experiments (each tracked; double down on paid calls)
| # | Experiment | Channel | Success metric | Status |
|---|---|---|---|---|
| E1 | README + examples pack | GitHub | repo views → paid calls | IN PROGRESS |
| E2 | Landing rewrite (data value prop + token-intel demo) | web | visitors → paid calls | IN PROGRESS |
| E3 | Show HN post (draft ready) | HN | clicks → paid calls | PREPARED |
| E4 | Reddit posts (drafts) | r/ethereum etc. | clicks → paid calls | PREPARED |
| E5 | MCP registry description refresh | registry | tool calls | when listings change |
| E6 | Weekly funnel report to Telegram | internal | visibility | BUILT |
| E7 | Directory re-submissions with corrected copy | x402-list, Glama, … | listing live | IN PROGRESS |
| E8 | x402 ecosystem showcase posts | X #x402 | referrals | needs Jonathan's account |

## Tracking (honest, no fabrication)
- Visitors: landing page hit counter + HTTP Referer (utm capture)
- Paid calls/revenue: `x402_payments` settled — already tracked
- Repeat customers: same wallet >1 settled payment
- Conversion source: landing referer/utm + channel-specific links (each
  listing points at `https://api.cortexcloud.org/?utm_source=<channel>`)
- Weekly GTM report cron: visitors / paid / revenue / repeat / top referers

## Milestones
- M1: 10 external paid calls (watchdog alerts each one) — target 2–4 weeks
- M2: 100 paid calls — then double down on the channels that produced them
