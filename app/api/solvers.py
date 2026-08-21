"""Free problem-domain encoders + dry-run simulate.

These mirror the published `cortexcloud-formulate` reference library (the same
math prod already uses) and match the live OpenAPI contracts exactly:
  POST /v1/solvers/portfolio  -> Markowitz QUBO (inputs: returns, covariance, cardinality, risk_aversion)
  POST /v1/solvers/bin-packing -> bin-packing QUBO (inputs: item_weights, bin_capacity, max_bins)
  POST /v1/solvers/routing     -> TSP QUBO        (inputs: distances)
  POST /v1/simulate            -> feasibility + confidence dry-run (no payment)

Re-derived from the OSS formulate lib + prod OpenAPI because prod source was
unreachable during reconciliation; diff against prod before any deploy.
"""
from __future__ import annotations

import logging

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.models import OptimizeJob  # noqa: F401  (keep import surface stable)
from app.optimizer.estimator import estimate
from app.optimizer.problem import ProblemInput

logger = logging.getLogger("cortexcloud.api")

router = APIRouter(prefix="/v1", tags=["solvers"])

MAX_N = 5000


# --- request models (exact match to prod OpenAPI) ---
class PortfolioInput(BaseModel):
    returns: list[float]
    covariance: list[list[float]]
    cardinality: int | None = Field(default=None, ge=1)
    risk_aversion: float = 1.0


class BinPackingInput(BaseModel):
    item_weights: list[float]
    bin_capacity: float = Field(gt=0.0)
    max_bins: int | None = Field(default=None, ge=1)


class RoutingInput(BaseModel):
    distances: list[list[float]]


def _qubo(problem_type: str, n: int, linear: list[float], quad: dict[str, float]) -> dict:
    return {"problem_type": problem_type, "n": n, "data": {"linear": linear, "quadratic": quad}}


@router.post("/solvers/portfolio", summary="Build a cardinality-constrained Markowitz QUBO")
async def solver_portfolio(req: PortfolioInput):
    n = len(req.returns)
    if len(req.covariance) != n or any(len(r) != n for r in req.covariance):
        raise HTTPException(status_code=422, detail="covariance must be an n x n matrix")
    card = req.cardinality or max(1, n // 2)
    returns = np.array(req.returns, dtype=float)
    cov = np.array(req.covariance, dtype=float)
    linear = (-returns).tolist()
    quad: dict[str, float] = {}
    for i in range(n):
        for j in range(i + 1, n):
            q = req.risk_aversion * float(cov[i, j])
            if abs(q) > 1e-12:
                quad[f"{i},{j}"] = q
    penalty = max(1.0, req.risk_aversion * abs(linear[np.argmax(np.abs(linear))]))
    for i in range(n):
        linear[i] += penalty * (1 - 2 * card)
    for i in range(n):
        for j in range(i + 1, n):
            key = f"{i},{j}"
            quad[key] = quad.get(key, 0.0) + 2 * penalty
    return _qubo("qubo", n, linear, quad)


@router.post("/solvers/bin-packing", summary="Build a bin-packing QUBO")
async def solver_bin_packing(req: BinPackingInput):
    weights = np.array(req.item_weights, dtype=float)
    n_items = len(weights)
    max_bins = req.max_bins or n_items
    cap = float(req.bin_capacity)
    # Variables x_{i,b}: item i in bin b. n = items * bins.
    B = max_bins
    n = n_items * B
    linear = [0.0] * n

    def idx(i, b):
        return i * B + b

    quad: dict[str, float] = {}
    penalty = float(np.max(weights) * B * 2 + 1.0)
    # Each item in exactly one bin.
    for i in range(n_items):
        for b1 in range(B):
            for b2 in range(b1 + 1, B):
                k = f"{min(idx(i, b1), idx(i, b2))},{max(idx(i, b1), idx(i, b2))}"
                quad[k] = quad.get(k, 0.0) + penalty
    # Capacity: penalise overfill per bin.
    for b in range(B):
        for i in range(n_items):
            for j in range(i + 1, n_items):
                load_pair = weights[i] + weights[j]
                if load_pair > cap + 1e-9:
                    k = f"{min(idx(i, b), idx(j, b))},{max(idx(i, b), idx(j, b))}"
                    quad[k] = quad.get(k, 0.0) + (load_pair - cap)
    return _qubo("qubo", n, linear, quad)


@router.post("/solvers/routing", summary="Build a TSP tour QUBO from a distance matrix")
async def solver_routing(req: RoutingInput):
    d = np.array(req.distances, dtype=float)
    if d.ndim != 2 or d.shape[0] != d.shape[1]:
        raise HTTPException(status_code=422, detail="distances must be an N x N matrix")
    N = d.shape[0]
    n = N * N

    def idx(city, pos):
        return city * N + pos

    linear = [0.0] * n
    quad: dict[str, float] = {}
    penalty = float(np.max(np.abs(d)) * N * 2 + 1.0)
    for i in range(N):
        for t1 in range(N):
            for t2 in range(t1 + 1, N):
                k = f"{min(idx(i, t1), idx(i, t2))},{max(idx(i, t1), idx(i, t2))}"
                quad[k] = quad.get(k, 0.0) + penalty
    for t in range(N):
        for c1 in range(N):
            for c2 in range(c1 + 1, N):
                k = f"{min(idx(c1, t), idx(c2, t))},{max(idx(c1, t), idx(c2, t))}"
                quad[k] = quad.get(k, 0.0) + penalty
    for c1 in range(N):
        for c2 in range(N):
            if c1 == c2:
                continue
            for t in range(N):
                nt = (t + 1) % N
                k = f"{min(idx(c1, t), idx(c2, nt))},{max(idx(c1, t), idx(c2, nt))}"
                quad[k] = quad.get(k, 0.0) + float(d[c1, c2])
    return _qubo("qubo", n, linear, quad)


@router.post("/simulate", summary="Free dry-run: feasibility + confidence before paying")
async def simulate(problem: ProblemInput):
    if problem.n > MAX_N:
        raise HTTPException(status_code=422, detail=f"n exceeds {MAX_N} variables")
    # A simulation is exactly a free estimate — no job, no payment.
    result = await estimate(problem, mode="auto")
    result["note"] = "Simulated dry-run (free). No job created, no payment required."
    return result
