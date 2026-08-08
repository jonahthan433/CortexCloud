# CortexCloud Optimization Network

**Optimization infrastructure for AI agents.** Agents discover, pay for, and
execute classical, hybrid, or quantum optimization through a single API:
machine-payable via x402 (USDC on Base), fully discovered via
`/.well-known/`, `llms.txt`, `/openapi.json` and MCP.

## The surface

| Endpoint | Method | Cost | Purpose |
|---|---|---|---|
| `/v1/estimate` | POST | free | analyze a QUBO/Ising, get mode/algorithm/backend/runtime/price |
| `/v1/optimize` | POST | x402 USDC | solve (classical/hybrid/quantum), returns `job_id` |
| `/v1/jobs/{id}` | GET | free | poll job status + result |
| `/v1/backends` | GET | free | list solvers/backends + availability |
| `/v1/capabilities` | GET | free | what this service is and what it can run |
| `/x402/v1/mcp` | POST | free* | MCP gateway: 4 tools (`cortex_optimize` paid) |
| `/.well-known/x402.json` | GET | free | x402 discovery manifest |
| `/.well-known/bazaar` | GET | free | bazaar/MCP discovery doc |
| `/llms.txt` | GET | free | agent-readable index |
| `/openapi.json` | GET | free | full OpenAPI (x402 security declared) |
| `/health` `/metrics` | GET | free | ops |

## Problem format

```json
{"problem_type": "qubo", "n": 4,
 "data": {"linear": [1.0, -2.0, 3.0, -4.0], "quadratic": {"0,1": -1.5, "2,3": 2.0}}}
```
`ising` uses `{"h": [...], "J": {"i,j": c}}`. Ising is converted to QUBO for execution.

## Solvers & honesty

- **classical**: `brute-force` (exact, n ≤ 20), `simulated-annealing` (n ≤ 5000). Pure stdlib.
- **hybrid**: `qaoa-local` — QAOA with a classical outer loop, exact state-vector simulation.
- **quantum**: `wukong` — Origin Quantum Wukong via Quafu cloud, isolated adapter
  (`app/solvers/origin.py`), **never reachable from the public API**, enabled only
  with `ORIGINQ_API_TOKEN`. The public API lies only behind `app.solvers.registry`.
- `/v1/estimate` NEVER recommends a backend without evidence. Quantum is only
  proposed when: (a) configured+available, AND (b) benchmark rows show it wins.
  `estimator` falls back to classical when it is cheaper/faster — no marketing.

Benchmark rows (`benchmarks` table) accumulate on every solved job so estimates
become measured, not modeled.

## Payments (x402)

`POST /v1/optimize` price follows the requested mode:
classical `$0.02`, hybrid `$0.10`, quantum `$0.25` (fixed per call). Free routes
never return 402. ECDSA-signed responses (`X-Cortex-Signature`), public key at
`/x402/v1/pubkey`. Nonces are replay-protected in PostgreSQL; proof cache +
per-payer + per-IP rates are in-process (single uvicorn worker).

## Local development

```bash
pip install -r requirements.txt          # base deps
pip install -r requirements-quantum.txt  # ONLY for the Wukong adapter
cp .env.example .env                     # fill DB + wallet values
alembic upgrade head
uvicorn app.main:app --reload
python update_openapi_v2.py              # regenerate /openapi.json
```

## Tests

```bash
pytest -q            # needs the real DB (new tables only; truncated per run)
```

## Origin Quantum (Wukong)

Adapter: `app/solvers/origin.py` — uses the current official Origin Quantum
cloud path (Quafu/ScQ-Cloud: API-token auth, program upload, submit, poll).
Config:
- `ORIGINQ_API_TOKEN` — from Origin Q Cloud console.
- `ORIGIN_BACKEND` — target device (default: picked from account listing at
  connect time, falls back to the env value).

Until a real token is configured the backend advertises `available: false` and
`/v1/estimate` will not recommend quantum mode. Real-device calibration is the
only remaining step (see SECURITY.md road-map).