"""CortexWallet — the only component that touches the private key.

Deterministic policy gate around x402 signing. The LLM never sees the key and
never decides spend: this class refuses to sign unless payTo is allowlisted,
the per-call amount is within cap, and the cumulative total is within budget.
Budget is decremented by the ESTIMATED amount BEFORE signing (fail-closed).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from cortexcloud.signing import sign_payment

USDC_DECIMALS = 1_000_000
# ponytail: single default payee — CortexCloud's merchant wallet. Extend the
# allowlist per deployment; never allow arbitrary payees (prompt-injection safe).
DEFAULT_ALLOWLIST = {"0x5a0353bc9c75b893a9b5735d3e79f1bd988ea143"}


class PolicyViolation(Exception):
    """Raised when a payment would break allowlist/cap/budget policy."""


class Halt(Exception):
    """Raised when the kill switch is active."""


@dataclass
class CortexWallet:
    private_key: str
    budget_usd: float
    allowlist: set[str] = field(default_factory=lambda: set(DEFAULT_ALLOWLIST))
    max_per_call_usd: float | None = None  # None -> bounded only by remaining
    kill_switch_path: str | None = None     # touch this file to halt
    spent_usd: float = 0.0

    def __post_init__(self) -> None:
        if self.max_per_call_usd is None:
            self.max_per_call_usd = self.budget_usd

    # ── kill switch ───────────────────────────────────────────────
    def halted(self) -> bool:
        if os.environ.get("CORTEXOS_HALT") == "1":
            return True
        if self.kill_switch_path and Path(self.kill_switch_path).exists():
            return True
        return False

    def halt(self) -> None:
        if self.kill_switch_path:
            Path(self.kill_switch_path).touch()

    # ── policy ────────────────────────────────────────────────────
    @property
    def remaining_usd(self) -> float:
        return self.budget_usd - self.spent_usd

    def _check(self, pay_to: str, amount_usd: float) -> None:
        if self.halted():
            raise Halt("kill switch active")
        if pay_to.lower() not in self.allowlist:
            raise PolicyViolation(f"payTo {pay_to} not in allowlist")
        if amount_usd > self.remaining_usd:
            raise PolicyViolation(
                f"amount ${amount_usd:.6f} exceeds remaining ${self.remaining_usd:.6f}")
        cap = self.max_per_call_usd  # set in __post_init__; never None here
        assert cap is not None
        if amount_usd > cap:
            raise PolicyViolation(
                f"amount ${amount_usd:.6f} exceeds max_per_call ${cap:.6f}")

    # ── sign (the only key-touching path) ────────────────────────
    def authorize(self, challenge: dict) -> str:
        """Validate policy, decrement budget, return the x402 payment header.

        `challenge` is the 402 body (same shape sign_payment expects):
        {"accepts":[{"payTo":..., "amount":<atomic usdc>, ...}], ...}
        """
        acc = challenge["accepts"][0]
        pay_to = acc["payTo"]
        amount_usd = int(acc["amount"]) / USDC_DECIMALS
        self._check(pay_to, amount_usd)
        self.spent_usd += amount_usd  # ponytail: pre-deduct before signing
        try:
            return sign_payment(challenge, self.private_key)
        except Exception:
            self.spent_usd -= amount_usd  # roll back on sign failure
            raise
