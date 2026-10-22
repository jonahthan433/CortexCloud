"""Bazaar extension builders + MCP tool registry.

x402's bazaar extension lets agents discover what a paid endpoint does:
input schema, output example, pricing — all derived from the x402
pricing table. The registry below mirrors the live paid data surface
(15 routes) plus the free capabilities tool and is served at
/.well-known/bazaar (mcp.tools).

The MCP gateway itself is a separate host service — a zero-dependency
relay (:3100, exposed as https://api.cortexcloud.org/mcp) that holds no
payment logic: it forwards HTTP + x402 payment headers to /v1/* and
returns whatever the API says, 402 challenge included. Keep its TOOLS
table in sync with _SPEC below; test_discovery_reconcile.py pins the
registry to the advertised paid surface.
"""
from __future__ import annotations

from app.middleware.x402 import INPUT_EXAMPLES, INPUT_SCHEMAS
from app.x402.pricing import ROUTE_DESCRIPTIONS, ROUTE_PRICING

# tool name -> (method, path). Exactly one tool per advertised paid route
# (PUBLIC_PRODUCT_ROUTES), plus the free capabilities tool. Nothing
# speculative.
_SPEC: tuple[tuple[str, str, str], ...] = (
    ("cortex_token_balances", "POST", "/v1/data/token-balances"),
    ("cortex_token_price", "POST", "/v1/data/token-price"),
    ("cortex_nft_ownership", "POST", "/v1/data/nft-ownership"),
    ("cortex_tx_history", "POST", "/v1/data/tx-history"),
    ("cortex_gas_oracle", "GET", "/v1/data/gas-oracle"),
    ("cortex_block", "GET", "/v1/data/block"),
    ("cortex_token_risk", "POST", "/v1/data/token-risk"),
    ("cortex_wallet_intel", "POST", "/v1/data/wallet-intel"),
    ("cortex_whale_alerts", "POST", "/v1/data/whale-alerts"),
    ("cortex_cross_chain_compare", "POST", "/v1/data/cross-chain-compare"),
    ("cortex_token_intel", "POST", "/v1/data/token-intel"),
    ("cortex_aggregate_balances", "POST", "/v1/aggregate/balances"),
    ("cortex_aggregate_nfts", "POST", "/v1/aggregate/nfts"),
    ("cortex_aggregate_prices", "POST", "/v1/aggregate/prices"),
    ("cortex_aggregate_tx_history", "POST", "/v1/aggregate/tx-history"),
)


def _tool_entry(method: str, path: str) -> dict:
    key = f"{method} {path}"
    description = ROUTE_DESCRIPTIONS.get(key, "").strip()
    price = ROUTE_PRICING.get(key, "")
    if price and price != "$0.00":
        description = f"{description} x402 paid: {price} USDC on Base per call.".strip()
    return {
        "method": method,
        "path": path,
        "description": description,
        "input_schema": INPUT_SCHEMAS.get(path, {"type": "object", "properties": {}}),
        "example_input": INPUT_EXAMPLES.get(path),
    }


_TOOLS: dict[str, dict] = {
    name: _tool_entry(method, path) for name, method, path in _SPEC
}
_TOOLS["cortex_capabilities"] = {
    "method": "GET",
    "path": "/v1/capabilities",
    "description": "Free: service capabilities, supported chains/providers, payment terms and discovery index.",
    "input_schema": {"type": "object", "properties": {}},
    "example_input": None,
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
