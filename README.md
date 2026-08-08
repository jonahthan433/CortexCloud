# CortexCloud — Optimization Infrastructure for AI Agents

> Automatically solve suitable problems using **classical or quantum** backends
> and **pay per optimization with x402** (USDC on Base). No API keys, no
> subscriptions — an agent can go from "discover" to "solved" in three calls.

**Live endpoint:** `https://api.cortexcloud.org` · **MCP:** `https://api.cortexcloud.org/mcp` · **Manifest:** `/.well-known/x402.json`

## Why it exists

LLMs can *describe* scheduling, routing, portfolio and allocation problems —
but they can't *solve* them. CortexCloud is the pay-per-call solving layer:
an agent formulates the problem as QUBO/Ising, we recommend the right solver
(classical, hybrid, or quantum on a real Rigetti QPU), and it pays per run
with x402 micropayments. No signup, no keys — the wallet is the account.

## Quickstart (agent / developer)

**1. Estimate — free.** Get the recommended mode, algorithm, backend, runtime
and price for your problem:

```bash
curl -s https://api.cortexcloud.org/v1/estimate \
  -H 'content-type: application/json' \
  -d '{"problem_type":"qubo","n":4,"data":{"linear":[1,-2,3,-4],"quadratic":{"0,1":-1.5}}}'
```

**2. Pay & solve — from $0.05.** `POST /v1/optimize` returns an x402
PaymentRequirements challenge (USDC on Base, chain 8453). Sign with your
wallet, resend, then poll the job:

```bash
curl -s https://api.cortexcloud.org/v1/optimize \
  -H 'content-type: application/json' \
  -d '{"problem_type":"qubo","n":4,"data":{"linear":[1,-2,3,-4],"quadratic":{"0,1":-1.5}}}'
# -> 402 + x402 challenge; settle USDC; resend with X-PAYMENT header
# -> {"job_id": "..."}
curl -s https://api.cortexcloud.org/v1/jobs/<job_id>
```

**3. Or connect an MCP client (Claude, Cursor, Codex):**

```bash
claude mcp add cortexcloud --transport http https://api.cortexcloud.org/mcp
```

Four tools: `cortex_estimate_optimization` (free), `cortex_optimize` (paid,
auto-x402), `cortex_get_job`, `cortex_list_backends`.

## Endpoints

| Endpoint | Method | Cost | Purpose |
|---|---|---|---|
| `/v1/estimate` | POST | free | analyze a QUBO/Ising, get mode/algorithm/backend/runtime/price |
| `/v1/optimize` | POST | x402 USDC | solve (classical/hybrid/quantum), returns `job_id` |
| `/v1/jobs/{id}` | GET | free | poll job status + result |
| `/v1/backends` | GET | free | list solvers/backends + availability |
| `/v1/capabilities` | GET | free | what this service is and what it can run |
| `/v1/examples` | GET | free | canonical portfolio/assignment/scheduling/routing/QUBO examples |
| `/mcp` | POST | free* | MCP server (Streamable HTTP): 4 tools (`cortex_optimize` paid) |
| `/.well-known/x402.json` | GET | free | x402 discovery manifest |
| `/.well-known/bazaar` | GET | free | bazaar/MCP discovery doc |
| `/openapi.json` | GET | free | OpenAPI 3.1 spec |

## Pricing

| Mode | Solver | Price |
|---|---|---|
| classical | `brute-force` (exact, n≤20) / `simulated-annealing` | $0.05 |
| hybrid | `qaoa-local` (QAOA + classical outer loop) | $0.10 |
| quantum | `rigetti` (Rigetti Cepheus QPU via AWS Braket) | $0.85 |

Quantum is only recommended with benchmark evidence — never on marketing.

## Examples

See [`examples/`](examples/) for copy-paste scheduling, portfolio and
delivery-routing problems (free estimates + paid solves).

## Agent discovery

- `llms.txt`, `/.well-known/agentsearch.txt`, `/.well-known/x402.json`, `/.well-known/bazaar`, `/openapi.json`
- MCP registries: official MCP Registry (`io.github.jonahthan433/cortexcloud`),
  Smithery, x402scan, mppscan, Poncho, AgentCash

## Development

- Tests: `pytest tests/ -q` (44 passing)
- State + ops: `CORTEXCLOUD_STATE.md`, `CT105_HARDENING.md`, `MARKETPLACE_LISTINGS.md`, `GTM_PLAN.md`
