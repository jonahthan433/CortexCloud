"""Thin x402 v2 client: challenge -> EIP-3009 sign -> payment-signature header.

Ported from the production-verified scripts/verify_integration.py flow
(eth-account >= 0.13 keyword-arg API, canonical v2 PaymentPayload).
"""
import base64
import json
import os
import time

from eth_account import Account

EIP712_TYPES = {
    "TransferWithAuthorization": [
        {"name": "from", "type": "address"},
        {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"},
        {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"},
        {"name": "nonce", "type": "bytes32"},
    ]
}


def sign_payment(challenge: dict, private_key: str) -> str:
    """Return the base64 x402 v2 payment-signature header for a challenge."""
    acc = challenge["accepts"][0]
    now = int(time.time())
    nonce = "0x" + os.urandom(32).hex()
    account = Account.from_key(private_key)
    auth = {
        "from": account.address,
        "to": acc["payTo"],
        "value": str(int(acc["amount"])),
        "validAfter": "0",
        "validBefore": str(now + int(acc["maxTimeoutSeconds"])),
        "nonce": nonce,
    }
    signed = Account.sign_typed_data(
        private_key,
        domain_data={
            "name": acc["extra"]["name"],
            "version": acc["extra"]["version"],
            "chainId": 8453,
            "verifyingContract": acc["asset"],
        },
        message_types=EIP712_TYPES,
        message_data={
            "from": account.address,
            "to": acc["payTo"],
            "value": int(acc["amount"]),
            "validAfter": 0,
            "validBefore": int(auth["validBefore"]),
            "nonce": bytes.fromhex(nonce[2:]),
        },
    )
    sig_hex = (
        "0x"
        + signed.r.to_bytes(32, "big").hex()
        + signed.s.to_bytes(32, "big").hex()
        + format(signed.v, "02x")
    )
    payload = {
        "x402Version": 2,
        "resource": challenge.get("resource"),
        "accepted": acc,
        "payload": {"signature": sig_hex, "authorization": auth},
        "extensions": {},
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()
