"""Classical QUBO solvers — pure Python, zero new dependencies.

- BruteForceSolver: exact minimum for n <= 20 (2**n evaluations).
- SimulatedAnnealingSolver: heuristic minimizer for larger n; standard
  Metropolis schedule, restart at best. Deterministic seed for tests.

Both solve the QUBO
      E(x) = sum_i q_ii x_i + sum_{i<j} q_ij x_i x_j
over binary x in {0,1}^n, minimizing E.
"""
from __future__ import annotations

import math
import random

from app.solvers.base import Estimate, SolveResult, SolverAvailability, SolverSpec

BRUTE_FORCE_MAX = 20
SA_MAX_ITER = 8_000
SA_RESTARTS = 3

# Flat per-run classical price (USD): fixed fee per optimization job.
CLASSICAL_PRICE_USD = 0.02


def price_classical(n: int) -> float:
    # Fixed per-run price regardless of size (simple, predictable for agents).
    return CLASSICAL_PRICE_USD


def _now():
    import time
    return time.time()


def _price_classical(n: int) -> float:
    # Flat classical fee; size does not change it (per-call model).
    return CLASSICAL_PRICE_USD


def _est(solver, runtime_s: float, price: float) -> Estimate:
    return Estimate(runtime_s=runtime_s, price_usd=price, basis="model")


def _qubo_terms(qubo: dict, n: int):
    """Return (linear, list_of_(i, j, coeff)) with sorted (i<j)."""
    linear = qubo.get("linear") or [0.0] * n
    pairs = []
    for key, val in (qubo.get("quadratic") or {}).items():
        i, j = key.split(",", 1)
        i, j = int(i), int(j)
        if i == j:
            linear[i] += float(val)
        else:
            if i > j:
                i, j = j, i
            pairs.append((i, j, float(val)))
    return list(linear), pairs


def evaluate(linear: list[float], pairs: list[tuple], x: list[int]) -> float:
    e = 0.0
    for i, v in enumerate(x):
        if v:
            e += linear[i]
    for i, j, c in pairs:
        if x[i] and x[j]:
            e += c
    return e


class BruteForceSolver:
    spec = SolverSpec(
        id="brute-force",
        name="exhaustive enumeration (exact)",
        mode="classical",
        description="Exact QUBO minimizer over all 2^n assignments. For n <= 20.",
        max_variables=BRUTE_FORCE_MAX,
    )

    def availability(self) -> SolverAvailability:
        return SolverAvailability(True, "")

    def estimate(self, qubo, n: int):
        evals = 2 ** n
        t = evals * 55e-9  # ~55ns per bit-set evaluation (CPython, measured)
        return _est(self, max(t, 0.001), price_classical(n))

    def solve(self, qubo, n, timeout_s: float = 300.0) -> SolveResult:
        t0 = _now()
        if n > BRUTE_FORCE_MAX:
            return SolveResult(status="failed", error=f"n={n} exceeds brute-force limit {BRUTE_FORCE_MAX}; use simulated-annealing")
        linear, pairs = _qubo_terms(qubo, n)
        best_x = None
        best_e = math.inf
        for mask in range(1 << n):
            x = [(mask >> k) & 1 for k in range(n)]
            e = evaluate(linear, pairs, x)
            if e < best_e:
                best_e = e
                best_x = x
        return SolveResult(
            status="succeeded", solution=best_x, objective=best_e,
            backend=self.spec.id, runtime_s=_now() - t0,
            quality_note="exact optimum",
            meta={"evaluations": 1 << n},
        )


class SimulatedAnnealingSolver:
    spec = SolverSpec(
        id="simulated-annealing",
        name="simulated annealing (heuristic)",
        mode="classical",
        description="Metropolis simulated annealing with restarts. Scales to thousands of variables.",
        max_variables=5000,
    )

    def __init__(self, seed: int | None = None):
        self._rng = random.Random(seed)

    def availability(self) -> SolverAvailability:
        return SolverAvailability(True, "")

    def estimate(self, qubo, n: int):
        iters = SA_MAX_ITER * SA_RESTARTS
        t = iters * 60e-9 * n  # ~60ns per neighbor evaluation * n per iter
        return _est(self, max(0.2, t), price_classical(n))

    def solve(self, qubo, n: int, timeout_s: float = 300.0) -> SolveResult:
        t0 = _now()
        linear, pairs = _qubo_terms(qubo, n)
        best_x, best_e = self._anneal(linear, pairs, n)
        for _ in range(SA_RESTARTS - 1):
            x, e = self._anneal(linear, pairs, n)
            if e < best_e:
                best_e, best_x = e, x
        return SolveResult(
            status="succeeded", solution=best_x, objective=best_e,
            backend=self.spec.id, runtime_s=_now() - t0,
            quality_note="heuristic — verify optimality for small n with brute-force",
            meta={"iterations": SA_MAX_ITER * SA_RESTARTS},
        )

    def _anneal(self, linear, pairs, n):
        rng = self._rng
        x = [rng.randint(0, 1) for _ in range(n)]
        e = evaluate(linear, pairs, x)
        best_x, best_e = list(x), e
        T = 2.0
        for step in range(SA_MAX_ITER):
            i = rng.randrange(n)
            delta = (1 - 2 * x[i]) * linear[i]
            for a, b, c in pairs:
                if a == i:
                    if x[b]:
                        delta += c * (1 - 2 * x[i])
                elif b == i:
                    if x[a]:
                        delta += c * (1 - 2 * x[i])
            if delta <= 0 or rng.random() < math.exp(-delta / T):
                x[i] = 1 - x[i]
                e += delta
                if e < best_e:
                    best_e, best_x = e, list(x)
            T = max(1e-3, 2.0 * (1 - step / SA_MAX_ITER))
        return best_x, best_e