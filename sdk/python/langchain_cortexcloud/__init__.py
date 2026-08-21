"""langchain_cortexcloud — LangChain tool wrapper for CortexCloud.

Thin: delegates to the cortexcloud SDK; exposes estimate/simulate/preset as
free tools and optimize as a paid tool (needs a funded wallet key).
"""
from __future__ import annotations

from typing import Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from cortexcloud import CortexCloud


class EstimateInput(BaseModel):
    problem: dict = Field(description="QUBO/Ising problem: {problem_type, n, data:{linear, quadratic}}")


class OptimizeInput(EstimateInput):
    max_price_usd: float = Field(default=0.25, description="budget ceiling before paying")


class CortexCloudEstimate(BaseTool):
    name = "cortexcloud_estimate"
    description = ("Solve a QUBO/Ising combinatorial optimization problem via CortexCloud. "
                   "Free exact quote first: returns recommended mode, solver, price in USD and runtime.")
    args_schema: Type[BaseModel] = EstimateInput

    def _run(self, problem: dict) -> dict:
        return self.client.estimate(problem)

    client: CortexCloud = Field(default_factory=CortexCloud)


class CortexCloudOptimize(BaseTool):
    name = "cortexcloud_optimize"
    description = ("Pay-per-call solve of a QUBO/Ising problem via CortexCloud x402 "
                   "(USDC on Base, no API key). Refuses to pay above max_price_usd.")
    args_schema: Type[BaseModel] = OptimizeInput

    def _run(self, problem: dict, max_price_usd: float = 0.25) -> dict:
        rec = self.client.estimate(problem)["recommendation"]
        if rec["cortexcloud_price_usd"] > max_price_usd:
            return {"error": "over_budget", "price_usd": rec["cortexcloud_price_usd"]}
        job = self.client.optimize(problem)
        return self.client.wait(job["job_id"])

    client: CortexCloud = Field(default_factory=CortexCloud)
