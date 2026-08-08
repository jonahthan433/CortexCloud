"""Estimation & auto mode selection.

/v1/estimate contract: analyze a QUBO/Ising, recommend the cheapest
honest path (mode -> provider -> backend -> algorithm). The actual
decision lives in app.solvers.quantum.router; this module formats the
response and keeps the honesty ledger (benchmark evidence + caveats).

Rules (evidence, not marketing):
1. Exact classical (brute-force) when n fits its window — never beat.
2. Else the cheapest available solver by (cost, runtime).
3. Quantum is recommended ONLY when a backend is available AND n fits
   the device AND benchmark evidence exists; without evidence it is
   never promoted, and the caveat says why.
4. Provider cost and CortexCloud's x402 price are reported separately;
   provider figures are model estimates (basis="model") until verified.
"""
from __future__ import annotations

from app.optimizer.problem import ProblemInput, to_qubo
from app.solvers import registry
from app.solvers.quantum import router


async def estimate(problem: ProblemInput) -> dict:
    n = problem.n
    qubo = to_qubo(problem)
    bench_count = await benchmark_evidence(problem)
    sel = router.select(
        problem_type=problem.problem_type,
        qubo=qubo,
        n=n,
        bench_count=bench_count,
    )
    best = sel["recommended"]
    if best is None:
        return {
            "problem": {"problem_type": problem.problem_type, "n": n},
            "recommendation": None,
            "alternatives": [],
            "decision": {
                "recommended": False,
                "mode": None,
                "provider": None,
                "backend": None,
                "algorithm": None,
                "reason": sel["reason"],
                "estimated_cost_usd": None,
                "cortexcloud_price_usd": None,
                "quantum_available": False,
                "quantum_recommended": False,
            },
            "evidence": {
                "benchmark_rows": bench_count,
                "basis": "measured" if bench_count else "model",
                "note": sel["reason"],
            },
            "caveats": _caveats(problem),
        }

    alternatives = [c for c in sel["ranked"] if c["solver_id"] != best["solver_id"]]
    recommended = {
        **best,  # mode, algorithm, backend, provider, estimates, costs
        "estimated_cost_usdc": best["cortexcloud_price_usd"],
        "reason": sel["reason"],
        "cost": {
            "provider_cost_usd": best["provider_cost_usd"],
            "cortexcloud_price_usd": best["cortexcloud_price_usd"],
            "margin_usd": best["margin_usd"],
            "note": "provider cost is a model estimate until verified pricing/benchmarks exist",
        },
    }
    quantum_available = any(
        s.availability().available for s in registry.for_mode("quantum")
    )
    return {
        "problem": {"problem_type": problem.problem_type, "n": n},
        "recommendation": recommended,
        "alternatives": alternatives,
        "decision": {
            "recommended": True,
            "mode": best["mode"],
            "provider": best["provider"],
            "backend": best["backend"],
            "algorithm": best["algorithm"],
            "reason": sel["reason"],
            "estimated_cost_usd": best["estimated_price_usd"],
            "cortexcloud_price_usd": best["cortexcloud_price_usd"],
            "quantum_available": quantum_available,
            "quantum_recommended": best["mode"] == "quantum",
        },
        "evidence": {
            "benchmark_rows": bench_count,
            "basis": "measured" if bench_count else "model",
            "note": "Quantum is recommended only when benchmark evidence supports it."
            if bench_count
            else "No benchmark rows exist yet; quantum backends are never promoted without evidence.",
        },
        "caveats": _caveats(problem),
    }


async def benchmark_evidence(problem: ProblemInput) -> int:
    """Rows in the benchmarks ledger for this problem family.

    This is the ONLY input that can promote a quantum backend; it is
    populated by real runs (runner.py), never by synthetic data.
    """
    try:
        from sqlalchemy import func, select

        from app.database.session import AsyncSessionLocal
        from app.models import Benchmark

        async with AsyncSessionLocal() as db:
            return int(
                (
                    await db.execute(
                        select(func.count(Benchmark.id)).where(Benchmark.problem_type == problem.problem_type)
                    )
                ).scalar()
                or 0
            )
    except Exception:
        return 0


def _caveats(problem: ProblemInput) -> list[str]:
    out: list[str] = []
    quantum = registry.for_mode("quantum")
    if not any(q.availability().available for q in quantum):
        out.append(
            "Quantum execution not offered: no provider credentials configured "
            "(ORIGINQ_API_TOKEN / AWS_ACCESS_KEY_ID+SECRET)."
        )
    else:
        out.append(
            "Quantum backends are available but only recommended with benchmark evidence; "
            "none exists yet, so quantum is never promoted."
        )
    if problem.n > 18:
        out.append("Heuristic result — verify optimality for small n with the brute-force solver.")
    return out