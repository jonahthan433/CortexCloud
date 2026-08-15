#!/usr/bin/env python3
"""CortexCloud integration verification — both operational modes.

Mode 1 (public x402): knapsack estimate -> 402 challenge -> EIP-3009
  micro-payment on Base -> job poll -> captured solution.
Mode 2 (private): static PRIVATE_API_KEY gate — /health open, API routes
  401 without the key, 200 with it (no blockchain settlement).

Exit code 0 = every check passed. No test framework, plain asserts.

Usage:
  python verify_integration.py --mode public --private-key <path-or-0x>
  python verify_integration.py --mode private --base http://localhost:8001 --api-key <key>
  python verify_integration.py --mode all --private-key ... --api-key ... --base ...
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time

import httpx

PUBLIC_BASE = "https://api.cortexcloud.org"
USDC_ON_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
CHAIN_ID = 8453

# ── Knapsack instance: 8 items, capacity 15 ──────────────────
ITEMS = [(5, 10), (3, 6), (2, 4), (7, 12), (4, 8), (8, 15), (1, 2), (6, 9)]
CAPACITY = 15
LAMBDA = 10.0  # penalty weight on capacity violation


def knapsack_qubo() -> dict:
    """QUBO: minimize -sum(v_i x_i) + lam*(sum(w_i x_i) - C)^2.

    Expanded: linear_i = -v_i + lam*(w_i^2 - 2*C*w_i),
               quadratic_ij = 2*lam*w_i*w_j (constant C^2 dropped).
    """
    n = len(ITEMS)
    linear = [-v + LAMBDA * (w * w - 2 * CAPACITY * w) for w, v in ITEMS]
    quadratic = {}
    for i in range(n):
        for j in range(i + 1, n):
            quadratic[f"{i},{j}"] = 2 * LAMBDA * ITEMS[i][0] * ITEMS[j][0]
    return {"problem_type": "qubo", "n": n, "data": {"linear": linear, "quadratic": quadratic}}


def check_estimate(client: httpx.Client, base: str) -> dict:
    r = client.post(f"{base}/v1/estimate", json=knapsack_qubo(), timeout=30)
    assert r.status_code == 200, f"estimate: expected 200, got {r.status_code}: {r.text[:200]}"
    rec = r.json()["recommendation"]
    for field in ("mode", "solver_id", "cortexcloud_price_usd", "estimated_runtime_s"):
        assert field in rec, f"estimate: missing recommendation.{field}"
    print(f"  PASS estimate: {rec['mode']} {rec['solver_id']} ${rec['cortexcloud_price_usd']} "
          f"~{rec['estimated_runtime_s']}s (n={knapsack_qubo()['n']} knapsack)")
    return rec


def check_challenge(client: httpx.Client, base: str) -> dict:
    r = client.post(f"{base}/v1/optimize", json={"mode": "auto", "problem": knapsack_qubo()},
                    headers={"accept": "application/json"}, timeout=30)
    assert r.status_code == 402, f"challenge: expected 402, got {r.status_code}: {r.text[:200]}"
    c = r.json()
    assert c.get("x402Version") == 2, "challenge: x402Version != 2"
    a = c["accepts"][0]
    assert a["scheme"] == "exact" and a["network"] == "eip155:8453", "challenge: bad scheme/network"
    assert a["asset"] == USDC_ON_BASE, f"challenge: unexpected asset {a['asset']}"
    assert int(a["amount"]) > 0 and a["payTo"].startswith("0x"), "challenge: bad amount/payTo"
    assert a.get("extra", {}).get("name") == "USD Coin", "challenge: missing EIP-712 domain"
    # header contract: payment-required base64 decodes to the same body
    hdr = r.headers.get("payment-required")
    assert hdr, "challenge: missing payment-required header"
    assert json.loads(base64.b64decode(hdr)) == c, "challenge: header/body mismatch"
    print(f"  PASS challenge: x402 v2, {int(a['amount']) / 1e6:.2f} USDC -> "
          f"{a['payTo'][:6]}...{a['payTo'][-4:]}")
    return c


def sign_payment(challenge: dict, private_key: str) -> str:
    """EIP-3009 transferWithAuthorization -> canonical x402 v2 PaymentPayload."""
    from eth_account import Account

    acc = challenge["accepts"][0]
    now = int(time.time())
    nonce = "0x" + os.urandom(32).hex()
    from_addr = Account.from_key(private_key).address
    auth = {"from": from_addr, "to": acc["payTo"], "value": str(int(acc["amount"])),
            "validAfter": "0",
            "validBefore": str(now + int(acc["maxTimeoutSeconds"])),
            "nonce": nonce}
    # eth-account >= 0.13: keyword-arg API, message_types excludes EIP712Domain
    signed = Account.sign_typed_data(
        private_key,
        domain_data={"name": acc["extra"]["name"], "version": acc["extra"]["version"],
                     "chainId": CHAIN_ID, "verifyingContract": acc["asset"]},
        message_types={
            "TransferWithAuthorization": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce", "type": "bytes32"},
            ],
        },
        message_data={"from": from_addr, "to": acc["payTo"], "value": int(acc["amount"]),
                      "validAfter": 0,
                      "validBefore": now + int(acc["maxTimeoutSeconds"]),
                      "nonce": nonce},
    )
    sig_hex = ("0x" + signed.r.to_bytes(32, "big").hex()
               + signed.s.to_bytes(32, "big").hex() + format(signed.v, "02x"))
    payload = {
        "x402Version": 2,
        "resource": challenge.get("resource"),
        "accepted": acc,
        "payload": {"signature": sig_hex, "authorization": auth},
        "extensions": {},
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


def check_paid_solve(client: httpx.Client, base: str, private_key: str) -> dict:
    sig = sign_payment(check_challenge(client, base), private_key)
    r = client.post(f"{base}/v1/optimize", json={"mode": "auto", "problem": knapsack_qubo()},
                    headers={"accept": "application/json", "payment-signature": sig}, timeout=120)
    assert r.status_code == 200, f"paid solve: expected 200, got {r.status_code}: {r.text[:300]}"
    job = r.json()
    assert job.get("job_id"), f"paid solve: no job_id in {job}"
    paid_hdr = r.headers.get("x-payment-response")
    assert paid_hdr, "paid solve: missing x-payment-response audit header"
    print(f"  PASS paid solve: settled, job {job['job_id']}")

    deadline = time.time() + 180
    while time.time() < deadline:
        j = client.get(f"{base}/v1/jobs/{job['job_id']}", timeout=15).json()
        if j.get("status") in ("completed", "succeeded", "failed"):
            break
        time.sleep(2)
    assert j.get("status") in ("completed", "succeeded"), \
        f"job did not complete: {j.get('status')} {j.get('error', '')}"
    assert isinstance(j.get("result"), dict), f"job result missing: {j}"
    print(f"  PASS job {job['job_id']}: {j['status']}, result keys: {sorted(j['result'].keys())[:6]}")
    return j


def check_private(client: httpx.Client, base: str, api_key: str) -> None:
    # /health stays open
    r = client.get(f"{base}/health", timeout=15)
    assert r.status_code == 200, f"private: /health expected 200, got {r.status_code}"
    print("  PASS private: /health open without key")
    # API routes reject without the key
    r = client.post(f"{base}/v1/optimize", json={"mode": "auto", "problem": knapsack_qubo()},
                    headers={"accept": "application/json"}, timeout=15)
    assert r.status_code == 401, f"private: /v1/optimize without key expected 401, got {r.status_code}"
    r = client.get(f"{base}/v1/estimate", timeout=15)
    assert r.status_code == 401, f"private: /v1/estimate without key expected 401, got {r.status_code}"
    print("  PASS private: API routes 401 without key")
    # With the key: free estimate + immediate solve (no blockchain)
    r = client.post(f"{base}/v1/estimate", json=knapsack_qubo(),
                    headers={"x-api-key": api_key}, timeout=30)
    assert r.status_code == 200, f"private: estimate with key expected 200, got {r.status_code}"
    print("  PASS private: estimate 200 with key")
    r = client.post(f"{base}/v1/optimize", json={"mode": "auto", "problem": knapsack_qubo()},
                    headers={"accept": "application/json", "x-api-key": api_key}, timeout=60)
    assert r.status_code == 200, f"private: optimize with key expected 200, got {r.status_code}: {r.text[:300]}"
    print("  PASS private: optimize 200 with key (no payment required)")


def load_key(value: str) -> str:
    if os.path.exists(value):
        return open(value).read().strip()
    return value


def main() -> int:
    ap = argparse.ArgumentParser(description="CortexCloud integration verification")
    ap.add_argument("--mode", choices=["public", "private", "all"], required=True)
    ap.add_argument("--base", default=PUBLIC_BASE, help="API base URL")
    ap.add_argument("--api-key", help="PRIVATE_API_KEY for private mode")
    ap.add_argument("--private-key", help="EVM private key (0x...) or key file for public mode")
    args = ap.parse_args()

    ok = True
    with httpx.Client(base_url=args.base, timeout=30) as client:
        if args.mode in ("public", "all"):
            print(f"[public x402] {args.base}")
            try:
                check_estimate(client, args.base)
                check_challenge(client, args.base)
                if args.private_key:
                    check_paid_solve(client, args.base, load_key(args.private_key))
                else:
                    print("  SKIP paid solve: pass --private-key to settle the micro-payment")
            except Exception as e:  # noqa: BLE001 — verification must report, not trace
                ok = False
                print(f"  FAIL public: {e}")

        if args.mode in ("private", "all"):
            print(f"[private gate] {args.base}")
            if not args.api_key:
                print("  FAIL private: --api-key required")
                ok = False
            else:
                try:
                    check_private(client, args.base, args.api_key)
                except Exception as e:  # noqa: BLE001
                    ok = False
                    print(f"  FAIL private: {e}")

    print("RESULT:", "ALL CHECKS PASSED" if ok else "FAILURES DETECTED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
