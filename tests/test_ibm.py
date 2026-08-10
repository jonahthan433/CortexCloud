"""IBM Quantum adapter tests (mocked service — never touches the real account)."""
import pytest

from app.solvers.quantum import ibm
from app.solvers.quantum.ibm import IBMBackend

QB = {"problem_type": "qubo", "n": 4, "data": {"linear": [1.0, -2.0, 3.0, -4.0], "quadratic": {"0,1": -1.5}}}


class _FakeBackend:
    name = "ibm_test_qpu"
    num_qubits = 32
    simulator = False


class _FakeService:
    def backends(self, simulator=False, operational=True):
        return [_FakeBackend()]

    def backend(self, name):
        return _FakeBackend()


def _no_token(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.IBM_QUANTUM_TOKEN", None)


def _with_service(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.IBM_QUANTUM_TOKEN", "ibm-test-token")
    monkeypatch.setattr(IBMBackend, "_new_service", lambda self: _FakeService())


def test_ibm_unavailable_without_token(monkeypatch):
    _no_token(monkeypatch)
    av = IBMBackend().availability()
    assert av.available is False
    assert "token" in av.reason.lower()


def test_ibm_available_after_discovery(monkeypatch):
    _with_service(monkeypatch)
    b = IBMBackend()
    av = b.availability()
    assert av.available is True
    assert "qpu" in av.reason.lower()
    assert b.spec.id == "ibm"
    assert b.spec.mode == "quantum"
    assert b.provider == "ibm_quantum"
    assert b.estimate(QB, 4).price_usd == 0.0  # Open Plan is free


def test_ibm_solve_blocked_without_live_flag(monkeypatch):
    _with_service(monkeypatch)
    monkeypatch.setattr("app.core.config.settings.QUANTUM_LIVE_EXECUTION", False)
    res = IBMBackend().solve(QB, 4)
    assert res.status == "failed"
    assert "QUANTUM_LIVE_EXECUTION" in res.error


def test_ibm_solve_success(monkeypatch):
    _with_service(monkeypatch)
    monkeypatch.setattr("app.core.config.settings.QUANTUM_LIVE_EXECUTION", True)

    class _Counts:
        def get_counts(self):
            return {"0010": 8, "1000": 4, "0001": 2}

    class _Data:
        c = _Counts()

    class _Pub:
        data = _Data()

    class _Res:
        def __getitem__(self, i):
            return _Pub()

    class _Job:
        def result(self, timeout=None):
            return _Res()

    class _SamplerFake:
        def __init__(self, mode=None):
            pass

        def run(self, circs, shots=1024):
            return _Job()

    monkeypatch.setattr("qiskit_ibm_runtime.SamplerV2", _SamplerFake)
    monkeypatch.setattr("qiskit.transpile", lambda circ, backend=None, optimization_level=1: circ)
    res = IBMBackend().solve(QB, 4)
    assert res.status == "succeeded"
    assert res.backend == "ibm:ibm_test_qpu"
    assert res.solution is not None
    assert res.meta["shots"] == 1024
