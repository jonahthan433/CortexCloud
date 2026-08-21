"""POST /v1/solvers/{routing|bin-packing|portfolio} — free QUBO builders.

Plain-language constraints in, a ready-to-submit /v1/optimize payload out.
Free by design: the agent pays only when it submits the QUBO for a solve.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.solvers.presets import BUILDERS, portfolio_qubo, bin_packing_qubo, routing_qubo

logger = logging.getLogger("cortexcloud.api")

router = APIRouter(prefix="/v1/solvers", tags=["domain presets"])


class PortfolioInput(BaseModel):
    returns: list[float] = Field(description="expected per-asset return (any units)")
    covariance: list[list[float]] = Field(description="n x n covariance matrix")
    cardinality: int | None = Field(default=None, ge=1, description="max assets to select")
    risk_aversion: float = Field(default=1.0, gt=0)
    cardinality_penalty: float = Field(default=2.0, gt=0)


class BinPackingInput(BaseModel):
    item_weights: list[float] = Field(min_length=1, description="item weights")
    bin_capacity: float = Field(gt=0)
    max_bins: int | None = Field(default=None, ge=1)


class RoutingInput(BaseModel):
    distances: list[list[float]] = Field(description="N x N pairwise distance matrix")


@router.post("/portfolio", summary="Build a cardinality-constrained Markowitz QUBO")
async def preset_portfolio(inp: PortfolioInput) -> dict:
    try:
        qubo = portfolio_qubo(inp.returns, inp.covariance, inp.cardinality,
                              inp.risk_aversion, inp.cardinality_penalty)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _preset_response("portfolio", qubo)


@router.post("/bin-packing", summary="Build a bin-packing QUBO")
async def preset_bin_packing(inp: BinPackingInput) -> dict:
    try:
        qubo = bin_packing_qubo(inp.item_weights, inp.bin_capacity, inp.max_bins)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _preset_response("bin-packing", qubo)


@router.post("/routing", summary="Build a TSP tour QUBO from a distance matrix")
async def preset_routing(inp: RoutingInput) -> dict:
    try:
        qubo = routing_qubo(inp.distances)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _preset_response("routing", qubo)


def _preset_response(kind: str, qubo: dict) -> dict:
    return {
        "preset": kind,
        "problem_type": qubo["problem_type"],
        "n": qubo["n"],
        "qubo": qubo,
        "optimize_payload": {"mode": "auto", "problem": qubo},
        "next": {"estimate": "POST /v1/estimate with optimize_payload (free)",
                 "solve": "POST /v1/optimize with optimize_payload (x402-paid)"},
    }
