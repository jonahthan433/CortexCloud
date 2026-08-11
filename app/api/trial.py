"""
Free trial endpoint — solve small QUBO/Ising problems without payment.
POST /v1/trial — synchronous, n ≤ 10, rate-limited per IP.
Returns the solution directly (no async job, no x402 challenge).
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.optimizer.problem import ProblemInput, to_qubo
from app.solvers import registry

router = APIRouter(prefix="/v1", tags=["trial"])

# ponytail: in-memory rate limiter — per-IP bucket, resets on restart.
# Replace with Redis sliding window when traffic justifies it.
_trial_limits: dict[str, list[float]] = defaultdict(list)
_TRIAL_MAX_N = 10
_TRIAL_MAX_PER_IP = 10       # requests per window
_TRIAL_WINDOW_S = 3600       # 1 hour


class TrialRequest(BaseModel):
    problem: ProblemInput
    mode: str = Field(default="auto", description="auto | classical | hybrid | quantum")

    class Config:
        json_schema_extra = {
            "example": {
                "mode": "auto",
                "problem": {
                    "problem_type": "qubo",
                    "n": 6,
                    "data": {
                        "linear": [-0.5, -1.2, -0.8, -2.0, -0.3, -1.5],
                        "quadratic": {"0,1": 0.3, "1,3": 0.4},
                    },
                },
            }
        }


@router.post("/trial", summary="Free trial solve (n ≤ 10, rate-limited, no payment)")
async def trial(req: TrialRequest, request: Request):
    if req.problem.n > _TRIAL_MAX_N:
        raise HTTPException(
            status_code=422,
            detail=f"Trial limited to n ≤ {_TRIAL_MAX_N}. "
                   f"For larger problems use /v1/optimize (x402-paid).",
        )
    if req.mode not in ("auto", "classical", "hybrid", "quantum"):
        raise HTTPException(422, detail=f"mode must be auto|classical|hybrid|quantum")

    # Rate limit
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = [t for t in _trial_limits[ip] if now - t < _TRIAL_WINDOW_S]
    if len(window) >= _TRIAL_MAX_PER_IP:
        raise HTTPException(
            429,
            detail=f"Trial rate limit: {_TRIAL_MAX_PER_IP} free solves per hour. "
                   f"Use /v1/optimize for unlimited access (x402-paid).",
        )
    window.append(now)
    _trial_limits[ip] = window

    # Solve synchronously (small n — fast enough)
    qubo = to_qubo(req.problem)
    if req.mode in ("classical", "auto"):
        solvers = registry.for_mode("classical")
        for s in solvers:
            if s.availability().available and req.problem.n <= s.spec.max_variables:
                result = s.solve(qubo, req.problem.n)
                return {
                    "trial": True,
                    "solver": s.spec.id,
                    "mode": "classical",
                    "solution": result.solution,
                    "objective": result.objective,
                    "runtime_s": round(result.runtime_s, 4) if result.runtime_s else None,
                    "note": "Free trial — exact classical solve. For larger problems or "
                            "quantum backends, use /v1/optimize ($0.05–$1.50, x402).",
                }

    # Fallback: run first available solver
    for s in registry.solvers():
        if s.availability().available and req.problem.n <= s.spec.max_variables:
            result = s.solve(qubo, req.problem.n)
            return {
                "trial": True,
                "solver": s.spec.id,
                "mode": s.spec.mode,
                "solution": result.solution,
                "objective": result.objective,
                "runtime_s": round(result.runtime_s, 4) if result.runtime_s else None,
                "note": "Free trial solve. Use /v1/optimize for production use (x402-paid).",
            }

    raise HTTPException(503, detail="No solver available for trial. Try again later.")
