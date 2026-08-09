"""Braket adapter + backend router: honesty contract.

Cheap mocked boto3 — no AWS account, no network, no QPU money.
"""

import pytest

from app.optimizer.problem import ProblemInput, to_qubo
from app.solvers.base import SolverAvailability
from app.solvers.quantum import braket
from app.solvers.quantum.braket import BraketBackend
from app.solvers.quantum.origin import OriginWukongAdapter
from app.solvers.quantum import router


QB = {"problem_type": "qubo", "n": 18, "data": {"linear": [float(i % 3) - 1 for i in range(18)], "quadratic": {"0,1": -1.0}}}
QUBO = to_qubo(ProblemInput(**QB))


def _device(provider_arn_suffix="rigetti/Ankaa-3", qubits=100):
    return [
        {
            "deviceArn": f"arn:aws:braket:us-east-1::device/qpu/{provider_arn_suffix}",
            "deviceName": "Ankaa-3",
            "deviceStatus": "ONLINE",
            "providerName": "Rigetti",
            "deviceType": "QPU",
            "deviceCapabilities": "{\"action\":{\"braket.ir.jaqcd.program\":{}}}",
            "quantumComputingDeviceData": {"qpuSpecifications": {"qubitCount": qubits}},
        }
    ]


@pytest.fixture
def no_aws(monkeypatch):
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.setattr("app.core.config.settings.AWS_ACCESS_KEY_ID", None)
    monkeypatch.setattr("app.core.config.settings.AWS_SECRET_ACCESS_KEY", None)


@pytest.fixture
def aws_creds(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.AWS_ACCESS_KEY_ID", "AKIA_TEST")
    monkeypatch.setattr("app.core.config.settings.AWS_SECRET_ACCESS_KEY", "secret")


@pytest.fixture
def braket_discovery(monkeypatch):
    class FakeClient:
        def search_devices(self, filters=None):
            return {"devices": _device()}

        def get_device(self, deviceArn):
            # search_devices omits capabilities; get_device returns them
            return _device()[0]

    monkeypatch.setattr(braket, "_new_client", lambda region: FakeClient())


# -- Braket adapter -------------------------------------------------
def test_braket_init_spec():
    b = BraketBackend("rigetti")
    assert b.spec.id == "rigetti"
    assert b.spec.mode == "quantum"
    assert b.provider == "aws_braket"
    assert b.algorithm == "QAOA"
    assert b.spec.requires_token is True


def test_braket_unavailable_without_creds(no_aws):
    b = BraketBackend("ionq")
    av = b.availability()
    assert av.available is False
    assert "credential" in av.reason.lower()


def test_braket_unavailable_on_check_error(aws_creds, monkeypatch):
    def boom(region):
        raise RuntimeError("throttled")

    monkeypatch.setattr(braket, "_new_client", boom)
    b = BraketBackend("rigetti")
    av = b.availability()
    assert av.available is False
    assert "capability check failed" in av.reason.lower()


def test_braket_available_after_discovery(aws_creds, braket_discovery):
    b = BraketBackend("rigetti")
    av = b.availability()
    assert av.available is True
    assert "capability check" in av.reason.lower()
    assert b.spec.max_variables == 100  # qubitCount from live discovery


def test_braket_no_online_devices(aws_creds, monkeypatch):
    class Empty:
        def search_devices(self, filters=None):
            return {"devices": []}

    monkeypatch.setattr(braket, "_new_client", lambda region: Empty())
    b = BraketBackend("aqt")
    av = b.availability()
    assert av.available is False
    assert "no online" in av.reason.lower()


def test_braket_solve_blocked_live_off(aws_creds, braket_discovery, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.QUANTUM_LIVE_EXECUTION", False)
    b = BraketBackend("rigetti")
    res = b.solve(QUBO, 4)
    assert res.status == "failed"
    assert "QUANTUM_LIVE_EXECUTION" in res.error


def test_origin_solve_blocked_live_off(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.QUANTUM_LIVE_EXECUTION", False)
    a = OriginWukongAdapter(api_token="x", backend=None)
    res = a.solve(QUBO, 4)
    assert res.status == "failed"
    assert "QUANTUM_LIVE_EXECUTION" in res.error


# --- router --------------------------------------------------------
@pytest.fixture
def rigetti_available(monkeypatch):
    def fake_av(self):
        return SolverAvailability(True, "mocked")

    monkeypatch.setattr(BraketBackend, "availability", fake_av)
    return monkeypatch


def _router_select(n, bench, force_mode=None):
    return router.select(problem_type="qubo", qubo=QUBO, n=n, bench_count=bench, force_mode=force_mode)


def test_router_classical_selection(no_aws, rigetti_available):
    sel = _router_select(4, 0)
    assert sel["recommended"]["solver_id"] == "brute-force"


def test_router_quantum_requires_evidence(no_aws, rigetti_available):
    sel = _router_select(4, 0)
    assert not any(c["mode"] == "quantum" for c in sel["ranked"])
    assert "evidence" in sel["quantum_gate"]


def test_router_quantum_with_evidence(no_aws, no_ibm, rigetti_available):
    sel = _router_select(4, 3)
    assert any(c["provider"] == "aws_braket" and c["backend"] == "rigetti" for c in sel["ranked"])


def test_router_never_unavailable(no_aws, no_ibm):
    sel = _router_select(4, 4)
    assert not any(c["mode"] == "quantum" for c in sel["ranked"])


def test_router_explicit_quantum_uses_available(no_aws, no_ibm, rigetti_available):
    sel = _router_select(4, 0, force_mode="quantum")
    assert sel["recommended"]["provider"] == "aws_braket"
    assert sel["recommended"]["mode"] == "quantum"
    # cheapest available provider wins the ranking (QuEra 0.25 < Rigetti 0.35)
    assert sel["recommended"]["backend"] == "quera"


def test_router_cost_breakdown(no_aws, no_ibm, rigetti_available):
    sel = _router_select(4, 0)
    c = sel["recommended"]
    assert {"provider_cost_usd", "cortexcloud_price_usd", "margin_usd"} <= set(c)


# --- isolation ------------------------------------------------------
def test_origin_braket_modules_isolated():
    import pathlib

    src = pathlib.Path(__file__).resolve().parents[1] / "app" / "solvers" / "quantum"
    origin_src = (src / "origin.py").read_text()
    braket_src = (src / "braket.py").read_text()
    # import-level isolation only: neither module may import the other
    # (words like "origin" appear in prose and are fine).
    assert "import braket" not in origin_src
    assert "import origin" not in braket_src
    assert "from app.solvers.quantum.braket" not in origin_src
    assert "from app.solvers.quantum.origin" not in braket_src