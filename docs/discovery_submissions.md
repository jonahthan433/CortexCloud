# CortexCloud — Discovery Directory Submissions (A1)
# Branding: "CortexCloud — agent-native x402 APIs at api.cortexcloud.org"
# payTo / payment address: 0x5a0353bc9c75b893a9b5735d3e79f1bd988ea143
# Rule: NO paid listings, subscriptions, or promoted placement.

## DONE (free, no payment, no browser)
- [x402-index/x402-discovery-index] GitHub issue #36 — OPEN (pending their 24h verification)
      URL: https://github.com/x402-index/x402-discovery-index/issues/36
      Account: existing GitHub (jonahthan433) — no new creds

## DEAD / UNREACHABLE (skip)
- [x402scout.com] — service SUSPENDED (HTTP 503). Skip.

## READY — needs browser (Chrome not running) or account — NOT submitted yet
- [402radar.io] web form https://402radar.io/submit (200) — payload ready
- [x402-list.com] web form https://x402-list.com/submit (200) — payload ready
- [agent-tools.cloud] web form https://agent-tools.cloud/submit (200) — payload ready
      (passive crawl also possible via our live /.well-known/bazaar + x402.json + /mcp)
- [2s.io learn/x402] catalog — no programmatic submit; web only
- [MCP registries] smithery.ai / mcp.so / glama.ai/mcp — web forms/accounts
- [punkpeye/awesome-mcp-servers] GitHub PR — deferred (gh api rate-limited; format TBD)

## PASSIVE (no action — crawler-based, surfaces already live + 200)
- /.well-known/x402.json, /.well-known/bazaar, /.well-known/agentsearch.txt,
  /llms.txt, /openapi.json, /mcp all return 200 (crawlable by agent directories).

## BLOCKERS (environmental, not policy)
- X search (x_search / xAI Grok): CREDITS EXHAUSTED — cannot run batched search or post.
- Browser tool: no Chrome running — cannot submit web forms or post to communities.
- Posting to r/x402 / DEV.to / x402 Discord needs accounts (your click).

## HIGH-INTENT COMMUNITIES FOUND (for when posting unblocked)
- r/x402 (Reddit), x402 Discord (Coinbase/Cloudflare x402 Foundation),
  DEV Community x402 thread (dev.to), 2s.io learn/x402, x402 tutorials
  (Sera, Coinbase CDP docs, DevToolLab), x402 GitBook Discussions.

## Notes
- All payloads lead with api.cortexcloud.org + "agent-native x402 API platform".
- No credentials created yet beyond existing GitHub. Record any new account here:
      (none yet)
