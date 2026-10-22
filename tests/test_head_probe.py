"""H2 regression: HEAD must answer with an empty body and a length that
describes it.

Before the fix the probe middleware copied the GET response's Content-Length
onto an empty HEAD body. Under uvicorn that aborted the connection with
"RuntimeError: Response content shorter than Content-Length" on every HEAD to
an unpriced GET route (health, openapi, capabilities...), poisoning x402scan
crawls. These tests pin: HEAD -> 200, empty body, content-length 0.

Run: pytest tests/test_head_probe.py
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


@pytest_asyncio.fixture
async def client():
    app = create_app(override_openapi=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/health", "/v1/capabilities", "/openapi.json"])
async def test_head_empty_body_and_matching_content_length(client, path):
    r = await client.head(path)
    assert r.status_code == 200, f"HEAD {path} -> {r.status_code}"
    assert r.content == b"", "HEAD responses must carry no body"
    cl = r.headers.get("content-length")
    assert cl == "0", f"content-length must describe the empty body, got {cl!r}"


@pytest.mark.asyncio
async def test_head_on_paid_route_still_gets_paywall(client):
    # The paywall runs outside the probe shim: a paid path answers 402 for
    # every method, HEAD included (x402scan method-aware status capture).
    r = await client.head("/v1/data/block")
    assert r.status_code == 402, f"paid HEAD must see the 402 challenge, got {r.status_code}"
