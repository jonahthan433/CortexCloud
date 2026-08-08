"""Root discovery endpoints — /.well-known/x402.json and /llms.txt.

Generated at request time from live config (app.x402.pricing) so they
never describe a stale surface. Covers the paid route (/v1/optimize) and
the free endpoints agents need.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.x402.pricing import FREE_ROUTES, ROUTE_DESCRIPTIONS, ROUTE_PRICING

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

## Discovery

- MCP server (stdio + Streamable HTTP): /x402/v1/mcp
- Payment manifest: /.well-known/x402.json
- Bazaar discovery: /.well-known/bazaar
- OpenAPI: /openapi.json

## Honesty

Quantum execution is never faked and never claimed superior without
benchmark evidence: /v1/backends lists availability, /v1/estimate routes
to classical whenever it is cheaper/faster, and the Origin Quantum token
must be configured before the wukong backend reports available.

## Reference

- GitHub: https://github.com/jonahthan433/CortexCloudAPI
"""
    return PlainTextResponse(text, media_type="text/plain; charset=utf-8")