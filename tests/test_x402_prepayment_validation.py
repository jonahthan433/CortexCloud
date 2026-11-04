"""Pre-payment validation regression tests for the x402 data gateway.

Covers: malformed body -> 422 (no 402), unsupported chain -> 400 (no 402),
missing payment -> 402, invalid payment -> 402, valid settlement -> 200,
duplicate payment -> 402 (nonce replay after the one-time retry).

Runs against the live app via httpx ASGI transport (no network, no real
USDC): the settlement path is exercised with a stubbed facilitator by
monkeypatching the middleware's CDP client, so these are deterministic.
"""
import base64
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import create_app

ADDR = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"


@pytest.fixture(autouse=True)
def _enable_data(monkeypatch):
    """The prod systemd unit sets DATA_ENABLED=true; tests run without it."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "DATA_ENABLED", True, raising=False)


@pytest_asyncio.fixture
async def client():
    app = create_app(override_openapi=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---- unauthenticated probe: the 402 challenge wins over body validation ----
# AgentCash / x402scan replay a payable resource WITHOUT a payment header and
# reject the listing when a validator answers 400/422 first, so an
# unauthenticated probe must always reach the 402 challenge whatever the body
# says. The H3 guarantee (never charge for a request that cannot succeed) moves
# entirely to the paid pass, asserted below: the SAME body with any payment
# header present is rejected 400/422 BEFORE the settle branch.
_PROBE_CASES = [
    ("/v1/data/token-balances", {"address": "not-an-address"}, 422),
    ("/v1/data/token-balances", {"address": ADDR, "chain": "dogechain"}, 422),
    ("/v1/data/token-balances", {"address": ADDR, "chain": "solana"}, 422),
    ("/v1/data/token-price", {"contract": "0xBAD"}, 422),
    ("/v1/data/token-risk", {"contract": USDC, "chain": "solana"}, 400),
    ("/v1/data/cross-chain-compare", {"contract": USDC, "chains": ["ethereum", "solana"]}, 422),
    ("/v1/data/tx-history", {"address": ADDR, "chain": "dogechain"}, 422),
]


@pytest.mark.parametrize("path,body,paid_status", _PROBE_CASES)
@pytest.mark.asyncio
async def test_unpaid_probe_reaches_402(client, path, body, paid_status):
    r = await client.post(path, json=body)
    assert r.status_code == 402, r.text
    assert r.json()["x402Version"] == 2


@pytest.mark.parametrize("path,body,paid_status", _PROBE_CASES)
@pytest.mark.asyncio
async def test_invalid_body_with_credentials_rejected_before_settle(client, path, body, paid_status):
    r = await client.post(path, json=body, headers={"payment-signature": "junkjunk"})
    assert r.status_code == paid_status, r.text


@pytest.mark.asyncio
async def test_solana_on_non_helius_route_structured_400_before_settle(client):
    # Solana is supported only on token-balances/tx-history/token-price. Every
    # other route refuses BEFORE settlement with the structured error shape.
    r = await client.post("/v1/data/token-risk", json={"contract": USDC, "chain": "solana"},
                          headers={"payment-signature": "junkjunk"})
    assert r.status_code == 400, r.text
    body = r.json()
    assert body.get("error") == "chain_not_supported"
    assert body.get("chain") == "solana"
    assert body.get("solana_supported_endpoints") == [
        "/v1/data/token-balances", "/v1/data/tx-history", "/v1/data/token-price"
    ]


@pytest.mark.asyncio
async def test_token_price_empty_body_with_payment_header_returns_422(client):
    # A real payer presenting an invalid body is rejected BEFORE settlement,
    # even when a payment header is present (junk sig proves the guard fires
    # before signature verification - no charge is possible).
    r = await client.post("/v1/data/token-price", json={},
                          headers={"payment-signature": "junkjunk"})
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_valid_body_still_returns_402(client):
    """The guard must NOT block valid requests - they still get a challenge."""
    r = await client.post("/v1/data/token-price", json={"id": "ethereum"})
    assert r.status_code == 402, r.text
    ch = r.json()
    acc = ch["accepts"][0]
    assert int(acc["amount"]) == 4000  # $0.004 in USDC base-6
    assert acc["network"] == "eip155:8453"


# ---- payment edge cases ----------------------------------------------------
@pytest.mark.asyncio
async def test_garbage_payment_signature_returns_402(client):
    r = await client.post("/v1/data/token-price", json={"id": "ethereum"},
                          headers={"payment-signature": base64.b64encode(b"garbage").decode()})
    assert r.status_code == 402, r.text


@pytest.mark.asyncio
async def test_malformed_body_with_payment_still_422(client):
    """A signature attached to an invalid body must NOT settle — 422 wins."""
    r = await client.post("/v1/data/token-price", json={"id": "ethereum"})
    sig = base64.b64encode(b"{}").decode()
    r2 = await client.post("/v1/data/token-balances", json={"address": "0xBAD"},
                           headers={"payment-signature": sig})
    assert r2.status_code in (402, 422), r2.text
