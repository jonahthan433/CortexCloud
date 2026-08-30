# CortexCloud Telegram GTM — owned community + retention

Role split: **Telegram = owned community/retention. X = acquisition.** No product features, no spend, no ads.

## Audit (2026-08-25)
- Channel: t.me/cortexcloudonline
- Subscribers: **4** (baseline)
- Pinned post: none. Recent messages: none.
- Description (STALE): "Learn Artificial Intelligence, Machine Learning, Data Science, Python, Programming, Automation, APIs, Tech Tools, and more…" — generic, no api.cortexcloud.org, no x402 positioning.

## Recommended channel description (DRAFT — apply on approval)
> CortexCloud — agent-native x402 API platform. Optimization, AI, research, on-chain data, automation (ML preview), callable by agents and settled per call in USDC on Base. No API keys, no subscriptions. 🛜 api.cortexcloud.org · MCP + /well-known discovery · free estimates.

## Pinned welcome post (DRAFT — apply on approval)
> 👋 Welcome to the CortexCloud community.
>
> We run an agent-native x402 API platform: optimization, AI, research, on-chain data, automation (ML preview) — each callable by an agent and settled per call in USDC on Base. No API keys, no subscriptions.
>
> 🔗 Live platform: https://api.cortexcloud.org/?ref=tg0
> 📚 API reference: https://api.cortexcloud.org/docs
> 🧪 Free examples: https://api.cortexcloud.org/v1/examples
> 🤝 MCP (16 tools): `claude mcp add cortexcloud --transport http https://api.cortexcloud.org/mcp`
>
> This channel is for AI developers, agent builders, and API users. Share what you're building, ask anything, post x402/agent news. No spam, no shilling.
>
> Ground rules: be constructive, stay on agents/APIs/x402, links welcome if relevant.

## Content calendar (4 months, ~3 posts/week)
Ratio: **70% useful AI/dev content · 20% CortexCloud ecosystem/API · 10% direct promo.**
Sustainable cadence: Mon = useful dev, Wed = ecosystem/API or community, Fri = promo/win.

### Month 1 — Foundation & useful baseline
- W1: (Mon) "How agents pay for APIs without API keys — x402 explainer (link to our /v1/examples)". (Wed) Pin welcome + ask members what they're building. (Fri) "We shipped 16 MCP tools over x402 — try one."
- W2: (Mon) "QUBO/Ising in 5 minutes: when to use optimization." (Wed) "Our endpoint catalog: optimization/AI/research/data/automation." (Fri) "Free estimate, pay only when it runs — api.cortexcloud.org/?ref=tg2"
- W3: (Mon) "Agent automation patterns: webhook + schedule + workflow over x402." (Wed) Community Q&A thread. (Fri) "Real request → 402 → settle walkthrough."
- W4: (Mon) "On-chain data for agents: balances/prices via Alchemy+CoinGecko." (Wed) "How discovery works: /.well-known/x402.json + bazaar + llms.txt." (Fri) Monthly recap + ask for feedback.

### Month 2 — Depth & cross-pollination
- Theme: deeper technical series (optimization backends, AI endpoints, research synthesis), cross-promo from X/GitHub.
- Keep 70/20/10. Pull X high-intent threads into TG discussions. GitHub README links here.

### Month 3 — Community & proof
- Theme: member showcases, guest use-cases, "build with us" prompts. Highlight any external paid-call milestones (anonymized).

### Month 4 — Scale & retention loops
- Theme: onboarding funnel (X→TG→API), referral prompts, sticky documentation. Aim to convert lurkers to callers.

## Cross-promotion (no spam)
- X: each X reply/post that's community-relevant ends with "join t.me/cortexcloudonline".
- GitHub: add channel link to README + /docs.
- Directories (x402-list, agent-tools, x402-index): ensure TG link listed.
- Web communities (r/x402, x402 Discord, DEV.to): share TG only where self-promo is allowed.

## Tracking (separate from X)
- TG-shared links use `?ref=tgN` (tg0 welcome, tg1.. per post).
- Counts via uvicorn/nginx access logs (grep ref=tg*).
- Metrics: subscribers, views (channel stats if bot available), link clicks (ref=tg* in logs), API visits, unique external payers, paid API calls (scripts/gtm_metrics.py, excludes internal).
- Report alongside X in the daily GTM metrics cron (extend gtm_daily.sh later if approved).

## What needs approval before acting
- Apply new description + pinned post (needs admin/bot or you do it).
- Posting cadence execution (you manually, or an approved Telegram bot).
- Any bot/token setup = tooling, requires separate approval.

## Spend status
$0. No features built. Self-heal cron paused. X budget $3 fully preserved.
