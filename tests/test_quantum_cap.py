"""Quantum cost-cap gate: hard per-job provider-cost limit before ANY QPU submission."""
from app.core.config import settings
from app.optimizer.runner import quantum_cost_cap_error
from app.solvers.base import Estimate, SolverSpec


class FakeSolver:
    spec = SolverSpec(id="fake-qpu", name="Fake QPU", mode="quantum", description="", max_variables=100)

    def __init__(self, price: float):
        self._price = price

    def estimate(self, qubo, n):
        return Estimate(runtime_s=1.0, price_usd=self._price, basis="model")


def test_cap():
    qubo = {"linear": [0.0, 0.0], "quadratic": {}, "n": 2}
    old_cap = settings.QUANTUM_MAX_COST_USD
    try:
        # cheap run under cap and under price -> allowed
        settings.QUANTUM_MAX_COST_USD = 5.0
        assert quantum_cost_cap_error(FakeSolver(0.35), qubo, 2) is None  # real Cepheus cost
        # above price ($0.85) but under cap -> margin guard blocks
        err = quantum_cost_cap_error(FakeSolver(3.40), qubo, 2)
        assert err and "quantum margin guard" in err
        # over cap -> cost cap blocks
        err = quantum_cost_cap_error(FakeSolver(9.99), qubo, 2)
        assert err and "quantum cost cap exceeded" in err
        # cap disabled (<=0) -> never blocks
        settings.QUANTUM_MAX_COST_USD = 0.0
        assert quantum_cost_cap_error(FakeSolver(9.99), qubo, 2) is None
        # classical solver never gated
        class C(FakeSolver):
            spec = SolverSpec(id="local", name="Local", mode="classical", description="", max_variables=100)
        settings.QUANTUM_MAX_COST_USD = 5.0
        assert quantum_cost_cap_error(C(999.0), qubo, 2) is None
    finally:
        settings.QUANTUM_MAX_COST_USD = old_cap
    print("quantum cost-cap gate: OK")


def test_margin_guard():
    """Quantum route must not be sold below estimated provider cost unless
    QUANTUM_ALLOW_SUBSIDY=true."""
    from app.x402.pricing import MODE_PRICE_USD, below_cost, gross_margin_usd

    qubo = {"linear": [0.0, 0.0], "quadratic": {}, "n": 2}
    old_cap = settings.QUANTUM_MAX_COST_USD
    old_sub = settings.QUANTUM_ALLOW_SUBSIDY
    try:
        settings.QUANTUM_MAX_COST_USD = 5.0
        # verified Cepheus run: cost 0.50 < effective 1.00 -> positive margin, no block
        assert MODE_PRICE_USD["quantum"] == 0.85
        assert gross_margin_usd("quantum") == round(1.503 - 0.7515, 6)  # eff 1.503 - total 0.7515
        assert below_cost("quantum") is False
        assert quantum_cost_cap_error(FakeSolver(0.35), qubo, 2) is None
        # cost above price -> blocked by default
        settings.QUANTUM_ALLOW_SUBSIDY = False
        err = quantum_cost_cap_error(FakeSolver(2.00), qubo, 2)  # > eff 1.503
        assert err and "quantum margin guard" in err
        # explicit subsidy allowance -> allowed
        settings.QUANTUM_ALLOW_SUBSIDY = True
        assert quantum_cost_cap_error(FakeSolver(2.00), qubo, 2) is None
        # classical/hybrid (local provider cost 0) never margin-gated
        assert below_cost("classical") is False
        assert gross_margin_usd("hybrid") == round(0.10 - 0.0015, 6)  # 0.10 - infra+payment
    finally:
        settings.QUANTUM_MAX_COST_USD = old_cap
        settings.QUANTUM_ALLOW_SUBSIDY = old_sub
    print("quantum margin guard: OK")


def test_effective_pricing():
    """Provider-cost-aware dynamic pricing: price = max(list, cost x MARKUP);
    sellable flag at the charged mode price."""
    from app.x402.pricing import MARKUP, classical_price_for_n, effective_price_usd, price_for_mode, sellable_at_mode_price

    # list floor holds while cost x markup is below it (quantum cost 0.50 -> 1.00)
    assert effective_price_usd("quantum") == 1.503  # (0.75 + 0.0015) x 2.0
    assert price_for_mode("quantum") == "$1.503000"
    assert price_for_mode("auto") == "$0.050000"  # no n -> classical list floor
    # expensive provider pushes the effective price up automatically
    assert effective_price_usd("quantum", 3.40) == round(3.4015 * MARKUP, 6)
    assert effective_price_usd("quantum", 3.40) == 6.803
    # size-based classical pricing tiers
    assert classical_price_for_n(4) == 0.05
    assert classical_price_for_n(20) == 0.05
    assert classical_price_for_n(21) == 0.10
    assert classical_price_for_n(200) == 0.10
    assert classical_price_for_n(201) == 0.25
    assert classical_price_for_n(5000) == 0.25
    assert effective_price_usd("classical", n=4) == 0.05
    assert effective_price_usd("classical", n=50) == 0.10
    assert effective_price_usd("classical", n=1000) == 0.25
    assert price_for_mode("classical", n=50) == "$0.100000"
    assert effective_price_usd("auto", n=50) == 0.10
    # sellability at the charged (mode-level) price
    assert sellable_at_mode_price("quantum", 0.35) is True
    assert sellable_at_mode_price("quantum", 3.40) is False
    assert sellable_at_mode_price("quantum", float("nan")) is False
    print("effective pricing: OK")


def test_braket_preflight():
    """Adapter-level preflight: refuse unless cost known, positive, within cap."""
    from app.solvers.base import Estimate
    from app.solvers.quantum.braket import BRAKET_SHOTS, BraketBackend

    b = BraketBackend("rigetti")
    qubo = {"linear": [0.0, 0.0], "quadratic": {}, "n": 2}
    assert BRAKET_SHOTS == 1024
    old = settings.QUANTUM_MAX_COST_USD
    try:
        settings.QUANTUM_MAX_COST_USD = 5.0
        assert b._preflight_cost(qubo, 2) is None  # 0.35 within cap
        settings.QUANTUM_MAX_COST_USD = 0.10
        err = b._preflight_cost(qubo, 2)
        assert err and "QUANTUM_MAX_COST_USD" in err  # 0.35 > 0.10

        class NoCost(BraketBackend):
            def estimate(self, qubo, n):
                return Estimate(runtime_s=1.0, price_usd=None, basis="model")

        assert "unavailable" in NoCost("rigetti")._preflight_cost(qubo, 2)

        class ZeroCost(BraketBackend):
            def estimate(self, qubo, n):
                return Estimate(runtime_s=1.0, price_usd=0.0, basis="model")

        assert "not confidently determined" in ZeroCost("rigetti")._preflight_cost(qubo, 2)

        class NaNCost(BraketBackend):
            def estimate(self, qubo, n):
                return Estimate(runtime_s=1.0, price_usd=float("nan"), basis="model")

        assert "not confidently determined" in NaNCost("rigetti")._preflight_cost(qubo, 2)
    finally:
        settings.QUANTUM_MAX_COST_USD = old
    print("braket preflight gate: OK")


if __name__ == "__main__":
    test_cap()
    test_margin_guard()
    test_effective_pricing()
    test_braket_preflight()
