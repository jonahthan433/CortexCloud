#!/usr/bin/env python3
"""Full x402 v2 paid flow against CortexCloud via the SDK (verified signing).

  pip install cortexcloud
  WALLET_KEY=0x... python3 solve.py

Estimates free, then pays for one classical solve in USDC on Base.
"""
from cortexcloud import CortexCloud

PROBLEM = {
    "problem_type": "qubo",
    "n": 4,
    "data": {"linear": [1, -2, 3, -4], "quadratic": {"0,1": -1.5}},
}


def main() -> None:
    cc = CortexCloud()  # free estimate needs no key
    est = cc.estimate(PROBLEM)
    print("ESTIMATE:", est["recommendation"])

    key = __import__("os").environ.get("WALLET_KEY")
    if not key:
        raise SystemExit("WALLET_KEY env required (Base private key with USDC)")
    paid = CortexCloud(private_key=key)
    job = paid.optimize(PROBLEM, mode="classical")
    print("RESULT:", paid.wait(job["job_id"]))


if __name__ == "__main__":
    main()
