"""x402_payments.category must be set for EVERY paid route.

Regression: the category was only assigned in the POST /v1/data/ branch of the
middleware, so GET data routes (block, gas-oracle), every /v1/aggregate route
and the whale-alert webhook registration all settled with category=NULL.

Run: pytest tests/test_payment_category.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "X402_ENABLED", True)
    monkeypatch.setattr(settings, "DATA_ENABLED", True)
    monkeypatch.setattr(settings, "WALLET_ADDRESS", "0x" + "11" * 20)


@pytest_asyncio.fixture
async def client():
    app = create_app(override_openapi=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def test_category_for_path_maps_every_paid_family():
    from app.middleware.x402 import _category_for_path
    assert _category_for_path("/v1/data/block") == "data"
    assert _category_for_path("/v1/aggregate/prices") == "aggregate"
    assert _category_for_path("/v1/webhooks/whale-alerts") == "webhook"
    assert _category_for_path("/v1/capabilities") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,expected", [
    ("GET", "/v1/data/block", "data"),
    ("GET", "/v1/data/gas-oracle", "data"),
    ("POST", "/v1/data/token-balances", "data"),
    ("POST", "/v1/aggregate/balances", "aggregate"),
    ("POST", "/v1/aggregate/tx-history", "aggregate"),
    ("POST", "/v1/webhooks/whale-alerts", "webhook"),
])
async def test_category_set_for_every_paid_route(client, monkeypatch, method, path, expected):
    # The challenge builder calls _resource_url for every paid probe; spy on
    # it to read the category the middleware put on request.state.
    import app.middleware.x402 as x402

    seen = {}
    _orig = x402._resource_url

    def _spy(request, p):
        seen["category"] = getattr(request.state, "category", None)
        return _orig(request, p)

    monkeypatch.setattr(x402, "_resource_url", _spy)
    r = await client.request(method, path, json={} if method == "POST" else None)
    assert r.status_code == 402, f"{method} {path} -> {r.status_code}"
    assert seen.get("category") == expected, (
        f"{method} {path}: category {seen.get('category')!r} != {expected!r}"
    )
