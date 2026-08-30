# Outreach Drafts — PREPARED, NOT SENT
Posting requires Jonathan's accounts/approval. Each draft is written to be
legitimate (no spam, no fabricated metrics). Measure clicks via
utm_source links (tracked by /v1/track).

## E3 — Show HN (Hacker News)
Title: Show HN: CortexCloud — agent-native x402 API platform (Automation, Data, Research, Optimization/Quantum)

> I built CortexCloud — an agent-native, pay-per-use API platform settled by x402 (USDC on Base, no API keys). Agents call Automation (safe outbound HTTP), Data (on-chain prices/balances/gas), Research (web search + answers), AI, and Optimization/Quantum (QUBO/Ising solvers for scheduling/routing/portfolio).
>
> Easiest to start: Automation and Data at $0.004/call, Research at $0.006. Optimization/Quantum is the technical differentiator — classical, hybrid, and real Rigetti QPU backends, benchmark-gated.
>
> Agent flow: POST /v1/estimate (free) -> recommends mode + price -> paid endpoint returns an x402 challenge -> agent pays USDC on Base per call. No signup, no API keys — the wallet is the account. MCP server so Claude/Cursor/Codex call it directly: claude mcp add cortexcloud --transport http https://api.cortexcloud.org/mcp
>
> Free to try: https://api.cortexcloud.org/?utm_source=hn — estimate never charges. Examples: https://github.com/jonahthan433/CortexCloudAPI/tree/main/docs
>
> Why x402: agents need micropayments without accounts. Happy to discuss the QUBO formulation, the benchmark-gated quantum routing, or the MCP tooling.

## E4a — r/quantumcomputing
Title: [P] Pay-per-call QUBO solving with a real Rigetti QPU over x402 — no accounts, USDC on Base

> CortexCloud routes QUBO/Ising problems to classical, hybrid (QAOA) or
> quantum (Rigetti Cepheus via AWS Braket) backends. Agents pay per call with
> x402 micropayments. Quantum is only recommended when benchmarks support it
> — the estimate endpoint shows the evidence. Free to probe:
> https://api.cortexcloud.org/?utm_source=reddit_qc
> MCP: https://api.cortexcloud.org/mcp (4 tools). Not an ad for a company —
> open to feedback on the routing/benchmark design.

## E4b — r/algorithms / r/optimization
Title: [P] A pay-per-call API for QUBO/Ising optimization — agents can solve scheduling/routing/allocation problems

> Some of us build agents that hit OR problems (scheduling, routing,
> allocation). I made a tiny API that takes QUBO/Ising, estimates the best
> solver (exact/annealing/QAOA/quantum), and charges per run via x402 (USDC).
> Zero signup. Estimates are free: https://api.cortexcloud.org/?utm_source=reddit_opt
> Would love solver feedback — especially on when QAOA/quantum is worth it.

## E8 — X post (#x402 #aiagents #quantum)
> Optimization infrastructure for AI agents is live.
> Estimate free → solve from $0.05 → pay per run with x402 (USDC on Base).
> Classical, hybrid, and a real Rigetti QPU — benchmark-gated, never hype.
> MCP-ready: claude mcp add cortexcloud --transport http https://api.cortexcloud.org/mcp
> https://api.cortexcloud.org/?utm_source=x
