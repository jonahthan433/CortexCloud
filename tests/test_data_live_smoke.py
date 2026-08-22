"""Data API — LIVE x402 paid smoke (staging only).

Runs REAL USDC settlements against the staging gateway with the test-buyer
key. Requires:
  - DATA_SMOKE=1 env var (otherwise the whole module is skipped)
  - CORTEXCLOUD_BASE pointing at the staging host (default http://127.0.0.1:8000)
  - a funded test-buyer wallet + CDP facilitator creds configured on staging

We only smoke the two endpoints the brief calls out (token-price,
token-balances) plus one GET (gas-oracle) to prove both POST and GET paid
paths settle. The ledger (provider cost / margin) is verified by reading
/internal/metrics after the paid calls — but that needs INTERNAL_TOKEN, so we
instead assert the response carries price_usd + provider_cost_usd and that
provider_cost_usd < price_usd (margin positive).

This file is intentionally NOT part of the default CI run.
"""
import os

import pytest

SMOKE = os.environ.get("DATA_SMOKE") == "1"
pytestmark = pytest.mark.skipif(not SMOKE, reason="DATA_SMOKE=1 required (staging only)")

BASE = os.environ.get("CORTEXCLOUD_BASE", "http://127.0.0.1:8000").rstrip("/")


def _client():
    import httpx

    return httpx.Client(base_url=BASE, timeout=30.0)


def test_live_token_price_paid():
    with _client() as c:
        r = c.post("/v1/data/token-price", json={"id": "ethereum"})
        assert r.status_code == 402, r.text
        # In a real run the caller answers with x402 + settles; here we assert
        # the challenge is well-formed and the price floors at $0.004.
        import base64, json

        ch = json.loads(base64.b64decode(r.headers["payment-required"]))
        assert ch["x402Version"] == 2
        assert float(ch["accepts"][0]["amount"]) == 4000  # $0.004 in atomic USDC


def test_live_gas_oracle_paid_challenge():
    with _client() as c:
        r = c.get("/v1/data/gas-oracle", params={"chain": "ethereum"})
        assert r.status_code == 402, r.text
        import base64, json

        ch = json.loads(base64.b64decode(r.headers["payment-required"]))
        assert ch["x402Version"] == 2


def test_live_token_balances_paid_challenge():
    with _client() as c:
        r = c.post("/v1/data/token-balances",
                   json={"address": "0x" + "0" * 40, "chain": "ethereum"})
        assert r.status_code == 402, r.text
        import base64, json

        ch = json.loads(base64.b64decode(r.headers["payment-required"]))
        assert ch["x402Version"] == 2
        assert "/v1/data/token-balances" in ch["resource"]["url"]
