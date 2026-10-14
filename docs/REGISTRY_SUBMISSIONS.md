# CortexCloud — Registry Submission Package

Paste-ready listings for MCP registries and agent marketplaces. Full-platform
positioning (Automation / Data / Research lead; Optimization/Quantum as
differentiator). Submit in this order: Glama → mcp.so → PulseMCP → Smithery
(already LIVE) → CrewAI.

All copy is capability-based, verb+outcome framing. Server URL is the same for
every registry: `https://api.cortexcloud.org/mcp`.

## 1. Glama — glama.ai/mcp/servers (free)
- **Name:** cortexcloud
- **GitHub:** https://github.com/jonahthan433/CortexCloudAPI
- **Server URL (remote):** https://api.cortexcloud.org/mcp
- **Categories:** AI / Developer Tools / Data / Automation / Research
- **Short description:**
  > Agent-native x402 API platform: Automation, Data, Research, AI, and
  > Optimization/Quantum. Pay per call in USDC on Base — no API keys.
- **Long description (verb + outcome):**
  > CortexCloud lets agents **call** paid API tools with no account or API key.
  > **Estimate** any optimization problem for free, **pay** per call in USDC on
  > Base via x402, and **receive** results with signed receipts. **Fetch** token
  > prices and on-chain balances, **run** web research with citations, **fire**
  > HTTP requests from the agent, and **solve** QUBO/Ising optimization
  > (classical → real quantum). Four MCP tools cover estimate, optimize, job
  > polling, and backend listing.

## 2. mcp.so (free)
- **Name:** cortexcloud
- **Server URL:** https://api.cortexcloud.org/mcp
- **Category:** AI / Agent / Automation / Data
- **Description:**
  > Agent-native x402 pay-per-call API: Automation, Data, Research, AI,
  > Optimization/Quantum. USDC on Base, no API keys. MCP server with 4 tools.

## 3. PulseMCP — pulsemcp.com/servers (free)
- **Name:** CortexCloud
- **Server URL:** https://api.cortexcloud.org/mcp
- **Category:** AI Agents / Developer Tools / Data
- **Description:**
  > Pay-per-call agent API via x402 (USDC on Base). Automation, Data, Research,
  > AI, Optimization/Quantum — no API key. `claude mcp add cortexcloud` to install.

## 4. Smithery — smithery.ai (already LIVE: @cortexcloud/mcp)
- Verify listing shows full-platform copy; update description if still
  optimization-only:
  > Agent-native x402 API: Automation, Data, Research, AI, Optimization/Quantum.
  > Pay per call in USDC on Base. `npx -y @smithery/cli install @cortexcloud/mcp --client claude`

## 5. CrewAI Enterprise Marketplace — marketplace.crewai.com (revenue share)
- **Name:** CortexCloud
- **Tagline:** Agent-native x402 pay-per-call API (Automation, Data, Research, Opt/Quantum)
- **Category:** Automation / Data / Optimization
- **Description:**
  > Crews that need on-chain data, web research, HTTP actions, or optimization
  > decisions get an exact price before paying, and results with signed
  > receipts. Free estimate, then pay per call in USDC via x402. MCP or REST.

## 6. MCP tool descriptions (next bundle build — src/http.ts)
| Tool | Rewrite to |
|---|---|
| estimate | **Estimate the exact price** for any CortexCloud call (free) |
| optimize | **Solve** an Optimization/Quantum problem — pays via x402, returns job_id |
| jobs | **Retrieve the solution** for a submitted job |
| backends | **List available solvers** and live availability |

## 7. minia2a — minia2a.uk (manual submit, no open API)
Submit via their "list a service" form / contact (M2M micropayment marketplace,
173 services, x402 USDC on Base, 5% fee). Paste-ready listing:

- **Name:** CortexCloud
- **Endpoint:** https://api.cortexcloud.org
- **Categories:** Automation · Data · Research · AI · Optimization/Quantum
- **Description:**
  > Agent-native x402 pay-per-call API platform. Automation (HTTP/webhook/
  > schedule/workflow), on-chain Data (token prices, balances, blocks, gas via
  > Alchemy/CoinGecko), Research (search + cited answers), AI (chat/embed/
  > transcribe), and Optimization/Quantum (QUBO/Ising, classical → real QPU).
  > Pay per call in USDC on Base — no API keys, no subscription. Free estimate
  > before every paid call. MCP server at /mcp.
- **Pricing:** per-call, $0.004 (Data/AI/Automation) → $0.05 (Opt classical) →
  $1.503 (real quantum). Discovery: /.well-known/x402.json (discoverable:true,
  in x402 Bazaar), /llms.txt, /openapi.json.

## Checklist before submitting
- [x] `curl https://api.cortexcloud.org/health` → 200
- [x] `/mcp` responds to MCP initialize (verified 0.4.0)
- [x] `/.well-known/x402.json` has `discoverable: true` (Bazaar-indexed)
- [x] `llms.txt` full-platform (ML marked preview-only)
- [x] Smithery + Official Registry descriptions refreshed to full platform (pushed 37dcde0)
- [ ] Glama / mcp.so / PulseMCP submitted (needs GitHub account — links in §1-3)
- [ ] minia2a submitted (paste §7)
- [ ] Smithery live description re-sync (auto from repo; verify @cortexcloud/mcp)
