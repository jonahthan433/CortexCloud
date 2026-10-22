"""H3 regression: GET data routes (block, gas-oracle) must validate query
params BEFORE any payment challenge or settlement.

Before the fix the route-level 400 (bad chain) ran only after the CDP settle:
the payer was charged for a request that could never succeed, with no refund
path. Now an invalid chain/block is a clean 400 and no 402 is asked.

Run: pytest tests/test_get_param_guard.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture(autouse=True)
def _enable_data(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "X402_ENABLED", True)
    monkeypatch.setattr(settings, "DATA_ENABLED", True)


@pytest_asyncio.fixture
async def client():
    app = create_app(override_openapi=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_block_bad_chain_is_400_not_402(client):
    r = await client.get("/v1/data/block", params={"chain": "bogus"})
    assert r.status_code == 400, f"invalid chain must be a clean 400, got {r.status_code}: {r.text[:200]}"
    assert r.json().get("error") == "bad_chain"
    assert "x-payment-required" not in {k.lower() for k in r.headers}


@pytest.mark.asyncio
async def test_gas_oracle_bad_chain_is_400_not_402(client):
    r = await client.get("/v1/data/gas-oracle", params={"chain": "bogus"})
    assert r.status_code == 400, f"invalid chain must be a clean 400, got {r.status_code}"
    assert r.json().get("error") == "bad_chain"


@pytest.mark.asyncio
async def test_block_bad_tag_is_400_not_402(client):
    r = await client.get("/v1/data/block", params={"chain": "ethereum", "block": "not-a-block"})
    assert r.status_code == 400, f"invalid block tag must be a clean 400, got {r.status_code}"
    assert r.json().get("error") == "bad_block"


@pytest.mark.asyncio
@pytest.mark.parametrize("chain", ["ethereum", "base", "8453", "arbitrum", "polygon", "optimism", "eth", "1"])
async def test_valid_chain_still_reaches_paywall(client, chain):
    r = await client.get("/v1/data/block", params={"chain": chain})
    assert r.status_code == 402, f"valid request must still be paywalled, got {r.status_code}"


@pytest.mark.asyncio
async def test_hex_block_tag_passes_guard(client):
    r = await client.get("/v1/data/block", params={"chain": "base", "block": "0x10d4f"})
    assert r.status_code == 402, "valid hex block must pass the guard and reach the paywall"


@pytest.mark.asyncio
async def test_latest_tag_passes_guard(client):
    r = await client.get("/v1/data/gas-oracle", params={"chain": "latest-land"})
    assert r.status_code == 400  # sanity: unknown chain still 400
    r2 = await client.get("/v1/data/block", params={"chain": "optimism", "block": "latest"})
    assert r2.status_code == 402
