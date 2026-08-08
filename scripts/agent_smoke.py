#!/usr/bin/env python3
"""External-agent smoke test against the LIVE API.

Walks the exact journey an autonomous agent takes:
discover -> capabilities -> estimate -> decide -> submit (402 challenge)
-> [pay, if a funded payer key is available] -> poll -> consume result.

Never exposes private keys: the payer key is read from the PAYER_PRIVATE_KEY
env var, used to sign the x402 challenge, and never printed or logged.
Run: python3 scripts/agent_smoke.py [base_url]
"""
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://api.cortexcloud.org"
UA = {"User-Agent": "cortex-agent-smoke/1.0 (+https://api.cortexcloud.org)"}
PROBLEM = {
    "problem_type": "qubo",
    "n": 4,
    "data": {"linear": [1.0, -2.0, 3.0, -4.0], "quadratic": {"0,1": -1.5, "1,2": 0.5, "2,3": -2.0}},
}


def get(path, headers=None):
    req = urllib.request.Request(BASE + path, headers={**UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def post(path, body, headers=None):
    data = json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json", **UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def ok(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return cond


def main():
    print(f"== agent smoke against {BASE} ==")
    results = []

    s, h, body = get("/.well-known/x402.json")
    manifest = json.loads(body)
    results.append(ok("discover x402 manifest", s == 200 and manifest.get("x402") is True))

    s, h, body = get("/v1/capabilities")
    caps = json.loads(body)
    results.append(ok("read capabilities", s == 200 and caps["payments"]["scheme"] == "x402"))
    results.append(ok("examples discoverable", "examples" in ", ".join(caps.get("discovery", [])) or "v1/examples" in json.dumps(caps)))

    s, h, body = get("/v1/backends")
    backends = json.loads(body)["backends"]
    quantum_ok = any(b["available"] for b in backends if b["mode"] == "quantum")
    results.append(ok("backends listed with availability", s == 200 and all("available" in b for b in backends)))

    s, h, body = post("/v1/estimate", PROBLEM)
    est = json.loads(body)
    decision = est.get("decision", {})
    results.append(ok("estimate -> decision block", s == 200 and "recommended" in decision and "cortexcloud_price_usd" in decision))
    results.append(ok("decision exposes quantum availability", "quantum_available" in decision))
    results.append(ok("quantum honesty (unavailable != recommended)", (not decision.get("quantum_recommended")) or decision.get("quantum_available")))

    s, h, body = post("/v1/optimize", {"mode": "auto", "problem": PROBLEM})
    results.append(ok("optimize -> 402 challenge", s == 402 and "payment-required" in h))
    pr = json.loads(base64.b64decode(h["payment-required"]))
    payee = (pr.get("accepts") or [pr])[0].get("payTo") or pr.get("recipient")
    results.append(ok("challenge carries payee + amount", bool(payee) and str(payee).startswith("0x")))
    # Replay protection: the 402 challenge carries no nonce by design — the
    # payer's signed EIP-3009 authorization has one, claimed atomically in
    # PostgreSQL (core/nonce.py). Exercised by unit test test_nonce_replay.
    results.append(ok("challenge schema matches x402 v2 (resource+accepts+extensions)",
                      set(["resource", "accepts"]) <= set(pr.keys())))

    payer_key = os.environ.get("PAYER_PRIVATE_KEY", "").strip()
    if not payer_key:
        print("\n  [SKIP] full paid flow — PAYER_PRIVATE_KEY not set (needs a funded wallet; never auto-created)")
        results.append(("skip", "paid flow"))
    else:
        # TODO(payment): sign challenge with payer key, call facilitator
        # settle, resubmit with payment-signature headers like a wallet SDK.
        results.append(("skip", "paid flow — payer key present but funding/settle leg not executed in this harness"))

    print("\n== summary ==")
    for r in results:
        if isinstance(r, tuple):
            print(f"  {r[0].upper()}: {r[1]}")
        else:
            print(f"  {'PASS' if r else 'FAIL'}")
    sys.exit(0 if all(r is True for r in results) else 2)


if __name__ == "__main__":
    main()