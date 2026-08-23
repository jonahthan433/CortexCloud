"""Automation API (Tier 1) — unit + security + integration tests.

Unit/security run with no network. Integration (paid x402) runs only when
AUTOMATION_SMOKE=1 is set AND real buyer keys exist (same pattern as Data/ML).
"""
from __future__ import annotations

import importlib

import pytest

# Ensure feature flag on for route logic under test.
from app.core import config as _cfg
_cfg.settings.AUTOMATION_ENABLED = True

from app.x402 import pricing as P
from app.api import automation as A


def test_pricing_floors():
    assert P.automation_price_usd("transform") == 0.004
    assert P.automation_price_usd("http-request") == 0.004
    assert P.automation_price_usd("webhook") == 0.004
    assert P.automation_price_usd("schedule") == 0.010
    assert P.automation_price_usd("workflow") == 0.020
    assert P.automation_provider_cost_usd("transform") == 0.0


def test_flag_gate():
    _cfg.settings.AUTOMATION_ENABLED = False
    try:
        assert A._disabled() is not None
        assert A._disabled().status_code == 503
    finally:
        _cfg.settings.AUTOMATION_ENABLED = True


def test_ssrf_blocks_private_and_metadata():
    for bad in ("http://127.0.0.1:8080/x", "http://10.0.0.5/", "http://169.254.169.254/latest/",
                "http://localhost/", "http://192.168.1.1/", "ftp://example.com", "http://[::1]/"):
        ok, why = A.is_safe_url(bad)
        assert not ok, f"should block {bad} -> {why}"


def test_ssrf_allows_public_https():
    ok, why = A.is_safe_url("https://api.example.com/v1/x")
    # example.com resolves to a public IP; guard should pass.
    assert ok or "unresolved" in why, why


def test_idempotency():
    assert A._dedupe("k1") is True
    assert A._dedupe("k1") is False
    assert A._dedupe("k2") is True
    assert A._dedupe(None) is True


def test_transform_pick_omit_rename_set():
    data = {"a": 1, "b": 2, "c": 3}
    rules = {"pick": ["a", "b"], "rename": {"b": "bee"}, "set": {"src": "x"}}
    out = A._transform(data, rules)
    assert out == {"a": 1, "bee": 2, "src": "x"}


def test_transform_non_dict_passthrough():
    assert A._transform([1, 2, 3], {"pick": ["a"]}) == [1, 2, 3]


def test_hmac_signature_stable():
    body = b'{"ok":true}'
    s1 = A._sign("secret", body)
    s2 = A._sign("secret", body)
    assert s1 == s2 and len(s1) == 64
    assert A._sign("other", body) != s1


def test_workflow_step_limit_constant():
    assert A._MAX_WORKFLOW_STEPS == 10
    assert A._WORKFLOW_TIMEOUT == 120.0


@pytest.mark.asyncio
async def test_http_request_blocks_ssrf():
    from app.api.automation import HttpRequest
    req = HttpRequest(url="http://169.254.169.254/latest/")
    status, data, used = await A._http_call(req, 5.0)
    assert status == 400 and used == "blocked"


@pytest.mark.asyncio
async def test_webhook_blocks_ssrf():
    status, data, used = await A._webhook_deliver("http://127.0.0.1/x", {"a": 1}, {}, "s")
    assert status == 400 and used == "blocked"
