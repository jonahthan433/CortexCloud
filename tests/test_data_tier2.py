"""Self-check for Tier 2 data routes: pricing, TTL, provider registration,
money-path validation. Run: python tests/test_data_tier2.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.x402.pricing import (
    DATA_TIER2_PRICE_USD, DATA_TTL_S, DATA_PROVIDERS, data_price_usd, data_provider_cost_usd,
)

# Pricing is the published list price, within the brief's ranges.
assert data_price_usd("token-risk") == 0.020, data_price_usd("token-risk")
assert 0.01 <= data_price_usd("token-risk") <= 0.03
assert 0.003 <= data_price_usd("wallet-intel") <= 0.01
assert 0.01 <= data_price_usd("whale-alerts") <= 0.05
assert 0.02 <= data_price_usd("cross-chain-compare") <= 0.05

# Provider cost scales with fan-out calls (so ledger margin is real).
assert data_provider_cost_usd("token-risk", 4) > data_provider_cost_usd("token-risk", 1)
assert data_provider_cost_usd("cross-chain-compare", 10) > data_provider_cost_usd("cross-chain-compare", 2)

# All four have a TTL + provider entry (cache + cost accounting wired).
for ep in DATA_TIER2_PRICE_USD:
    assert ep in DATA_TTL_S, f"missing TTL for {ep}"
    assert ep in DATA_PROVIDERS, f"missing provider for {ep}"

# Tier 1 unchanged: still the $0.004 floor path.
assert data_price_usd("token-price") == 0.004

print("PASS: tier2 pricing/ttl/provider/cost-scaling; tier1 floor intact")
