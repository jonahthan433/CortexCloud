# CortexCloud — Registry Submission Package (prepared)

Paste-ready listings for MCP registries and agent marketplaces. All copy uses
capability-based, verb+outcome framing (Glama's own research: LLMs select such
descriptions 260% more often). Submit in this order: Glama → Smithery →
AgentCash polish → CrewAI marketplace.

## 1. Glama — glama.ai/mcp/servers (free)

- **Name:** cortexcloud
- **GitHub:** https://github.com/jonahthan433/CortexCloudAPI
- **Server URL (remote):** https://api.cortexcloud.org/mcp
- **Categories:** AI/ML · Optimization · Quantum Computing · Developer Tools
- **Short description:**
  > Solve QUBO/Ising optimization problems — portfolio selection, vehicle
  > routing, bin packing, scheduling — with classical, hybrid, or real quantum
  > backends. Pay per call in USDC via x402. No API keys, no signup.

- **Long description (verb + outcome framing):**
  > CortexCloud lets agents and developers **solve** combinatorial
  > optimization problems without any account or API key. **Estimate** the
  > exact price for free, **pay** per call in USDC on Base via the x402
  > protocol, and **receive** verified solutions with signed execution
  > receipts. **Minimize** routing cost, **select** portfolios under
  > cardinality constraints, **pack** items into the minimum number of bins,
  > **schedule** staff or jobs — all through one MCP server with four tools.
  > Real quantum hardware (IBM, Rigetti) for problems beyond classical limits.

## 2. Smithery — smithery.ai (free)

- **Name:** @cortexcloud/mcp
- **Install:**
  ```
  npx -y @smithery/cli install @cortexcloud/mcp --client claude
  ```
- **Categories:** Optimization · AI Agents · Quantum · Analytics
- **Description:**
  > Pay-per-call QUBO/Ising optimization for AI agents. Estimate free, solve
  > from $0.05 (classical) to $1.503 (real QPU), settle in USDC on Base via
  > x402 — no API key, no signup. Four tools: estimate, optimize, poll jobs,
  > list backends. Domain presets turn plain constraints into QUBO matrices
  > automatically (portfolio, bin-packing, routing).

## 3. AgentCash listing polish — agentcash.dev (already listed)

Replace the listing description with:
> Solve portfolio selection, vehicle routing, bin packing, and scheduling
> problems as QUBO/Ising. Classical from $0.05, hybrid $0.10, real quantum
> hardware $1.503. Free estimate + free dry-run simulation before you pay.
> Settles automatically via x402/MPP — no API keys, no human checkout.

## 4. CrewAI Enterprise Marketplace — marketplace.crewai.com (revenue share)

- Fork the marketplace submission template, fill:
  - **Name:** CortexCloud Optimization
  - **Tagline:** Pay-per-call QUBO/Ising optimization (classical → real quantum)
  - **Category:** Optimization / Quantum / Data
  - **Description:**
    > Crews that need scheduling, routing, portfolio, or resource-assignment
    > decisions get an exact price before paying, and solutions with signed
    > receipts. Free estimate, free simulate, then pay per solve in USDC via
    > x402. Works through MCP or direct REST — no API key management.
  - **Pricing model:** per-call ($0.05–$1.503) · **Revenue share:** opt-in

## 5. MCP tool descriptions (for the next bundle build — src/http.ts)

Apply when the source repo is available (bundle currently ships these; the
source lives on the dev machine):

| Tool | Current-ish | Rewrite to |
|---|---|---|
| estimate | Analyze a problem | **Estimate the exact price and recommended solver** for a QUBO/Ising problem (free) |
| optimize | Solve (paid) | **Solve a QUBO/Ising optimization problem** — pays per call via x402, returns a job_id |
| jobs | Poll job | **Retrieve the solution** for a submitted optimization job |
| backends | List backends | **List available solvers** and their live availability |

## Checklist before submitting

- [ ] `curl https://api.cortexcloud.org/health` → 200 (live)
- [ ] `curl https://api.cortexcloud.org/mcp` responds to MCP initialize (live, verified 0.4.0)
- [ ] OpenAPI at /openapi.json declares all 19 paths with rich descriptions (done)
- [ ] llms.txt advertises presets + simulate (done 2026-08-19)
