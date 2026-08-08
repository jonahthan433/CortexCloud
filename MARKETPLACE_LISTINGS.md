# MARKETPLACE_LISTINGS.md — Agent/API Marketplace Audit & Listing Kit

Audit date: 2026-08-08. Goal: get CortexCloud listed where AUTONOMOUS AGENTS can
discover it and call the paid optimization API directly (x402 USDC-on-Base or MCP).
Nothing here is submitted; every item needing credentials/approval is marked
`ACTION: JONATHAN`. Canonical facts (endpoints, prices) come from the live API —
refresh via `scripts/update_state.py` output if prices change.

## Canonical listing facts (use everywhere)

- Base URL / paid route: `POST https://api.cortexcloud.org/v1/optimize` (x402)
- Free: `POST /v1/estimate` · `GET /v1/jobs/{id}` · `GET /v1/backends` · `GET /v1/capabilities` · `GET /v1/examples`
- Prices (USDC on Base, eip155:8453, 6 decimals): classical $0.05 (50000) · hybrid $0.10 (100000) · quantum $0.85 (850000)
- Payee: `0x5a0353bc9c75b893a9b5735d3e79f1bd988ea143` (primary; challenge `accepts` advertises wallets)
- MCP: `https://api.cortexcloud.org/mcp` (Streamable HTTP + stdio; 4 tools; v0.4.0) — tools wrap the REST surface 1:1 and pay x402 automatically
- Discovery: `/llms.txt` · `/.well-known/x402.json` · `/.well-known/bazaar` · `/.well-known/agentsearch.txt` · `/openapi.json`
- Repo: https://github.com/jonahthan433/CortexCloudAPI (public, for registry review)

### Canonical description
- Short (~120 chars): `Pay-per-call QUBO/Ising optimization API for AI agents. Estimate free, solve per run via x402 (USDC on Base). $0.05-$0.85/run, no API keys.`
- Long (directories/forms):
  `CortexCloud Optimization Network — pay-per-call QUBO/Ising optimization for autonomous agents. Estimate for free (decision block: mode, backend, provider cost, price), then solve per run: classical $0.05, hybrid $0.10, quantum $0.85, paid via x402 in USDC on Base (no API keys, no signup). Quantum QPU execution (Rigetti via Amazon Braket) is opt-in and only recommended with benchmark evidence. MCP server at /mcp (cortex_estimate_optimization, cortex_optimize, cortex_get_job, cortex_list_backends).`

## Tier 1 — x402-native marketplaces (agents pay per call directly) — DONE / VERIFY

| Platform | URL | Status | Action |
|---|---|---|---|
| x402scan | x402scan.app | ✅ REGISTERED (14 resources) | Verify quantum price shows $0.85/850000; refresh if stale |
| mppscan | mppscan (Merit) | ✅ REGISTERED | Verify as above |
| Poncho AI | tryponcho.com/m/api.cortexcloud.org | ✅ REGISTERED | Verify |
| AgentCash directory | agentcash.dev/apis | ⚠️ AUTO (feeds from x402scan+mppscan) | Search "CortexCloud" in the directory; if absent, re-check scan entries (category/summary fields drive it) |

Note: AgentCash's directory is populated from x402scan/mppscan listings, so the
highest-leverage single action is keeping the two scan entries accurate
(category = optimization, summary with prices). Agents with AgentCash wallets
can already call the API today.

## Tier 2 — MCP directories (agents install the MCP server; x402 pays inside tools)

| Platform | Submission | Cost | Needs | Priority |
|---|---|---|---|---|
| smithery.ai | `smithery mcp publish https://api.cortexcloud.org/mcp -n cortexcloud/cortexcloud` (CLI or web) | free | GitHub account (Jonathan) | 1 |
| glama.ai/mcp | Submit server URL at glama.ai (has a submit tool); metaregistry, ~21k servers, daily index | free | account | 2 |
| mcp.so | https://mcp.so/submit (name, URL, description, category) | free | none sensitive; still a public submit | 3 |
| PulseMCP | pulse.mcp.so submit form | free | account | 4 |
| awesome-mcp-servers (punkpeye) | GitHub PR adding one line (content below) | free | PR from jonathan444 | 5 |
| registry.modelcontextprotocol.io (official) | npm publish of an MCP package + server.json | free | ⛔ BLOCKED: npm 2FA is passkey-only — publish from Lenovo (fingerprint) or iPhone | 6 |

Entry for awesome-mcp-servers (PR body):
```
- [CortexCloud](https://api.cortexcloud.org/mcp) - Pay-per-call QUBO/Ising optimization for AI agents: estimate free, solve per run (classical $0.05, hybrid $0.10, quantum $0.85) via x402 (USDC on Base). No API keys.
```
Suggested smithery metadata: name `cortexcloud/cortexcloud`, categories `optimization, quantum, payments`, tags `x402, qubo, ising, usdc`.

## Tier 3 — API directories agents read (OpenAPI-driven)

| Platform | Submission | Notes | Priority |
|---|---|---|---|
| apis.guru | https://apis.guru/add-api (PR to APIs-guru/openapi-directory with openapi.json) | machine-readable; agent tooling (incl. a GPT plugin) reads it | 3 |
| RapidAPI | publisher account + spec upload | human-first, key-based (not x402) — weak fit for agent-direct payments | low |

For apis.guru: submit `https://api.cortexcloud.org/openapi.json` (already served, self-updating).

## Tier 4 — Self-discovery (already live, zero listing) — FOUNDATION

Agents can already find the service without any listing: `/llms.txt`,
`/.well-known/agentsearch.txt`, `/.well-known/x402.json`, `/.well-known/bazaar`,
`/openapi.json`. All Tier 1–3 listings should point at these URLs.

## Backlog / next moves (no submissions made)

1. ✅ Verify scan entries' price fields ($0.85 quantum) — keeps AgentCash directory accurate
2. Jonathan: `smithery mcp publish` (GitHub auth) — highest-value MCP listing
3. Jonathan: glama + mcp.so + PulseMCP form submissions (5 min each)
4. Jonathan: open awesome-mcp-servers PR (one line above)
5. Jonathan: apis.guru PR with openapi.json
6. Official MCP registry: npm publish from Lenovo/iPhone (passkey) — package the existing bundle as `@cortexcloud/mcp-server`
7. Long-tail (when idle): mcpdirectory.com, cursor.directory, x402jp.com (Japan Bazaar), note.com/x402inc outreach
