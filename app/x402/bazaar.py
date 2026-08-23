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
    "cortex_data_token_balances": {
        "method": "POST", "path": "/v1/data/token-balances",
        "description": "ERC-20 token balances for a wallet on an EVM chain (Alchemy). x402-paid USDC on Base.",
        "input_schema": {"type": "object", "properties": {"address": {"type": "string"}, "chain": {"type": "string", "default": "ethereum"}, "tokens": {"type": "array", "items": {"type": "string"}}, "max_tokens": {"type": "integer", "default": 50}}, "required": ["address"]},
        "example": {"address": "0x0000000000000000000000000000000000000000"}, "free": False,
    },
    "cortex_data_token_price": {
        "method": "POST", "path": "/v1/data/token-price",
        "description": "Spot USD price for a coin (CoinGecko) or token contract (Alchemy). x402-paid USDC on Base.",
        "input_schema": {"type": "object", "properties": {"id": {"type": "string"}, "contract": {"type": "string"}, "chain": {"type": "string", "default": "ethereum"}}},
        "example": {"id": "ethereum"}, "free": False,
    },
    "cortex_data_nft_ownership": {
        "method": "POST", "path": "/v1/data/nft-ownership",
        "description": "NFTs owned by a wallet on an EVM chain (Alchemy). x402-paid USDC on Base.",
        "input_schema": {"type": "object", "properties": {"address": {"type": "string"}, "chain": {"type": "string", "default": "ethereum"}, "page_size": {"type": "integer", "default": 100}}, "required": ["address"]},
        "example": {"address": "0x0000000000000000000000000000000000000000"}, "free": False,
    },
    "cortex_data_tx_history": {
        "method": "POST", "path": "/v1/data/tx-history",
        "description": "Normalized transactions for an address on an EVM chain (Alchemy). x402-paid USDC on Base.",
        "input_schema": {"type": "object", "properties": {"address": {"type": "string"}, "chain": {"type": "string", "default": "ethereum"}, "limit": {"type": "integer", "default": 25}, "from_block": {"type": "integer"}}, "required": ["address"]},
        "example": {"address": "0x0000000000000000000000000000000000000000"}, "free": False,
    },
    "cortex_data_gas_oracle": {
        "method": "GET", "path": "/v1/data/gas-oracle",
        "description": "Current base + priority fee (gas price) for an EVM chain (Alchemy). x402-paid USDC on Base.",
        "input_schema": {"type": "object", "properties": {"chain": {"type": "string", "default": "ethereum"}}},
        "example": {"chain": "ethereum"}, "free": False,
    },
    "cortex_data_block": {
        "method": "GET", "path": "/v1/data/block",
        "description": "Block by number or 'latest' on an EVM chain (Alchemy). x402-paid USDC on Base.",
        "input_schema": {"type": "object", "properties": {"chain": {"type": "string", "default": "ethereum"}, "block": {"type": "string", "default": "latest"}}},
        "example": {"chain": "ethereum", "block": "latest"}, "free": False,
    },
    # Automation API (Tier 1)
    "cortex_automation_estimate": {
        "method": "POST", "path": "/v1/automation/estimate",
        "description": "Free: predict the USDC price for an automation request before paying.",
        "input_schema": {"type": "object", "properties": {"endpoint": {"type": "string", "enum": ["transform", "http-request", "webhook", "schedule", "workflow"]}}},
        "example": {"endpoint": "workflow"}, "free": True,
    },
    "cortex_automation_transform": {
        "method": "POST", "path": "/v1/automation/transform",
        "description": "Pure JSON/data transformation (no egress). x402-paid USDC on Base.",
        "input_schema": {"type": "object", "properties": {"data": {"type": "object"}, "rules": {"type": "object"}}},
        "example": {"data": {"a": 1, "b": 2}, "rules": {"pick": ["a"]}}, "free": False,
    },
    "cortex_automation_http_request": {
        "method": "POST", "path": "/v1/automation/http-request",
        "description": "Outbound HTTP/API request via SSRF-guarded egress. x402-paid USDC on Base.",
        "input_schema": {"type": "object", "properties": {"method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"]}, "url": {"type": "string"}, "headers": {"type": "object"}, "body": {}}},
        "example": {"method": "GET", "url": "https://api.example.com/health"}, "free": False,
    },
    "cortex_automation_webhook": {
        "method": "POST", "path": "/v1/automation/webhook",
        "description": "Deliver a signed (HMAC) webhook payload to a URL. x402-paid USDC on Base.",
        "input_schema": {"type": "object", "properties": {"url": {"type": "string"}, "payload": {}, "headers": {"type": "object"}}},
        "example": {"url": "https://hook.example.com/event", "payload": {"ok": True}}, "free": False,
    },
    "cortex_automation_schedule": {
        "method": "POST", "path": "/v1/automation/schedule",
        "description": "Persist a delayed/recurring task; CortexCloud fires a signed webhook to your URL later. x402-paid USDC on Base.",
        "input_schema": {"type": "object", "properties": {"url": {"type": "string"}, "payload": {}, "delay_seconds": {"type": "integer"}, "cron": {"type": "string"}, "max_retries": {"type": "integer"}}},
        "example": {"url": "https://hook.example.com/job", "delay_seconds": 3600}, "free": False,
    },
    "cortex_automation_workflow": {
        "method": "POST", "path": "/v1/automation/workflow",
        "description": "Sequence up to 10 transform/http/webhook steps (120s cap). x402-paid USDC on Base.",
        "input_schema": {"type": "object", "properties": {"steps": {"type": "array", "items": {"type": "object"}}}},
        "example": {"steps": [{"type": "transform", "data": {"a": 1}, "rules": {}}, {"type": "webhook", "url": "https://hook.example.com", "payload": {"a": 1}}]}, "free": False,
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