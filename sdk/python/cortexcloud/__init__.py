"""cortexcloud — pay-per-call QUBO/Ising optimization for AI agents.

No API keys. Estimate free, pay USDC on Base per call via x402, poll for
the solution. Works from any agent runtime (CrewAI, LangGraph, plain code).
"""
from .client import CortexCloud, CortexCloudError  # noqa: F401

__version__ = "0.1.0"
