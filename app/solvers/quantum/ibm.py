"""IBM Quantum (Qiskit Runtime) adapter — primary quantum provider.

Follows the same Solver contract as the Braket adapter (app/solvers/quantum/
braket.py): dynamic backend discovery, cached availability, cost estimate,
QAOA solve. Provider cost is $0.00 on the IBM Quantum Open Plan (free QPU
quota) so the quantum tier sells at the $0.85 list price with honest margin.
"""
from __future__ import annotations

import logging
import math
import time

from app.core.config import settings
from app.solvers.base import Estimate, SolveResult, SolverAvailability, SolverSpec
from app.solvers.quantum.base import QuantumBackend

_DISCOVERY_TTL_S = 300.0  # mirror Braket: single TTL for the discovery cache
_SHOTS = 1024
_DISCOVERY_TIMEOUT_S = 15.0  # hard cap so a stalled IBM API can't wedge a job


def _list_backends(service):
    """service.backends() can hang with no effective timeout in the IBM SDK;
    run it in a thread and give up after _DISCOVERY_TIMEOUT_S. The orphaned
    thread is harmless (bounded by the discovery TTL)."""
    import concurrent.futures as _cf

    with _cf.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(service.backends, simulator=False, operational=True)
        try:
            backends = fut.result(timeout=_DISCOVERY_TIMEOUT_S)
        except _cf.TimeoutError:
            ex.shutdown(wait=False)
            raise TimeoutError("IBM API discovery timed out")
    return [
        {
            "name": b.name,
            "num_qubits": int(getattr(b, "num_qubits", 0) or 0),
            "simulator": bool(getattr(b, "simulator", False)),
        }
        for b in backends
    ]


def _qubo_terms(qubo: dict, n: int):
    linear = qubo.get("linear") or [0.0] * n
    pairs: dict[tuple[int, int], float] = {}
    for k, v in (qubo.get("quadratic") or {}).items():
        i, j = (int(x) for x in str(k).split(","))
        pairs[(min(i, j), max(i, j))] = float(v)
    return linear, pairs


def _energy(x: list[int], linear: list[float], pairs: dict[tuple[int, int], float]) -> float:
    e = sum(linear[i] * x[i] for i in range(len(x)))
    for (i, j), v in pairs.items():
        e += v * x[i] * x[j]
    return e


class IBMBackend(QuantumBackend):
    """Primary quantum provider: IBM Quantum real-time QPU via Qiskit Runtime."""

    def __init__(self):
        self._cfg = {"name": "IBM", "price_usd": 0.50, "runtime_s": 1200.0, "cap": 127}
        # price_usd 0.50 keeps IBM sellable at the $1.00 mode price;
        # runtime_s 1200 reflects open-plan queue reality, so the router's
        # cost+latency sort keeps Braket (60s) primary.
        # price_usd 0.50 (== rigetti): equal effective $1.00, so the router's
        # registry-order tie-break keeps Braket primary; IBM stays a fallback.
        self._devices: list[dict] | None = None
        self._error: str | None = None
        self._discovered_at = 0.0
        self._log = logging.getLogger("cortexcloud.solvers.ibm")
        super().__init__(
            SolverSpec(
                id="ibm",
                name="IBM Quantum (QPU)",
                mode="quantum",
                description=(
                    "QAOA on IBM Quantum real-time QPU via Qiskit Runtime — "
                    "backend discovered dynamically, never hardcoded."
                ),
                max_variables=self._cfg["cap"],
                requires_token=True,
            ),
            provider="ibm_quantum",
            algorithm="QAOA",
        )

    def _credentials_present(self) -> bool:
        return bool(settings.IBM_QUANTUM_TOKEN)

    def _new_service(self):
        """QiskitRuntimeService seam — monkeypatched in tests."""
        from qiskit_ibm_runtime import QiskitRuntimeService

        return QiskitRuntimeService(channel="ibm_quantum_platform", token=settings.IBM_QUANTUM_TOKEN)

    def _discover(self) -> tuple[list[dict] | None, str | None]:
        """(backends, error). Cached TTL; failures cached too."""
        if self._devices is not None and time.time() - self._discovered_at < _DISCOVERY_TTL_S:
            return self._devices, self._error
        try:
            if not self._credentials_present():
                self._devices, self._error = [], "IBM_QUANTUM_TOKEN not set"
                self._discovered_at = time.time()
                return self._devices, self._error
            service = self._new_service()
            found = _list_backends(service)
            self._devices, self._error = found, None
        except ImportError as exc:
            self._devices, self._error = [], f"qiskit SDK not installed ({exc})"
        except Exception as exc:
            self._log.warning("ibm discovery failed: %s", exc)
            self._devices, self._error = [], str(exc)
        self._discovered_at = time.time()
        return self._devices, self._error

    def availability(self) -> SolverAvailability:
        if not self._credentials_present():
            return SolverAvailability(False, "IBM_QUANTUM_TOKEN not set")
        devices, err = self._discover()
        if devices is None or not devices:
            return SolverAvailability(False, err or "no operational IBM real-time backend")
        return SolverAvailability(True, f"{len(devices)} IBM QPU(s) online")

    def estimate(self, qubo, n: int) -> Estimate:
        return Estimate(
            runtime_s=float(self._cfg["runtime_s"]),
            price_usd=float(self._cfg["price_usd"]),
            basis="model",
        )

    def solve(self, qubo, n: int, timeout_s: float = 1200.0) -> SolveResult:
        t0 = time.time()
        try:
            return self._solve(qubo, n, timeout_s, t0)
        except Exception as exc:
            self._log.error("ibm solve failed: %s", exc)
            return SolveResult(status="failed", error=f"ibm execution failed: {exc}")

    def _solve(self, qubo, n: int, timeout_s: float, t0: float) -> SolveResult:
        if not settings.QUANTUM_LIVE_EXECUTION:
            return SolveResult(
                status="failed",
                error="QUANTUM_LIVE_EXECUTION=false (live QPU execution is opt-in)",
            )
        if not self._credentials_present():
            return SolveResult(status="failed", error="IBM_QUANTUM_TOKEN not set")
        devices, err = self._discover()
        if not devices:
            return SolveResult(status="failed", error=f"no available IBM backend ({err})")

        linear, pairs = _qubo_terms(qubo, n)
        backend_name = devices[0]["name"]

        from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister
        from qiskit_ibm_runtime import SamplerV2

        qr = QuantumRegister(n, "q")
        cr = ClassicalRegister(n, "c")
        circ = QuantumCircuit(qr, cr)
        circ.h(qr)  # |+>^n
        gamma, beta = math.pi / 4.0, math.pi / 4.0  # p=1 QAOA angles (heuristic)
        for (i, j), v in pairs.items():
            # RZZ(theta) = CX(i,j) RZ(theta,j) CX(i,j) — Heron supports RZZ
            # only in [0, pi/2]; the CX decomposition is exact for any angle.
            circ.cx(qr[i], qr[j])
            circ.rz(2 * gamma * v, qr[j])
            circ.cx(qr[i], qr[j])
        for i in range(n):
            circ.rz(2 * gamma * linear[i], qr[i])
        circ.rx(2 * beta, qr)
        circ.measure(qr, cr)

        service = self._new_service()
        backend = service.backend(backend_name)
        from qiskit import transpile

        tcirc = transpile(circ, backend=backend, optimization_level=1)
        sampler = SamplerV2(mode=backend)
        job = sampler.run([tcirc], shots=_SHOTS)
        result = job.result(timeout=timeout_s)
        counts = result[0].data.c.get_counts()

        best_x, best_e = None, math.inf
        for bitstr, cnt in counts.items():
            x = [int(b) for b in bitstr]
            e = _energy(x, linear, pairs)
            if e < best_e:
                best_e, best_x = e, x

        return SolveResult(
            status="succeeded",
            solution=best_x,
            objective=best_e,
            backend=f"ibm:{backend_name}",
            runtime_s=round(time.time() - t0, 3),
            quality_note=f"QAOA p=1 sample on IBM {backend_name}; {len(counts)} bitstrings",
            meta={"shots": _SHOTS, "counts": counts, "backend": backend_name},
        )
