"""Core data-API contract tests (the only public surface).

The optimization/AI/research/ML surfaces were removed from the public API;
their tests were deleted with them. This file covers what remains: the
capability catalog + the removed routes returning an honest 404.
"""
import json

import pytest


@pytest.mark.asyncio
async def test_capabilities_is_data_only(client):
    r = await client.get("/v1/capabilities")
    assert r.status_code == 200, r.text
    caps = r.json()
    assert caps["service"] == "CortexCloud On-Chain Data API"
    assert set(caps["categories"]) == {"data", "aggregate"}
    assert caps["payments"]["scheme"] == "x402"
    assert caps["providers"] == ["alchemy", "coingecko"]


@pytest.mark.asyncio
async def test_removed_routes_return_404(client):
    """The optimization/AI/research/ML surface is unmounted: every old path
    must answer an honest 404, never a stale 402 or a phantom 200."""
    for method, path in [
        ("POST", "/v1/optimize"),
        ("POST", "/v1/estimate"),
        ("POST", "/v1/quantum/optimize"),
        ("GET", "/v1/backends"),
        ("GET", "/v1/examples"),
        ("GET", "/v1/jobs/some-id"),
        ("POST", "/v1/ai/chat"),
        ("POST", "/v1/research/search"),
        ("POST", "/v1/ml/rerank"),
        ("POST", "/v1/trial"),
        ("POST", "/v1/simulate"),
        ("POST", "/v1/solvers/portfolio"),
        ("GET", "/benchmarks"),
    ]:
        r = await client.request(method, path, json={} if method == "POST" else None)
        assert r.status_code == 404, f"{method} {path} -> {r.status_code}"


@pytest.mark.asyncio
async def test_paid_data_route_still_challenges(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "DATA_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "X402_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "WALLET_ADDRESS", "0x" + "11" * 20, raising=False)
    r = await client.post("/v1/data/token-price", json={"id": "ethereum"})
    assert r.status_code == 402
    assert r.headers.get("payment-required")
