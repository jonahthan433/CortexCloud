"""Discovery surfaces: llms.txt, /.well-known/*, openapi.json, MCP tools."""

import json

import pytest

MCP_TOOLS = {"cortex_estimate_optimization", "cortex_optimize", "cortex_get_job", "cortex_list_backends"}

# MCP is served by the standalone cortexcloud-mcp service on :3100, NOT mounted
# on the API gateway (bazaar discovery advertises https://api.cortexcloud.org/mcp,
# which the LB routes to :3100). The API app fixture cannot exercise it.
# Validate the MCP service directly (initialize -> tools/list) out of band.
skip_mcp = pytest.mark.skip(reason="MCP served by standalone :3100 service, not mounted on API gateway; test via MCP service directly")


async def test_llms_txt(client):
    r = await client.get("/llms.txt")
    assert r.status_code == 200
    text = r.text
    assert "OPTIMIZATION" in text.upper()
    assert "POST /v1/optimize" in text
    assert "POST /v1/estimate" in text
    assert "Classic API key" not in text


async def test_well_known_x402(client):
    r = await client.get("/.well-known/x402.json")
    assert r.status_code == 200
    body = r.json()
    assert body["x402"] is True
    assert body["merchant_wallet"].startswith("0x")
    paths = {e["path"] for e in body["endpoints"]}
    assert "/v1/optimize" in paths
    free = {f["path"] for f in body.get("free_endpoints", [])}
    assert "/v1/estimate" in free
    assert "/v1/backends" in free


async def test_bazaar_root(client):
    r = await client.get("/.well-known/bazaar")
    assert r.status_code == 200
    body = r.json()
    assert body["payment"]["scheme"] == "x402"
    tool_names = [t["name"] for t in body["mcp"]["tools"]]
    assert set(tool_names) == MCP_TOOLS
    ep_paths = {e["path"] for e in body["endpoints"]}
    assert "/v1/optimize" in ep_paths and "/v1/estimate" in ep_paths


async def test_openapi_spec_payments(client):
    r = await client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    op = spec["paths"]["/v1/optimize"]["post"]
    assert op.get("security") == [{"x402": []}]
    assert op["x-payment-info"]["scheme"] == "x402"
    assert "402" in op["responses"]
    free_paths = [p for p in spec["paths"] if p.startswith("/v1/")]
    assert "/v1/estimate" in free_paths


@skip_mcp
async def test_mcp_tools_list(client):
    r = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert r.status_code == 200, r.text
    body = r.json()
    tools = {t["name"] for t in body["result"]["tools"]}
    assert tools == MCP_TOOLS


@skip_mcp
async def test_mcp_call_free_tool(client, qb_small):
    r = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
              "params": {"name": "cortex_estimate_optimization", "arguments": qb_small}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "text" in body["result"]["content"][0]
    assert "brute-force" in body["result"]["content"][0]["text"]


@skip_mcp
async def test_mcp_optimize_forwards_402(client, qb_small):
    r = await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 3, "method": "tools/call",
              "params": {"name": "cortex_optimize", "arguments": {"mode": "classical", "problem": qb_small}}},
    )
    assert r.status_code == 402, r.text


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["database"] in ("healthy", "unhealthy")
    assert "backends" in body