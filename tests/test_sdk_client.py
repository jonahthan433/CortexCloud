import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk" / "python"))

import pytest
import cortexcloud.client as client_module
from cortexcloud import CortexCloud, CortexCloudError


class FakeResponse:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.default_headers = kwargs.get("headers") or {}
        self.responses = []
        self.calls = []

    def request(self, method, path, json=None, headers=None):
        merged = {**self.default_headers, **(headers or {})}
        self.calls.append((method, path, json, merged))
        return self.responses.pop(0)

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)


def _configure_fake(fake, kwargs):
    fake.default_headers = kwargs.get("headers") or {}
    return fake


def test_subscription_api_key_pays_without_private_key(monkeypatch):
    fake = FakeClient()
    fake.responses = [FakeResponse(200, {"ok": True})]
    monkeypatch.setattr(client_module.httpx, "Client", lambda *a, **k: _configure_fake(fake, k))
    cc = CortexCloud(api_key="cx_live_example")
    assert cc.pay("POST", "/v1/data/token-price", {"id": "ethereum"}) == {"ok": True}
    assert fake.calls[0][3]["Authorization"] == "Bearer cx_live_example"


def test_api_key_falls_back_to_x402_when_private_key_is_available(monkeypatch):
    fake = FakeClient()
    fake.responses = [FakeResponse(402, {"accepts": [{}]}), FakeResponse(200, {"paid": True})]
    monkeypatch.setattr(client_module.httpx, "Client", lambda *a, **k: fake)
    monkeypatch.setattr(client_module, "sign_payment", lambda challenge, key: "signed-payment")
    cc = CortexCloud(api_key="cx_live_example", private_key="0xprivate")
    assert cc.pay("POST", "/v1/data/token-price", {"id": "ethereum"}) == {"paid": True}
    assert fake.calls[1][3]["Authorization"] == "Bearer cx_live_example"
    assert fake.calls[1][3]["payment-signature"] == "signed-payment"


def test_no_api_key_or_private_key_rejects_paid_call():
    cc = CortexCloud()
    with pytest.raises(CortexCloudError):
        cc.pay("POST", "/v1/data/token-price", {"id": "ethereum"})


def test_token_price_uses_coin_id_schema(monkeypatch):
    fake = FakeClient()
    fake.responses = [FakeResponse(200, {"usd": 1.0})]
    monkeypatch.setattr(client_module.httpx, "Client", lambda *a, **k: fake)
    cc = CortexCloud(api_key="cx_live_example")
    cc.token_price("ethereum")
    assert fake.calls[0][2] == {"id": "ethereum", "currency": "usd", "chain": "ethereum"}


def test_block_uses_block_query_parameter(monkeypatch):
    fake = FakeClient()
    fake.responses = [FakeResponse(200, {"number": 1})]
    monkeypatch.setattr(client_module.httpx, "Client", lambda *a, **k: fake)
    cc = CortexCloud(api_key="cx_live_example")
    cc.block(chain="base", number="latest")
    assert fake.calls[0][1] == "/v1/data/block?chain=base&block=latest"
