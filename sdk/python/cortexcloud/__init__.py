"""cortexcloud — agent-native, pay-per-call API platform (x402, USDC on Base).

Six categories: Optimization/Quantum, AI, Research, Data, Automation, MCP.
No API keys. Free endpoints (estimate/simulate/trial) need no wallet; paid
endpoints (optimize, token_price, research_answer, http_request, chat, ...)
settle per call in USDC via x402. Works from any agent runtime.
"""
from .client import CortexCloud, CortexCloudError  # noqa: F401

__version__ = "0.1.0"
