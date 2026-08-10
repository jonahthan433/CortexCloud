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


async def estimate(problem: ProblemInput, mode: str = "auto") -> dict:
    n = problem.n
    qubo = to_qubo(problem)
    bench_count = await benchmark_evidence(problem)
    sel = router.select(
        problem_type=problem.problem_type,
        qubo=qubo,
        n=n,
        bench_count=bench_count,
        force_mode=mode if mode != "auto" else None,
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

    # Public projection: only what an agent needs to act (mode, solver,
    # runtime, price, reason). Internal cost/margin/benchmark bookkeeping
    # stays in the router and never crosses this boundary.
    def _public(d: dict) -> dict:
        return {k: d[k] for k in (
            "mode", "solver_id", "backend", "algorithm", "description",
            "max_variables", "estimated_runtime_s",
            "cortexcloud_price_usd", "estimated_cost_usdc",
        ) if k in d}

    alternatives = [_public(c) for c in sel["ranked"] if c["solver_id"] != best["solver_id"]]
    recommended = {
        **_public(best),
        "estimated_cost_usdc": best["cortexcloud_price_usd"],
        "reason": sel["reason"],
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
            "backend": best["backend"],
            "algorithm": best["algorithm"],
            "reason": sel["reason"],
            "estimated_cost_usd": best["cortexcloud_price_usd"],
            "cortexcloud_price_usd": best["cortexcloud_price_usd"],
            "quantum_available": quantum_available,
            "quantum_recommended": best["mode"] == "quantum",
        },
        "evidence": {
            "benchmark_rows": bench_count,
            "basis": "measured" if bench_count else "model",
            "note": "Recommendations are evidence-based; quantum is never promoted without measured support."
            if bench_count
            else "No measured evidence exists yet for this problem family; quantum is never promoted without it.",
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
            "Quantum execution is not currently offered — no quantum backend is online. "
            "Classical and hybrid modes are unaffected."
        )
    else:
        out.append(
            "Quantum backends are available; quantum is only recommended automatically "
            "when measured quality evidence exists for the problem family."
        )
    if problem.n > 18:
        out.append("Heuristic result — for an exact optimality guarantee use n <= 18.")
    return out