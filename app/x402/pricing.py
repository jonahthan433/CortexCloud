"""x402 pricing — single source of truth for paid/free routes.

/v1/optimize is the only paid route; its price follows the requested
mode (classical 0.05 / hybrid 0.10 / quantum 0.85). Everything else is
free. The middleware reads this dict by path to build the 402 challenge,
so this table is also what discovery (/.well-known/x402.json, llms.txt,
bazaar) renders.

Costs are kept separate from prices: MODE_PRICE_USD is what customers
pay; PROVIDER_COST_USD is our estimated per-run provider cost (model
basis; finer per-device estimates live in the solver adapters, e.g. the
braket device cfg). gross_margin_usd(mode) = price - cost. Quantum must
never be sold below estimated provider cost unless QUANTUM_ALLOW_SUBSIDY
=true (enforced in runner.quantum_cost_cap_error + braket preflight).
"""
from __future__ import annotations

# mode -> USD per optimization run (customer price)
MODE_PRICE_USD = {"classical": 0.05, "hybrid": 0.10, "quantum": 0.85}

# mode -> estimated provider cost per run, USD (model basis). Quantum
# reflects the verified Aug-2026 Rigetti Cepheus-1-108Q run (1024 shots,
# $0.35). Solver adapters may carry finer per-device estimates; this
# table is the documented default the margin guard reasons about.
# Quantum mode cost: $0.50/run (Braket rigetti, primary provider; fixed
# 1024 shots -> flat cost) + buffer. IBM Open Plan fallback costs $0.00 and
# stays sellable at the effective price via the per-provider margin guard.
# Verified Rigetti Cepheus-1-108Q on Braket: $0.30/task + $0.000425/shot
# (published rate card, Aug-2026) = $0.7352 at the fixed 1024 shots; round
# up 0.75 as the billing buffer. IBM Open Plan fallback costs $0.00.
PROVIDER_COST_USD = {"classical": 0.0, "hybrid": 0.0, "quantum": 0.75}

# Per-request fixed costs beyond provider spend (model basis):
INFRA_COST_USD = 0.0010     # compute, DB, bandwidth, Cloudflare, hosting
PAYMENT_COST_USD = 0.0005   # x402 verify + settlement relay + ledger write


def total_cost_usd(mode: str, provider_cost: float | None = None) -> float:
    """All-in cost of one paid request: provider + infra + payment."""
    m = (mode or "auto").lower()
    prov = PROVIDER_COST_USD.get(m, 0.0) if provider_cost is None else float(provider_cost)
    return prov + INFRA_COST_USD + PAYMENT_COST_USD

# Margin policy: the charged price for a mode is never below the list
# price, and never below provider_cost x MARKUP — prices move with
# provider cost automatically. List prices are the published floor.
MARKUP = 2.0

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
    "POST /v1/simulate": "Dry-run a problem (free) — feasibility and confidence score before paying for a solve.",
    "POST /v1/solvers/portfolio": "Build a cardinality-constrained Markowitz QUBO from returns/covariance (free).",
    "POST /v1/solvers/bin-packing": "Build a bin-packing QUBO from item weights and bin capacity (free).",
    "POST /v1/solvers/routing": "Build a TSP tour QUBO from a distance matrix (free).",
}


def price_for_mode(mode: str, n: int | None = None) -> str:
    return f"${effective_price_usd(mode, n=n):.6f}"


# Size-based classical pricing: exact brute-force fits n<=20, heuristic
# classical (SA) handles mid problems, large jobs are premium compute.
CLASSICAL_SIZE_TIERS: tuple[tuple[int, float], ...] = ((20, 0.05), (200, 0.10), (2**31 - 1, 0.25))


def classical_price_for_n(n: int) -> float:
    """Classical customer price by problem size (n variables)."""
    n = int(n or 0)
    for cap, price in CLASSICAL_SIZE_TIERS:
        if n <= cap:
            return price
    return 0.25


def effective_price_usd(mode: str, provider_cost: float | None = None, n: int | None = None) -> float:
    """Charged price for a mode: max(list price, provider cost x MARKUP).
    Classical/auto prices are size-aware (n tiers). provider_cost defaults
    to the mode's estimated provider cost, so the price rises automatically
    if provider costs climb."""
    m = (mode or "auto").lower()
    if m in ("classical", "auto") and n is not None:
        base = classical_price_for_n(n)
    else:
        base = MODE_PRICE_USD.get(m, MODE_PRICE_USD["classical"])
    cost = total_cost_usd(m, provider_cost)
    return max(base, cost * MARKUP)


def sellable_at_mode_price(mode: str, provider_cost: float) -> bool:
    """True when a provider's estimated cost fits under the charged price
    (margin >= 0 at current prices)."""
    try:
        return total_cost_usd(mode, provider_cost) <= effective_price_usd(mode)
    except (TypeError, ValueError):
        return False


def gross_margin_usd(mode: str) -> float:
    """Customer price minus estimated provider cost, USD."""
    m = (mode or "auto").lower()
    return effective_price_usd(m) - total_cost_usd(m)


def below_cost(mode: str) -> bool:
    """True when the route would sell below estimated provider cost."""
    return gross_margin_usd(mode) < 0.0


def usd_to_usdc_atomic(usd_str: str) -> int:
    try:
        return int(float(usd_str.lstrip("$")) * 1_000_000)
    except (TypeError, ValueError):
        return 0


def usdc_atomic_to_usd(atomic: int) -> float:
    return int(atomic) / 1_000_000
