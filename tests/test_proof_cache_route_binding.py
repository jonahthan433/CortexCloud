"""H1 regression: the payment-proof cache must be bound to the resource path.

Before the fix the proof cache was keyed on the payment signature alone: pay
$0.004 on a cheap route, replay the same signed proof on the $0.040 flagship
within the 60s TTL and it was served from cache WITHOUT re-checking path or
price. These tests pin: a same-path retry is served exactly once; a
cross-path replay is never served (it falls through to the nonce/verification
checks) and the route handler never runs.

Run: pytest tests/test_proof_cache_route_binding.py
"""
import asyncio
import inspect
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core import cache as proofcache
from app.main import create_app

SIG = "proof-binding-test-signature"
CHEAP = "/v1/data/token-price"
RICH = "/v1/data/block"


async def _prime(sig, path):
    """Prime the proof cache exactly like a settled request would, tolerant of
    the pre-fix two-argument signature (so the old behavior is still testable
    and fails with an assertion, not a TypeError)."""
    if "path" in inspect.signature(proofcache.proof_set).parameters:
        proofcache.proof_set(sig, "settled", path)
    else:
        proofcache.proof_set(sig, "settled")


async def _consume(sig, path):
    if "path" in inspect.signature(proofcache.proof_consume).parameters:
        return await proofcache.proof_consume(sig, path)
    return await proofcache.proof_consume(sig)


def test_consume_is_path_bound_unit():
    async def run():
        await _prime(SIG, CHEAP)
        mismatch = await _consume(SIG, RICH)
        # the mismatching replay must NOT have consumed the entry:
        match = await _consume(SIG, CHEAP)
        return mismatch, match

    mismatch, match = asyncio.run(run())
    assert mismatch is False, "cross-route replay must not hit the proof cache"
    assert match is True, "same-route retry must still be served from cache"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "X402_ENABLED", True)
    monkeypatch.setattr(settings, "DATA_ENABLED", True)
    monkeypatch.setattr(settings, "ALCHEMY_API_KEY", settings.ALCHEMY_API_KEY or "test-key")


@pytest_asyncio.fixture
async def client():
    app = create_app(override_openapi=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_cross_route_replay_not_served(client, monkeypatch):
    calls = []

    async def fake_rpc(network, method, params):
        calls.append((network, method))
        return 200, {"result": {
            "number": "0x100", "hash": "0x" + "11" * 32, "timestamp": "0x1",
            "transactions": [], "parentHash": "0x" + "22" * 32,
        }}

    monkeypatch.setattr("app.api.data._alchemy_rpc", fake_rpc)
    await _prime(SIG, CHEAP)
    r = await client.get("/v1/data/block", params={"chain": "ethereum"},
                         headers={"payment-signature": SIG})
    assert r.status_code == 402, f"cross-route replay must be rejected, got {r.status_code}: {r.text[:200]}"
    assert calls == [], "the block handler must never run for a replayed proof"
