"""POST /v1/simulate — free dry-run: feasibility + confidence before paying.

Three tiny simulated-annealing probes on the raw problem dict (no solver
dispatch), plus structural checks. Confidence = 1 - normalized objective
spread across probes (stable objective => high confidence).

ponytail: probe capped at n <= 400 (O(n^2) per evaluation); larger problems
get structural checks only. Upgrade to a proper sampling backend if agents
start relying on confidence for big instances.
"""

from __future__ import annotations

import logging
import math
import random
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.optimizer.problem import ProblemInput
from app.optimizer.estimator import estimate
from app.solvers import registry
from app.x402.pricing import effective_price_usd

logger = logging.getLogger("cortexcloud.api")

router = APIRouter(prefix="/v1", tags=["simulation"])

PROBE_MAX_N = 400
PROBES = 3
SA_ITERS = 300


def _objective(x: list[int], data: dict, ising: bool) -> float:
    lin = data.get("linear") or data.get("h") or []
    quad = data.get("quadratic") or data.get("J") or {}
    obj = 0.0
    for i, c in enumerate(lin):
        obj += c * (x[i] if not ising else (1 if x[i] else -1))
    for key, c in quad.items():
        i, j = (int(t) for t in key.split(","))
        xi = x[i] if not ising else (1 if x[i] else -1)
        xj = x[j] if not ising else (1 if x[j] else -1)
        obj += c * xi * xj
    return obj


def _sa_probe(data: dict, n: int, ising: bool, seed: int) -> float:
    rng = random.Random(seed)
    x = [rng.randint(0, 1) for _ in range(n)]
    cur = _objective(x, data, ising)
    best = cur
    t = 1.0
    for _ in range(SA_ITERS):
        t *= 0.99
        i = rng.randrange(n)
        x[i] = 1 - x[i]
        nxt = _objective(x, data, ising)
        if nxt <= cur or rng.random() < math.exp((cur - nxt) / max(t, 1e-9)):
            cur = nxt
            if cur < best:
                best = cur
        else:
            x[i] = 1 - x[i]
    return best


@router.post("/simulate", summary="Free dry-run: feasibility + confidence before paying")
async def simulate(problem: ProblemInput, mode: str = "auto") -> dict:
    if mode not in ("auto", "classical", "hybrid", "quantum"):
        raise HTTPException(status_code=422, detail=f"mode must be one of auto|classical|hybrid|quantum, got {mode!r}")

    issues: list[str] = []
    if problem.n > 5000:
        raise HTTPException(status_code=422, detail="n exceeds 5000 variables")

    ising = problem.problem_type == "ising"
    data = problem.data
    t0 = time.time()

    # Structural checks
    if not registry.mode_has_available_solver(mode):
        issues.append(f"no available backend for mode={mode!r} right now")

    rec = await estimate(problem, mode)
    price = effective_price_usd(mode, n=problem.n)

    confidence = 1.0
    if problem.n <= PROBE_MAX_N:
        objs = [_sa_probe(data, problem.n, ising, seed) for seed in range(PROBES)]
        spread = max(objs) - min(objs)
        denom = max(abs(o) for o in objs) + 1.0
        confidence = round(max(0.0, min(1.0, 1.0 - spread / denom)), 3)
    else:
        issues.append(f"n > {PROBE_MAX_N}: confidence is structural only (no objective probes)")

    return {
        "feasible": len(issues) == 0,
        "confidence": confidence,
        "issues": issues,
        "recommended_mode": rec["recommendation"]["mode"],
        "recommended_solver": rec["recommendation"]["solver_id"],
        "estimated_price_usd": price,
        "estimated_runtime_s": rec["recommendation"].get("estimated_runtime_s"),
        "probe_ms": int((time.time() - t0) * 1000),
        "disclaimer": "Dry-run only. Pay via POST /v1/optimize only when you accept the quoted price.",
    }
