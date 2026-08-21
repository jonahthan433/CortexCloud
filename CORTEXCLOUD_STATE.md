# CORTEXCLOUD_STATE.md — Authoritative Project State

Single source of truth for what CortexCloud Optimization Network IS, what it
charges, what is enabled, and what the commercialization backlog is. The Live
Snapshot section is regenerated weekly by `scripts/update_state.py`; the rest
is hand-maintained. Code is always the final truth (`app/x402/pricing.py` for
prices).

## What this is
Pay-per-call QUBO/Ising optimization API over x402 (USDC on Base, eip155:8453).
Classical + hybrid solvers run locally; quantum runs on real QPUs (Amazon
Braket / Origin) but live execution is OPT-IN and not enabled without a
business/benchmark reason. Goal: recurring external paid optimization calls.

## Live surface
- API: `cortexcloud.service` (uvicorn :8000) — `POST /v1/optimize` (paid),
  `POST /v1/estimate`, `GET /v1/jobs/{id}`, `GET /v1/backends`,
  `GET /v1/capabilities`, `GET /v1/examples` (free)
- Discovery: `/llms.txt`, `/.well-known/x402.json`, `/.well-known/bazaar`,
  `/.well-known/agentsearch.txt`, `/openapi.json`
- MCP: `cortexcloud-mcp.service` (Streamable HTTP :3100 + stdio) — 4 tools
  (cortex_estimate_optimization, cortex_optimize, cortex_get_job, cortex_list_backends)
- Gateway: `cortexcloud-gateway.service` (Node)
- Internal: `/internal/metrics` (X-Internal-Token) — revenue aggregates only, never public

## Pricing policy
| mode | list $ | est provider cost $ | margin $ |
|---|---|---|---|
| classical | 0.05 | 0.00 (local) | 0.05 |
| hybrid | 0.10 | 0.00 (local) | 0.10 |
| quantum | 0.85 | 0.35 (Rigetti Cepheus-1-108Q, 1024 shots, verified Aug 2026) | 0.50 |

- Charged price = `max(list, provider_cost × MARKUP 2.0)` — rises automatically with provider cost.
- Margin guard: quantum never sold below estimated provider cost unless `QUANTUM_ALLOW_SUBSIDY=true`.
- Per-backend `estimated_provider_cost_usd` / `effective_price_usd` / `sellable_at_mode_price` in `/v1/backends` and `/v1/capabilities`.
- Per-device provider costs (model basis): rigetti 0.35, iqm 0.40, aqt 0.30, quera 0.25, origin 0.25, ionq 3.40 (not sellable at 0.85 — margin guard).

## Safety gates (never loosen casually)
- `QUANTUM_LIVE_EXECUTION=false` default — live QPU is opt-in
- `QUANTUM_MAX_COST_USD=5.0` hard per-job provider-cost cap (runner + braket preflight)
- `QUANTUM_ALLOW_SUBSIDY=false` default — below-cost sales blocked
- Benchmarks: only real runs populate the ledger; quantum is never promoted without evidence

## Evidence / routing
- Every successful execution records a `Benchmark` row (provider cost, price, margin)
- `/v1/estimate` promotes quantum ONLY with benchmark evidence; otherwise classical/hybrid
- `benchmark_evidence(problem)` counts rows by problem_type (1 row today: the Aug-2026 Cepheus run)

## Revenue posture
- `/internal/metrics`: optimization_requests, paid_requests, settled/failed payments,
  revenue USD, margin USD, solvers_selected, providers_selected, revenue_by_mode,
  revenue_last_24h_usd (token-gated; 503 when INTERNAL_TOKEN unset, 401 on bad token)
- Every settled x402 request records a Payment row (mode, n_vars, amount, payer)

## Deploy & test (CT105 /opt/CortexCloudAPI)
```bash
/opt/cortexcloud-venv/bin/python -m pytest tests/ -q          # must be green
/opt/cortexcloud-venv/bin/python update_openapi_v2.py          # regen OpenAPI
systemctl restart cortexcloud.service                          # deploy API
systemctl restart cortexcloud-mcp.service                      # deploy MCP
curl -s localhost:8000/v1/capabilities                         # verify pricing
curl -s -X POST localhost:8000/v1/optimize -H 'Content-Type: application/json' \
  -d '{"mode":"quantum","n":3,"data":{"linear":[1,2,3],"quadratic":{"0,1":-2}}}'  # expect 402 + amount
curl -s localhost:8000/.well-known/agentsearch.txt             # verify discovery
```
MCP rebuild (from the source repo on the Hermes host):
`npx tsc --noEmit && npx --no-install esbuild src/http.ts --bundle --format=cjs --platform=node --outfile=dist/mcp-bundle.cjs` then push the bundle to CT105 `/opt/cortexcloud-mcp/mcp-bundle.cjs`.

## Commercialization backlog (hand-maintained — next moves)
1. Recurring external paid calls: agent-catalog listing, demo funnel, referrals
2. Benchmark accumulation: every paid classical/hybrid run adds routing evidence
3. Pricing experiments: hold quantum $0.85; revisit ionq sellability only if demand justifies
4. Agent discovery: verify llms.txt + agentsearch.txt crawlability; submit to agent directories
5. MCP registry: refresh listing after version bumps; keep tool descriptions in sync with the API

## Live snapshot

- commit: `c1e0dd3` (2026-08-17T05:01Z UTC)
- services: API=active MCP=active
- prices (list / est provider cost / effective): classical $0.05 / $0.00 / $0.05; hybrid $0.10 / $0.00 / $0.10; quantum $0.85 / $0.75 / $1.50
- markup: 2.0x
- benchmark_rows: 18   payments: 21   revenue_usd: 7.253000
- live QPU execution: off by default (QUANTUM_LIVE_EXECUTION=false)
