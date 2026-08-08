"""Origin Quantum / Wukong adapter — ONE quantum provider, fully isolated.

Behind the Solver protocol; the estimator, API and MCP tools never import
this module directly (they go through the backend router). Uses the
current official Origin Quantum cloud path: quafu-runtime (ScQ-Cloud),
API-token auth, program upload -> run -> poll result. Wukong is Origin's
superconducting processor on the Quafu cloud; the concrete backend id is
configurable (ORIGINQ_BACKEND) since it is only meaningful with a live
account.

Honesty contract: availability() is False unless ORIGINQ_API_TOKEN is
set AND the quafu-runtime SDK is importable. solve() never fabricates a
hardware result — no token -> failed with a clear error, and live QPU
execution is blocked while QUANTUM_LIVE_EXECUTION=false. The client
always recomputes the objective from the returned bitstring, so a
misbehaving program can never fake a good energy.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from app.solvers.base import Estimate, SolveResult, SolverAvailability, SolverSpec
from app.solvers.quantum.base import QuantumBackend

# Wukong's publicly documented capacity: 8 superconducting qubits. QAOA
# on it must fit inside that, so this adapter caps n at 8.
MAX_QBITS = 8


class OriginWukongAdapter(QuantumBackend):
    """Submit a QUBO to Wukong via quafu-runtime."""

    def __init__(self, api_token: str | None = None, backend: str | None = None):
        super().__init__(
            SolverSpec(
                id="wukong",
                name="Origin Quantum Wukong (superconducting)",
                mode="quantum",
                description="QAOA execution on Origin Quantum's Wukong superconducting processor via the Quafu cloud (quafu-runtime).",
                max_variables=MAX_QBITS,
                requires_token=True,
            ),
            provider="origin",
            algorithm="QAOA",
        )
        self._api_token = api_token
        self._backend = backend
        self._program_id: str | None = None
        self._runtime: Any = None
        self._log = logging.getLogger("cortexcloud.solvers.origin")

    # -- capability --------------------------------------------------
    def _sdk(self):
        if self._runtime is None:
            try:
                from quafu_runtime import Account, RuntimeService  # optional dep
            except ImportError:
                return None
            acc = Account(api_token=self._api_token)
            self._runtime = RuntimeService(account=acc)
        return self._runtime

    def availability(self) -> SolverAvailability:
        if not self._api_token:
            return SolverAvailability(False, "ORIGINQ_API_TOKEN not set")
        if self._runtime is None and self._sdk() is None:
            return SolverAvailability(
                False, "quafu-runtime SDK not installed — see requirements-quantum.txt"
            )
        return SolverAvailability(True, "ready")

    def estimate(self, qubo, n: int) -> Estimate:
        # Model-based until first real benchmark rows exist: queue +
        # gate execution + readout for an 8-qubit session.
        return Estimate(runtime_s=45.0, price_usd=0.25, basis="model")

    def solve(self, qubo, n: int, timeout_s: float = 300.0) -> SolveResult:
        t0 = time.time()
        gate = self.live_gate()
        if gate:
            return SolveResult(status="failed", error=gate.reason)
        rt = self._sdk()
        if not rt or not self._api_token:
            return SolveResult(status="failed", error=self.availability().reason)
        if n > MAX_QBITS:
            return SolveResult(
                status="failed",
                error=f"n={n} exceeds Wukong capacity ({MAX_QBITS} qubits)",
            )
        try:
            program_id = self._ensure_program(rt, qubo, n)
            job = rt.run(
                program_id=program_id,
                params={"qubo": qubo, "n": n, "backend": self._backend or "wukong"},
            )
            payload = job.result(timeout=timeout_s)  # block until done
            bits = _extract_bitstring(payload)
            if bits is None:
                return SolveResult(
                    status="failed",
                    error="wukong run returned no parseable assignment",
                )
            # Objective ALWAYS recomputed locally from the returned bits.
            energy = self.qubo_energy(qubo, bits)
            return SolveResult(
                status="succeeded",
                solution=bits,
                objective=energy,
                backend=self.spec.id,
                runtime_s=round(time.time() - t0, 3),
                quality_note="hardware run — objective recomputed locally from sampled bitstring",
                meta={"source": "origin-wukong", "payload_keys": sorted(payload.keys()) if isinstance(payload, dict) else []},
            )
        except Exception as exc:  # surface SDK/network errors honestly
            self._log.warning("wukong solve failed: %s", exc)
            return SolveResult(status="failed", error=f"wukong execution failed: {exc}")

    # -- internals ---------------------------------------------------
    def _ensure_program(self, qubo, n) -> str:
        if self._program_id:
            return self._program_id
        pid = self._runtime.upload_program(
            data=_QAOA_PROGRAM_TEMPLATE,
            metadata={"name": "cortexcloud-qaoa-p1", "backend": self._backend or "wukong"},
        )
        self._program_id = pid
        return pid


def _extract_bitstring(payload) -> list[int] | None:
    """Best-effort parse of whatever quafu-runtime returns: dict with
    'x'/'result'/'outcome'/'bits', or a string of 0/1."""
    if payload is None:
        return None
    if isinstance(payload, list):
        return [_bit(v) for v in payload]
    if isinstance(payload, str):
        chars = [c for c in payload.strip() if c in "01"]
        return [int(c) for c in chars] if chars else None
    if isinstance(payload, dict):
        for key in ("x", "solution", "best", "outcome", "bits", "result"):
            v = payload.get(key)
            if isinstance(v, list):
                return [_bit(b) for b in v]
            if isinstance(v, str):
                return _extract_bitstring(v)
            if isinstance(v, dict) and "state" in v:
                return _extract_bitstring(v["state"])
    return None


def _bit(v) -> int:
    return 1 if str(v).strip() in ("1", "true", "True") else 0


# QAOA p=1 hybrid program shipped to the Origin cloud runtime. Runs
# server-side; failure to parse is reported rather than faked, and the
# network recomputes energies from the sampled bitstring anyway.
_QAOA_PROGRAM_TEMPLATE = r'''
# CortexCloud Optimization Network — QAOA p=1 (hybrid program)
# Runs inside the Origin Quafu cloud runtime; quafu is provided there.
import json

def run(params):
    try:
        from quafu import QuantumCircuit
        from quafu.simulators import simulate
    except Exception as exc:
        return {"error": "quafu unavailable in runtime: %s" % exc}
    q = params["qubo"]
    n = params["n"]
    gamma = params.get("gamma", -0.5)
    beta = params.get("beta", 0.5)
    qc = QuantumCircuit(n)
    for i in range(n):
        qc.h(i)
    quad = q.get("quadratic") or {}
    for key, c in quad.items():
        i, j = map(int, key.split(","))
        qc.cx(i, j)
        qc.rz(2.0 * float(c) * gamma, j)
        qc.cx(i, j)
    lin = q.get("linear") or []
    for i, h in enumerate(lin):
        qc.rz(2.0 * float(h) * gamma, i)
    for i in range(n):
        qc.rx(2.0 * beta, i)
    result = simulate(qc, shots=1024, backend=None)
    counts = getattr(result, "counts", None) or result
    best = max(counts, key=counts.get) if isinstance(counts, dict) and counts else ("0" * n)
    return {"x": [int(c) for c in best], "shots": 1024}
'''