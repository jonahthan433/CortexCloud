#!/usr/bin/env python3
"""PAID x402 smoke for Data API (Tier 1) — reuses the proven buyer/SDK flow.

Settles REAL USDC from the test buyer wallet to the merchant wallet on
/v1/data/token-price, /v1/data/token-balances and /v1/data/gas-oracle.
Run against a staging instance with DATA_ENABLED=true (throwaway port).
"""
import asyncio
import json
import sys

import httpx
from eth_account import Account
from x402 import x402Client, prefer_network
from x402.http.x402_http_client import x402HTTPClient
from x402.mechanisms.evm.exact import ExactEvmScheme

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8011"
pk = open("/root/bzcheck/test_buyer.key").read().strip()
buyer = Account.from_key(pk)
client = x402Client()
client.register("eip155:8453", ExactEvmScheme(signer=buyer))
client.register_policy(prefer_network("eip155:8453"))
http_client = x402HTTPClient(client)

CALLS = [
    ("POST", "/v1/data/token-price", {"id": "ethereum"}),
    ("POST", "/v1/data/token-balances", {"address": "0x" + "0" * 40, "chain": "ethereum"}),
    ("GET", "/v1/data/gas-oracle", None, {"chain": "ethereum"}),
]


async def settle_one(method, path, json_body=None, params=None):
    fwd = {"host": "api.cortexcloud.org", "x-forwarded-proto": "https"}
    async with httpx.AsyncClient(timeout=120) as session:
        kw = {"headers": {"content-type": "application/json", **fwd}}
        if json_body is not None:
            kw["json"] = json_body
        if params is not None:
            kw["params"] = params
        r1 = await session.request(method, f"{BASE}{path}", **kw)
        print(f"[*] {method} {path} -> {r1.status_code}")
        if r1.status_code != 402:
            print(f"[!] expected 402, got {r1.status_code}: {r1.text[:300]}")
            return False
        body1 = r1.json()
        pr = http_client.get_payment_required_response(lambda n: r1.headers.get(n), body1)
        payload = await http_client.create_payment_payload(pr)
        pay_headers = http_client.encode_payment_signature_header(payload)
        kw2 = {"headers": {**kw["headers"], **pay_headers}}
        if json_body is not None:
            kw2["json"] = json_body
        if params is not None:
            kw2["params"] = params
        r2 = await session.request(method, f"{BASE}{path}", **kw2)
        print(f"[+] paid {method} {path} -> {r2.status_code}")
        if r2.status_code == 200:
            j = r2.json()
            print(f"    price_usd={j.get('price_usd')} provider_cost_usd={j.get('provider_cost_usd')} margin_usd={j.get('margin_usd')}")
            return True
        print(f"[!] paid failed: {r2.text[:400]}")
        return False


async def main():
    results = []
    for c in CALLS:
        if len(c) == 3:
            results.append(await settle_one(c[0], c[1], c[2]))
        else:
            results.append(await settle_one(c[0], c[1], None, c[3]))
    print("\n=== RESULT ===")
    print("ALL PAID OK" if all(results) else f"PARTIAL/FAILED: {results}")


asyncio.run(main())
