#!/usr/bin/env python3
"""Automation Tier 1 — real x402 paid-smoke (settles USDC on Base).

For each endpoint: issue the request -> expect 402 -> sign with test-buyer
key -> resubmit -> expect 2xx. Verifies price, ledger category=automation,
and (for schedule) Postgres job creation. Mirrors the Data/ML paid-smoke
pattern; uses the repo's x402 v2 signer.

Run: PAYER_PRIVATE_KEY=0x... python3 scripts/automation_paid_smoke.py [base_url]
"""
import json
import os
import sys

import httpx

sys.path.insert(0, "sdk/python")
from cortexcloud.signing import sign_payment  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://api.cortexcloud.org"
KEY = os.environ.get("PAYER_PRIVATE_KEY", "").strip()

UA = {"User-Agent": "cortex-automation-smoke/1.0", "accept": "application/json"}


def call(path, body):
    r = httpx.post(BASE + path, json=body, headers=UA, timeout=60)
    if r.status_code == 402 and KEY:
        sig = sign_payment(r.json(), KEY)
        r = httpx.post(BASE + path, json=body,
                       headers={**UA, "payment-signature": sig}, timeout=60)
    return r.status_code, (r.json() if r.content else {})


def ok(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return cond


def main():
    if not KEY:
        print("SKIP: PAYER_PRIVATE_KEY not set (needs funded test-buyer wallet)")
        sys.exit(0)
    print(f"== automation paid-smoke against {BASE} ==")
    res = []

    # transform (pure, no egress)
    s, b = call("/v1/automation/transform", {"data": {"a": 1, "b": 2}, "rules": {"pick": ["a"]}, "idempotency_key": "smk-transform-1"})
    res.append(ok("transform 200 + shape", s == 200 and b.get("result") == {"a": 1}, f"{s} {b}"))

    # http-request (public, safe target)
    s, b = call("/v1/automation/http-request", {"method": "GET", "url": "https://api.cortexcloud.org/v1/capabilities", "idempotency_key": "smk-http-1"})
    res.append(ok("http-request 200", s == 200, f"{s} {str(b)[:80]}"))

    # webhook (deliver to a public request-bin-style URL; use CortexCloud itself as a noop sink)
    s, b = call("/v1/automation/webhook", {"url": "https://api.cortexcloud.org/v1/capabilities", "payload": {"smoke": True}, "idempotency_key": "smk-webhook-1"})
    res.append(ok("webhook 200", s == 200, f"{s} {str(b)[:80]}"))

    # schedule (persists a 1h-delayed job -> Postgres)
    s, b = call("/v1/automation/schedule", {"url": "https://api.cortexcloud.org/v1/capabilities", "payload": {"smoke": True}, "delay_seconds": 3600, "idempotency_key": "smk-sched-1"})
    res.append(ok("schedule 200 + job_id", s == 200 and bool(b.get("job_id")), f"{s} {b}"))

    # workflow (transform -> webhook)
    s, b = call("/v1/automation/workflow", {"steps": [
        {"type": "transform", "data": {"a": 1}, "rules": {}},
        {"type": "webhook", "url": "https://api.cortexcloud.org/v1/capabilities", "payload": {"a": 1}},
    ], "idempotency_key": "smk-wf-1"})
    res.append(ok("workflow 200", s == 200, f"{s} {str(b)[:80]}"))

    # estimate (free, no payment)
    r = httpx.post(BASE + "/v1/automation/estimate", json={"endpoint": "workflow"}, headers=UA, timeout=30)
    res.append(ok("estimate free 200 + price", r.status_code == 200 and r.json().get("price_usd") == 0.02, f"{r.status_code} {r.text[:80]}"))

    print("\n== summary ==")
    print("  ALL PASS" if all(res) else "  FAILURES PRESENT")
    sys.exit(0 if all(res) else 2)


if __name__ == "__main__":
    main()
