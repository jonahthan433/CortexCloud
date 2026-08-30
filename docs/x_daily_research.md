# X / GTM daily research — free GET only, $0 spent

Policy: no POST/write, no `search` (401 on free tier), only `posts @handle` GET reads.
Budget: $3 preserved entirely. Max ~3–4 GETs/day. Last quota: 69/75.

## Day 1 — 2026-08-25

### High-intent accounts read (free GET)
- @x402 → RT of @PayBox: "Amazon is now live on PayBox, powered by @trypurch and x402" (retweets 36). Ecosystem heating up.
- @trypurch → building x402 agent-commerce: Amazon/Shopify purchasing endpoints, MoonPay, Crossmint, Circle, SolanaFndn. "Shopping endpoints your agent can call with zero signup, just pay-as-you-need."
- @cortexcloud1 mentions → @OfficialMeddieS: "an agent-native optimization API that lets AI agents pay per call — no signup, no API keys — to solve real-world combinatorial…" (warm inbound, already accurate).

### Opportunities (5–10)

**O1 — @OfficialMeddieS (inbound mention of @cortexcloud1) [X, warm]**
Relevance: someone already described us correctly and positively. Engaging builds the relationship and signals an active, responsive project.
Draft reply (hold for approval):
> Appreciate the shoutout @OfficialMeddieS — that's exactly the model: agents pay per call, no keys, no subs. We've since expanded past optimization to AI, research, on-chain data, automation and ML, all on the same x402 rail. Live endpoints + free estimates at api.cortexcloud.org

**O2 — @trypurch / @PayBox x402 commerce thread [X, high]**
Relevance: they're proving "agents pay for services via x402" — our platform is the API/compute side of that exact pattern. Natural fit, not competitor.
Draft reply:
> Love seeing x402 agent-commerce go live. The same primitive works for compute/APIs: we expose optimization, AI, research, data and automation as pay-per-call endpoints agents settle in USDC on Base — no checkout, no keys. api.cortexcloud.org if useful.

**O3 — @SolanaFndn "Shopping endpoints your agent can call" [X, high]**
Relevance: direct parallel — callable endpoints agents hit with zero signup. We're the API-analog for optimization/AI/data/automation.
Draft reply:
> "endpoints your agent can call with zero signup" — same shape we use for APIs: discover via MCP/.well-known, estimate free, pay per call over x402. Different domain (compute vs commerce) but same agent-native pattern. api.cortexcloud.org

**O4 — @pixelarthur ERC-1271/8004/8183 + x402 standards thread [X, medium]**
Relevance: standards convergence (agent identity, verification, delivery-payment) around x402. We implement x402 settlement today.
Draft reply:
> The stack is converging fast: ERC-1271 (agent signs), ERC-8004 (verified), ERC-8183 (pay on delivery), x402 (no checkout). We settled the payment leg for callable APIs — agents estimate free, pay per call in USDC on Base. api.cortexcloud.org

**O5 — r/x402 intro / showcase thread [WEB, free, high]**
Relevance: devs actively building x402 agents look here for infrastructure.
Draft (for web post, hold):
> If you're building x402 agents and need callable compute (optimization/QUBO, AI, research, on-chain data, automation), CortexCloud exposes it all as pay-per-call endpoints settled in USDC on Base — MCP + /well-known discovery, free estimates. api.cortexcloud.org

**O6 — x402 Discord (tutorials: Sera / Coinbase CDP / DevToolLab) [WEB, free, medium]**
Relevance: tutorial authors hit "how do I actually call a paid endpoint" — we have a working /v1/estimate → 402 → settle loop to reference.
Draft: link our live examples as a copy-paste reference when a thread is stuck on the payment flow.

**O7 — DEV.to x402 article discussion [WEB, free, medium]**
Relevance: production perspective (ledger, margins, settlement) adds value to theoretical posts.
Draft: contribute the "what it costs to run x402 settlement" view; mention api.cortexcloud.org as a live example.

**O8 — 2s.io / agent-tool catalogs [MONITOR, free]**
Relevance: we should be listed where agents discover tools. Confirm presence, request addition if missing.

**O9 — agent-tools.cloud (already auto-listed: slug api-cortexcloud-org-bazaar) [MONITOR]**
Relevance: passive discovery working. Keep bazaar/x402.json fresh.

**O10 — Coinbase CDP / DevToolLab x402 docs [WEB, free, low]**
Relevance: ensure our platform is referenced where devs learn x402. Comment only if directly relevant.

### Improved bio for @cortexcloud1 (PREPARED — NOT POSTED, no write)
> CortexCloud — agent-native x402 API platform. Optimization, AI, research, on-chain data, automation & ML, callable by agents and settled per call in USDC on Base. No API keys. No subscriptions. api.cortexcloud.org

### Tracking plan (no code change)
- Share links as https://api.cortexcloud.org/?ref=x1 … ?ref=xN.
- X-attributed visits counted via uvicorn/nginx access logs (grep ref=x*).
- External payers/calls via scripts/gtm_metrics.py (excludes internal test-buyer).

### Spend status
$0 of $3 spent. 0 writes. Quota 69/75. Self-heal cron PAUSED (per user).
