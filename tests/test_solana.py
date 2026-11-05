"""Solana (Helius) coverage: chain routing, evidence shape, honest gaps.

Run on CT105 (has the app env): pytest tests/test_solana.py
No network: every Helius call is monkeypatched.
"""
from __future__ import annotations

import pytest

from app.x402 import pricing as p

SOL = "HN7cABqLq46Es1jh92dQQgehrS7oKQh2J4nrGk4Fk9Vk"  # arbitrary valid base58
MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC mint (base58)


@pytest.fixture(autouse=True)
def _enable(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "DATA_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "X402_ENABLED", False, raising=False)


# ---------------------------------------------------------------------------
# Pricing / chain table (single source)
# ---------------------------------------------------------------------------
def test_solana_is_not_an_alchemy_network():
    from app.api.data import _network
    for alias in ("solana", "sol", "mainnet-beta", "101"):
        with pytest.raises(ValueError):
            _network(alias)


def test_helius_wiring_is_priced_on_the_floor_and_cheap():
    assert p.HELIUS_ENDPOINTS == ("token-balances", "tx-history", "token-price")
    assert p.helius_provider_cost_usd(1) == 0.000049
    assert p.helius_provider_cost_usd(3) == 0.000147
    # Solana reads stay at the $0.004 floor (provider cost is ~80x below it).
    for ep in p.HELIUS_ENDPOINTS:
        assert p.data_provider_cost_usd(ep) < p.PRICING_FLOOR_USD
        assert p.data_price_usd(ep) == p.PRICING_FLOOR_USD


def test_all_data_chains_is_evm_plus_solana():
    assert p.ALL_DATA_CHAINS == set(p.DATA_CHAINS) | p.SOLANA_CHAINS
    assert p.is_solana("SOL")
    assert not p.is_solana("ethereum")
    assert not p.is_solana(None)


# ---------------------------------------------------------------------------
# Provider config gate
# ---------------------------------------------------------------------------
async def test_solana_without_key_is_503_provider_unconfigured(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "HELIUS_API_KEY", None, raising=False)
    r = await client.post("/v1/data/token-balances", json={"address": SOL, "chain": "solana"})
    assert r.status_code == 503, r.text
    assert r.json()["error"] == "provider_unconfigured"
    assert r.json()["chain"] == "solana"
    assert "settings" not in r.text and "api-key" not in r.text.lower()


# ---------------------------------------------------------------------------
# token-balances (Helius getTokenAccountsByOwner)
# ---------------------------------------------------------------------------
async async def test_solana_token_balances_uses_helius(client, monkeypatch):
    from app.core.config import settings
    from app.api.data import SOLANA_TOKEN_PROGRAM, SOLANA_TOKEN_2022_PROGRAM
    monkeypatch.setattr(settings, "HELIUS_API_KEY", "test-key", raising=False)
    seen_programs = []

    async def fake_rpc(method, params):
        assert method == "getTokenAccountsByOwner"
        assert params[0] == SOL  # base58 passed through, not lowercased
        program = params[1]["programId"]
        seen_programs.append(program)
        if program == SOLANA_TOKEN_PROGRAM:
            values = [{
                "pubkey": "LegacyAccount111111111111111111111111111111",
                "account": {"data": {"parsed": {"info": {
                    "mint": MINT,
                    "owner": SOL,
                    "tokenAmount": {"amount": "1500000", "decimals": 6, "uiAmount": 1.5},
                }}}},
            }]
        else:
            values = []
        return 200, {"result": {"value": values}}

    monkeypatch.setattr("app.api.data._helius_rpc", fake_rpc)
    r = await client.post("/v1/data/token-balances",
                          json={"address": SOL, "chain": "solana"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["chain"] == "solana"
    assert set(seen_programs) == {SOLANA_TOKEN_PROGRAM, SOLANA_TOKEN_2022_PROGRAM}
    # Wrapper keys are snake_case like the rest of the API surface.
    assert body["balances"] == [{"mint": MINT, "raw": "1500000", "decimals": 6, "ui_amount": 1.5}]
    assert body["evidence"]["token_accounts"]["source"] == "helius"
    assert body["evidence"]["balances"]["checked_at"]
    assert body["price_usd"] == 0.004
    assert body["provider_cost_usd"] == 0.000098


async def test_solana_token_balances_filters_by_mint_and_includes_token_2022(client, monkeypatch):
    from app.core.config import settings
    from app.api.data import SOLANA_TOKEN_PROGRAM, SOLANA_TOKEN_2022_PROGRAM
    monkeypatch.setattr(settings, "HELIUS_API_KEY", "test-key", raising=False)

    def account(pubkey, mint, raw):
        return {"pubkey": pubkey, "account": {"data": {"parsed": {"info": {
            "mint": mint,
            "tokenAmount": {"amount": raw, "decimals": 0, "uiAmount": float(raw)},
        }}}}}

    async def fake_rpc(method, params):
        program = params[1]["programId"]
        if program == SOLANA_TOKEN_PROGRAM:
            values = [account("LegacyAcct111111111111111111111111111111", MINT, "1")]
        else:
            values = [account("Token2022Acct1111111111111111111111111111", SOL, "2")]
        return 200, {"result": {"value": values}}

    monkeypatch.setattr("app.api.data._helius_rpc", fake_rpc)
    r = await client.post("/v1/data/token-balances",
                          json={"address": SOL, "chain": "solana", "tokens": [SOL]})
    assert r.status_code == 200, r.text
    assert [b["mint"] for b in r.json()["balances"]] == [SOL]


async def test_solana_token_balances_fails_closed_if_one_program_fails(client, monkeypatch):
    from app.core.config import settings
    from app.api.data import SOLANA_TOKEN_PROGRAM
    monkeypatch.setattr(settings, "HELIUS_API_KEY", "test-key", raising=False)

    async def fake_rpc(method, params):
        if params[1]["programId"] == SOLANA_TOKEN_PROGRAM:
            return 200, {"result": {"value": []}}
        return 503, {"error": "provider unavailable"}

    monkeypatch.setattr("app.api.data._helius_rpc", fake_rpc)
    r = await client.post("/v1/data/token-balances",
                          json={"address": SOL, "chain": "solana"})
    assert r.status_code == 503, r.text
    assert r.json()["error"] == "upstream_helius"


# ---------------------------------------------------------------------------
# tx-history (Helius Enhanced Transactions)
# ---------------------------------------------------------------------------
async def test_solana_tx_history_parses_enhanced_transactions(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "HELIUS_API_KEY", "test-key", raising=False)

    async def fake_tx(address, limit):
        assert address == SOL
        return 200, [{
            "signature": "5" * 88,
            "type": "TRANSFER",
            "description": "Test transfer",
            "timestamp": 1730000000,
            "slot": 123,
            "fee": 5000,
            "feePayer": SOL,
            "nativeTransfers": [{"fromUserAccount": SOL, "toUserAccount": MINT,
                                "amount": 1000}],
            "tokenTransfers": [],
        }]

    monkeypatch.setattr("app.api.data._helius_transactions", fake_tx)
    r = await client.post("/v1/data/tx-history",
                          json={"address": SOL, "chain": "solana", "limit": 1})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["chain"] == "solana" and body["count"] == 1
    tx = body["transactions"][0]
    assert tx["hash"] == "5" * 88
    assert tx["timestamp"].startswith("2024-10-27")
    assert body["evidence"]["transactions"]["source"] == "helius"


# ---------------------------------------------------------------------------
# token-price (Helius getAsset price_info)
# ---------------------------------------------------------------------------
async def test_solana_token_price_from_helius_asset(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "HELIUS_API_KEY", "test-key", raising=False)

    async def fake_rpc(method, params):
        assert method == "getAsset"
        return 200, {"result": {"token_info": {
            "symbol": "USDC", "decimals": 6,
            "price_info": {"price_per_token": 0.9999, "currency": "USD"},
        }}}

    monkeypatch.setattr("app.api.data._helius_rpc", fake_rpc)
    r = await client.post("/v1/data/token-price",
                          json={"contract": MINT, "chain": "solana"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["usd"] == 0.9999
    assert body["provider"] == "helius"
    assert body["evidence"]["price_usd"]["source"] == "helius"


async def test_solana_token_price_rejects_evm_contract(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "HELIUS_API_KEY", "test-key", raising=False)
    r = await client.post("/v1/data/token-price",
                          json={"contract": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                                "chain": "solana"})
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# Honest gaps: every other route says chain_not_supported
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("path,body", [
    ("/v1/data/nft-ownership", {"address": SOL, "chain": "solana"}),
    ("/v1/data/token-risk", {"contract": MINT, "chain": "solana"}),
    ("/v1/data/wallet-intel", {"address": SOL, "chain": "solana"}),
    ("/v1/data/whale-alerts", {"address": SOL, "chain": "solana"}),
    ("/v1/data/token-intel", {"contract": MINT, "chain": "solana"}),
    ("/v1/data/market-snapshot", {"contract": MINT, "chain": "solana"}),
])
async def test_solana_is_explicitly_unsupported_elsewhere(client, path, body):
    r = await client.post(path, json=body)
    assert r.status_code == 400, (path, r.text)
    payload = r.json()
    assert payload["error"] == "chain_not_supported", payload
    assert payload["endpoint"] == path
    assert payload["chain"] == "solana"


async def test_solana_on_get_routes_is_chain_not_supported(client):
    for path in ("/v1/data/gas-oracle", "/v1/data/block"):
        r = await client.get(path, params={"chain": "solana"})
        assert r.status_code == 400, (path, r.text)


# ---------------------------------------------------------------------------
# Discovery surfaces expose the Solana subset
# ---------------------------------------------------------------------------
async def test_discovery_advertises_solana_subset(client):
    r = await client.get("/v1/capabilities")
    body = r.json()
    assert "helius" in body["providers"]
    assert body["solana"]["endpoints"] == [
        "/v1/data/token-balances", "/v1/data/tx-history", "/v1/data/token-price"
    ]
    assert "helius" in body["categories"]["data"]["providers"]

    llms = (await client.get("/llms.txt")).text
    assert "Solana (Helius)" in llms
    assert "chain_not_supported" in llms
    # The TTL table is generated from DATA_TTL_S, not hand-written.
    for name, ttl in p.DATA_TTL_S.items():
        assert f"| /v1/data/{name} | {ttl}s |" in llms
