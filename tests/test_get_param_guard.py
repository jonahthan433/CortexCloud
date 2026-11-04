"""GET data routes: an unauthenticated probe must reach the 402 challenge.

This supersedes the earlier "bad chain/block is a clean 400 BEFORE the
challenge" guard. AgentCash and x402scan replay a payable resource without a
payment header and reject the listing when a validator answers 400/422 first,
so query validation can no longer run ahead of the paywall.

The H3 guarantee that guard protected (never charge for a request that cannot
succeed) is unchanged: the paid pass validates chain + block BEFORE the settle
branch, which the `*_with_credentials_*` tests below cover.

Run: pytest tests/test_get_param_guard.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import create_app

JUNK_SIG = {"payment-signature": "junkjunk"}


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


# ---- unauthenticated probe: the paywall wins, whatever the query says -------
@pytest.mark.asyncio
async def test_block_bad_chain_reaches_paywall(client):
    r = await client.get("/v1/data/block", params={"chain": "bogus"})
    assert r.status_code == 402, r.text
    assert r.json()["x402Version"] == 2
    assert "payment-required" in {k.lower() for k in r.headers}


@pytest.mark.asyncio
async def test_gas_oracle_bad_chain_reaches_paywall(client):
    r = await client.get("/v1/data/gas-oracle", params={"chain": "bogus"})
    assert r.status_code == 402, r.text


@pytest.mark.asyncio
async def test_block_bad_tag_reaches_paywall(client):
    r = await client.get("/v1/data/block",
                         params={"chain": "ethereum", "block": "not-a-block"})
    assert r.status_code == 402, r.text


# ---- credentials present: rejected BEFORE settle (H3, no charge) -----------
@pytest.mark.asyncio
async def test_block_bad_chain_with_credentials_is_400_not_charged(client):
    r = await client.get("/v1/data/block", params={"chain": "bogus"}, headers=JUNK_SIG)
    assert r.status_code == 400, r.text
    assert r.json().get("error") == "bad_chain"


@pytest.mark.asyncio
async def test_gas_oracle_bad_chain_with_credentials_is_400_not_charged(client):
    r = await client.get("/v1/data/gas-oracle", params={"chain": "bogus"}, headers=JUNK_SIG)
    assert r.status_code == 400, r.text
    assert r.json().get("error") == "bad_chain"


@pytest.mark.asyncio
async def test_block_bad_tag_with_credentials_is_400_not_charged(client):
    r = await client.get("/v1/data/block",
                         params={"chain": "ethereum", "block": "not-a-block"},
                         headers=JUNK_SIG)
    assert r.status_code == 400, r.text
    assert r.json().get("error") == "bad_block"


@pytest.mark.asyncio
async def test_solana_on_block_with_credentials_is_structured_400(client):
    r = await client.get("/v1/data/block", params={"chain": "solana"}, headers=JUNK_SIG)
    assert r.status_code == 400, r.text
    assert r.json().get("error") == "chain_not_supported"


# ---- valid requests still reach the paywall --------------------------------
@pytest.mark.parametrize("chain", ["ethereum", "base", "8453", "arbitrum", "polygon",
                                   "optimism", "eth", "1"])
@pytest.mark.asyncio
async def test_valid_chain_still_reaches_paywall(client, chain):
    r = await client.get("/v1/data/block", params={"chain": chain})
    assert r.status_code == 402, f"valid request must still be paywalled, got {r.status_code}"


@pytest.mark.asyncio
async def test_hex_block_tag_passes_guard(client):
    r = await client.get("/v1/data/block", params={"chain": "base", "block": "0x10d4f"})
    assert r.status_code == 402


@pytest.mark.asyncio
async def test_latest_tag_passes_guard(client):
    r = await client.get("/v1/data/gas-oracle", params={"chain": "latest-land"})
    assert r.status_code == 402
    r2 = await client.get("/v1/data/block", params={"chain": "optimism", "block": "latest"})
    assert r2.status_code == 402
