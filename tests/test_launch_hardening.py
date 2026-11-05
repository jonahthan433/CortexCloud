"""Launch-hardening regressions: metrics gating, usage privacy, llms.txt copy.

Run without a database for the auth/copy cases; the payer-matching case skips
when the scratch Postgres is unreachable (it is exercised in CI, which serves
Postgres as a service).
"""
import pytest


@pytest.mark.asyncio
async def test_metrics_is_token_gated(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "INTERNAL_TOKEN", "test-internal-token", raising=False)
    r = await client.get("/metrics")
    assert r.status_code == 401, r.text
    r = await client.get("/metrics", headers={"X-Internal-Token": "wrong"})
    assert r.status_code == 401
    r = await client.get("/metrics", headers={"X-Internal-Token": "test-internal-token"})
    assert r.status_code == 200, r.text
    assert "python_gc" in r.text or r.text.startswith("# HELP")


@pytest.mark.asyncio
async def test_metrics_disabled_when_token_unset(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "INTERNAL_TOKEN", None, raising=False)
    r = await client.get("/metrics")
    assert r.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/x402/v1/usage", "/x402/v1/receipts"])
async def test_usage_and_receipts_require_ownership(client, monkeypatch, path):
    """No public enumeration of any wallet's payment history."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "INTERNAL_TOKEN", "test-internal-token", raising=False)
    addr = "0xCed8a9ff73427302cD0F0F95892EbfC2Ac83374A"
    r = await client.get(path, params={"address": addr})
    assert r.status_code == 401, r.text
    assert r.json()["error"] == "payment_privacy"
    # Operator token passes the gate (200 with a DB, 503 without one).
    r = await client.get(path, params={"address": addr},
                         headers={"X-Internal-Token": "test-internal-token"})
    assert r.status_code in (200, 503), r.text


@pytest.mark.asyncio
async def test_llms_txt_free_webhook_list_requires_owner(client):
    r = await client.get("/llms.txt")
    assert r.status_code == 200
    assert "GET /v1/webhooks/whale-alerts" in r.text
    assert "requires ?owner=0x..." in r.text
    assert "optionally filtered" not in r.text


@pytest.mark.asyncio
async def test_usage_matches_checksummed_payer(client, monkeypatch):
    """Regression: the ledger stores EIP-55 checksummed payers, so both sides
    of the comparison must be lowercased or the endpoint always returns []."""
    from app.core.config import settings
    from app.database.session import AsyncSessionLocal
    from app.models import Payment
    from sqlalchemy import text

    monkeypatch.setattr(settings, "INTERNAL_TOKEN", "test-internal-token", raising=False)
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        pytest.skip("scratch Postgres unavailable")

    addr = "0xCed8a9ff73427302cD0F0F95892EbfC2Ac83374A"
    async with AsyncSessionLocal() as db:
        db.add(Payment(endpoint="/v1/test", payer=addr, amount_atomic=4000,
                       amount_usd=0.004, status="settled"))
        await db.commit()

    r = await client.get("/x402/v1/usage", params={"address": addr},
                         headers={"X-Internal-Token": "test-internal-token"})
    assert r.status_code == 200, r.text
    assert any(u["endpoint"] == "/v1/test" for u in r.json()["usage"])


@pytest.mark.asyncio
async def test_notify_noop_without_credentials(monkeypatch):
    from app.core.config import settings
    from app.core.notify import notify
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", None, raising=False)
    monkeypatch.setattr(settings, "TELEGRAM_ALERT_CHAT_ID", None, raising=False)
    assert await notify("x") is False


@pytest.mark.asyncio
async def test_notify_posts_when_configured(monkeypatch):
    import httpx
    from app.core.config import settings
    from app.core import notify as notify_mod

    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "test-token", raising=False)
    monkeypatch.setattr(settings, "TELEGRAM_ALERT_CHAT_ID", "12345", raising=False)

    seen = {}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            seen["url"] = url
            seen["json"] = json
            return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(notify_mod.httpx, "AsyncClient", FakeClient)
    assert await notify_mod.notify("hello") is True
    assert "test-token" in seen["url"]
    assert seen["json"]["chat_id"] == "12345"
    assert seen["json"]["text"] == "hello"


def test_format_alert_is_secret_free():
    """Only an allow-list of fields is forwarded — arbitrary kwargs (a token,
    a signature, a raw body) must never reach the alert."""
    from app.core.notify import format_alert
    msg = format_alert("proof_rejected", 3, {
        "payer": "0xabc", "reason": "bad_sig", "bucket": "proof",
        "secret": "SHOULD_NOT_APPEAR", "signature": "SHOULD_NOT_APPEAR",
    })
    assert "proof_rejected" in msg and "0xabc" in msg and "bad_sig" in msg
    assert "SHOULD_NOT_APPEAR" not in msg
