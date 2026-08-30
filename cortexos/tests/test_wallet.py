"""Runnable self-check for CortexWallet policy gate. No framework.

Run:  python3 cortexos/tests/test_wallet.py
(needs eth-account — same dep as the cortexcloud SDK)
"""
import os
import sys
import tempfile

# Make the SDK importable (cortexcloud.signing) when run from repo root.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "sdk", "python"))
sys.path.insert(0, ROOT)

from cortexos.wallet import CortexWallet, PolicyViolation, Halt  # noqa: E402

# A real CortexCloud 402 challenge shape (Data token-price, $0.004 = 4000 atomic).
def challenge(pay_to="0x5a0353bc9c75b893a9b5735d3e79f1bd988ea143", amount=4000):
    return {"accepts": [{"payTo": pay_to, "amount": str(amount),
                         "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                         "maxTimeoutSeconds": 60,
                         "extra": {"name": "x402", "version": "2"}}]}

DUMMY_KEY = "0x" + "11" * 32  # never funded; we only assert policy, not chain


def main() -> None:
    # 1. valid sign within budget
    w = CortexWallet(private_key=DUMMY_KEY, budget_usd=0.50)
    hdr = w.authorize(challenge())
    assert isinstance(hdr, str) and hdr  # base64 header produced
    assert w.spent_usd == 0.004
    assert w.remaining_usd == 0.496

    # 2. non-allowlisted payee blocked
    w2 = CortexWallet(private_key=DUMMY_KEY, budget_usd=1.0)
    try:
        w2.authorize(challenge(pay_to="0x9999999999999999999999999999999999999999"))
        raise SystemExit("FAIL: allowed non-allowlisted payee")
    except PolicyViolation:
        pass

    # 3. cumulative overspend blocked
    w3 = CortexWallet(private_key=DUMMY_KEY, budget_usd=0.005)  # only one $0.004 call fits
    w3.authorize(challenge())  # $0.004 ok
    try:
        w3.authorize(challenge())  # second $0.004 -> $0.008 > $0.005
        raise SystemExit("FAIL: allowed overspend")
    except PolicyViolation:
        pass

    # 4. per-call cap blocked
    w4 = CortexWallet(private_key=DUMMY_KEY, budget_usd=10.0, max_per_call_usd=0.001)
    try:
        w4.authorize(challenge(amount=4000))  # $0.004 > cap $0.001
        raise SystemExit("FAIL: allowed over per-call cap")
    except PolicyViolation:
        pass

    # 5. kill switch halts
    with tempfile.NamedTemporaryFile(delete=False) as f:
        kpath = f.name
    w5 = CortexWallet(private_key=DUMMY_KEY, budget_usd=1.0, kill_switch_path=kpath)
    w5.halt()
    try:
        w5.authorize(challenge())
        raise SystemExit("FAIL: signed while halted")
    except Halt:
        pass
    os.unlink(kpath)

    # 6. env kill switch
    os.environ["CORTEXOS_HALT"] = "1"
    w6 = CortexWallet(private_key=DUMMY_KEY, budget_usd=1.0)
    try:
        w6.authorize(challenge())
        raise SystemExit("FAIL: signed with env halt")
    except Halt:
        pass
    del os.environ["CORTEXOS_HALT"]

    print("CortexWallet self-check OK — all 6 policy gates hold")


if __name__ == "__main__":
    main()
