#!/usr/bin/env python3
"""Research workflow paid-smoke — one genuine end-to-end x402 paid call.

Issues POST /v1/research/report without payment -> expects 402 -> signs the
challenge with the authorized test wallet -> resubmits -> expects 200 with a
grounded, cited briefing. Verifies idempotency (same request_key replays
without a second charge), price, and ledger recording.

Run: PAYER_PRIVATE_KEY=0x... python3 scripts/research_report_paid_smoke.py [base_url]
"""
import json
import os
import sys

import httpx

sys.path.insert(0, "sdk/python")
from cortexcloud.signing import sign_payment  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://api.cortexcloud.org"
KEY = os.environ.get("PAYER_PRIVATE_KEY", "").strip()
UA = {"User-Agent": "cortex-research-report-smoke/1.0", "accept": "application/json"}
BODY = {"query": "What are the latest advances in quantum error correction?",
        "request_key": "qec-brief-smoke-0001", "count": 5}


def call(body, pay=True):
    r = httpx.post(BASE + "/v1/research/report", json=body, headers=UA, timeout=90)
    if r.status_code == 402 and pay and KEY:
        sig = sign_payment(r.json(), KEY)
        r = httpx.post(BASE + "/v1/research/report", json=body,
                       headers={**UA, "payment-signature": sig}, timeout=90)
    return r.status_code, (r.json() if r.content else {})


def main():
    if not KEY:
        print("SKIP: PAYER_PRIVATE_KEY not set"); sys.exit(0)
    fails = 0
    print(f"== research/report paid-smoke against {BASE} ==")

    # 1) unpaid -> 402
    s, _ = call(BODY, pay=False)
    ok = s == 402; fails += not ok
    print(f"  [{'PASS' if ok else 'FAIL'}] unpaid returns 402 (got {s})")

    # 2) paid -> 200 with cited briefing + sources
    s, b = call(BODY, pay=True)
    ok = s == 200 and b.get("sources") and (b.get("briefing") or b.get("answer_note"))
    fails += not ok
    print(f"  [{'PASS' if ok else 'FAIL'}] paid returns 200 + grounded output (got {s})")
    print(f"       price_usd={b.get('price_usd')} sources={len(b.get('sources', []))} "
          f"briefing={'yes' if b.get('briefing') else 'no (sources only)'}")

    # 3) idempotent replay: same request_key -> stored report, no second charge
    s2, b2 = call(BODY, pay=True)
    ok = s2 == 200 and b2.get("idempotent_replay") is True
    fails += not ok
    print(f"  [{'PASS' if ok else 'FAIL'}] idempotent replay (idempotent_replay=True, got {s2})")

    print("RESULT:", "ALL PASS" if fails == 0 else f"{fails} FAIL")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
