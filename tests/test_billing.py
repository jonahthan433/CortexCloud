from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from starlette.requests import Request

from app.database.session import AsyncSessionLocal
from app.models.subscription import WalletAPIKey, WalletCreditTransaction, WalletSubscription


async def _db_ready():
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("PostgreSQL scratch database is unavailable")


def _request(path: str) -> Request:
    raw = path.encode()
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST", "scheme": "http", "path": path, "raw_path": raw,
        "query_string": b"", "headers": [], "server": ("test", 80),
        "client": ("127.0.0.1", 12345), "root_path": "",
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_billing_plans_and_manual_prepaid_subscription(client):
    await _db_ready()
    plans = await client.get("/v1/billing/plans")
    assert plans.status_code == 200
    body = plans.json()
    assert body["network"] == "eip155:8453"
    assert {p["id"]: p["credits"] for p in body["plans"]} == {
        "starter": 19000, "trading-pro": 49000, "agent-fleet": 99000,
    }
    assert "no automatic wallet withdrawals" in body["billing"]

    wallet = "0x" + "12" * 20
    nonce = uuid.uuid4().hex
    path = "/v1/billing/subscribe/starter"
    request = _request(path)
    request.state.x402_payer = wallet
    request.state.x402_nonce = nonce
    request.state.x402_amount_atomic = 19_000_000
    request.state.x402_path = path
    from app.api.billing import subscribe
    result = await subscribe("starter", request)
    assert result["status"] == "active"
    assert result["credits_remaining"] == 19000
    assert result["api_key"].startswith("cx_live_")
    assert result["renewal"] == "manual; no automatic wallet withdrawals"

    account = await client.get(
        "/v1/billing/account",
        headers={"Authorization": "Bearer " + result["api_key"]},
    )
    assert account.status_code == 200, account.text
    assert account.json()["wallet"] == wallet
    assert account.json()["credits_remaining"] == 19000
    assert len(account.json()["api_keys"]) == 1

    usage = await client.get(
        "/v1/billing/usage",
        headers={"Authorization": "Bearer " + result["api_key"]},
    )
    assert usage.status_code == 200
    assert usage.json()["transactions"][0]["type"] == "subscription_grant"

    revoke = await client.post(
        "/v1/billing/keys/revoke",
        headers={"Authorization": "Bearer " + result["api_key"]},
        json={"key_id": account.json()["api_keys"][0]["id"]},
    )
    assert revoke.status_code == 200
    assert revoke.json()["revoked"] is True


@pytest.mark.asyncio
async def test_subscription_api_key_spends_weighted_credits(client, monkeypatch):
    await _db_ready()
    from app.core.config import settings
    monkeypatch.setattr(settings, "DATA_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "X402_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "ALCHEMY_API_KEY", "test-key", raising=False)
    monkeypatch.setattr(settings, "WALLET_ADDRESS", "0x" + "11" * 20, raising=False)

    wallet = "0x" + "13" * 20
    raw_key = "cx_live_" + uuid.uuid4().hex
    async with AsyncSessionLocal() as db:
        db.add(WalletSubscription(
            wallet_address=wallet, plan_id="starter", status="active",
            period_start=datetime.now(timezone.utc),
            period_end=datetime.now(timezone.utc) + timedelta(days=30),
            credits_granted=20, credits_remaining=20,
        ))
        db.add(WalletAPIKey(
            wallet_address=wallet, name="test", prefix=raw_key[:16],
            hashed_key=hashlib.sha256(raw_key.encode()).hexdigest(), is_active=True,
        ))
        await db.commit()

    async def fake_rpc(network, method, params):
        assert method == "eth_getBlockByNumber"
        return 200, {"result": {
            "number": "0x2", "hash": "0xabc", "timestamp": "0x64",
            "transactions": [], "parentHash": "0xdef",
        }}

    monkeypatch.setattr("app.api.data._alchemy_rpc", fake_rpc)
    response = await client.get(
        "/v1/data/block?chain=ethereum&block=latest",
        headers={"Authorization": "Bearer " + raw_key, "Idempotency-Key": "block-call-1"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["X-CortexCloud-Billing"] == "subscription_credits"
    assert response.headers["X-CortexCloud-Credits-Used"] == "4"
    assert response.headers["X-CortexCloud-Credits-Remaining"] == "16"

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(WalletSubscription).where(WalletSubscription.wallet_address == wallet))
        subscription = result.scalar_one()
        assert subscription.credits_remaining == 16
        tx = await db.execute(select(WalletCreditTransaction).where(
            WalletCreditTransaction.wallet_address == wallet,
            WalletCreditTransaction.type == "usage_charge",
        ))
        assert tx.scalar_one().amount_credits == -4


@pytest.mark.asyncio
async def test_exhausted_subscription_falls_back_to_x402_overage(client, monkeypatch):
    await _db_ready()
    from app.core.config import settings
    monkeypatch.setattr(settings, "DATA_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "X402_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "ALCHEMY_API_KEY", "test-key", raising=False)
    monkeypatch.setattr(settings, "WALLET_ADDRESS", "0x" + "11" * 20, raising=False)

    wallet = "0x" + "14" * 20
    raw_key = "cx_live_" + uuid.uuid4().hex
    async with AsyncSessionLocal() as db:
        db.add(WalletSubscription(
            wallet_address=wallet, plan_id="starter", status="active",
            period_start=datetime.now(timezone.utc),
            period_end=datetime.now(timezone.utc) + timedelta(days=30),
            credits_granted=10, credits_remaining=0,
        ))
        db.add(WalletAPIKey(
            wallet_address=wallet, name="test", prefix=raw_key[:16],
            hashed_key=hashlib.sha256(raw_key.encode()).hexdigest(), is_active=True,
        ))
        await db.commit()

    response = await client.get(
        "/v1/data/block?chain=ethereum&block=latest",
        headers={"Authorization": "Bearer " + raw_key},
    )
    assert response.status_code == 402, response.text
    assert response.json()["x402Version"] == 2


@pytest.mark.asyncio
async def test_subscription_key_idempotency_prevents_double_debit(client, monkeypatch):
    await _db_ready()
    from app.core.config import settings
    monkeypatch.setattr(settings, "DATA_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "X402_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "ALCHEMY_API_KEY", "test-key", raising=False)
    monkeypatch.setattr(settings, "WALLET_ADDRESS", "0x" + "11" * 20, raising=False)

    wallet = "0x" + "15" * 20
    raw_key = "cx_live_" + uuid.uuid4().hex
    async with AsyncSessionLocal() as db:
        db.add(WalletSubscription(
            wallet_address=wallet, plan_id="starter", status="active",
            period_start=datetime.now(timezone.utc),
            period_end=datetime.now(timezone.utc) + timedelta(days=30),
            credits_granted=20, credits_remaining=20,
        ))
        db.add(WalletAPIKey(
            wallet_address=wallet, name="test", prefix=raw_key[:16],
            hashed_key=hashlib.sha256(raw_key.encode()).hexdigest(), is_active=True,
        ))
        await db.commit()

    async def fake_rpc(network, method, params):
        return 200, {"result": {"number": "0x2", "hash": "0xabc",
                                "timestamp": "0x64", "transactions": [], "parentHash": "0xdef"}}
    monkeypatch.setattr("app.api.data._alchemy_rpc", fake_rpc)
    headers = {"Authorization": "Bearer " + raw_key, "Idempotency-Key": "same-call"}
    first = await client.get("/v1/data/block?chain=ethereum&block=latest", headers=headers)
    second = await client.get("/v1/data/block?chain=ethereum&block=latest", headers=headers)
    assert first.status_code == 200
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_billing_discovery_and_dashboard_are_published(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "X402_ENABLED", True, raising=False)
    capabilities = await client.get("/v1/capabilities")
    assert capabilities.status_code == 200
    billing = capabilities.json()["categories"]["billing"]
    assert billing["status"] == "available"
    assert "/v1/billing/plans" == billing["plans_endpoint"]
    assert "POST /v1/billing/subscribe/starter" in billing["subscription_routes"]

    manifest = await client.get("/.well-known/bazaar")
    assert manifest.status_code == 200
    paths = {item["path"] for item in manifest.json()["endpoints"]}
    assert "/v1/billing/subscribe/starter" in paths

    llms = await client.get("/llms.txt")
    assert "Monthly prepaid subscriptions" in llms.text
    assert "/v1/billing/subscribe/trading-pro" in llms.text

    dashboard = await client.get("/billing.html")
    assert dashboard.status_code == 200
    assert "Billing &amp; usage" in dashboard.text or "Billing & usage" in dashboard.text


@pytest.mark.asyncio
async def test_subscription_purchase_uses_x402_usdc_challenge(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "X402_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "WALLET_ADDRESS", "0x" + "11" * 20, raising=False)
    response = await client.post("/v1/billing/subscribe/starter")
    assert response.status_code == 402, response.text
    body = response.json()
    assert body["x402Version"] == 2
    assert body["accepts"][0]["network"] == "eip155:8453"
    assert body["accepts"][0]["maxAmountRequired"] == "19000000"


@pytest.mark.asyncio
async def test_billing_account_rejects_invalid_api_key(client):
    response = await client.get(
        "/v1/billing/account",
        headers={"Authorization": "Bearer cx_live_not-a-real-key"},
    )
    assert response.status_code == 401
