"""Stateless Streamable HTTP MCP gateway backed by existing x402 REST routes."""
import base64
import json
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.x402.bazaar import build_discovery_doc

router = APIRouter()
BASE = settings.X402_RESOURCE_BASE.rstrip("/")

# ponytail: explicit finite catalog; add a route only when the REST capability is live.
_TOOL_ROUTES = (
    ("chat_completions", "POST", "/x402/v1/chat/completions", "OpenAI-compatible chat and vision completion."),
    ("embeddings", "POST", "/x402/v1/embeddings", "Generate text embeddings."),
    ("image_generation", "POST", "/x402/v1/images/generations", "Generate an image from a prompt."),
    ("image_edit", "POST", "/x402/v1/images/image2image", "Edit a base64 PNG with a prompt."),
    ("text_to_speech", "POST", "/x402/v1/audio/speech", "Generate speech audio."),
    ("transcription", "POST", "/x402/v1/audio/transcriptions", "Transcribe base64 audio."),
    ("messages", "POST", "/x402/v1/messages", "Anthropic Messages API passthrough."),
    ("base_balance", "GET", "/x402/v1/data/base/balance", "Get a Base native-token balance."),
    ("base_token_balance", "GET", "/x402/v1/data/base/token-balance", "Get a Base ERC-20 balance."),
    ("base_nonce", "GET", "/x402/v1/data/base/nonce", "Get a Base transaction nonce."),
    ("token_prices", "GET", "/x402/v1/data/prices", "Get token prices."),
    ("coin_search", "GET", "/x402/v1/data/coins/search", "Search coins."),
    ("dex_search", "GET", "/x402/v1/data/dex/search", "Search DEX pairs."),
    ("dex_pairs", "GET", "/x402/v1/data/dex/pairs", "Get DEX pairs."),
)


def mcp_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": description,
            "inputSchema": {"type": "object", "additionalProperties": True},
            "_route": (method, path),
        }
        for name, method, path, description in _TOOL_ROUTES
    ]


def _result(message_id: Any, content: list[dict[str, Any]], is_error: bool = False) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": message_id, "result": {"content": content, "isError": is_error}})


@router.get("/.well-known/bazaar", tags=["Bazaar Discovery"])
async def bazaar_discovery() -> JSONResponse:
    return JSONResponse(content=build_discovery_doc())


@router.get("/mcp", tags=["MCP"])
async def mcp_info() -> JSONResponse:
    return JSONResponse({"name": "CortexCloud MCP", "transport": "streamable-http", "endpoint": "/x402/v1/mcp"})


@router.post("/mcp", tags=["MCP"])
async def mcp_http(request: Request) -> JSONResponse:
    try:
        message = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}, status_code=400)

    message_id = message.get("id")
    method = message.get("method")
    if method == "initialize":
        return JSONResponse({"jsonrpc": "2.0", "id": message_id, "result": {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}}, "serverInfo": {"name": "CortexCloud", "version": "1.0"}}})
    if method == "tools/list":
        return JSONResponse({"jsonrpc": "2.0", "id": message_id, "result": {"tools": [{k: v for k, v in tool.items() if k != "_route"} for tool in mcp_tools()]}})
    if method != "tools/call":
        return JSONResponse({"jsonrpc": "2.0", "id": message_id, "error": {"code": -32601, "message": "Method not found"}}, status_code=404)

    params = message.get("params") or {}
    tool = next((tool for tool in mcp_tools() if tool["name"] == params.get("name")), None)
    if not tool:
        return _result(message_id, [{"type": "text", "text": "Unknown tool."}], True)
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        return _result(message_id, [{"type": "text", "text": "arguments must be an object."}], True)

    route_method, route_path = tool["_route"]
    headers = {"content-type": "application/json"}
    for header in ("payment-signature", "x-payment", "x-correlation-id"):
        if value := request.headers.get(header):
            headers[header] = value
    async with httpx.AsyncClient(timeout=180.0) as client:
        upstream = await client.request(
            route_method, f"{BASE}{route_path}", headers=headers,
            params=arguments if route_method == "GET" else None,
            json=arguments if route_method != "GET" else None,
        )

    if upstream.status_code == 402:
        response = JSONResponse(upstream.json(), status_code=402)
        for header in ("payment-required", "payment-response"):
            if value := upstream.headers.get(header):
                response.headers[header] = value
        return response
    if not upstream.is_success:
        return _result(message_id, [{"type": "text", "text": upstream.text[:4000]}], True)
    if upstream.headers.get("content-type", "").startswith("audio/"):
        return _result(message_id, [{"type": "audio", "mimeType": upstream.headers["content-type"].split(";", 1)[0], "data": base64.b64encode(upstream.content).decode()}])
    try:
        body: Any = upstream.json()
    except ValueError:
        body = upstream.text
    return _result(message_id, [{"type": "text", "text": json.dumps(body)}])
