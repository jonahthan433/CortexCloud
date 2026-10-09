#!/usr/bin/env python3
"""Reference x402 buyer for CortexCloud — official SDK path, copy-paste.

pip install "x402" eth-account httpx

    TEST_BUYER_KEY=0x... python examples/paid_client.py

Default target: POST /v1/data/token-price ($0.004). Override with CC_PATH /
CC_BODY / CC_URL. Uses x402Client + ExactEvmScheme so the PAYMENT-SIGNATURE
payload matches what CDP validates (hand-rolling the v2 payload drifts:
missing `resource`/`extensions` and alias casing get rejected).
"""
import asyncio
import base64
import json
import os
import sys

import httpx
from eth_account import Account
from x402.client import x402Client
from x402.mechanisms.evm.exact import ExactEvmClientScheme
from x402.schemas.payments import PaymentRequired

URL = os.getenv("CC_URL", "https://api.cortexcloud.org")
PATH = os.getenv("CC_PATH", "/v1/data/token-price")
BODY = json.loads(os.getenv("CC_BODY", '{"id":"ethereum"}'))
NETWORK = "eip155:8453"


async def main():
    key = os.getenv("TEST_BUYER_KEY")
    if not key:
        sys.exit("set TEST_BUYER_KEY=0x... (Base wallet with USDC + a little ETH)")
    signer = Account.from_key(key)
    print(f"buyer: {signer.address}")

    client = x402Client()
    client.register(NETWORK, ExactEvmClientScheme(signer))

    async with httpx.AsyncClient(timeout=90) as hc:
        r = await hc.post(URL + PATH, json=BODY)
        if r.status_code != 402:
            sys.exit(f"expected 402, got {r.status_code}: {r.text[:200]}")
        ch = r.json()
        acc = ch["accepts"][0]
        print(f"challenge: ${int(acc['amount']) / 1e6:.6f} -> {acc['payTo'][:10]}... on {acc['network']}")

        payload = await client.create_payment_payload(PaymentRequired.model_validate(ch))
        # model_dump_json() emits the camelCase v2 wire shape (x402Version, payTo)
        header = base64.b64encode(payload.model_dump_json().encode()).decode()

        r2 = await hc.post(URL + PATH, json=BODY, headers={"payment-signature": header})
        print(f"paid call: {r2.status_code}")
        if r2.status_code == 200:
            print("RESULT:", json.dumps(r2.json(), indent=1)[:600])
            print("SETTLED — receipt:", r2.headers.get("x-payment-response", "")[:120])
        else:
            print("FAILED:", r2.text[:400])
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
