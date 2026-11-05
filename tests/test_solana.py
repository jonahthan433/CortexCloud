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
    monkeypatch.setattr(settings, "HELIUS_VERIFIED", True, raising=False)


# ---------------------------------------------------------------------------
# Pricing / chain table (single source)
# ---------------------------------------------------------------------------
def test_solana_is_not_an_alchemy_network():
    from app.api.data import _network
    for alias in ("solana", "sol", "mainnet-beta", "101"):
        with pytest.raises(ValueError):
            _network(alias)


def test_helius_wiring_is_priced_on_the_floor_and_cheap():
    assert p.HELIUS_ENDPOINTS == ("token-balances", "tx-history", "token-price", "wallet-intel", "token-intel", "token-risk", "whale-alerts", "cross-chain-compare")
    assert p.helius_provider_cost_usd(1) == 0.000049
    assert p.helius_provider_cost_usd(3) == 0.000147
    # Tier-1 Solana reads stay at the $0.004 floor; Tier-2 routes retain their
    # distinct intelligence prices.
    for ep in ("token-balances", "tx-history", "token-price"):
        assert p.data_provider_cost_usd(ep) < p.PRICING_FLOOR_USD
        assert p.data_price_usd(ep) == p.PRICING_FLOOR_USD
    assert p.data_price_usd("wallet-intel") == 0.006
    assert p.data_price_usd("token-risk") == 0.020
    assert p.data_price_usd("token-intel") == 0.030


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
    monkeypatch.setattr(settings, "HELIUS_VERIFIED", False, raising=False)
    r = await client.post("/v1/data/token-balances", json={"address": SOL, "chain": "solana"})
    assert r.status_code == 503, r.text
    assert r.json()["error"] == "provider_unconfigured"
    assert r.json()["chain"] == "solana"
    assert "settings" not in r.text and "api-key" not in r.text.lower()


# ---------------------------------------------------------------------------
# token-balances (Helius getTokenAccountsByOwner)
# ---------------------------------------------------------------------------
async def test_solana_token_balances_uses_helius(client, monkeypatch):
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
async def test_discovery_advertises_solana_subset(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "HELIUS_API_KEY", "test-key", raising=False)
    r = await client.get("/v1/capabilities")
    body = r.json()
    assert "helius" in body["providers"]
    assert body["solana"]["endpoints"] == [
        "/v1/data/token-balances", "/v1/data/tx-history", "/v1/data/token-price", "/v1/data/wallet-intel", "/v1/data/token-intel", "/v1/data/token-risk", "/v1/data/whale-alerts", "/v1/data/cross-chain-compare"
    ]
    assert "helius" in body["categories"]["data"]["providers"]

    llms = (await client.get("/llms.txt")).text
    assert "Solana (Helius)" in llms
    assert "chain_not_supported" in llms
    # The TTL table is generated from DATA_TTL_S, not hand-written.
    for name, ttl in p.DATA_TTL_S.items():
        assert f"| /v1/data/{name} | {ttl}s |" in llms


async def test_discovery_hides_unconfigured_helius_and_solana(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "HELIUS_API_KEY", None, raising=False)
    r = await client.get("/v1/capabilities")
    body = r.json()
    assert "helius" not in body["providers"]
    assert "helius" not in body["categories"]["data"]["providers"]
    assert body["solana"]["status"] == "not_configured"
    assert body["solana"]["endpoints"] == []


async def test_solana_wallet_intel_uses_helius(client, monkeypatch):
    from app.core.config import settings
    from app.api.data import SOLANA_TOKEN_PROGRAM, SOLANA_TOKEN_2022_PROGRAM
    monkeypatch.setattr(settings, "HELIUS_API_KEY", "test-key", raising=False)

    async def fake_rpc(method, params):
        if method == "getBalance":
            return 200, {"result": {"value": 2_000_000_000}}
        assert method == "getTokenAccountsByOwner"
        if params[1]["programId"] == SOLANA_TOKEN_PROGRAM:
            return 200, {"result": {"value": []}}
        assert params[1]["programId"] == SOLANA_TOKEN_2022_PROGRAM
        return 200, {"result": {"value": [{
            "pubkey": "Token2022Acct1111111111111111111111111111",
            "account": {"data": {"parsed": {"info": {
                "mint": MINT,
                "tokenAmount": {"amount": "2500000", "decimals": 6, "uiAmount": 2.5},
            }}}},
        }]}}

    async def fake_transactions(address, limit):
        assert address == SOL and limit == 10
        return 200, [{
            "signature": "sig-one",
            "timestamp": 1730000000,
            "nativeTransfers": [{"fromUserAccount": SOL, "toUserAccount": "Counterparty111111111111111111111111111", "amount": 500000000}],
            "tokenTransfers": [],
        }]

    monkeypatch.setattr("app.api.data._helius_rpc", fake_rpc)
    monkeypatch.setattr("app.api.data._helius_transactions", fake_transactions)
    r = await client.post("/v1/data/wallet-intel", json={"address": SOL, "chain": "solana", "limit": 10})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["native_balance"] == 2.0
    assert body["holdings"][0]["mint"] == MINT
    assert body["recent_out"][0]["asset"] == "SOL"
    assert body["counterparties"][0]["sent_count"] == 1
    assert body["evidence"]["transactions"]["source"] == "helius"


async def test_solana_token_intel_uses_helius_asset_and_activity(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "HELIUS_API_KEY", "test-key", raising=False)

    async def fake_rpc(method, params):
        assert method == "getAsset"
        assert params[0]["id"] == MINT
        return 200, {"result": {
            "id": MINT,
            "interface": "FungibleToken",
            "content": {"metadata": {"name": "Example Solana Token", "symbol": "EST"}},
            "token_info": {
                "symbol": "EST", "decimals": 6, "supply": "1000000000",
                "token_program": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
                "mint_authority": None, "freeze_authority": None,
                "price_info": {"price_per_token": 0.99, "currency": "USD", "24h_change": 1.2},
            },
        }}

    async def fake_transactions(address, limit):
        return 200, [{"signature": "mint-tx", "type": "CREATE", "timestamp": 1730000000, "slot": 10}]

    monkeypatch.setattr("app.api.data._helius_rpc", fake_rpc)
    monkeypatch.setattr("app.api.data._helius_transactions", fake_transactions)
    r = await client.post("/v1/data/token-intel", json={"contract": MINT, "chain": "solana"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["chain"] == "solana"
    assert body["facts"]["symbol"]["value"] == "EST"
    assert body["facts"]["price_usd"]["value"] == 0.99
    assert body["facts"]["token_program"]["value"].startswith("Tokenz")
    assert body["facts"]["latest_transfer"]["value"]["signature"] == "mint-tx"


async def test_solana_token_risk_uses_authorities_and_supply_concentration(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "HELIUS_API_KEY", "test-key", raising=False)

    async def fake_rpc(method, params):
        if method == "getAsset":
            return 200, {"result": {"id": MINT, "token_info": {
                "mint_authority": "Authority11111111111111111111111111111",
                "freeze_authority": None,
            }}}
        if method == "getTokenSupply":
            return 200, {"result": {"value": {"amount": "1000000000", "decimals": 6, "uiAmount": 1000.0}}}
        if method == "getTokenLargestAccounts":
            return 200, {"result": {"value": [
                {"address": "LargestAccount111111111111111111111111111", "amount": "250000000", "decimals": 6, "uiAmount": 250.0},
                {"address": "OtherAccount11111111111111111111111111111", "amount": "100000000", "decimals": 6, "uiAmount": 100.0},
            ]}}
        raise AssertionError(method)

    monkeypatch.setattr("app.api.data._helius_rpc", fake_rpc)
    r = await client.post("/v1/data/token-risk", json={"contract": MINT, "chain": "solana"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["chain"] == "solana"
    assert body["verdict"] == "medium"
    assert "mint_authority_enabled" in body["risk_flags"]
    concentration = next(e for e in body["evidence"] if e["check"] == "largest_token_accounts")
    assert concentration["largest_account_pct_of_supply"] == 25.0
    assert "beneficial wallet owner" in concentration["note"]


async def test_solana_whale_alerts_require_wallet_and_apply_real_usd_prices(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "HELIUS_API_KEY", "test-key", raising=False)

    async def fake_transactions(address, limit):
        return 200, [{
            "signature": "whale-sig",
            "timestamp": 1730000000,
            "nativeTransfers": [{
                "fromUserAccount": address, "toUserAccount": "WhaleCounterparty11111111111111111111111",
                "amount": 1_000_000_000,
            }],
            "tokenTransfers": [{
                "fromUserAccount": "OtherWallet111111111111111111111111111111",
                "toUserAccount": address, "mint": MINT, "tokenAmount": 50.0,
            }],
        }]

    async def fake_rpc(method, params):
        assert method == "getAsset" and params[0]["id"] == MINT
        return 200, {"result": {"token_info": {"price_info": {
            "price_per_token": 2.0, "currency": "USD",
        }}}}

    async def fake_sol_price():
        return 100.0, "test SOL/USD feed"

    monkeypatch.setattr("app.api.data._helius_transactions", fake_transactions)
    monkeypatch.setattr("app.api.data._helius_rpc", fake_rpc)
    monkeypatch.setattr("app.api.data._solana_native_usd_price", fake_sol_price)
    r = await client.post("/v1/data/whale-alerts", json={
        "address": SOL, "chain": "solana", "min_usd": 100.0, "limit": 10,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["alerts_count"] == 2
    assert all(item["value_usd"] >= 100 for item in body["alerts"])
    assert body["unpriced_transfers"] == 0


async def test_solana_whale_alerts_reject_chain_wide_scan(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "HELIUS_API_KEY", "test-key", raising=False)
    r = await client.post("/v1/data/whale-alerts", json={"chain": "solana"})
    assert r.status_code == 422
    assert r.json()["error"] == "address_required"


async def test_solana_cross_chain_compare_requires_explicit_mint_and_compares_both_networks(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "HELIUS_API_KEY", "test-key", raising=False)
    monkeypatch.setattr(settings, "ALCHEMY_API_KEY", "test-key", raising=False)

    async def fake_alchemy(network, method, params):
        if method == "eth_getCode":
            return 200, {"result": "0x6000"}
        if method == "alchemy_getAssetTransfers":
            return 200, {"result": {"transfers": [{"hash": "evm-tx", "blockNum": "0x10"}]}}
        raise AssertionError(method)

    async def fake_helius(method, params):
        assert method == "getAsset" and params[0]["id"] == MINT
        return 200, {"result": {"id": MINT, "token_info": {
            "price_info": {"price_per_token": 1.0, "currency": "USD", "24h_change": 0.5},
        }}}

    async def fake_transactions(address, limit):
        return 200, [{"signature": "sol-tx", "slot": 20}]

    monkeypatch.setattr("app.api.data._alchemy_rpc", fake_alchemy)
    monkeypatch.setattr("app.api.data._helius_rpc", fake_helius)
    monkeypatch.setattr("app.api.data._helius_transactions", fake_transactions)
    r = await client.post("/v1/data/cross-chain-compare", json={
        "contract": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "chains": ["ethereum", "solana"],
        "solana_mint": MINT,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]["chains_checked"] == 2
    sol = next(item for item in body["chains"] if item["chain"] == "solana")
    assert sol["deployed"] is True
    assert sol["price_usd"] == 1.0
    assert sol["latest_tx"] == "sol-tx"


async def test_solana_is_not_advertised_until_helius_is_configured(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "HELIUS_API_KEY", None, raising=False)
    monkeypatch.setattr(settings, "HELIUS_VERIFIED", False, raising=False)
    capabilities = await client.get("/v1/capabilities")
    body = capabilities.json()
    assert body["solana"]["status"] == "not_configured"
    assert body["solana"]["endpoints"] == []
    assert "helius" not in body["providers"]

    llms = await client.get("/llms.txt")
    assert "Solana (Helius)" not in llms.text
    assert "Token-2022" not in llms.text

    monkeypatch.setattr(settings, "HELIUS_API_KEY", "configured-but-not-verified", raising=False)
    capabilities = await client.get("/v1/capabilities")
    body = capabilities.json()
    assert body["solana"]["status"] == "not_verified"
    assert body["solana"]["endpoints"] == []
    assert "helius" not in body["providers"]


async def test_unconfigured_helius_is_rejected_before_x402_settlement(monkeypatch):
    from app.core.config import settings
    from app.middleware.x402 import _chain_not_supported_response
    monkeypatch.setattr(settings, "HELIUS_API_KEY", None, raising=False)
    monkeypatch.setattr(settings, "HELIUS_VERIFIED", False, raising=False)
    result = _chain_not_supported_response(
        "/v1/data/token-balances", {"address": SOL, "chain": "solana"}
    )
    assert result is not None
    assert result.status_code == 503
    assert result.body and b"provider_unconfigured" in result.body

    compare = _chain_not_supported_response(
        "/v1/data/cross-chain-compare",
        {"contract": "0x" + "11" * 20, "chains": ["ethereum", "solana"], "solana_mint": MINT},
    )
    assert compare is not None and compare.status_code == 503


async def test_helius_internal_verification_does_not_auto_enable_solana(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "HELIUS_API_KEY", "fake-test-key", raising=False)
    monkeypatch.setattr(settings, "HELIUS_VERIFIED", False, raising=False)
    monkeypatch.setattr(settings, "INTERNAL_TOKEN", "internal-test-token", raising=False)

    async def fake_rpc(method, params):
        assert method == "getHealth"
        return 200, {"result": "ok"}

    monkeypatch.setattr("app.api.data._helius_rpc", fake_rpc)
    denied = await client.post("/internal/providers/helius/verify",
                               headers={"X-Internal-Token": "wrong"})
    assert denied.status_code == 401

    response = await client.post("/internal/providers/helius/verify",
                                 headers={"X-Internal-Token": "internal-test-token"})
    assert response.status_code == 200, response.text
    assert response.json()["verified"] is True
    assert response.json()["solana_enabled"] is False
    assert "fake-test-key" not in response.text


async def test_solana_data_calls_require_verified_helius(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "HELIUS_API_KEY", "configured-but-not-verified", raising=False)
    monkeypatch.setattr(settings, "HELIUS_VERIFIED", False, raising=False)
    response = await client.post(
        "/v1/data/token-balances",
        json={"address": SOL, "chain": "solana"},
    )
    assert response.status_code == 503
    assert response.json()["error"] == "provider_unverified"
