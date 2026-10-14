#!/usr/bin/env python3
"""Working integration examples for CortexCloud's Token Intelligence surface.

Copy-paste. Each example is ONE paid x402 call against the LIVE API.

    pip install "x402" eth-account httpx
    export TEST_BUYER_KEY=0x...   # Base wallet with USDC + a little ETH
    python token_intel_examples.py risk     # screen an ERC-20 ($0.020)
    python token_intel_examples.py wallet   # profile a counterparty ($0.006)
    python token_intel_examples.py whale    # watch a whale wallet ($0.030)
    python token_intel_examples.py cross    # one contract across chains ($0.040)
    python token_intel_examples.py price    # spot price primitive ($0.004)

Overrides: CC_URL (default https://api.cortexcloud.org).

The payment path is the SAME official-SDK flow as examples/paid_client.py
(PaymentRequired.model_validate -> client.create_payment_payload ->
base64(model_dump_json()) as the payment-signature header), so a hand-rolled
v2 payload can never drift from the wire shape CDP validates.
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

NETWORK = "eip155:8453"
BASE = os.getenv("CC_URL", "https://api.cortexcloud.org")

EXAMPLES = {
    "risk": {
        "path": "/v1/data/token-risk",
        "body": {"contract": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                 "chain": "ethereum", "coin_id": "usd-coin"},
        "use": "Screen an ERC-20 before an agent trades or holds it.",
    },
    "wallet": {
        "path": "/v1/data/wallet-intel",
        "body": {"address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                 "chain": "ethereum", "limit": 25},
        "use": "Profile a counterparty wallet before sending funds.",
    },
    "whale": {
        "path": "/v1/data/whale-alerts",
        "body": {"address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                 "chain": "ethereum", "min_usd": 100000, "limit": 50},
        "use": "Watch a whale wallet for large transfers.",
    },
    "cross": {
        "path": "/v1/data/cross-chain-compare",
        "body": {"contract": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                 "chains": ["ethereum", "base", "arbitrum"]},
        "use": "Same contract across chains: price, activity, deployment.",
    },
    "price": {
        "path": "/v1/data/token-price",
        "body": {"id": "ethereum"},
        "use": "Cheapest primitive: spot USD price + 24h change.",
    },
}


async def paid_call(path: str, body: dict):
    """402 challenge -> sign -> resend. Returns (status, json, receipt)."""
    key = os.environ["TEST_BUYER_KEY"]
    signer = Account.from_key(key)
    client = x402Client()
    client.register(NETWORK, ExactEvmClientScheme(signer))

    async with httpx.AsyncClient(timeout=90) as hc:
        r = await hc.post(BASE + path, json=body)
        if r.status_code != 402:
            return r.status_code, r.json(), ""
        payload = await client.create_payment_payload(
            PaymentRequired.model_validate(r.json())
        )
        header = base64.b64encode(payload.model_dump_json().encode()).decode()
        r2 = await hc.post(BASE + path, json=body,
                           headers={"payment-signature": header})
        return r2.status_code, r2.json(), r2.headers.get("x-payment-response", "")


async def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "risk"
    ex = EXAMPLES[which]
    print(f"# {which}: {ex['use']}")
    status, body, receipt = await paid_call(ex["path"], ex["body"])
    print(f"POST {ex['path']} -> {status}")
    print(json.dumps(body, indent=2)[:1800])
    if receipt:
        print(f"settled (receipt {receipt[:40]}...)")


if __name__ == "__main__":
    asyncio.run(main())
