"""Encoder registry: mode -> concrete solver instance."""

from __future__ import annotations

from typing import Iterable

from app.core.config import settings
from app.solvers.base import Solver, SolverAvailability
from app.solvers.classical import BruteForceSolver, SimulatedAnnealingSolver
from app.solvers.hybrid import QaoaLocalSolver

# Quantum adapter load is optional & guarded by its own availability().
_origin_wukong = None


def _wukong():
    global _origin_wukong
    if _origin_wukong is None:
        try:
            from app.solvers.origin import OriginWukongAdapter

            _origin_wukong = OriginWukongAdapter(
                api_token=settings.ORIGINQ_API_TOKEN,
                backend=settings.ORIGINQ_BACKEND,
            )
        except Exception:
            _origin_wukong = False
    return _origin_wukong or None


def solvers() -> list[Solver]:
    out: list[Solver] = [BruteForceSolver(), SimulatedAnnealingSolver()]
    out.append(QaoaLocalSolver())
    wk = _wukong()
    if wk is not None:
        out.append(wk)
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
    """Agent-readable /v1/backends entry."""
    a = s.availability()
    base = {
        "id": s.spec.id,
        "name": s.spec.name,
        "mode": s.spec.mode,
        "description": s.spec.description,
        "max_variables": s.spec.max_variables,
        "requires_token": s.spec.requires_token,
        "available": a.available,
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