"""market-snapshot: one paid call, three sections, partial failures survive.

The bundle is priced below the sum of its parts on purpose (it is one
settlement instead of three). These tests pin that economics, the merge
shape, and the rule that a failing section degrades to an `error` key
instead of failing the whole response.
"""
from __future__ import annotations

import pytest
from fastapi.responses import JSONResponse

from app.x402 import pricing as p

USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"


@pytest.fixture(autouse=True)
def _enable(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "DATA_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "X402_ENABLED", False, raising=False)
    # The route gates on provider config before it fans out; stubs never call
    # the providers, so a placeholder key is enough.
    monkeypatch.setattr(settings, "ALCHEMY_API_KEY", "test-key", raising=False)
    # A snapshot result is cached for 20s; isolate tests from each other.
    from app.api import data as d
    for cache in d._CACHES.values():
        cache._data.clear()
    yield
    for cache in d._CACHES.values():
        cache._data.clear()


def _stub_sections(monkeypatch, *, token=None, whale=None, risk=None):
    """Replace the three sub-handlers. Each defaults to a successful dict."""
    from app.api import data as d

    async def _token(req, request):
        if isinstance(token, BaseException):
            raise token
        if isinstance(token, JSONResponse):
            return token
        return token if token is not None else {
            "contract": req.contract, "chain": req.chain, "symbol": "USDC",
            "cache_hit": False, "price_usd": 0.03, "provider_cost_usd": 0.0001,
            "margin_usd": 0.0299, "currency": "USDC",
        }

    async def _whale(req, request):
        if isinstance(whale, BaseException):
            raise whale
        if isinstance(whale, JSONResponse):
            return whale
        return whale if whale is not None else {
            "watched_address": req.address, "chain": req.chain,
            "alerts": [], "alerts_count": 0, "cache_hit": False,
            "price_usd": 0.05, "currency": "USDC",
        }

    async def _risk(req, request):
        if isinstance(risk, BaseException):
            raise risk
        if isinstance(risk, JSONResponse):
            return risk
        return risk if risk is not None else {
            "contract": req.contract, "chain": req.chain, "verdict": "low",
            "risk_flags": [], "cache_hit": False, "price_usd": 0.02, "currency": "USDC",
        }

    monkeypatch.setattr(d, "token_intel", _token)
    monkeypatch.setattr(d, "whale_alerts", _whale)
    monkeypatch.setattr(d, "token_risk", _risk)


# ---------------------------------------------------------------------------
# Economics
# ---------------------------------------------------------------------------
def test_snapshot_undercuts_the_sum_of_its_parts():
    assert p.ROUTE_PRICING["POST /v1/data/market-snapshot"] == "$0.070"
    assert p.data_price_usd("market-snapshot") == 0.070
    parts = (p.data_price_usd("token-intel")
             + p.data_price_usd("whale-alerts")
             + p.data_price_usd("token-risk"))
    assert parts == 0.100
    assert 0.070 < parts


def test_whale_alerts_price_raise_is_applied_everywhere():
    assert p.ROUTE_PRICING["POST /v1/data/whale-alerts"] == "$0.050"
    assert p.DATA_TIER2_PRICE_USD["whale-alerts"] == 0.050
    assert p.data_price_usd("whale-alerts") == 0.050


def test_snapshot_ttl_and_provider_cost():
    assert p.DATA_TTL_S["market-snapshot"] == 20
    assert p.DATA_PROVIDERS["market-snapshot"].estimate_cost(calls=12).provider_cost_usd > 0
    # 12 upstream calls, still far below the $0.07 price.
    assert p.data_provider_cost_usd("market-snapshot", calls=12) < 0.070


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------
async def test_snapshot_merges_three_sections(client, monkeypatch):
    _stub_sections(monkeypatch)
    r = await client.post("/v1/data/market-snapshot",
                          json={"contract": USDC, "chain": "ethereum"})
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["contract"] == USDC.lower()
    assert body["chain"] == "ethereum"
    assert body["address"] == USDC.lower()  # defaults to the contract
    for key in ("token", "whale_activity", "risk"):
        assert key in body and isinstance(body[key], dict)
    assert body["snapshot_at"]
    assert body["partial"] is False
    assert body["sections"] == {"requested": 3, "ok": 3, "failed": 0}
    assert body["price_usd"] == 0.070
    assert body["currency"] == "USDC"
    # One settlement: the inner routes' own price stamps must not leak through.
    for key in ("token", "whale_activity", "risk"):
        assert "price_usd" not in body[key]
        assert "provider_cost_usd" not in body[key]


async def test_snapshot_honours_address_and_min_usd(client, monkeypatch):
    seen = {}

    from app.api import data as d

    async def _whale(req, request):
        seen["address"] = req.address
        seen["min_usd"] = req.min_usd
        return {"watched_address": req.address, "alerts": [], "alerts_count": 0}

    async def _ok(req, request):
        return {"contract": req.contract}

    monkeypatch.setattr(d, "whale_alerts", _whale)
    monkeypatch.setattr(d, "token_intel", _ok)
    monkeypatch.setattr(d, "token_risk", _ok)

    wallet = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
    r = await client.post("/v1/data/market-snapshot",
                          json={"contract": USDC, "address": wallet, "min_usd": 5000})
    assert r.status_code == 200, r.text
    assert seen == {"address": wallet.lower(), "min_usd": 5000.0}
    assert r.json()["address"] == wallet.lower()


# ---------------------------------------------------------------------------
# Partial failure: one bad section never fails the whole snapshot
# ---------------------------------------------------------------------------
async def test_snapshot_partial_on_upstream_error(client, monkeypatch):
    _stub_sections(
        monkeypatch,
        whale=JSONResponse(status_code=502, content={"error": "upstream_alchemy"}),
        risk=RuntimeError("boom"),
    )
    r = await client.post("/v1/data/market-snapshot",
                          json={"contract": USDC, "chain": "ethereum"})
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["partial"] is True
    assert body["sections"] == {"requested": 3, "ok": 1, "failed": 2}
    assert body["errors"] == {
        "whale_activity": "upstream_alchemy",
        "risk": "subcall_failed:RuntimeError",
    }
    assert body["whale_activity"] == {"error": "upstream_alchemy"}
    assert body["risk"] == {"error": "subcall_failed:RuntimeError"}
    # The surviving section is intact.
    assert body["token"]["symbol"] == "USDC"


async def test_snapshot_all_sections_failing_still_returns_200(client, monkeypatch):
    _stub_sections(
        monkeypatch,
        token=JSONResponse(status_code=503, content={"error": "provider_unconfigured"}),
        whale=JSONResponse(status_code=503, content={"error": "provider_unconfigured"}),
        risk=JSONResponse(status_code=503, content={"error": "provider_unconfigured"}),
    )
    r = await client.post("/v1/data/market-snapshot",
                          json={"contract": USDC, "chain": "ethereum"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["partial"] is True
    assert body["sections"]["ok"] == 0
    assert set(body["errors"]) == {"token", "whale_activity", "risk"}


# ---------------------------------------------------------------------------
# Input validation (no charge ever reaches these: middleware rejects first)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("payload", [
    {},                                                    # contract required
    {"contract": "not-an-address"},                        # format
    {"contract": USDC, "min_usd": -1},                     # negative floor
    {"contract": USDC, "limit": 0},                        # out of range
    {"contract": USDC, "limit": 101},
    {"contract": USDC, "address": "0xBAD"},                # wallet format
])
async def test_snapshot_rejects_bad_input(client, payload):
    r = await client.post("/v1/data/market-snapshot", json=payload)
    assert r.status_code == 422, r.text


async def test_snapshot_refuses_solana_with_structured_error(client):
    r = await client.post("/v1/data/market-snapshot",
                          json={"contract": USDC, "chain": "solana"})
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["error"] == "chain_not_supported"
    assert body["endpoint"] == "/v1/data/market-snapshot"


# ---------------------------------------------------------------------------
# Discovery / examples
# ---------------------------------------------------------------------------
def test_snapshot_examples_satisfy_their_schema():
    from app.middleware.x402 import INPUT_EXAMPLES, INPUT_SCHEMAS, OUTPUT_EXAMPLES
    import re

    schema = INPUT_SCHEMAS["/v1/data/market-snapshot"]
    example = INPUT_EXAMPLES["/v1/data/market-snapshot"]
    assert schema["type"] == "object"
    for field in schema.get("required", []):
        assert field in example, f"example missing required field {field}"
    assert re.fullmatch(schema["properties"]["contract"]["pattern"], example["contract"])

    out = OUTPUT_EXAMPLES["/v1/data/market-snapshot"]
    for key in ("contract", "chain", "token", "whale_activity", "risk",
                "snapshot_at", "partial", "sections"):
        assert key in out
    assert out["price_usd"] == 0.070


async def test_capabilities_and_bazaar_advertise_snapshot(client):
    caps = (await client.get("/v1/capabilities")).json()
    assert "/v1/data/market-snapshot" in caps["categories"]["data"]["endpoints"]
    assert "helius" in caps["categories"]["data"]["providers"]

    from app.x402.bazaar import tool_entry
    tool = tool_entry("cortex_market_snapshot")
    assert tool["path"] == "/v1/data/market-snapshot"
    assert tool["input_schema"]["type"] == "object"

    llms = (await client.get("/llms.txt")).text
    assert "POST /v1/data/market-snapshot" in llms
    assert "$0.070" in llms
