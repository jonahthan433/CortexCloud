# CortexCloud

An agent-native, pay-per-use API platform settled by x402 (USDC on Base). Call **Automation, Research, Data, Optimization, AI, and Quantum** endpoints — no API key, no subscription, pay only when it runs.

Easiest to start: **Automation** (safe outbound HTTP, $0.004), **Data** (token prices, balances, gas, $0.004), and **Research** (web search + synthesized answers, $0.006). **Optimization/Quantum** (QUBO/Ising solvers — classical, hybrid, quantum backends) is our technical differentiator for scheduling, routing, and portfolio problems.

## Quick start (free, no wallet)

```bash
curl https://api.cortexcloud.org/v1/examples
```

Returns worked request/response schemas for every problem type. For a free
price/feasibility preview of an optimization problem, use `POST /v1/estimate`
or `POST /v1/simulate` — both free, no wallet.

## What you can call

| Category | Cheapest | Example endpoints |
|---|---|---|
| **Automation** (start here) | $0.004 | `POST /v1/automation/http-request`, `/schedule`, `/transform`, `/webhook` |
| **Data** (start here) | $0.004 | `GET /v1/data/block`, `/gas-oracle`, `POST /v1/data/token-price`, `/token-balances` |
| **Research** (start here) | $0.006 | `POST /v1/research/search`, `/answer` |
| **AI** | $0.004 | `POST /v1/ai/chat`, `/embed`, `/transcribe` |
| **Optimization / Quantum** (differentiator) | $0.05 | `POST /v1/optimize` (QUBO/Ising: scheduling, routing, portfolio) |
| **ML** | — | Preview only; not yet generally available |

## Portfolio Optimization (Optimization/Quantum)

Minimize risk for a target return by selecting asset weights.

```bash
curl -X POST https://api.cortexcloud.org/v1/optimize \
  -H "Content-Type: application/json" \
  -d '{"problem":"portfolio","returns":[0.12,0.08,0.15],"cov":[[0.04,0.01,0.02],[0.01,0.03,0.01],[0.02,0.01,0.05]],"risk_aversion":0.5}'
```

Settled in USDC via x402 on Base. Get a free estimate first at `/v1/estimate`.

## Route Planning

Shortest tour across locations (TSP / vehicle routing).

```bash
curl -X POST https://api.cortexcloud.org/v1/optimize \
  -H "Content-Type: application/json" \
  -d '{"problem":"routing","coords":[[0,0],[3,4],[6,1],[2,7]]}'
```

## Job Scheduling

Sequence jobs to minimize makespan under precedence and capacity constraints.

```bash
curl -X POST https://api.cortexcloud.org/v1/optimize \
  -H "Content-Type: application/json" \
  -d '{"problem":"scheduling","jobs":[{"id":1,"dur":3,"deps":[]},{"id":2,"dur":2,"deps":[1]}]}'
```

## Payment model

Paid endpoints return an x402 `402 Payment Required` with USDC terms on Base.
Your x402 client settles the per-call price (from $0.05) and retries. No API key,
no account. Free endpoints: `/v1/trial` and `/v1/estimate`.

## Discovery

- Agent terms: `/.well-known/x402.json`
- LLM docs: `/llms.txt`
- Examples: `/v1/examples`

Base URL: https://api.cortexcloud.org
