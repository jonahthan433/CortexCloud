#!/usr/bin/env python3
"""ML API (Tier 1) paid validation — 3 endpoints.

For each: 402 -> sign -> CDP settle -> provider -> 200 -> cost/price/margin.
Reuses the proven x402 buyer + SDK. Run: python3 ml_paid_smoke.py <base>
"""
import asyncio
import sys
import httpx
from eth_account import Account
from x402 import x402Client, prefer_network
from x402.http.x402_http_client import x402HTTPClient
from x402.mechanisms.evm.exact import ExactEvmScheme

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://api.cortexcloud.org"
pk = open("/root/bzcheck/test_buyer.key").read().strip()
buyer = Account.from_key(pk)
client = x402Client()
client.register("eip155:8453", ExactEvmScheme(signer=buyer))
client.register_policy(prefer_network("eip155:8453"))
hc = x402HTTPClient(client)
FWD = {"host": "api.cortexcloud.org", "x-forwarded-proto": "https"}

CALLS = [
    ("POST", "/v1/ml/image-generate", {"prompt": "a serene lake at sunrise, oil painting", "model": "sdxl"}, None),
    ("POST", "/v1/ml/image-understand", {"image_b64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC", "prompt": "What color is this image?"}, None),
    ("POST", "/v1/ml/rerank", {"query": "best pizza in town", "documents": ["How to fix a bike", "Top 10 pizzerias downtown", "Pizza recipe book"]}, None),
]


async def paid(method, path, json_body, params):
    async with httpx.AsyncClient(timeout=150) as s:
        kw = {"headers": {"content-type": "application/json", **FWD}}
        if json_body:
            kw["json"] = json_body
        if params:
            kw["params"] = params
        r1 = await s.request(method, f"{BASE}{path}", **kw)
        if r1.status_code != 402:
            return f"EXPECTED 402 got {r1.status_code}: {r1.text[:200]}"
        pr = hc.get_payment_required_response(lambda n: r1.headers.get(n), r1.json())
        payload = await hc.create_payment_payload(pr)
        pay = hc.encode_payment_signature_header(payload)
        kw2 = {"headers": {**kw["headers"], **pay}}
        if json_body:
            kw2["json"] = json_body
        if params:
            kw2["params"] = params
        r2 = await s.request(method, f"{BASE}{path}", **kw2)
        if r2.status_code != 200:
            return f"PAID FAIL {r2.status_code}: {r2.text[:400]}"
        j = r2.json()
        r3 = await s.request(method, f"{BASE}{path}", **kw2)
        ch = r3.json().get("cache_hit") if r3.status_code == 200 else None
        return (f"200 price={j.get('price_usd')} prov_cost={j.get('provider_cost_usd')} "
                f"margin={j.get('margin_usd')} provider={j.get('provider')} cache2={r3.status_code}/{ch}")


async def main():
    print(f"BASE={BASE}\n")
    for m, p, jb, prm in CALLS:
        res = await paid(m, p, jb, prm)
        print(f"{m} {p}: {res}")

asyncio.run(main())
