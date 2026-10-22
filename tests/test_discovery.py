"""Discovery surfaces: llms.txt, /.well-known/*, openapi.json, MCP tools."""

import json

import pytest

# MCP: the gateway (separate host service, relayed at /mcp) exposes one tool
# per advertised paid route + free metadata tools; bazaar mirrors that list.



async def test_llms_txt(client):
    r = await client.get("/llms.txt")
    assert r.status_code == 200
    text = r.text
    # advertised product = on-chain data; legacy routes stay mounted but unadvertised
    assert "ON-CHAIN DATA" in text.upper()
    assert "POST /v1/data/token-intel" in text
    assert "POST /v1/optimize" not in text
    assert "Classic API key" not in text


async def test_well_known_x402(client):
    r = await client.get("/.well-known/x402.json")
    assert r.status_code == 200
    body = r.json()
    assert body["x402"] is True
    assert body["merchant_wallet"].startswith("0x")
    paths = {e["path"] for e in body["endpoints"]}
    assert "/v1/data/token-intel" in paths
    assert "/v1/optimize" not in paths  # de-positioned: still paywalled, not advertised
    free = {f["path"] for f in body.get("free_endpoints", [])}
    assert "/v1/capabilities" in free


async def test_bazaar_root(client):
    r = await client.get("/.well-known/bazaar")
    assert r.status_code == 200
    body = r.json()
    assert body["payment"]["scheme"] == "x402"
    # MCP registry mirrors the live paid surface (rebuilt 2026-10-18)
    tools = body["mcp"]["tools"]
    assert len(tools) == 16
    tool_names = {t["name"] for t in tools}
    assert "cortex_token_balances" in tool_names
    assert "cortex_token_intel" in tool_names
    assert "cortex_capabilities" in tool_names
    assert all(t["inputSchema"].get("type") == "object" for t in tools)
    ep_paths = {e["path"] for e in body["endpoints"]}
    assert "/v1/data/token-intel" in ep_paths
    assert "/v1/optimize" not in ep_paths


async def test_openapi_spec_payments(client):
    r = await client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    op = spec["paths"]["/v1/data/token-price"]["post"]
    # paid ops advertise a 402 challenge (verified against the live middleware;
    # the regenerated OpenAPI reflects the route's own responses)
    assert "402" in op["responses"] or "402" in json.dumps(op)
    # the removed optimization surface is gone from the spec
    assert "/v1/optimize" not in spec["paths"]
    assert "/v1/estimate" not in spec["paths"]


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["database"] in ("healthy", "unhealthy")
    assert body["mcp"] in ("running", "down")
    # the solver/optimizer surface is gone; /health must not advertise it
    assert "backends" not in body