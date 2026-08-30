# CortexCloud Telegram + web content — copy-ready (Wk1–Wk2)

All links use ?ref= for attribution. TG=Telegram, X=X/Twitter, WEB=reddit/discord/dev.to.
Posting requires your accounts (no bot cred here). Tracking: ref_tracking.sh greps prod logs.

## Telegram — Weeks 1–2 (3/wk, Mon/Wed/Fri)
Ratio target: 70% useful dev · 20% CortexCloud ecosystem · 10% promo.

### Week 1
**Mon (useful):** How agents pay for APIs without API keys — x402 in 1 minute.
> x402 lets an agent settle a USDC payment per API call, no stored credentials, no subscription. The flow: discover → estimate (free) → 402 challenge → pay → result. We run it for optimization/AI/research/data/automation at api.cortexcloud.org/?ref=tg1
> 🔗 https://api.cortexcloud.org/v1/examples?ref=tg1

**Wed (ecosystem):** Our 16-tool MCP server — agents call us without a backend.
> Connect any MCP client to CortexCloud in one line:
> `claude mcp add cortexcloud --transport http https://api.cortexcloud.org/mcp`
> Exposes optimize, AI, research, on-chain data, automation — each settled per call over x402. Docs: https://api.cortexcloud.org/docs?ref=tg2

**Fri (promo):** Free estimate, pay only when it runs.
> Spin up a real paid API call in 60s — no signup. Try a free /v1/estimate, then pay per call in USDC on Base. https://api.cortexcloud.org/?ref=tg3

### Week 2
**Mon (useful):** QUBO/Ising in 5 min: when to reach for optimization.
> Binary-decision problems (scheduling, routing, portfolio, max-cut) map to QUBO/Ising. Classical solvers handle most; real QPU for the heavy tail. We price classical $0.05–0.25, hybrid $0.10, QPU $1.50. https://api.cortexcloud.org/v1/examples?ref=tg4

**Wed (community):** What are you building?
> This channel is for AI devs, agent builders, API users. Drop what you're shipping — agent infra, x402 experiments, automation. We'll point to the right endpoint. (No spam, real replies.)

**Fri (promo):** One rail, six categories.
> Optimization · AI · research · on-chain data · automation · ML (preview) — all on one x402 payment rail. Estimate free, pay per call. https://api.cortexcloud.org/?ref=tg5

## Web-community reply drafts (post from your accounts)
Anchor to real threads found earlier (r/x402, x402 Discord, DEV.to, @trypurch/@SolanaFndn on X).

**WEB-1 (r/x402 intro):** If you're building x402 agents and need callable compute (optimization/QUBO, AI, research, on-chain data, automation), CortexCloud exposes it all as pay-per-call endpoints settled in USDC on Base — MCP + /.well-known discovery, free estimates. https://api.cortexcloud.org/?ref=dir1

**WEB-2 (x402 Discord tutorial stuck on payment flow):** The live loop is simpler than it looks — POST /v1/estimate (free) → get 402 + price → settle USDC on Base → poll result. Copy-paste examples: https://api.cortexcloud.org/v1/examples?ref=dir2

**WEB-3 (DEV.to x402 article):** Production note — settlement ledger + margins matter more than the handshake. We log every call (payer, amount, latency) and exclude test traffic. Happy to share the metrics shape. Platform: https://api.cortexcloud.org/?ref=dir3

**X-1 (@trypurch/@PayBox commerce thread):** Love seeing x402 agent-commerce go live. Same primitive for compute/APIs — agents pay per call, no checkout. https://api.cortexcloud.org/?ref=x1

**X-2 (@SolanaFndn "endpoints your agent can call"):** "zero signup, pay-as-you-need" — same shape we use for APIs: discover via MCP, estimate free, pay per call over x402. https://api.cortexcloud.org/?ref=x2

## Status
- Content ready. Posting blocked on your accounts (no bot cred / web tokens here).
- Attribution live via ?ref= + ref_tracking.sh.
- Remaining: apply TG description/pin (you), Google re-auth (you: paste oob code).
