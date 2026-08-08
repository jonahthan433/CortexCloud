"""Estimation & auto mode selection.

/ v1/estimate contract: analyze a QUBO/Ising, recommend the cheapest
honest path. Routing rules (evidence, not marketing):

1. Exact classical (brute-force) when n fits its window — never beat,
   no price premium.
2. Else heuristic classical (simulated annealing) by default.
3. Hybrid (QAOA local) listed as an alternative — a hybrid algorithm
   running on CPU; fine for small n, usually not the cheaper pick.
4. Quantum (Wukong) is listed ONLY when the backend is actually
   available AND (a) n fits the device AND (b) benchmark evidence for
   this problem family shows it wins. Without benchmarks the estimate
   explicitly says so — we never claim advantage we can't show.

Benchmarks refine runtime/quality models per (problem_type, n, solver);
until rows exist the basis is "model".
"""
from __future__ import annotations

from app.optimizer.problem import ProblemInput, to_qubo
from app.solvers import registry

# Soft preferences (mode -> rank; lower is better). Brute-force exact
# beats annealing when it fits; the grid is only populated after the
# per-solver estimates.
BRUTE_FORCE_CAP = 18  # brute-force window used by the estimator (2^18 evals)


async def estimate(problem: ProblemInput) -> dict:
    n = problem.n
    qubo = to_qubo(problem)
    bench_count = await _benchmark_evidence(problem)
    candidates: list[dict] = []
    for s in registry.solvers():
        if not s.availability().available:
            continue
        if s.spec.mode == "quantum":
            continue  # gated below, only with evidence
        est = s.estimate(qubo, n)
        candidates.append(
            {
                **est.to_dict(s.spec),
                "solver_id": s.spec.id,
                "_cost": est.price_usd + est.runtime_s * 1e-4,  # gentle latency tax
            }
        )

    quantum = _quantum_candidate(problem, qubo, bench_count)
    if quantum:
        candidates.append(quantum)

    candidates.sort(key=lambda c: c["_cost"])
    best = candidates[0]
    recommended = {
        "mode": best["mode"],
        "algorithm": best["algorithm"],
        "backend": best["backend"],
        "solver_id": best["solver_id"],
        "estimated_runtime_s": best["estimated_runtime_s"],
        "estimated_price_usd": best["estimated_price_usd"],
    }
    alternatives = [c for c in candidates[1:] if c["solver_id"] != best["solver_id"]]
    for c in alternatives:
        c.pop("_cost", None)

    return {
        "problem": {"problem_type": problem.problem_type, "n": n},
        "recommendation": recommended,
        "alternatives": alternatives,
        "evidence": {
            "benchmark_rows": bench_count,
            "basis": "measured" if bench_count else "model",
            "note": "Quantum is recommended only when benchmark evidence supports it; none exists yet, so it is never promoted.",
        },
        "caveats": _caveats(problem, best["solver_id"], quantum),
    }


def _quantum_candidate(problem: ProblemInput, qubo: dict, bench_count: int) -> dict | None:
    """Quantum appears ONLY with availability + n fits + benchmark evidence."""
    wk = registry.by_id("wukong")
    if wk is None:
        return None
    if not wk.availability().available:
        return None
    if problem.n > wk.spec.max_variables:
        return None
    if bench_count == 0:
        return None  # no evidence -> no quantum claim (see caveat)
    est = wk.estimate(qubo, problem.n)
    return {
        **est.to_dict(wk.spec),
        "solver_id": "wukong",
        "_cost": est.price_usd + est.runtime_s * 1e-4,
    }


async def _benchmark_evidence(problem: Problem) -> int:
    """Rows in the benchmarks ledger for this (type, solver) combination."""
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


def _caveats(problem, chosen_solver_id: str, quantum_present: bool) -> list[str]:
    out = []
    if chosen_solver_id == "simulated-annealing":
        out.append("Heuristic result — verify optimality for small n with the brute-force solver.")
    if quantum_present is None:
        out.append("Quantum execution not offered: no Origin Quantum token/back-end configured yet.")
        return out
    return out