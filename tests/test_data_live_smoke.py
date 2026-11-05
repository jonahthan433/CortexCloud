"""Data API — staging x402 challenge smoke (not a settlement test).

Checks that the staging gateway exposes correctly formed x402 payment
challenges for representative paid POST and GET data routes. These tests
DO NOT submit payment, settle USDC, execute the paid handler, or verify
billing-ledger entries/provider margins.

Requires:
  - DATA_SMOKE=1 env var (otherwise the whole module is skipped)
  - CORTEXCLOUD_BASE pointing at the staging host (default http://127.0.0.1:8000)
  - the staging API to have its data routes and x402 challenge configuration enabled

A separate funded-buyer integration test is still required to prove end-to-end
USDC settlement, successful paid responses, and ledger accounting.

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


def test_staging_token_price_x402_challenge():
    with _client() as c:
        r = c.post("/v1/data/token-price", json={"id": "ethereum"})
        assert r.status_code == 402, r.text
        import base64, json

        ch = json.loads(base64.b64decode(r.headers["payment-required"]))
        assert ch["x402Version"] == 2
        assert float(ch["accepts"][0]["amount"]) == 4000  # $0.004 in atomic USDC


def test_staging_gas_oracle_x402_challenge():
    with _client() as c:
        r = c.get("/v1/data/gas-oracle", params={"chain": "ethereum"})
        assert r.status_code == 402, r.text
        import base64, json

        ch = json.loads(base64.b64decode(r.headers["payment-required"]))
        assert ch["x402Version"] == 2


def test_staging_token_balances_x402_challenge():
    with _client() as c:
        r = c.post("/v1/data/token-balances",
                   json={"address": "0x" + "0" * 40, "chain": "ethereum"})
        assert r.status_code == 402, r.text
        import base64, json

        ch = json.loads(base64.b64decode(r.headers["payment-required"]))
        assert ch["x402Version"] == 2
        assert "/v1/data/token-balances" in ch["resource"]["url"]
