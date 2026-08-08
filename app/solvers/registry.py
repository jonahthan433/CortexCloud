"""Solver registry: mode -> concrete solver instances.

One registry feeds /v1/backends, /v1/capabilities, the estimator and the
job runner. Quantum adapters are loaded lazily and never affect startup
when their SDKs are absent — each one's availability() decides.
"""

from __future__ import annotations

from typing import Iterable

from app.core.config import settings
from app.solvers.base import Solver, SolverAvailability
from app.solvers.classical import BruteForceSolver, SimulatedAnnealingSolver
from app.solvers.hybrid import QaoaLocalSolver

# Quantum adapters are optional; construction is cheap (no network), so
# only Origin stays lazy below because quafu is import-guarded there.
_origin_wukong = None
_braket_backends: list[Solver] | None = None


def _wukong():
    global _origin_wukong
    if _origin_wukong is None:
        try:
            from app.solvers.quantum.origin import OriginWukongAdapter

            _origin_wukong = OriginWukongAdapter(
                api_token=settings.ORIGINQ_API_TOKEN,
                backend=settings.ORIGINQ_BACKEND,
            )
        except Exception:
            _origin_wukong = False
    return _origin_wukong or None


def _braket() -> list[Solver]:
    global _braket_backends
    if _braket_backends is None:
        try:
            from app.solvers.quantum.braket import BraketBackend, PROVIDERS

            _braket_backends = [BraketBackend(p) for p in PROVIDERS]
        except Exception:
            _braket_backends = []
    return _braket_backends


def solvers() -> list[Solver]:
    out: list[Solver] = [BruteForceSolver(), SimulatedAnnealingSolver(), QaoaLocalSolver()]
    wk = _wukong()
    if wk is not None:
        out.append(wk)
    out.extend(_braket())
    return out


def by_id(solver_id: str) -> Solver | None:
    for s in solvers():
        if s.spec.id == solver_id:
            return s
    return None


def for_mode(mode: str) -> list[Solver]:
    """All solvers declared for a mode (quantum only when configured)."""
    return [s for s in solvers() if s.spec.mode == mode]


def availability(s: Solver) -> SolverAvailability:
    return s.availability()


def backend_dict(s: Solver) -> dict:
    """Agent-readable /v1/backends entry. 'available' for a quantum
    backend means its own credential + capability check passed; live
    execution additionally requires QUANTUM_LIVE_EXECUTION=true."""
    a = s.availability()
    base = {
        "id": s.spec.id,
        "name": s.spec.name,
        "mode": s.spec.mode,
        "provider": getattr(s, "provider", "local"),
        "algorithm": getattr(s, "algorithm", s.spec.name),
        "description": s.spec.description,
        "max_variables": s.spec.max_variables,
        "requires_token": s.spec.requires_token,
        "available": a.available,
        "verified": a.available if s.spec.mode == "quantum" else True,
    }
    if not a.available:
        base["note"] = a.reason
    return base


def availability_summary() -> dict:
    """/health payload: alive backend count per mode."""
    out = {}
    for s in solvers():
        a = s.availability()
        out[s.spec.mode] = out.get(s.spec.mode, {"available": 0, "total": 0})
        out[s.spec.mode]["total"] += 1
        if a.available:
            out[s.spec.mode]["available"] += 1
    return out