"""Hybrid solver: QAOA (p=1) with a classical outer loop.

A real, honest pipeline — quantum circuit (phase separator + mixer)
parameterized by a classical optimizer — run here as an exact state
vector simulation for small n. When the Origin quantum adapter is
configured, the same job can be dispatched to real hardware instead
(see origin.py); the API surface never knows which.

This is NOT a claim of quantum advantage: the simulator is classical
compute. 'hybrid' means the algorithm is hybrid (quantum circuit driven
by a classical loop), the backend is CPU. Benchmarks decide routing.
"""
from __future__ import annotations

import cmath
import math
import time

from app.solvers.base import Estimate, SolveResult, SolverAvailability, SolverSpec

QAOA_MAX_N = 12       # 2^n complex amplitudes — keep it snappy
QAOA_GRID = 24         # grid steps per angle (gamma, beta)


def _qubo_terms(qubo: dict, n: int):
    """Same normalization as classical.py: linear[] + pairs[(i,j,c)]."""
    linear = qubo.get("linear") or [0.0] * n
    pairs = []
    for key, val in (qubo.get("quadratic") or {}).items():
        i, j = (int(t) for t in key.split(","))
        if i == j:
            linear[i] += float(val)
        else:
            a, b = (i, j) if i < j else (j, i)
            pairs.append((a, b, float(val)))
    return list(linear), pairs


def _energy(x: int, linear: list[float], pairs: list[tuple]) -> float:
    e = 0.0
    for i, v in enumerate(linear):
        if (x >> i) & 1:
            e += v
    for i, j, c in pairs:
        if (x >> i) & 1 and (x >> j) & 1:
            e += c
    return e


class QaoaLocalSolver:
    """QAOA p=1, exact state-vector simulation, grid search over (gamma, beta)."""

    spec = SolverSpec(
        id="qaoa-local",
        name="Hybrid QAOA",
        mode="hybrid",
        description="Hybrid quantum-classical: QAOA with a classical parameter optimization loop (n <= 12).",
        max_variables=QAOA_MAX_N,
    )

    def availability(self) -> SolverAvailability:
        return SolverAvailability(True, "")

    def estimate(self, qubo, n: int):
        t = max(0.05, (1 << n) * QAOA_GRID * 30e-9)
        return Estimate(runtime_s=round(t, 3), price_usd=0.10, basis="model")

    def solve(self, qubo, n: int, timeout_s: float = 300.0) -> SolveResult:
        t0 = time.time()
        if n > QAOA_MAX_N:
            return SolveResult(status="failed", error=f"n={n} exceeds QAOA local limit {QAOA_MAX_N}")
        linear, pairs = _qubo_terms(qubo, n)
        dim = 1 << n
        energies = [_energy(x, linear, pairs) for x in range(dim)]

        def phase_gate(state, gamma):
            return [a * cmath.exp(-1j * gamma * e) for a, e in zip(state, energies)]

        def mixer(state, beta):
            """Apply Rx(beta) to every qubit: pair-flip updates."""
            out = list(state)
            cosb, sinb = math.cos(beta / 2), math.sin(beta / 2)
            for k in range(n):
                bit = 1 << k
                for base in range(dim):
                    if base & bit:
                        continue
                    partner = base | bit
                    a, b = out[base], out[partner]
                    out[base] = cosb * a - 1j * sinb * b
                    out[partner] = -1j * sinb * a + cosb * b
            return out

        plus = [complex(1.0 / math.sqrt(dim))] * dim

        best = None  # (expectation, state)
        for g_i in range(QAOA_GRID):
            gamma = -math.pi * g_i / (QAOA_GRID - 1)
            for b_i in range(QAOA_GRID):
                beta = math.pi * b_i / (QAOA_GRID - 1)
                state = mixer(phase_gate(plus, gamma), beta)
                exp = sum(abs(a) ** 2 * e for a, e in zip(state, energies))
                if best is None or exp < best[0]:
                    best = (exp, state)
        _, state = best
        best_x = max(range(dim), key=lambda x: abs(state[x]) ** 2)
        obj = energies[best_x]
        return SolveResult(
            status="succeeded",
            solution=[(best_x >> k) & 1 for k in range(n)],
            objective=obj,
            backend=self.spec.id,
            runtime_s=round(time.time() - t0, 4),
            quality_note="QAOA p=1 sample; expectation %.4f (hybrid circuit)" % best[0],
            meta={"layers": 1, "simulation": True},
        )