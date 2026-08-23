# CortexCloud — Discovery Directory Submissions (A1/A browser-form batch)
# Branding: "CortexCloud — agent-native x402 APIs at api.cortexcloud.org"
# payTo: 0x5a0353bc9c75b893a9b5735d3e79f1bd988ea143
# Rule: NO paid listings, subscriptions, or promoted placement. Free only.

## DONE (free, no browser needed — reverse-engineered POST endpoints)
- [x402-index] GitHub issue #36 — OPEN (awaiting 24h verification)
      https://github.com/x402-index/x402-discovery-index/issues/36
- [x402-list] POST /api/v1/submit — HTTP 201, status=pending, 3 endpoints probed OK
      submission_id: 5bc566a8-622f-43b2-9509-3e0cf0281117
      payload key lesson: API wants "url" not "service_url"; endpoints as JSON array of /v1/paths
- [agent-tools.cloud] ALREADY LISTED (passive crawl via our live /.well-known/bazaar)
      slug: api-cortexcloud-org-bazaar  (confirmed present, no submit needed)

## DEAD / DOWN (skip)
- [x402scout.com] — SUSPENDED (HTTP 503). Dead.
- [402radar.io] — POST /api/radar-submit returns 503 (service degraded). Retried; still down.

## BLOCKED — needs authenticated account login (browser unavailable; account creation not approved)
- [Smithery] /publish 404, /new 308→login. Needs Smithery account.
- [mcp.so] unreachable from this IP (curl 000). Needs account/web.
- [Glama] /mcp/new 404. Needs Glama account.
- [punkpeye/awesome-mcp-servers] GitHub PR — deferred (gh api rate-limited; format TBD).

## PASSIVE (our surfaces live + 200; agent-tools auto-indexed us)
- /.well-known/x402.json, /.well-known/bazaar, /.well-known/agentsearch.txt,
  /llms.txt, /openapi.json, /mcp all 200 → crawlable. agent-tools.cloud confirmed pickup.

## Note
Browser/Chrome is NOT available in this runtime (no DISPLAY). Submissions done via
direct POST to each directory's backend API instead of a browser form — same result,
no payment, no accounts. MCP registries that require login were not submitted
(account creation not approved). Re-run when a browser/account is available.
