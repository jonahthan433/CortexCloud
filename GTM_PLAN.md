# CortexCloud GTM Plan — First 10 Paid Calls, then 100

Status: 2026-08-08. Customer-acquisition mode. No fabricated metrics; every
experiment measured against real API traffic and settled payments.

## Value Proposition (canonical, use everywhere)
> **Optimization infrastructure for AI agents — automatically solve suitable
> problems using classical or quantum backends and pay per optimization with x402.**

One-liner: "Pay-per-call QUBO/Ising optimization for AI agents. Estimate free,
solve from $0.05. No API keys — x402 USDC on Base."

## Funnel (no signups exist — x402 IS the onboarding)
visit → free /v1/estimate → paid /v1/optimize → repeat (same wallet)

## Channels, prioritized by (buyer density × conversion ease)
### Tier 1 — agents discover us programmatically (highest leverage, near-zero effort)
1. **Official MCP Registry** — LIVE (io.github.jonahthan433/cortexcloud). Every
   MCP client (Claude, Cursor, Codex) can browse it. Keep descriptions current.
2. **x402 scan ecosystem** (x402scan, mppscan, Poncho, AgentCash) — LIVE. This is
   where x402-native agents shop. Keep prices/manifest fresh.
3. **Glama / mcp.so / PulseMCP** — forms pending (Jonathan, 15 min).
4. **smithery.ai** — LIVE.

### Tier 2 — developers building optimization tooling
5. **GitHub**: rewrite README (CortexCloudAPI repo) + add examples/ pack with
   copy-paste QUBO/scheduling/routing demos. Repo is public — README is the ad.
6. **awesome-mcp-servers PR** — submitted (#11752); awesomes + glama feed.
7. **apis.guru** — submitted (#2992) → OpenAPI directory (agents + devtools read it).

### Tier 3 — communities where optimization buyers post (OUTREACH, prepared-only)
8. HN ("Show HN: pay-per-call optimization API for agents"), r/quantumcomputing,
   r/algorithms, r/optimization, Qiskit/PennyLane/D-Wave forums, X #x402 / agent
   dev circles, LangChain/Composio tool markets (x402 tools), quantum-agentics GH.
9. **Reference integrations**: post example MCP config + a "solve a delivery
   routing problem" tutorial to dev blogs / GH discussions of QUBO projects
   (pasqal-io/qubo-solver, agenticsorg/quantum-agentics) — as issues/PRs only if
   genuinely useful, no spam.

### Tier 4 — paid/partner (only with Jonathan's approval, no budget committed)
10. Cloudflare AI/agent marketplaces, D-Wave Leap-style partner programs, x402
    incubator/ecosystem grants. Requires money or commitments → ask first.

## Experiments (each tracked; double down on paid calls)
| # | Experiment | Channel | Success metric | Status |
|---|---|---|---|---|
| E1 | README + examples pack | GitHub | repo views → estimate calls | IN PROGRESS |
| E2 | Landing rewrite (value prop + 3 copy-paste demos) | web | visitors → estimate calls | IN PROGRESS |
| E3 | Show HN post (draft ready) | HN | clicks → estimates | PREPARED |
| E4 | Reddit/forum posts (drafts) | r/quantumcomputing etc. | clicks → estimates | PREPARED |
| E5 | MCP registry description refresh | registry | tool calls | when listings change |
| E6 | Weekly funnel report to Telegram | internal | visibility | BUILT |
| E7 | Reference-integration PRs to QUBO projects | GitHub | stars/PR traffic → estimates | needs review |
| E8 | x402 ecosystem showcase posts | X #x402 | referrals | needs Jonathan's account |

## Tracking (honest, no fabrication)
- Visitors: landing page hit counter + HTTP Referer (utm capture) → new table `referrals`
- Estimates: usage_logs (free calls) — already logged
- Paid calls/revenue: x402_payments settled — already tracked
- Repeat customers: same wallet >1 settled payment (new metric in paid_metrics)
- Conversion source: landing referer/utm + channel-specific links (each listing
  points at https://api.cortexcloud.org/?utm_source=<channel>)
- Weekly GTM report cron: visitors / estimates / paid / revenue / repeat / top referers

## Milestones
- M1: 10 external paid calls (watchdog alerts each one) — target 2–4 weeks
- M2: 100 paid calls — then double down on the channels that produced them
