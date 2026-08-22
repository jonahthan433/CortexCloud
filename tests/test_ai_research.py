"""AI + Research expansion tests.

These verify the agent-native surface WITHOUT touching Quantum:
- discovery advertises the new routes (x402.json, llms.txt, capabilities)
- feature flags gate the routes (AI off -> 503; Research off -> 503)
- pricing is pegged to provider cost (unit-level, no network)
- paid 402 challenge is returned for AI routes when AI_ENABLED
- the live paid x402 smoke for /v1/ai/chat lives in tests/test_ai_live_smoke.py
  (requires CT105 + test buyer key; run separately, not in CI).
"""
import base64
import json

import pytest

from app.x402 import pricing as p


# --- unit: pricing pegged to provider cost (no hardcoded cost in logic) ---
def test_ai_chat_price_pegged():
    # gemini-2.5-flash 1000 in / 2000 out -> cost $0.0053, price $0.008655
    cost = p.AI_PROVIDERS["chat"].estimate_cost("gemini-2.5-flash", 1000, 2000).provider_cost_usd
    price = p.ai_chat_price_usd("gemini-2.5-flash", 1000, 2000)
    assert cost == 0.0053
    assert price > cost
    # margin ~35% (excluding the flat infra add)
    assert price >= cost * p.PRICING_MARKUP - 0.002


def test_ai_floor_protects_tiny_calls():
    # 1 token in/out -> cost ~0, but floor keeps price >= $0.004
    price = p.ai_chat_price_usd("gemini-2.5-flash", 1, 1)
    assert price >= p.PRICING_FLOOR_USD


def test_research_price_pegged():
    cost = p.RESEARCH_PROVIDERS["search"].estimate_cost("web").provider_cost_usd
    price = p.research_price_usd("web")
    assert cost == 0.004
    assert price > cost
    # answer is slightly pricier than web (Brave AI-Grounding surcharge)
    assert p.research_price_usd("answer") > p.research_price_usd("web")


def test_provider_cost_not_hardcoded_in_business_logic():
    # The advertised rates live in PROVIDER_PRICING (data), not in the route.
    # Re-pricing a provider must change the sell price automatically.
    before = p.ai_chat_price_usd("gemini-2.5-flash", 1000, 2000)
    p.PROVIDER_PRICING["openrouter:gemini-2.5-flash"].input_per_1m = 0.60  # 2x input
    after = p.ai_chat_price_usd("gemini-2.5-flash", 1000, 2000)
    assert after > before
    # restore
    p.PROVIDER_PRICING["openrouter:gemini-2.5-flash"].input_per_1m = 0.30


# --- integration: discovery + feature flags ---
async def test_discovery_lists_ai_and_research(client):
    r = await client.get("/.well-known/x402.json")
    assert r.status_code == 200, r.text
    body = r.json()
    paid_paths = {(e["method"], e["path"]) for e in body["endpoints"]}
    assert ("POST", "/v1/ai/chat") in paid_paths
    assert ("POST", "/v1/research/search") in paid_paths


async def test_llms_txt_includes_categories(client):
    r = await client.get("/llms.txt")
    assert r.status_code == 200
    assert "AI, Research" in r.text or "six categories" in r.text


async def test_capabilities_reports_categories(client):
    r = await client.get("/v1/capabilities")
    assert r.status_code == 200
    cats = r.json()["categories"]
    assert "ai" in cats and "research" in cats and "quantum" in cats


async def test_ai_disabled_returns_503(client):
    # Default test config has AI_ENABLED False -> 503 honest disable.
    r = await client.post("/v1/ai/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 503, r.text
    assert r.json().get("error") == "ai_disabled"


async def test_research_disabled_returns_503(client):
    r = await client.post("/v1/research/search", json={"query": "quantum"})
    assert r.status_code == 503, r.text
    assert r.json().get("error") == "research_disabled"


async def test_ai_estimate_works_when_enabled(client, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.AI_ENABLED", True)
    r = await client.post("/v1/ai/estimate", json={"messages": [{"role": "user", "content": "x" * 400}], "max_tokens": 256})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["price_usd"] > 0
    assert body["provider_cost_usd"] >= 0
    assert body["currency"] == "USDC"


async def test_ai_chat_requires_payment(client, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.AI_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.OPENROUTER_API_KEY", "sk-or-test")
    r = await client.post("/v1/ai/chat", json={"messages": [{"role": "user", "content": "hi"}], "max_tokens": 64})
    # No payment header -> 402 with x402 challenge (same contract as /v1/optimize).
    assert r.status_code == 402, r.text
    assert "payment-required" in r.headers
    challenge = json.loads(base64.b64decode(r.headers["payment-required"]))
    assert challenge["x402Version"] == 2
    assert challenge["resource"]["url"].endswith("/v1/ai/chat")
    assert challenge["accepts"][0]["amount"]  # positive amount in atomic USDC
