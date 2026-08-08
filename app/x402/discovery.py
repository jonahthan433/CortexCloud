"""Root discovery endpoints — /.well-known/x402.json and /llms.txt.

Generated at request time from live config (app.x402.pricing) so they
never describe a stale surface. Covers the paid route (/v1/optimize) and
the free endpoints agents need.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.x402.pricing import FREE_ROUTES, MODE_PRICE_USD, ROUTE_DESCRIPTIONS, ROUTE_PRICING, effective_price_usd

router = APIRouter()


def _usd_atomic(price_str: str) -> str:
    try:
        return str(int(float(price_str.lstrip("$")) * 1_000_000))
    except ValueError:
        return "0"


def build_manifest(active: bool = True) -> dict:
    if not active:
        return {"x402": False, "message": "x402 payment gateway is not enabled on this instance."}

    endpoints = [
        {
            "path": path.split(" ", 1)[1],
            "method": path.split(" ", 1)[0],
            "price": price,
            "price_atomic_usdc": _usd_atomic(price),
            "description": ROUTE_DESCRIPTIONS.get(path, "Solve an optimization problem (x402-paid)"),
        }
        for path, price in ROUTE_PRICING.items()
        if float(price.lstrip("$")) > 0.0
    ]

    return {
        "x402": True,
        "version": 2,
        "facilitator": settings.X402_FACILITATOR_URL,
        "merchant_wallet": settings.WALLET_ADDRESS,
        "pricing_currency": "USDC",
        "pricing_decimals": 6,
        "network": {"chainId": 8453, "eip155": settings.X402_NETWORK, "name": "Base"},
        "endpoints": endpoints,
        "free_endpoints": [
            {"path": p.split(" ", 1)[1], "method": p.split(" ", 1)[0], "description": d}
            for p, d in FREE_ROUTES.items()
        ],
    }


@router.get("/.well-known/x402.json", tags=["x402 Discovery"])
async def well_known_x402():
    return build_manifest()


@router.get("/.well-known/x402", tags=["x402 Discovery"])
async def well_known_x402_v1():
    """v1 discovery document (resource URL list) — the shape x402scan-mcp and
    other v1 discovery tools parse. The rich v2 manifest stays at x402.json."""
    return {
        "version": 1,
        "resources": [
            "https://api.cortexcloud.org/v1/optimize",
            "https://api.cortexcloud.org/v1/estimate",
            "https://api.cortexcloud.org/v1/backends",
            "https://api.cortexcloud.org/v1/capabilities",
            "https://api.cortexcloud.org/v1/examples",
        ],
        "instructions": "Pay-per-call QUBO/Ising optimization via x402 (USDC on Base eip155:8453). Full pricing: https://api.cortexcloud.org/v1/capabilities; rich manifest: https://api.cortexcloud.org/.well-known/x402.json; agent docs: https://api.cortexcloud.org/llms.txt.",
    }


@router.get("/.well-known/agentsearch.txt", tags=["x402 Discovery"])
async def agentsearch_txt():
    """Agent-search discovery file (agentsearch.txt convention): what this
    service is, how agents call it, and where the machine-readable docs live."""
    prices = " / ".join(f"{m} ${effective_price_usd(m):.2f}" for m in MODE_PRICE_USD)
    text = "\n".join([
        "Name: CortexCloud Optimization Network",
        "Description: Pay-per-call QUBO/Ising optimization API over x402 (USDC on Base, eip155:8453). Estimate is free; optimize is paid per run. Prices: " + prices + ". Quantum QPU execution is opt-in and only recommended with benchmark evidence.",
        "Human URL: https://api.cortexcloud.org/",
        "Commands:",
        "- POST /v1/estimate with {mode, n, data} for a free recommendation (decision block) and price.",
        "- POST /v1/optimize with {mode: auto|classical|hybrid|quantum, n, data} to solve; a 402 x402 challenge is returned, settle USDC on Base, then poll the job.",
        "- GET /v1/jobs/{job_id} to poll job status (succeeded/failed + solution).",
        "- GET /v1/backends for backends, availability, and per-backend provider cost.",
        "Discovery: https://api.cortexcloud.org/llms.txt, https://api.cortexcloud.org/.well-known/x402.json, https://api.cortexcloud.org/.well-known/bazaar, https://api.cortexcloud.org/.well-known/agentsearch.txt, https://api.cortexcloud.org/openapi.json",
        "Pricing: https://api.cortexcloud.org/v1/capabilities",
    ])
    return PlainTextResponse(text + "\n", media_type="text/plain; charset=utf-8")


@router.get("/llms.txt", tags=["x402 Discovery"])
async def llms_txt():
    paid = [
        f"- {path.split(' ', 1)[0]} {path.split(' ', 1)[1]} — {price}"
        for path, price in sorted(ROUTE_PRICING.items())
        if float(price.lstrip("$")) > 0.0
    ]
    free = [f"- POST {path} — {desc}" for path, desc in sorted(FREE_ROUTES.items())]

    text = f"""# CortexCloud

CortexCloud — optimization infrastructure for AI agents. Agents discover,
pay for, and execute classical, hybrid, or quantum optimization through a
single API. Pay per call in USDC (Base, eip155:8453) via the x402 payment
protocol — no API keys, no subscriptions. Settlement is permissionless.

## Workflow (agent-first)

1. POST /v1/estimate (free) — describe your QUBO/Ising problem; get the
   recommended mode (classical/hybrid/quantum), algorithm, backend,
   estimated runtime and USDC price, based on measured benchmarks.
2. POST /v1/optimize (x402, paid) — submit the same problem; receive a
   job_id. Signed payment challenge details are returned on 402.
3. GET /v1/jobs/{{job_id}} (free) — poll until the job completes; the result
   contains solution assignments and the objective value.

## Endpoints

{chr(10).join(paid + free)}

## Input format (QUBO)

{{"problem_type": "qubo", "n": 3, "data": {{"linear": [1.0, 2.0, 3.0], "quadratic": {{"0,1": -2.0, "1,2": 1.5}}}}}}

## Decision block (machine-friendly)

POST /v1/estimate returns a top-level "decision" object agents can branch
on directly: {{"recommended": true, "mode": "classical", "provider": "local",
"backend": "brute-force", "algorithm": "...", "reason": "...",
"estimated_cost_usd": 0.0, "cortexcloud_price_usd": 0.05,
"quantum_available": false, "quantum_recommended": false}}.
"recommended" is false only when no usable solver exists. Quantum is never
recommended without benchmark evidence; if you explicitly need quantum,
check /v1/backends for an available=true quantum backend first.

## When NOT to use

- n > 5000 variables (rejected with 422).
- Problems that are not QUBO/Ising form — this is an optimization API, not a general MIP solver.
- Guaranteed global optimum for n > 18 (classical exact enumeration caps at 18; annealing is a heuristic).
- quantum mode when /v1/backends shows no available=true backend (job fails honestly; no fake hardware).

## Examples

Canonical portfolio / assignment / scheduling / routing / generic-QUBO
examples (request JSON, expected schema, constraints, response, pricing):
GET /v1/examples (free).

## Discovery

- MCP server (Streamable HTTP): https://api.cortexcloud.org/mcp
- Payment manifest (x402): https://api.cortexcloud.org/.well-known/x402.json
- Bazaar discovery: https://api.cortexcloud.org/.well-known/bazaar
- OpenAPI: https://api.cortexcloud.org/openapi.json
- Agent examples: https://api.cortexcloud.org/v1/examples

## Honesty

Quantum execution is never faked and never claimed superior without
benchmark evidence: /v1/backends lists availability, /v1/estimate routes
to classical whenever it is cheaper/faster, and the Origin Quantum token
must be configured before the wukong backend reports available.

## Reference

- GitHub: https://github.com/jonahthan433/CortexCloudAPI
"""
    return PlainTextResponse(text, media_type="text/plain; charset=utf-8")