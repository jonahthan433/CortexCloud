"""Shared quantum-backend base: provider identity, live-execution gate,
and the objective-recompute helper every hardware adapter uses.

Concrete providers (origin.py, braket.py) implement availability /
estimate / solve. The base only enforces the honesty contract both share:
- a backend is never "available" without its own credentials/capability check
- solve() refuses to touch a QPU while QUANTUM_LIVE_EXECUTION=false
- objectives are always recomputed locally from the sampled bitstring,
  so a misbehaving device program can never fake a good energy
"""
from __future__ import annotations

from app.core.config import settings
from app.solvers.base import SolverAvailability, SolverSpec


class QuantumBackend:
    """Base for quantum provider adapters (mode='quantum')."""

    mode = "quantum"

    def __init__(self, spec: SolverSpec, *, provider: str, algorithm: str):
        self.spec = spec
        self.provider = provider          # "origin" | "aws_braket" | ...
        self.algorithm = algorithm        # e.g. "QAOA"

    def live_gate(self) -> SolverAvailability | None:
        """None when live QPU execution is allowed, else the blocking reason."""
        if not settings.QUANTUM_LIVE_EXECUTION:
            return SolverAvailability(
                False, "QUANTUM_LIVE_EXECUTION=false (live QPU execution is opt-in)"
            )
        return None

    @staticmethod
    def qubo_energy(x: list[int], qubo: dict, n: int) -> float:
        """Objective recomputed locally — the anti-fake guard for all
        hardware adapters. x is the sampled [0/1...] assignment."""
        lin = list(qubo.get("linear") or [0.0] * n)
        e = 0.0
        for i, v in enumerate(x):
            if v:
                e += lin[i] if i < len(lin) else 0.0
        for key, c in (qubo.get("quadratic") or {}).items():
            i, j = (int(t) for t in key.split(","))
            if i < len(x) and j < len(x) and x[i] and x[j]:
                e += c
        return e