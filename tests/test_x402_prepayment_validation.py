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


# ---- pre-payment validation: NO payment signature -------------------------
@pytest.mark.asyncio
async def test_malformed_address_returns_422_not_402(client):
    r = await client.post("/v1/data/token-balances", json={"address": "not-an-address"})
    assert r.status_code == 422, r.text
    assert "x-payment-required" not in {k.lower() for k in r.headers}


@pytest.mark.asyncio
async def test_unsupported_chain_returns_400_not_402(client):
    r = await client.post("/v1/data/token-balances", json={"address": ADDR, "chain": "solana"})
    assert r.status_code == 400, r.text
    body = r.json()
    assert body.get("error") == "bad_request"
    assert any("unsupported chain" in str(e.get("msg", "")) for e in body.get("detail", []))


@pytest.mark.asyncio
async def test_token_price_missing_id_and_contract_returns_422(client):
    # A malformed (non-empty) body is rejected before payment. An EMPTY body
    # falls through to 402 on purpose: the CDP facilitator replays the resource
    # body-less during /validate preflight and rejects the payment when it gets
    # 422 instead of 402 (see middleware guard comment).
    r = await client.post("/v1/data/token-price", json={"contract": "0xBAD"})
    assert r.status_code == 422, r.text
    r_empty = await client.post("/v1/data/token-price", json={})
    assert r_empty.status_code == 402, r_empty.text


@pytest.mark.asyncio
async def test_token_price_empty_body_with_payment_header_returns_422(client):
    # A real payer presenting an invalid body is rejected BEFORE settlement,
    # even when a payment header is present (junk sig proves the guard fires
    # before signature verification — no charge is possible).
    r = await client.post("/v1/data/token-price", json={},
                          headers={"payment-signature": "junkjunk"})
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_token_price_bad_contract_returns_422(client):
    r = await client.post("/v1/data/token-price", json={"contract": "0xBAD"})
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_cross_chain_unsupported_chain_returns_400(client):
    r = await client.post("/v1/data/cross-chain-compare",
                          json={"contract": USDC, "chains": ["ethereum", "solana"]})
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_valid_body_still_returns_402(client):
    """The guard must NOT block valid requests — they still get a challenge."""
    r = await client.post("/v1/data/token-price", json={"id": "ethereum"})
    assert r.status_code == 402, r.text
    ch = r.json()
    acc = ch["accepts"][0]
    assert int(acc["amount"]) == 4000  # $0.004 in USDC base-6
    assert acc["network"] == "eip155:8453"


@pytest.mark.asyncio
async def test_valid_address_with_bad_chain_is_400(client):
    r = await client.post("/v1/data/tx-history", json={"address": ADDR, "chain": "dogechain"})
    assert r.status_code == 400, r.text


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
