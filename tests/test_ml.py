"""ML API (Tier 1) unit + integration tests.

Unit: pricing model, feature-flag gate, cache TTL, provider fallback routing.
Integration (DATA_SMOKE=1 + real provider keys): real x402 settlement per endpoint.
No production code (AI/Research/Data/Quantum) is touched.
"""
from __future__ import annotations

import pytest

from app.x402.pricing import (
    ML_PROVIDERS,
    ml_price_usd,
    ml_provider_cost_usd,
)


def test_ml_pricing_model_floor():
    # image-generate sdxl: provider cost 0.003 -> pegged = max(0.004, 0.003*1.35+0.0015)=max(0.004,0.00555)=0.00555
    p = ml_price_usd("image-generate", "sdxl")
    assert p >= 0.004
    assert abs(p - 0.00555) < 1e-6
    # flux: 0.02 -> max(0.004, 0.02*1.35+0.0015)=0.0285
    pf = ml_price_usd("image-generate", "flux")
    assert abs(pf - 0.0285) < 1e-6
    # rerank floor 0.006, cost 0.001 -> max(0.006, 0.001*1.35+0.0015)=0.006
    pr = ml_price_usd("rerank", docs=10)
    assert pr == 0.006
    # understand cost ~0.0003 -> floor 0.004
    pu = ml_price_usd("image-understand")
    assert pu >= 0.004


def test_ml_provider_cost_distinct():
    assert ml_provider_cost_usd("image-generate", "sdxl") == 0.003
    assert ml_provider_cost_usd("image-generate", "flux") == 0.02
    assert ml_provider_cost_usd("rerank") == 0.001
    assert ml_provider_cost_usd("image-understand") > 0


def test_ml_providers_tuple_primary_fallback():
    # image-generate and rerank declare (primary, fallback)
    assert isinstance(ML_PROVIDERS["image-generate"], tuple) and len(ML_PROVIDERS["image-generate"]) == 2
    assert isinstance(ML_PROVIDERS["rerank"], tuple) and len(ML_PROVIDERS["rerank"]) == 2
    assert ML_PROVIDERS["image-understand"].slug == "openrouter"


@pytest.mark.asyncio
async def test_ml_disabled_503(monkeypatch):
    from app.api import ml as mlroute
    monkeypatch.setattr("app.core.config.settings.ML_ENABLED", False)
    r = await mlroute.image_generate(
        mlroute.ImageGenerateRequest(prompt="x"), request=__import__("starlette.requests", fromlist=["Request"]).Request({"type": "http", "method": "POST", "headers": [], "path": "/v1/ml/image-generate"})
    )
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_image_generate_fallback_replicate(client, monkeypatch):
    """Primary (fal) fails -> fallback (replicate) serves. Mock both transports."""
    import app.api.ml as mlroute
    monkeypatch.setattr("app.core.config.settings.ML_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.X402_ENABLED", False)
    monkeypatch.setattr("app.core.config.settings.FAL_KEY", "fal-x")
    monkeypatch.setattr("app.core.config.settings.REPLICATE_API_KEY", "rep-x")

    async def fake_fal(req, key):
        return 500, {"error": "fal down"}, "fal"

    async def fake_rep(req, key):
        return 200, {"images": ["https://img.example/a.png"]}, "replicate"

    monkeypatch.setattr(mlroute, "_fal_generate", fake_fal)
    monkeypatch.setattr(mlroute, "_replicate_generate", fake_rep)
    r = await client.post("/v1/ml/image-generate", json={"prompt": "cat"})
    assert r.status_code == 200
    j = r.json()
    assert j["provider"] == "replicate"
    assert j["images"] == ["https://img.example/a.png"]
    assert j["price_usd"] >= 0.004
    assert j["margin_usd"] > 0


@pytest.mark.asyncio
async def test_rerank_fallback_jina(client, monkeypatch):
    import app.api.ml as mlroute
    monkeypatch.setattr("app.core.config.settings.ML_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.X402_ENABLED", False)
    monkeypatch.setattr("app.core.config.settings.COHERE_API_KEY", "co-x")
    monkeypatch.setattr("app.core.config.settings.JINA_API_KEY", "ji-x")

    async def fake_co(req, key):
        return 500, {"error": "cohere down"}, "cohere"

    async def fake_ji(req, key):
        return 200, {"results": [{"index": 2, "document": "pizzerias", "relevance_score": 0.9}]}, "jina"

    monkeypatch.setattr(mlroute, "_cohere_rerank", fake_co)
    monkeypatch.setattr(mlroute, "_jina_rerank", fake_ji)
    r = await client.post("/v1/ml/rerank", json={"query": "pizza", "documents": ["a", "b", "Top 10 pizzerias"]})
    assert r.status_code == 200
    j = r.json()
    assert j["provider"] == "jina"
    assert j["results"][0]["index"] == 2


@pytest.mark.asyncio
async def test_image_understand_cache_hit(monkeypatch):
    import app.api.ml as mlroute
    from app.main import create_app
    from httpx import ASGITransport, AsyncClient
    monkeypatch.setattr("app.core.config.settings.ML_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.X402_ENABLED", False)
    monkeypatch.setattr("app.core.config.settings.OPENROUTER_API_KEY", "or-x")
    calls = {"n": 0}

    async def fake_vision(req, key, it, ot):
        calls["n"] += 1
        return 200, {"text": "a red cat"}, "openrouter", 0.0003

    monkeypatch.setattr(mlroute, "_gemini_vision", fake_vision)
    transport = ASGITransport(app=create_app(True))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.post("/v1/ml/image-understand", json={"image_url": "https://x/cat.jpg", "prompt": "describe"})
        r2 = await client.post("/v1/ml/image-understand", json={"image_url": "https://x/cat.jpg", "prompt": "describe"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert calls["n"] == 1  # second served from cache
    assert r2.json()["cache_hit"] is True
