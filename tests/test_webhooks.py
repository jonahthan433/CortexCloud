"""Whale-alert webhooks: URL safety, one-time token, free list/delete,
HMAC delivery, and metered accrual.

Delivery is deliberately not paywalled (an outbound webhook cannot answer a
402), so the money path is: paid registration + $0.02 accrued per successful
delivery, visible in the list response.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os

import pytest

from app.api import webhooks as w

ADDR = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
OWNER = "0x5a0353bc9c75b893a9b5735d3e79f1bd988ea143"
URL = "https://example.com/hooks/whales"


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "DATA_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "WEBHOOKS_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "X402_ENABLED", False, raising=False)
    monkeypatch.setattr(settings, "WEBHOOK_STORE_PATH", str(tmp_path / "webhooks.json"), raising=False)
    yield
    w._worker = None


@pytest.fixture
def public_hosts(monkeypatch):
    async def _always(_host):
        return True
    monkeypatch.setattr(w, "_host_resolves_public", _always)


async def _register(client, **overrides):
    payload = {"url": URL, "address": ADDR, "chain": "ethereum", **overrides}
    return await client.post("/v1/webhooks/whale-alerts", json=payload)


def _store_file() -> str:
    from app.core.config import settings
    return os.path.abspath(settings.WEBHOOK_STORE_PATH)


def _read_store() -> dict:
    with open(_store_file()) as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# URL safety
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("url,reason", [
    ("http://example.com/hook", "https"),
    ("https://localhost/hook", "publicly routable"),
    ("https://localhost.localdomain/hook", "publicly routable"),
    ("https://foo.internal/hook", "publicly routable"),
    ("https://printer.local/hook", "publicly routable"),
    ("https://127.0.0.1/hook", "public address"),
    ("https://10.1.2.3/hook", "public address"),
    ("https://192.168.1.15/hook", "public address"),
    ("https://169.254.169.254/latest/meta-data", "public address"),
    ("https://[::1]/hook", "public address"),
    ("https://user:pass@example.com/hook", "credentials"),
    ("https:///hook", "host"),
])
def test_validate_webhook_url_rejects(url, reason):
    err = w.validate_webhook_url(url)
    assert err and reason in err, (url, err)


def test_validate_webhook_url_accepts_public_https():
    assert w.validate_webhook_url(URL) is None
    assert w.validate_webhook_url("https://hooks.example.org:8443/a?b=c") is None


async def test_register_rejects_literal_private_host(client):
    r = await _register(client, url="https://127.0.0.1/hook")
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["error"] == "invalid_webhook_url"
    assert "public" in body["detail"]


async def test_register_rejects_non_resolving_host(client):
    r = await _register(client, url="https://does-not-exist.invalid/hook")
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "invalid_webhook_url"


# ---------------------------------------------------------------------------
# Registration -> list -> delete
# ---------------------------------------------------------------------------
async def test_register_returns_one_time_token_and_no_secret_leak(client, public_hosts):
    r = await _register(client, secret="super-secret-value", min_usd=2500)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["id"]
    assert body["management_token"]
    assert body["price_usd"] == 0.10
    assert body["signed"] is True
    assert body["deliveries"] == 0 and body["amount_due_usd"] == 0.0
    assert body["delivery_price_usd"] == 0.02
    assert body["address"] == ADDR.lower()
    assert body["min_usd"] == 2500.0
    # The secret itself is never echoed; only the fact that signing is on.
    assert "secret" not in body
    assert "super-secret-value" not in r.text

    # On disk: token hash only, 0600.
    raw = _read_store()
    sub = raw["subscriptions"][0]
    assert sub["token_hash"] == hashlib.sha256(body["management_token"].encode()).hexdigest()
    assert body["management_token"] not in json.dumps(raw)
    assert sub["secret"] == "super-secret-value"  # required to sign; never returned
    assert os.stat(_store_file()).st_mode & 0o777 == 0o600
    assert sub["primed"] is False


async def test_list_requires_owner(client, public_hosts):
    r = await client.get("/v1/webhooks/whale-alerts")
    assert r.status_code == 400, r.text
    assert r.json()["error"] == "owner_required"


async def test_list_is_owner_scoped_and_never_leaks(client, public_hosts):
    reg = (await _register(client, secret="another-secret")).json()

    # Registration with x402 disabled has no settled payer; seed the owner so
    # the scoping predicate is exercised (registration sets it post-settlement).
    store = _read_store()
    store["subscriptions"][0]["owner"] = OWNER
    with open(_store_file(), "w") as fh:
        json.dump(store, fh)

    r = await client.get("/v1/webhooks/whale-alerts", params={"owner": OWNER})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["owner"] == OWNER
    assert body["count"] == 1
    assert body["delivery_price_usd"] == 0.02
    item = body["registrations"][0]
    assert item["id"] == reg["id"]
    for leaked in ("secret", "token_hash", "management_token"):
        assert leaked not in item
        assert leaked not in r.text

    other = await client.get("/v1/webhooks/whale-alerts", params={"owner": "0x" + "1" * 40})
    assert other.status_code == 200
    assert other.json()["count"] == 0


async def test_delete_requires_token_and_verifies_it(client, public_hosts):
    reg = (await _register(client)).json()
    sub_id = reg["id"]
    token = reg["management_token"]

    missing = await client.delete(f"/v1/webhooks/whale-alerts/{sub_id}")
    assert missing.status_code == 401, missing.text
    assert missing.json()["error"] == "management_token_required"

    wrong = await client.delete(f"/v1/webhooks/whale-alerts/{sub_id}", params={"token": "nope"})
    assert wrong.status_code == 403, wrong.text

    unknown = await client.delete(f"/v1/webhooks/whale-alerts/{'0' * 8}-dead-beef",
                                  headers={"X-Webhook-Token": token})
    assert unknown.status_code == 404, unknown.text

    ok = await client.delete(f"/v1/webhooks/whale-alerts/{sub_id}",
                             headers={"X-Webhook-Token": token})
    assert ok.status_code == 200, ok.text
    assert ok.json() == {"deleted": True, "id": sub_id, "deliveries": 0, "amount_due_usd": 0.0}
    assert _read_store()["subscriptions"] == []


async def test_registration_limit(client, public_hosts, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "WEBHOOK_MAX_SUBSCRIPTIONS", 1, raising=False)
    assert (await _register(client)).status_code == 200
    second = await _register(client)
    assert second.status_code == 429, second.text
    assert second.json()["error"] == "webhook_limit_reached"


async def test_short_secret_and_bad_address_are_422(client, public_hosts):
    assert (await _register(client, secret="short")).status_code == 422
    assert (await _register(client, address="not-an-address")).status_code == 422
    assert (await _register(client, chain="solana")).status_code == 422
    assert (await _register(client, chain="dogechain")).status_code == 422


# ---------------------------------------------------------------------------
# HMAC delivery
# ---------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code


def _fake_client(captured: dict, status_code: int = 200):
    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, content=None, headers=None):
            captured.update(url=url, content=content, headers=headers)
            return _FakeResponse(status_code)

    return _Client


def _sub(**overrides) -> dict:
    sub = {
        "id": "11111111-2222-3333-4444-555555555555",
        "url": URL, "secret": "delivery-secret", "address": ADDR.lower(),
        "chain": "ethereum", "min_usd": 100000.0, "limit": 50,
        "active": True, "owner": OWNER, "primed": True, "seen": [],
        "deliveries": 0, "amount_due_usd": 0.0, "last_error": None,
    }
    sub.update(overrides)
    return sub


_ALERT = {
    "direction": "out", "hash": "0x" + "ab" * 32, "block_num": "0x1",
    "asset": "ETH", "category": "external", "value": 250.0,
    "value_usd_est": 250.0, "from": ADDR.lower(), "to": "0x" + "cd" * 20,
    "block_timestamp": "2026-10-31T00:00:00Z", "usd_estimated": True,
}


async def test_delivery_is_hmac_signed_over_the_exact_body(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(w.httpx, "AsyncClient", _fake_client(captured))
    monkeypatch.setattr(w, "_host_resolves_public", lambda _h: _true())

    sub = _sub()
    assert await w._deliver(sub, _ALERT) is True

    body = captured["content"]
    expected = "sha256=" + hmac.new(b"delivery-secret", body, hashlib.sha256).hexdigest()
    assert captured["headers"]["X-CortexCloud-Signature"] == expected
    assert captured["headers"]["X-CortexCloud-Event"] == "whale_alert"
    assert captured["headers"]["X-CortexCloud-Delivery"]
    assert captured["url"] == URL

    payload = json.loads(body)
    assert payload["type"] == "whale_alert"
    assert payload["signed"] is True
    assert payload["alert"]["hash"] == _ALERT["hash"]
    assert payload["subscription_id"] == sub["id"]
    assert payload["delivered_at"]
    assert sub["last_error"] is None


async def test_unsigned_delivery_omits_signature(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(w.httpx, "AsyncClient", _fake_client(captured))
    monkeypatch.setattr(w, "_host_resolves_public", lambda _h: _true())

    sub = _sub(secret=None)
    assert await w._deliver(sub, _ALERT) is True
    assert "X-CortexCloud-Signature" not in captured["headers"]
    assert json.loads(captured["content"])["signed"] is False


async def test_delivery_http_error_is_recorded_not_raised(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(w.httpx, "AsyncClient", _fake_client(captured, status_code=500))
    monkeypatch.setattr(w, "_host_resolves_public", lambda _h: _true())

    sub = _sub()
    assert await w._deliver(sub, _ALERT) is False
    assert sub["last_error"] == "http_500"


async def test_delivery_skips_host_that_stops_resolving_public(monkeypatch):
    called = {"post": 0}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            called["post"] += 1
            return _FakeResponse()

    monkeypatch.setattr(w.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(w, "_host_resolves_public", lambda _h: _false())

    sub = _sub()
    assert await w._deliver(sub, _ALERT) is False
    assert called["post"] == 0
    assert "resolve" in sub["last_error"]


async def _true():
    return True


async def _false():
    return False


# ---------------------------------------------------------------------------
# Metered accrual (priming pass, dedupe, $0.02 per success)
# ---------------------------------------------------------------------------
async def test_delivery_metering_primes_dedupes_and_accrues(monkeypatch):
    from app.api import data as d

    alerts = [_ALERT]
    deliveries: list[dict] = []

    async def fake_payload(req, network):
        return {"alerts": list(alerts)}

    async def fake_deliver(sub, alert):
        deliveries.append(alert)
        return True

    monkeypatch.setattr(d, "whale_alert_payload", fake_payload)
    monkeypatch.setattr(w, "_deliver", fake_deliver)

    store = {"version": 1, "subscriptions": [_sub(primed=False)]}
    with open(_store_file(), "w") as fh:
        json.dump(store, fh)

    # Pass 1: prime — existing alerts are recorded, nothing is sent.
    stats = await w.deliver_once()
    assert stats == {"subscriptions": 1, "delivered": 0, "failed": 0, "primed": 1}
    assert deliveries == []
    sub = _read_store()["subscriptions"][0]
    assert sub["primed"] is True
    assert sub["deliveries"] == 0 and sub["amount_due_usd"] == 0.0
    assert len(sub["seen"]) == 1

    # Pass 2: one new alert -> delivered and metered.
    alerts.append({**_ALERT, "hash": "0x" + "ef" * 32})
    stats = await w.deliver_once()
    assert stats["delivered"] == 1 and stats["failed"] == 0
    assert len(deliveries) == 1
    sub = _read_store()["subscriptions"][0]
    assert sub["deliveries"] == 1
    assert sub["amount_due_usd"] == 0.02
    assert sub["last_delivery_at"]
    assert len(sub["seen"]) == 2

    # Pass 3: same alerts -> nothing new, no double charge.
    stats = await w.deliver_once()
    assert stats["delivered"] == 0
    sub = _read_store()["subscriptions"][0]
    assert sub["deliveries"] == 1 and sub["amount_due_usd"] == 0.02


async def test_failed_delivery_does_not_accrue(monkeypatch):
    from app.api import data as d

    async def fake_payload(req, network):
        return {"alerts": [{**_ALERT, "hash": "0x" + "12" * 32}]}

    async def failing_deliver(sub, alert):
        return False

    monkeypatch.setattr(d, "whale_alert_payload", fake_payload)
    monkeypatch.setattr(w, "_deliver", failing_deliver)

    store = {"version": 1, "subscriptions": [_sub(primed=True, seen=[])]}
    with open(_store_file(), "w") as fh:
        json.dump(store, fh)

    stats = await w.deliver_once()
    assert stats["failed"] == 1 and stats["delivered"] == 0
    sub = _read_store()["subscriptions"][0]
    assert sub["deliveries"] == 0 and sub["amount_due_usd"] == 0.0


# ---------------------------------------------------------------------------
# Money path: paid POST, free owner-scoped GET, free DELETE
# ---------------------------------------------------------------------------
async def test_paywall_prices_registration_and_keeps_list_free(client, monkeypatch):
    from app.core.config import settings

    # The autouse fixture disables x402 for route-level tests; this one is
    # about the paywall decision itself.
    monkeypatch.setattr(settings, "X402_ENABLED", True, raising=False)
    # A challenge needs a recipient; the test env has no .env, so pin ours.
    monkeypatch.setattr(settings, "WALLET_ADDRESS", OWNER, raising=False)

    # Parameterless GET advertises the paid resource; with ?owner= it is free.
    r = await client.get("/v1/webhooks/whale-alerts")
    assert r.status_code == 402, r.text
    challenge = r.json()
    accept = challenge["accepts"][0]
    assert int(accept["amount"]) == 100_000  # $0.10 in USDC atomic units

    post = await client.post("/v1/webhooks/whale-alerts", json={"url": URL, "address": ADDR})
    assert post.status_code == 402, post.text
    assert int(post.json()["accepts"][0]["amount"]) == 100_000

    listed = await client.get("/v1/webhooks/whale-alerts", params={"owner": OWNER})
    assert listed.status_code == 200, listed.text
    assert listed.json()["count"] == 0

    deleted = await client.delete("/v1/webhooks/whale-alerts/nope")
    assert deleted.status_code == 401, deleted.text


def test_registration_is_priced_in_the_single_source():
    from app.x402 import pricing as p

    assert p.ROUTE_PRICING["POST /v1/webhooks/whale-alerts"] == "$0.100"
    # Delivery is metered, not a route price: it lives in settings/webhooks.py.
    assert w.DELIVERY_PRICE_USD == 0.02
    assert w.REGISTER_PRICE_USD == 0.10


async def test_discovery_advertises_webhooks(client):
    caps = (await client.get("/v1/capabilities")).json()
    hooks = caps["categories"]["webhooks"]
    assert hooks["registration_price_usd"] == 0.10
    assert hooks["delivery_price_usd"] == 0.02
    assert "POST /v1/webhooks/whale-alerts" in hooks["endpoints"]
    assert "https:// only" in hooks["constraints"]

    llms = (await client.get("/llms.txt")).text
    assert "POST   /v1/webhooks/whale-alerts" in llms
    assert "$0.100" in llms and "$0.020" in llms
    assert "X-CortexCloud-Signature" in llms

    from app.x402.bazaar import tool_entry
    assert tool_entry("cortex_whale_alert_webhook")["path"] == "/v1/webhooks/whale-alerts"

    from app.middleware.x402 import INPUT_EXAMPLES, INPUT_SCHEMAS
    schema = INPUT_SCHEMAS["/v1/webhooks/whale-alerts"]
    example = INPUT_EXAMPLES["/v1/webhooks/whale-alerts"]
    for field in schema.get("required", []):
        assert field in example
