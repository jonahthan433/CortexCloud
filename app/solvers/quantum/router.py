"""Quantum Backend Router — the single mode/provider/backend decision point.

Used by /v1/estimate (auto recommendation) and the job runner (explicit
modes). For every candidate solver it weighs availability (never select
an unavailable/unverified backend), capacity vs n, algorithm fit,
benchmark evidence, estimated cost and runtime.

Decision rules (evidence, not marketing):
- quantum backends are RECOMMENDED only when benchmark evidence exists
  for the problem family; an explicit force_mode="quantum" request may
  use any AVAILABLE quantum backend.
- classical exact (brute-force) wins when it fits; else heuristic
  classical; hybrid/quantum enter the ranking by cost.

Costs stay separate — provider_cost_usd is what the underlying compute
costs CortexCloud, cortexcloud_price_usd is the x402 customer price
(MODE_PRICE_USD). The router never compares them as one number; the
margin is derived, not paid.
"""
from __future__ import annotations

from typing import Any

from app.solvers import registry
from app.x402.pricing import MODE_PRICE_USD

BRUTE_FORCE_CAP = 18  # 2^18 evals — exact window used for auto ranking
LATENCY_TAX = 1e-4    # gentle runtime penalty so pricing isn't the only axis


def _candidate(solver, qubo: dict, n: int) -> dict[str, Any]:
    est = solver.estimate(qubo, n)
    provider_cost = est.price_usd
    from app.x402.pricing import effective_price_usd
    customer = effective_price_usd(solver.spec.mode, provider_cost, n=n)
    return {
        **est.to_dict(solver.spec),
        "solver_id": solver.spec.id,
        "provider": getattr(solver, "provider", "local"),
        "provider_cost_usd": round(provider_cost, 6),
        "cortexcloud_price_usd": round(customer, 6),
        "margin_usd": round(customer - provider_cost, 6),
        "_cost": provider_cost + est.runtime_s * LATENCY_TAX,
    }


def select(
    problem_type: str,
    qubo: dict,
    n: int,
    bench_count: int = 0,
    force_mode: str | None = None,
) -> dict[str, Any]:
    """Rank available solvers. force_mode restricts to one mode (used by
    the runner for explicit 'quantum'; None = auto)."""
    ranked: list[dict[str, Any]] = []
    quantum_gate = ""
    for s in registry.solvers():
        if not s.availability().available:
            continue
        if s.spec.mode == "quantum":
            if n > s.spec.max_variables:
                continue  # does not fit the device
            if force_mode != "quantum" and bench_count == 0:
                quantum_gate = quantum_gate or (
                    f"{s.spec.id} not recommended: no benchmark evidence for {problem_type}"
                )
                continue
        if force_mode and s.spec.mode != force_mode:
            continue
        ranked.append(_candidate(s, qubo, n))

    ranked.sort(key=lambda c: c["_cost"])
    for c in ranked:
        c.pop("_cost", None)

    if not ranked:
        return {
            "recommended": None,
            "ranked": [],
            "reason": f"no available solver for mode={force_mode or 'auto'}",
            "quantum_gate": quantum_gate,
        }
    best = ranked[0]
    return {
        "recommended": best,
        "ranked": ranked,
        "reason": _reason(best, bench_count, quantum_gate),
        "quantum_gate": quantum_gate,
    }


def _reason(best: dict[str, Any], bench_count: int, quantum_gate: str) -> str:
    mode = best["mode"]
    if mode == "classical":
        if best["solver_id"] == "brute-force":
            return "exact enumeration fits this size at lowest cost"
        return "heuristic classical (simulated annealing) — exact infeasible at this size"
    if mode == "hybrid":
        return "hybrid QAOA (local) — classical heuristic pricier or unavailable"
    evidence = f"{bench_count} benchmark row(s)" if bench_count else "explicit request"
    return f"quantum {best['provider']}/{best['backend']} chosen on {evidence} + cost"