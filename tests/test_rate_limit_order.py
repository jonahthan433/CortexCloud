"""H3 regression: the payer rate limit must run BEFORE the CDP validate and
settle calls.

Before the fix an over-limit payer was settled first and got the 429 only
afterwards — charged for a request never served, with no refund path. These
tests pin: over-limit -> 429 + Retry-After with ZERO facilitator calls, even
when proof verification would succeed.

Run: pytest tests/test_rate_limit_order.py
"""
import base64
import json
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import create_app

PAYER = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"


class _FakeResp:
    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class _RecordingCDP:
    def __init__(self):
        self.calls = []

    async def post(self, url, json=None, headers=None):
        self.calls.append(url)
        if url.endswith("/validate"):
            return _FakeResp({"valid": True})
        return _FakeResp({"success": True, "transaction": "0x" + "ab" * 32})


@pytest.fixture
def fake_cdp(monkeypatch):
    fake = _RecordingCDP()
    monkeypatch.setattr("app.middleware.x402.shared_client", lambda name, timeout: fake)
    return fake


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "X402_ENABLED", True)
    monkeypatch.setattr(settings, "DATA_ENABLED", True)
    monkeypatch.setattr(settings, "X402_RATE_LIMIT", 0)  # any request is over the limit
    if not settings.X402_FACILITATOR_URL:
        monkeypatch.setattr(settings, "X402_FACILITATOR_URL", "https://facilitator.test", raising=False)


@pytest_asyncio.fixture
async def client():
    app = create_app(override_openapi=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _payment_header() -> str:
    payload = {
        "x402Version": 2,
        "payload": {"authorization": {
            "from": PAYER,
            "nonce": "0x" + uuid.uuid4().hex + uuid.uuid4().hex[:32],
            "validBefore": str(int(time.time()) + 300),
        }},
        "accepted": {"amount": "4000", "network": "eip155:8453"},
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


@pytest.mark.asyncio
async def test_over_limit_payer_never_reaches_facilitator(client, fake_cdp, monkeypatch):
    # Verification is stubbed OK: the ONLY thing between this request and the
    # facilitator is the rate limiter — which must answer 429 first.
    monkeypatch.setattr("app.middleware.payverify.verify_proof",
                        lambda sig, price, path: (True, "stubbed-ok", {}))
    r = await client.post("/v1/data/token-price", json={"id": "ethereum"},
                          headers={"payment-signature": _payment_header()})
    assert r.status_code == 429, f"over-limit payer must get 429, got {r.status_code}: {r.text[:200]}"
    assert r.headers.get("retry-after") == "60"
    assert fake_cdp.calls == [], f"facilitator must not be called for an over-limit payer (calls={fake_cdp.calls})"
