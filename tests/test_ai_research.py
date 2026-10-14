"""Post-removal positioning checks: the public catalog is data-only and the
de-positioned categories are gone from discovery."""
import pytest


@pytest.mark.asyncio
async def test_capabilities_reports_categories(client):
    r = await client.get("/v1/capabilities")
    assert r.status_code == 200
    cats = r.json()["categories"]
    assert set(cats) == {"data", "aggregate"}


@pytest.mark.asyncio
async def test_removed_categories_absent_from_discovery(client):
    """AI/research/optimization routes are unmounted: discovery must not
    advertise them anywhere."""
    r = await client.get("/.well-known/x402.json")
    paths = {e["path"] for e in r.json()["endpoints"]}
    for gone in ("/v1/ai/chat", "/v1/research/search", "/v1/optimize", "/v1/ml/rerank"):
        assert gone not in paths
    # and they 404 at runtime
    r2 = await client.post("/v1/ai/chat", json={"messages": [{"role": "user", "content": "x"}]})
    assert r2.status_code == 404
    r3 = await client.post("/v1/research/search", json={"query": "x"})
    assert r3.status_code == 404
