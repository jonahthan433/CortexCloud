"""Tests for the Aggregation API (Tier 1).

Research summarize/extract/compare were never implemented (they 404) and
were never advertised, so they are removed from the test surface.
"""
import pytest


async def test_aggregate_balances_returns_402_without_payment(client):
    r = await client.post("/v1/aggregate/balances", json={"addresses": ["0x0000000000000000000000000000000000000000"]})
    assert r.status_code == 402


async def test_aggregate_prices_returns_402_without_payment(client):
    r = await client.post("/v1/aggregate/prices", json={"ids": ["ethereum"]})
    assert r.status_code == 402


async def test_aggregate_nfts_returns_402_without_payment(client):
    r = await client.post("/v1/aggregate/nfts", json={"addresses": ["0x0000000000000000000000000000000000000000"]})
    assert r.status_code == 402


async def test_aggregate_tx_history_returns_402_without_payment(client):
    r = await client.post("/v1/aggregate/tx-history", json={"addresses": ["0x0000000000000000000000000000000000000000"]})
    assert r.status_code == 402


async def test_discovery_lists_aggregate_endpoints(client):
    r = await client.get("/.well-known/x402.json")
    assert r.status_code == 200
    paths = {e["path"] for e in r.json()["endpoints"]}
    assert "/v1/aggregate/balances" in paths
    assert "/v1/aggregate/prices" in paths
    assert "/v1/aggregate/nfts" in paths
    assert "/v1/aggregate/tx-history" in paths


async def test_llms_txt_includes_new_categories(client):
    r = await client.get("/llms.txt")
    assert r.status_code == 200
    assert "aggregate" in r.text.lower()


async def test_openapi_includes_aggregate_paths(client):
    r = await client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    assert "/v1/aggregate/balances" in spec["paths"]
