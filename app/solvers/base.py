"""Solver protocol + shared result types.

One interface, three modes: classical / hybrid / quantum. Estimate and
solve never lie: a solver declares availability and an honest cost /
runtime model, and the estimator only routes to backends whose
availability is true (benchmarks can refine the model, never override
availability).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class SolverSpec:
    """Static capability description of one solver/backend."""

    id: str                      # e.g. "brute-force", "simulated-annealing", "wukong"
    name: str
    mode: str                    # "classical" | "hybrid" | "quantum"
    description: str
    max_variables: int
    worst_case_iters: int | None = None   # for classical exact: 2**n
    requires_token: bool = False


@dataclass
class SolverAvailability:
    available: bool
    reason: str = ""


@dataclass
class Estimate:
    """Cost/runtime model for one solver on one problem."""

    runtime_s: float
    price_usd: float
    basis: str = "model"                      # "model" until benchmarks exist
    benchmark_samples: int = 0

    def to_dict(self, backend) -> dict[str, Any]:
        return {
            "backend": backend.id,
            "algorithm": backend.name,
            "mode": backend.mode,
            "estimated_runtime_s": round(self.runtime_s, 3),
            "estimated_price_usd": round(self.price_usd, 6),
            "estimate_basis": self.basis,
            "benchmark_samples": self.benchmark_samples,
            "max_variables": backend.max_variables,
            "description": backend.description,
        }


@dataclass
class SolveResult:
    status: str                  # "succeeded" | "failed"
    solution: list[int] | None = None    # assignments per variable [0/1...]
    objective: float | None = None        # minimized QUBO energy
    backend: str | None = None
    runtime_s: float | None = None
    quality_note: str | None = None
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "solution": self.solution,
            "objective": self.objective,
            "backend": self.backend,
            "runtime_s": self.runtime_s,
            "quality_note": self.quality_note,
            "error": self.error,
            "meta": self.meta,
        }


class Solver(Protocol):
    """What every concrete backend must implement."""

    spec: SolverSpec

    def availability(self) -> SolverAvailability:
        """False when required token/credentials are missing."""
        ...

    def estimate(self, qubo: dict, n: int) -> Estimate:
        """Needs no execution. Used by /v1/estimate."""
        ...

    def solve(self, qubo: dict, n: int, timeout_s: float = 300.0) -> SolveResult:
        """Execute. Must never fake a hardware run — when a required
        device or token is absent, return result(status="failed", error=...)."""
        ...


CACHE: dict[str, Any] = {}


def now() -> float:
    return time.time()