"""Research /ask — LIVE x402 paid smoke (staging only).

Settles REAL USDC from the funded test-buyer wallet to the merchant wallet,
exactly like scripts/data_paid_smoke.py, then asserts the streamed NDJSON
answer. Requires:
  - ASK_SMOKE=1 (otherwise skipped)
  - /root/bzcheck/test_buyer.key present on staging (funded buyer key)
  - CORTEXCLOUD_BASE pointing at the running instance (default http://127.0.0.1:8000)

Run on staging after deploy with RESEARCH_ENABLED=true:
  ASK_SMOKE=1 CORTEXCLOUD_BASE=http://127.0.0.1:8000 \\
    /opt/cortexcloud-venv/bin/python -m pytest tests/test_research_ask_paid_smoke.py -q

Intentionally NOT part of default CI.
"""
import asyncio
import json
import os
import sys

import pytest

SMOKE = os.environ.get("ASK_SMOKE") == "1"
pytestmark = pytest.mark.skipif(not SMOKE, reason="ASK_SMOKE=1 required (staging only)")

BASE = os.environ.get("CORTEXCLOUD_BASE", "http://127.0.0.1:8000").rstrip("/")
KEYPATH = "/root/bzcheck/test_buyer.key"


def test_live_ask_paid_stream():
    import httpx
    from eth_account import Account
    from x402 import x402Client
    from x402.http.x402_http_client import x402HTTPClient
    from x402.mechanisms.evm.exact import ExactEvmScheme

    pk = open(KEYPATH).read().strip()
    buyer = Account.from_key(pk)
    client = x402Client()
    client.register("eip155:8453", ExactEvmScheme(signer=buyer))
    http_client = x402HTTPClient(client)

    async def run():
        fwd = {"host": "api.cortexcloud.org", "x-forwarded-proto": "https"}
        async with httpx.AsyncClient(timeout=120) as session:
            kw = {"headers": {"content-type": "application/json", **fwd}}
            body = {"question": "What does the Bible say about shepherds?"}
            kw["json"] = body
            r1 = await session.post(f"{BASE}/v1/research/ask", **kw)
            assert r1.status_code == 402, r1.text[:400]
            pr = http_client.get_payment_required_response(
                lambda n: r1.headers.get(n), r1.json()
            )
            payload = await http_client.create_payment_payload(pr)
            pay_headers = http_client.encode_payment_signature_header(payload)
            kw2 = {"headers": {**kw["headers"], **pay_headers}, "json": body}
            r2 = await session.post(f"{BASE}/v1/research/ask", **kw2)
            assert r2.status_code == 200, r2.text[:400]
            assert r2.headers["content-type"].startswith("application/x-ndjson")

            kinds, saw_meta, saw_done, scripture_cited = [], False, False, False
            for line in r2.text.splitlines():
                ev = json.loads(line)
                if ev["type"] == "meta":
                    saw_meta = True
                    assert "request_id" in ev and "price_usd" in ev
                elif ev["type"] == "section":
                    kinds.append(ev["kind"])
                    if ev["kind"] == "scripture" and ev.get("refs"):
                        scripture_cited = True
                    for ref in ev.get("refs", []):
                        if ev["kind"] == "scripture" and ref.get("status") != "canonical":
                            raise AssertionError(f"non-canonical ref in Scripture section: {ref}")
                elif ev["type"] == "done":
                    saw_done = True
            assert saw_meta and saw_done, "stream must open with meta and close with done"
            assert kinds == ["scripture", "historical", "scholarly", "ai"], kinds
            assert scripture_cited, "Scripture section must cite a canonical passage"
            return r2

    res = asyncio.run(run())
    # surface ledger/metrics confirmation hint
    print(f"[+] paid /v1/research/ask -> 200, request flow verified")
