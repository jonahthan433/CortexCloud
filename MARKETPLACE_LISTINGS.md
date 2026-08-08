# MARKETPLACE_LISTINGS.md — Submission Kit & Status Tracker

Audit: 2026-08-08. Distribution phase active. Source of truth for all listing
metadata. Nothing requiring Jonathan's credentials/approval has been submitted;
every item is either LIVE, PREPARED (needs him), or BLOCKED. Statuses updated
as submissions land.

## Canonical listing facts

- Base / paid: `POST https://api.cortexcloud.org/v1/optimize` (x402) · Free: `/v1/estimate`, `/v1/jobs/{id}`, `/v1/backends`, `/v1/capabilities`, `/v1/examples`
- Prices (USDC on Base, eip155:8453, 6-dec): classical $0.05 (50000) · hybrid $0.10 (100000) · quantum $0.85 (850000) · payee `0x5a0353bc9c75b893a9b5735d3e79f1bd988ea143`
- MCP: `https://api.cortexcloud.org/mcp` (Streamable HTTP; 4 tools; v0.4.0) — verified reachable publicly (HTTP 200), `/openapi.json` and `/.well-known/agentsearch.txt` also 200. No production API changes required for listings.
- Discovery: `/llms.txt` · `/.well-known/x402.json` · `/.well-known/bazaar` · `/.well-known/agentsearch.txt` · `/openapi.json`

### Descriptions (reuse everywhere)
- Short: `Pay-per-call QUBO/Ising optimization API for AI agents. Estimate free, solve per run via x402 (USDC on Base). $0.05-$0.85/run, no API keys.`
- Long: `CortexCloud Optimization Network — pay-per-call QUBO/Ising optimization for autonomous agents. Estimate for free (decision block: mode, backend, provider cost, price), then solve per run: classical $0.05, hybrid $0.10, quantum $0.85, paid via x402 in USDC on Base (no API keys, no signup). Quantum QPU execution (Rigetti via Amazon Braket) is opt-in and only recommended with benchmark evidence. MCP server at /mcp (cortex_estimate_optimization, cortex_optimize, cortex_get_job, cortex_list_backends).`

## Submission tracker

| # | Platform | Status | Listing URL | Date | Needs |
|---|---|---|---|---|---|
| 0a | x402scan | ✅ LIVE | x402scan.com → resources?origin=api.cortexcloud.org (HTTP 200) | 2026-07 | price refresh: register page is JS-only; needs x402scan-MCP or browser (see below) |
| 0b | mppscan | ✅ LIVE | mppscan.com → search `api.cortexcloud.org` | 2026-07 | none |
| 0c | Poncho AI | ✅ LIVE | https://tryponcho.com/m/api.cortexcloud.org | 2026-07 | none (HTTP 200 verified 08-08) |
| 0d | AgentCash dir | ⚠️ AUTO | agentcash.dev/apis (fed by x402scan/mppscan) | — | verify presence |
| 1 | Smithery | ✅ LIVE | https://smithery.ai/servers/ampwerajonathan50/cortexcloud-mcp | 2026-08-08 | none (hosted proxy responding; v0.4.0) |
| 2 | Glama | 🧰 PREPARED | glama.ai/mcp/servers/… (est.) | — | Jonathan: account + submit URL |
| 3 | mcp.so | 🧰 PREPARED | mcp.so/servers/cortexcloud (est.) | — | Jonathan: submit form |
| 4 | PulseMCP | 🧰 PREPARED | pulsemcp.com (est.) | — | Jonathan: submit form |
| 5 | awesome-mcp-servers | 🧰 PREPARED | PR to punkpeye/awesome-mcp-servers | — | Jonathan: approve/`gh pr create` |
| 6 | apis.guru | 🧰 PREPARED | PR to APIs-guru/openapi-directory | — | Jonathan: approve/`gh pr create` |
| 7 | Official MCP Registry | ⛔ BLOCKED | registry.modelcontextprotocol.io | — | npm passkey publish (Lenovo/iPhone) + registry GitHub auth |

## Kit 1 — Smithery
```bash
npm i -g @smithery/cli
smithery login          # GitHub OAuth (Jonathan)
smithery mcp publish https://api.cortexcloud.org/mcp -n cortexcloud/cortexcloud
# metadata prompts: description = short desc above; categories: optimization; tags: x402, qubo, ising, usdc, quantum
```
Verify after publish: `https://smithery.ai/server/cortexcloud/cortexcloud`.

## Kit 2 — Glama (glama.ai/mcp)
1. Create account (GitHub OAuth) → glama.ai/mcp/servers → "Submit server".
2. Server URL: `https://api.cortexcloud.org/mcp` (remote HTTP — Glama probes it).
3. Name `CortexCloud` · description = short · category `optimization`.
Verify: `https://glama.ai/mcp/servers/cortexcloud-cortexcloud` (or search "cortexcloud").
Note: Glama also indexes from the official registry once live (metaregistry).

## Kit 3 — mcp.so
Form at `https://mcp.so/submit`: name `cortexcloud`, server URL `https://api.cortexcloud.org/mcp`,
description = short, category `AI / Optimization`. Verify: `https://mcp.so/servers/cortexcloud` (search "cortexcloud").

## Kit 4 — PulseMCP
Form at `https://pulsemcp.com` → Submit a server: URL `https://api.cortexcloud.org/mcp`, name `CortexCloud`,
description = short. Verify: pulsemcp.com search "cortexcloud". (Site is Cloudflare-fronted; 403 to bots — form only.)

## Kit 5 — awesome-mcp-servers (punkpeye/awesome-mcp-servers)
PR body / README addition:
```
- [CortexCloud](https://api.cortexcloud.org/mcp) - Pay-per-call QUBO/Ising optimization for AI agents: estimate free, solve per run (classical $0.05, hybrid $0.10, quantum $0.85) via x402 (USDC on Base). No API keys.
```
`gh` is authenticated as jonahthan433 — PR command ready:
```bash
gh repo clone punkpeye/awesome-mcp-servers /tmp/awesome-mcp && cd /tmp/awesome-mcp
# add line to README.md under relevant section, then:
git checkout -b add-cortexcloud && git add README.md && git commit -m "add CortexCloud MCP server"
gh pr create --title "Add CortexCloud MCP server" --body "Remote Streamable-HTTP MCP server: pay-per-call QUBO/Ising optimization via x402 (USDC on Base)."
```
(Requires Jonathan's approval before opening.)

## Kit 6 — apis.guru (APIs-guru/openapi-directory)
Submit via `https://apis.guru/add-api` — OpenAPI URL: `https://api.cortexcloud.org/openapi.json`
(the API is machine-readable; apis.guru fetches + validates it). This creates a PR in
APIs-guru/openapi-directory — approve as jonahthan433. Prepared issue/PR text:
```
Add CortexCloud Optimization Network — pay-per-call QUBO/Ising optimization API over x402 (USDC on Base).
OpenAPI: https://api.cortexcloud.org/openapi.json (self-maintained, 14 paths, 1 paid x402 operation).
```
Verify: apis.guru → search "cortexcloud".

## Kit 7 — Official MCP Registry (registry.modelcontextprotocol.io)
Server metadata (server.json) — verify exact schema in the registry UI at submission time:
```json
{
  "name": "github.jonahthan433/cortexcloud",
  "description": "Pay-per-call QUBO/Ising optimization for AI agents over x402 (USDC on Base). Estimate free, solve per run ($0.05-$0.85). Quantum QPU opt-in, benchmark-gated.",
  "version": "0.4.0",
  "remotes": {
    "https://api.cortexcloud.org/mcp": {}
  }
}
```
Publish path (both need Jonathan): (a) npm `@cortexcloud/mcp-server` — publish blocked headless
(passkey-only 2FA; run from Lenovo/iPhone), then register via registry website (GitHub auth);
or (b) attach server.json to a GitHub release of jonahthan433/CortexCloudAPI and register via
the registry website. Verify: registry.modelcontextprotocol.io → search "cortexcloud".

## Already-live verification (08-08)
- tryponcho.com/m/api.cortexcloud.org → HTTP 200, title "CortexCloud API • Poncho" ✅
- api.cortexcloud.org/mcp, /openapi.json, /.well-known/agentsearch.txt → HTTP 200 ✅
- x402scan.com/resources?origin=api.cortexcloud.org → HTTP 200 (client-rendered explorer; per-resource
  price display not extractable headlessly). Registration flow: public page
  x402scan.com/resources/register accepts a URL and auto-validates; the page is JS-only, so
  refreshing the scanned prices needs either a browser or the x402scan-MCP server
  (`npx -y x402scan-mcp@latest`). The served manifest (/.well-known/x402.json) is dynamic and
  already carries $0.85 — agents pay the correct amount regardless of the scan's cached display.
- mppscan: registered 2026-07 (entry via mppscan.com search).
- agentcash.dev/apis: fed automatically from the scans; verify "CortexCloud" appears.

## Paid-call watchdog (live 08-08)
- `cc-paid-call-watch` cron (every 30m, silent unless a new settled payment lands) reads
  `scripts/paid_metrics.py` (read-only settled-payment counters) on CT105 → alerts with
  total/10 + revenue + per-mode breakdown. Target: first 10 real paid optimization calls.
- Note: `INTERNAL_TOKEN` is unset in prod → `/internal/metrics` returns 503. The watchdog uses
  the DB read path instead; enable INTERNAL_TOKEN later if the revenue endpoint is wanted.

## Next actions (Jonathan only)
1. Smithery publish (2 min) → highest-value MCP listing
2. Glama + mcp.so + PulseMCP forms (~5 min each)
3. Approve 2 PRs (awesome-mcp-servers, apis.guru) — commands above, gh ready
4. Official registry: npm publish from Lenovo/iPhone (passkey) or GitHub-release path
