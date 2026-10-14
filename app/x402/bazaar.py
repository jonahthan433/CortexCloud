"""Bazaar extension builders + MCP tool registry.

x402's bazaar extension lets agents discover what a paid endpoint does:
input schema, output example, pricing — all derived from the x402
pricing table. The MCP tools here wrap the /v1/* REST surface 1:1 and
are the ONLY way the network is consumed from MCP clients.
"""
from __future__ import annotations

from app.x402.pricing import FREE_ROUTES, ROUTE_DESCRIPTIONS, ROUTE_PRICING

# Tool name -> (method, path, description, input_schema, example_input)
# MCP tools: exactly the 4 the spec requires, plus nothing speculative.
_TOOLS: dict[str, dict] = {
    # The optimization MCP surface was removed with the solver routes; the
    # on-chain data API is consumed over REST (its bazaar metadata is served
    # per-route in the 402 challenge extension).
}




def list_tools() -> list[dict]:
    """MCP tools/list entries."""
    return [
        {
            "name": name,
            "description": t["description"],
            "inputSchema": t["input_schema"],
        }
        for name, t in _TOOLS.items()
    ]


def tool_entry(tool_name: str) -> dict | None:
    return _TOOLS.get(tool_name)