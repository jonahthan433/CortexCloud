"""x402 pricing — single source of truth for paid/free routes.

/v1/optimize is the only paid route; its price follows the requested
mode (classical 0.02 / hybrid 0.10 / quantum 0.25). Everything else is
free. The middleware reads this dict by path to build the 402 challenge,
so this table is also what discovery (/.well-known/x402.json, llms.txt,
bazaar) renders.
"""
from __future__ import annotations

# mode -> USD per optimization run
MODE_PRICE_USD = {"classical": 0.05, "hybrid": 0.10, "quantum": 0.25}

ROUTE_PRICING = {
    "POST /v1/optimize": "$0.05",  # base; middleware overrides per mode
}

ROUTE_DESCRIPTIONS = {
    "POST /v1/optimize": "Solve a QUBO/Ising optimization problem. USDC on Base via x402; returns a job_id to poll.",
}

FREE_ROUTES = {
    "POST /v1/estimate": "Analyze a problem (free) — recommended mode/algorithm/backend, decision block for agents, estimated runtime and USDC price.",
    "GET /v1/jobs/{job_id}": "Poll an optimization job by id (free).",
    "GET /v1/backends": "List solver backends and availability (free).",
    "GET /v1/capabilities": "Service capabilities, limits, payment terms (free).",
    "GET /v1/examples": "Canonical portfolio/assignment/scheduling/routing/QUBO examples with schemas, constraints and pricing (free).",
}


def price_for_mode(mode: str) -> str:
    m = (mode or "auto").lower()
    if m in MODE_PRICE_USD:
        return f"${MODE_PRICE_USD[m]:.6f}"
    return f"${MODE_PRICE_USD['classical']:.6f}"  # auto defaults to classical


def usd_to_usdc_atomic(usd_str: str) -> int:
    try:
        return int(float(usd_str.lstrip("$")) * 1_000_000)
    except (TypeError, ValueError):
        return 0


def usdc_atomic_to_usd(atomic: int) -> float:
    return int(atomic) / 1_000_000