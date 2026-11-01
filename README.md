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

## Paid client examples (copy-paste)

Two reference buyers, both do the whole 402 -> sign -> replay loop for you:

- `examples/paid_client.py` — official Python SDK (`x402` + `eth-account` + `httpx`)
- `examples/paid_client.ts` — TypeScript / Bun (`@x402/fetch` + `@x402/evm` + `viem`)

```bash
pip install "x402" eth-account httpx
TEST_BUYER_KEY=0x... python examples/paid_client.py

bun add @x402/fetch @x402/evm viem
CC_PRIVATE_KEY=0x... \
CC_PATH=/v1/data/market-snapshot \
CC_BODY='{"contract":"0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48","chain":"ethereum"}' \
  bun run examples/paid_client.ts
```

Both default to `POST /v1/data/token-price` ($0.004) and accept `CC_URL`,
`CC_PATH`, `CC_BODY` overrides. The npm package `x402-fetch` is the deprecated
v1 client (it sends `X-PAYMENT`); this API settles x402 v2
(`PAYMENT-SIGNATURE`), so the TypeScript example uses its successor
`@x402/fetch`.

## New on the data surface

- `POST /v1/data/market-snapshot` — $0.070: token-intel + whale-alerts +
  token-risk fanned out in parallel (one 402 instead of three).
- `POST /v1/webhooks/whale-alerts` — $0.100 registration, $0.020 per delivered
  alert, HMAC-SHA256 signed when you supply a secret. `GET` (with `?owner=`)
  and `DELETE` (with `?token=`) are free.
- Solana (`"chain": "solana"`) on `token-balances`, `tx-history` and
  `token-price` via Helius; every other route answers a structured
  `chain_not_supported` instead of guessing.
- `whale-alerts` is now $0.050 (was $0.030) — three upstream scans per call.

## Discovery

- Agent terms: `/.well-known/x402.json`
- LLM docs: `/llms.txt`
- Examples: `/v1/examples`

Base URL: https://api.cortexcloud.org
