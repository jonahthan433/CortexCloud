"""Agent-facing optimization surface: /v1/*.

POST /v1/optimize is the only x402-payable route; everything else is
free. The middleware runs the 402 challenge; this router just runs the
job and never touches payments.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.config import settings
from app.database.session import AsyncSessionLocal
from app.models import OptimizeJob
from app.optimizer.estimator import estimate
from app.optimizer.problem import ProblemInput
from app.optimizer.runner import create_job, schedule
from app.solvers import registry
from app.x402.pricing import FREE_ROUTES, MARKUP, MODE_PRICE_USD, effective_price_usd

logger = logging.getLogger("cortexcloud.api")

router = APIRouter(prefix="/v1", tags=["optimization"])


class OptimizeRequest(BaseModel):
    problem: ProblemInput
    mode: str = Field(
        default="auto",
        description="auto | classical | hybrid | quantum. auto picks the cheapest honest path; quantum requires an available configured backend (Origin or AWS Braket).",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "mode": "auto",
                "problem": {
                    "problem_type": "qubo",
                    "n": 4,
                    "data": {
                        "linear": [1.0, -2.0, 3.0, -4.0],
                        "quadratic": {"0,1": -1.5, "1,2": 0.5, "2,3": -2.0},
                    },
                },
            }
        }


@router.post("/optimize", summary="Solve an optimization problem (x402-paid)")
async def optimize(req: OptimizeRequest, request: Request):
    if req.mode not in ("auto", "classical", "hybrid", "quantum"):
        raise HTTPException(status_code=422, detail=f"mode must be one of auto|classical|hybrid|quantum, got {req.mode!r}")
    if req.problem.n > 5000:
        raise HTTPException(status_code=422, detail="n exceeds 5000 variables")
    price = MODE_PRICE_USD.get(req.mode, MODE_PRICE_USD["classical"])
    job_id = await create_job(req.problem, req.mode, price)
    schedule(job_id)
    return {
        "job_id": job_id,
        "status": "queued",
        "mode": req.mode,
        "price_usd": price,
        "poll": f"/v1/jobs/{job_id}",
    }


@router.post("/estimate", summary="Analyze a problem for free — mode, algorithm, backend, runtime, price")
async def v1_estimate(problem: ProblemInput) -> dict:
    if problem.n > 5000:
        raise HTTPException(status_code=422, detail="n exceeds 5000 variables")
    return await estimate(problem)


@router.get("/jobs/{job_id}", summary="Poll an async optimization job")
async def get_job(job_id: str) -> dict:
    async with AsyncSessionLocal() as db:
        job = await db.get(OptimizeJob, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return {
            "job_id": job.id,
            "status": job.status,
            "mode": job.mode,
            "problem_type": job.problem_type,
            "n": job.n,
            "backend": job.backend,
            "algorithm": job.algorithm,
            "price_usd": float(job.price_usd) if job.price_usd is not None else None,
            "result": job.result,
            "error": job.error,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        }


def _examples_payload() -> dict:
    """Canonical agent examples (static file checked at boot; serves 404 only if missing)."""
    import json as _json
    import os

    p = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "examples", "agents.json")
    with open(p) as _f:
        return _json.load(_f)


@router.get("/examples", summary="Canonical examples for agents (portfolio/assignment/scheduling/routing/QUBO)")
async def v1_examples() -> dict:
    return _examples_payload()


@router.get("/backends", summary="List solver backends and availability")
async def list_backends() -> dict:
    backends = [registry.backend_dict(s) for s in registry.solvers()]
    return {
        "backends": backends,
        "prices_usd": MODE_PRICE_USD,
        "note": "available=true means the backend's credential + capability check passed (Origin token / AWS Braket get_devices); live QPU execution additionally requires QUANTUM_LIVE_EXECUTION=true.",
    }


@router.get("/capabilities", summary="Agent capability catalog")
async def capabilities() -> dict:
    return {
        "service": "CortexCloud Optimization Network",
        "version": "v1",
        "description": FREE_ROUTES,
        "problem_types": ["qubo", "ising"],
        "modes": ["classical", "hybrid", "quantum"],
        "max_variables": 5000,
        "algorithms": sorted({getattr(s, "algorithm", s.spec.name) for s in registry.solvers()}),
        "providers": sorted({getattr(s, "provider", "local") for s in registry.solvers()}),
        "backends": [registry.backend_dict(s) for s in registry.solvers()],
        "constraints": {"quantum_live_execution": bool(settings.QUANTUM_LIVE_EXECUTION), "quantum_capacity_max_variables": max((s.spec.max_variables for s in registry.solvers() if s.spec.mode == "quantum"), default=0)},
        "pricing": {
            "cortexcloud_price_usd": MODE_PRICE_USD,
            "effective_prices_usd": {m: effective_price_usd(m) for m in MODE_PRICE_USD},
            "markup": MARKUP,
            "note": "charged price = max(list price, provider cost x markup); provider-side costs are model estimates until verified on live hardware; quantum is recommended only with benchmark evidence.",
        },
        "payments": {
            "scheme": "x402",
            "network": "eip155:8453",
            "asset": "USDC (Base)",
            "endpoint": "POST /v1/optimize",
            "challenge": "POST any paid route without payment-signature returns 402 with the challenge",
        },
        "discovery": [
            "/.well-known/x402.json",
            "/.well-known/bazaar",
            "/llms.txt",
            "/openapi.json",
            "/x402/v1/mcp",
        ],
    }