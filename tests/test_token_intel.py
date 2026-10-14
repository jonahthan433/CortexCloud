"""Tests for the Token Intelligence flagship route + data-product positioning.

Run on CT105 (has Postgres): pytest tests/test_token_intel.py
No network in unit tests: provider calls are monkeypatched.
"""
from __future__ import annotations

import pytest


def test_public_product_routes_are_data_only():
    """The advertised product is the on-chain data API; legacy categories
    (optimization/AI/research/ML/automation) stay paywalled but unadvertised."""
    from app.x402.pricing import PUBLIC_PRODUCT_ROUTES, ROUTE_PRICING, public_routes

    assert "POST /v1/data/token-intel" in PUBLIC_PRODUCT_ROUTES
    assert "POST /v1/optimize" not in PUBLIC_PRODUCT_ROUTES
    assert "POST /v1/ai/chat" not in PUBLIC_PRODUCT_ROUTES
    assert "POST /v1/research/search" not in PUBLIC_PRODUCT_ROUTES
    assert "POST /v1/ml/rerank" not in PUBLIC_PRODUCT_ROUTES
    # paywall still gates everything (no free-serving regression)
    for r in PUBLIC_PRODUCT_ROUTES:
        assert r in ROUTE_PRICING
    pr = public_routes()
    assert all(k.startswith(("POST /v1/data/", "GET /v1/data/", "POST /v1/aggregate/")) for k in pr)


def test_token_intel_priced():
    from app.x402.pricing import ROUTE_PRICING, DATA_TTL_S, DATA_PROVIDERS, DATA_TIER2_PRICE_USD
    assert ROUTE_PRICING["POST /v1/data/token-intel"] == "$0.030"
    assert DATA_TTL_S["token-intel"] == 60
    assert "token-intel" in DATA_PROVIDERS
    assert DATA_TIER2_PRICE_USD["token-intel"] == 0.030


def test_manifest_lists_token_intel_not_optimize():
    from app.x402.discovery import build_manifest
    m = build_manifest()
    paths = {e["path"] for e in m["endpoints"]}
    assert "/v1/data/token-intel" in paths
    assert "/v1/optimize" not in paths
    assert "/v1/ai/chat" not in paths
    assert m["endpoints"], "manifest must not be empty"
    for e in m["endpoints"]:
        assert e["price"].startswith("$")
        assert e["description"]


async def test_llms_txt_is_data_positioned(client):
    r = await client.get("/llms.txt")
    assert r.status_code == 200
    body = r.text
    assert "on-chain data" in body.lower()
    assert "/v1/data/token-intel" in body
    assert "/v1/optimize" not in body


async def test_agentsearch_is_data_positioned(client):
    r = await client.get("/.well-known/agentsearch.txt")
    assert r.status_code == 200
    body = r.text
    assert "On-Chain Data API" in body
    assert "token-intel" in body


async def test_bazaar_root_is_data_positioned(client):
    import json
    r = await client.get("/.well-known/bazaar")
    assert r.status_code == 200
    body = r.json()
    paths = {e["path"] for e in body["endpoints"]}
    assert "/v1/data/token-intel" in paths
    assert "/v1/optimize" not in paths
    assert "On-Chain Data" in body["name"]


async def test_capabilities_service_name(client):
    r = await client.get("/v1/capabilities")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "CortexCloud On-Chain Data API"
    assert "/v1/data/token-intel" in body["categories"]["data"]["endpoints"]


async def test_token_intel_402_without_payment(client, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.DATA_ENABLED", True, raising=False)
    monkeypatch.setattr("app.core.config.settings.X402_ENABLED", True, raising=False)
    monkeypatch.setattr("app.core.config.settings.WALLET_ADDRESS", "0x" + "11" * 20, raising=False)
    r = await client.post("/v1/data/token-intel",
                    json={"contract": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "chain": "ethereum"})
    assert r.status_code == 402
    assert r.headers.get("payment-required")


async def test_token_intel_money_guard_rejects_before_payment(client, monkeypatch):
    """A malformed contract must 422 BEFORE any settlement (pay-then-fail is a
    bug). Empty-body probes fall through to 402 because the CDP facilitator
    replays the resource body-less during preflight and rejects payments when
    it gets 422 instead of 402."""
    monkeypatch.setattr("app.core.config.settings.DATA_ENABLED", True, raising=False)
    monkeypatch.setattr("app.core.config.settings.X402_ENABLED", True, raising=False)
    monkeypatch.setattr("app.core.config.settings.WALLET_ADDRESS", "0x" + "11" * 20, raising=False)
    r = await client.post("/v1/data/token-intel", json={"contract": "not-an-address"})
    assert r.status_code == 422
    r2 = await client.post("/v1/data/token-intel", json={})
    assert r2.status_code == 402  # empty probe -> paywall answers (facilitator replay)


async def test_token_intel_junk_sig_invalid_body_never_settles(client, monkeypatch):
    """A payer presenting an invalid body (even with a payment header) is
    rejected before signature verification and settlement."""
    monkeypatch.setattr("app.core.config.settings.DATA_ENABLED", True, raising=False)
    monkeypatch.setattr("app.core.config.settings.X402_ENABLED", True, raising=False)
    monkeypatch.setattr("app.core.config.settings.WALLET_ADDRESS", "0x" + "11" * 20, raising=False)
    r = await client.post("/v1/data/token-intel",
                          json={"contract": "not-an-address"},
                          headers={"payment-signature": "junkjunk"})
    assert r.status_code == 422


async def test_token_intel_503_when_disabled(client, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.DATA_ENABLED", False, raising=False)
    r = await client.post("/v1/data/token-intel",
                    json={"contract": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"})
    assert r.status_code == 503
    assert "disabled" in r.text.lower()


async def test_token_intel_response_shape(client, monkeypatch):
    """Every fact carries source + checked_at; unresolvable fields carry missing."""
    monkeypatch.setattr("app.core.config.settings.DATA_ENABLED", True, raising=False)
    monkeypatch.setattr("app.core.config.settings.ALCHEMY_API_KEY", "test-key-not-used", raising=False)
    monkeypatch.setattr("app.core.config.settings.X402_ENABLED", False, raising=False)

    async def fake_rpc(network, method, params):
        if method == "eth_getCode":
            return 200, {"result": "0x60806040"}
        if method == "alchemy_getTokenMetadata":
            return 200, {"result": {"symbol": "USDC", "name": "USD Coin", "decimals": 6}}
        if method == "alchemy_getAssetTransfers":
            return 200, {"result": {"transfers": []}}
        return 200, {"result": None}

    class FakeResp:
        status_code = 200
        def json(self):
            return {"0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": {"usd": 1.0001, "usd_24h_change": 0.01}}

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None):
            return FakeResp()

    import app.api.data as data_mod
    monkeypatch.setattr(data_mod, "_alchemy_rpc", fake_rpc)
    monkeypatch.setattr(data_mod.httpx, "AsyncClient", lambda *a, **k: FakeClient())
    monkeypatch.setattr(data_mod, "_coingecko_coin", lambda coin_id: _async_dict({}))

    r = await client.post("/v1/data/token-intel",
                    json={"contract": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "chain": "ethereum"})
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body["contract"] == "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    assert body["verdict"] in ("low", "medium", "high")
    facts = body["facts"]
    for key in ("contract_deployed", "symbol", "price_usd"):
        assert key in facts, f"missing fact {key}"
        assert facts[key]["source"], "every fact carries its source"
        assert facts[key]["checked_at"], "every fact carries a timestamp"
    # coin_id not supplied -> age/liquidity must be absent, NOT fabricated
    assert "age_days" not in facts
    assert body["price_usd"] == 0.03


async def _async_dict(d):
    return d
