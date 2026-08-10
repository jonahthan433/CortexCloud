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
    "cortex_estimate_optimization": {
        "method": "POST",
        "path": "/v1/estimate",
        "description": "Analyze an optimization problem for free — returns a machine-readable 'decision' block (recommended, mode, backend, algorithm, reason, estimated_cost_usd, cortexcloud_price_usd, quantum_available) plus estimated runtime and USDC price. Mirrors POST /v1/estimate; see GET /v1/examples for canonical inputs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "problem_type": {"type": "string", "enum": ["qubo", "ising"], "default": "qubo"},
                "n": {"type": "integer", "minimum": 2, "maximum": 5000},
                "data": {
                    "type": "object",
                    "properties": {
                        "linear": {"type": "array", "items": {"type": "number"}},
                        "quadratic": {"type": "object", "additionalProperties": {"type": "number"}},
                    },
                },
            },
            "required": ["n", "data"],
        },
        "example": {"name": "qubo", "n": 40, "data": {"linear": [1.0, -2.0, 3.0], "quadratic": {"0,1": -1.5}}},
        "free": True,
    },
    "cortex_optimize": {
        "method": "POST",
        "path": "/v1/optimize",
        "description": "Solve a QUBO/Ising optimization problem (x402-paid, USDC on Base). Returns a job_id to poll. The MCP gateway forwards the signed payment challenge.",
        "input_schema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["auto", "classical", "hybrid", "quantum"], "default": "auto"},
                "problem": {
                    "type": "object",
                    "properties": {
                        "problem_type": {"type": "string", "enum": ["qubo", "ising"], "default": "qubo"},
                        "n": {"type": "integer", "minimum": 2, "maximum": 5000},
                        "data": {"type": "object"},
                    },
                    "required": ["n", "data"],
                },
            },
            "required": ["problem"],
        },
        "example": {"mode": "auto", "problem": {"problem_type": "qubo", "n": 40, "data": {"linear": [1.0], "quadratic": {"0,1": -1.5}}}},
        "free": False,
    },
    "cortex_get_job": {
        "method": "GET",
        "path": "/v1/jobs/{job_id}",
        "description": "Poll an optimization job by id. Free — returns status, solution, objective, error.",
        "input_schema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]},
        "example": {"name": "job_id", "value": "3f5c2e6a-9a0b-4c8d-9e7f-1a2b3c4d5e6f"},
        "free": True,
    },
    "cortex_list_backends": {
        "method": "GET",
        "path": "/v1/backends",
        "description": "List solver backends (classical/hybrid/quantum), verified flag and availability. available=true is required before requesting a mode.",
        "input_schema": {"type": "object", "properties": {}},
        "example": {},
        "free": True,
    },
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