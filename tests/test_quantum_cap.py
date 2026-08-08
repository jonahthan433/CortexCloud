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
        # cheap run under cap -> allowed
        settings.QUANTUM_MAX_COST_USD = 5.0
        assert quantum_cost_cap_error(FakeSolver(0.35), qubo, 2) is None
        # expensive run over cap -> blocked
        assert quantum_cost_cap_error(FakeSolver(3.40), qubo, 2) is None  # under 5
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
    test_braket_preflight()
