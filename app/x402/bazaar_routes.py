"""Bazaar discovery root + MCP gateway (x402-wrapped /v1/* surface).

- /.well-known/bazaar   — human/agent index of what this service offers
- /x402/v1/mcp          — MCP (Streamable HTTP style) gateway: tools/list,
                          tools/call; paid tools forward the signed payment
                          challenge/verification to the REST layer.

The MCP layer never implements payment logic — it relays HTTP + payment
headers to /v1/* and returns whatever the gateway says, 402 included.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.http import shared_client
from app.x402.bazaar import list_tools, tool_entry
from app.x402.pricing import FREE_ROUTES, ROUTE_DESCRIPTIONS, ROUTE_PRICING

logger = logging.getLogger("cortexcloud.x402.bazaar")

router = APIRouter()


def _endpoint_catalog() -> list[dict]:
    paid = [
        {
            "method": path.split(" ", 1)[0],
            "path": path.split(" ", 1)[1],
            "price": price,
            "description": ROUTE_DESCRIPTIONS.get(path, ""),
        }
        for path, price in ROUTE_PRICING.items()
        if float(price.lstrip("$")) > 0.0
    ]
    free = [
        {"method": "POST", "path": "/v1/estimate", "price": "free", "description": FREE_ROUTES["POST /v1/estimate"]},
        {"method": "GET", "path": "/v1/backends", "price": "free", "description": FREE_ROUTES["GET /v1/backends"]},
        {"method": "GET", "path": "/v1/capabilities", "price": "free", "description": FREE_ROUTES["GET /v1/capabilities"]},
        {"method": "GET", "path": "/v1/jobs/{job_id}", "price": "free", "description": FREE_ROUTES["GET /v1/jobs/{job_id}"]},
        {"method": "GET", "path": "/v1/examples", "price": "free", "description": FREE_ROUTES["GET /v1/examples"]},
    ]
    return paid + free


@router.get("/.well-known/bazaar", tags=["x402 Discovery"])
async def bazaar_root():
    return {
        "name": "CortexCloud Optimization Network",
        "description": "Optimization infrastructure for AI agents — discover, pay for, and execute classical, hybrid, or quantum optimization through a single API.",
        "endpoints": _endpoint_catalog(),
        "mcp": {
            "transport": "streamable-http",
            "endpoint": "/x402/v1/mcp",
            "tools": list_tools(),
        },
        "payment": {
            "scheme": "x402",
            "network": settings.X402_NETWORK,
            "asset": "USDC",
            "facilitator": settings.X402_FACILITATOR_URL,
            "merchant_wallet": settings.WALLET_ADDRESS,
        },
        "discovery": ["/.well-known/x402.json", "/llms.txt", "/openapi.json"],
    }


# ---------------------------------------------------------------- MCP ----
_MCP_VERSION = "2025-03-26"
_DEFAULT_TIMEOUT = 60.0


async def _relay(request: Request, method: str, path: str, payload: dict) -> dict | JSONResponse:
    """Forward to the inner REST surface, carrying x402 payment headers."""
    url = f"http://127.0.0.1:{request.url.port or 8000}{path}"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        **{k: v for k, v in request.headers.items()
           if k.lower() in ("payment-signature", "x-payment", "x-correlation-id")},
    }
    client = shared_client("mcp", _DEFAULT_TIMEOUT)
    resp = await client.request(method, url, json=payload if payload else None, headers=headers)
    if resp.status_code == 402:
        # Return the challenge verbatim so the MCP client can pay.
        try:
            return JSONResponse(status_code=402, content=resp.json(), headers={"payment-required": resp.headers.get("payment-required", "")})
        except Exception:
            return JSONResponse(status_code=402, content={"error": "payment required"})
    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text}
    if resp.status_code >= 400:
        return JSONResponse(status_code=resp.status_code, content=body)
    return body


@router.post("/x402/v1/mcp", tags=["MCP"])
async def mcp_gateway(request: Request):
    try:
        msg = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None})
    method = msg.get("method")
    params = msg.get("params") or {}
    rpc_id = msg.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "protocolVersion": _MCP_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "cortexcloud-optimization-mcp", "version": "0.3.0"},
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rpc_id, "result": {"tools": list_tools()}}
    if method == "tools/call":
        tool_name = (params or {}).get("name")
        args = (params or {}).get("arguments") or {}
        tool = tool_entry(tool_name)
        if tool is None:
            return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32602, "message": f"Unknown tool: {tool_name}"}}
        path = tool["path"].replace("{job_id}", str(args.get("job_id", "")))
        payload = None if tool["method"] == "GET" else args
        if tool["method"] == "GET":
            payload = None
        result = await _relay(request, tool["method"], path, payload)
        if isinstance(result, JSONResponse):
            return result  # 402 challenge or error, untouched
        return {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {"content": [{"type": "text", "text": json.dumps(result, default=str)}]},
        }
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}