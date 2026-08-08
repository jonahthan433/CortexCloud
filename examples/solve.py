#!/usr/bin/env python3
"""Full x402 paid flow against CortexCloud: estimate -> 402 challenge ->
sign -> solve -> poll. Requires: python3, requests, eth-account,
WALLET_KEY env (Base wallet private key) and USDC on Base.

  pip install requests eth-account
  WALLET_KEY=0x... python3 solve.py
"""
import json
import os
import sys
import time
import urllib.request

import requests
from eth_account import Account

BASE = "https://api.cortexcloud.org"
PROBLEM = {
    "problem_type": "qubo",
    "n": 4,
    "data": {"linear": [1, -2, 3, -4], "quadratic": {"0,1": -1.5}},
}


def estimate():
    r = requests.post(f"{BASE}/v1/estimate", json=PROBLEM, timeout=20)
    r.raise_for_status()
    print("ESTIMATE:", json.dumps(r.json().get("decision", r.json()), indent=2))


def optimize():
    key = os.environ.get("WALLET_KEY")
    if not key:
        sys.exit("WALLET_KEY env required (Base private key)")
    acct = Account.from_key(key)

    # 1. trigger the 402 challenge
    r = requests.post(f"{BASE}/v1/optimize", json=PROBLEM, timeout=20)
    if r.status_code != 402:
        sys.exit(f"expected 402, got {r.status_code}: {r.text[:200]}")
    req = r.json()["x402PaymentRequirements"]
    print("CHALLENGE:", req["description"])

    # 2. sign the challenge (EIP-191 personal message)
    msg = json.dumps(req.get("challenge", {}), separators=(",", ":"))
    sig = acct.sign_message(Account.sign_message(msg))
    headers = {"X-PAYMENT": sig.signature.hex()}

    # 3. resubmit with the payment signature
    r2 = requests.post(f"{BASE}/v1/optimize", json=PROBLEM, headers=headers, timeout=30)
    r2.raise_for_status()
    job_id = r2.json()["job_id"]
    print("JOB:", job_id)

    # 4. poll
    for _ in range(60):
        j = requests.get(f"{BASE}/v1/jobs/{job_id}", timeout=20).json()
        if j.get("status") in ("succeeded", "failed"):
            print("RESULT:", json.dumps(j, indent=2)[:800])
            return
        time.sleep(2)
    print("timeout polling job", job_id)


if __name__ == "__main__":
    estimate()
    optimize()
