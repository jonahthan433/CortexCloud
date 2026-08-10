"""Amazon Braket quantum backend adapter — first multi-provider backend.

Provider-neutral: the public API sees plain mode='quantum' backends;
Braket concepts (arns, regions, boto3, braket-sdk) never leave this
module. Device names and capacities are DISCOVERED from the AWS Braket
get_devices API (free, no QPU time), never hardcoded — so a provider
that stops selling on Braket simply reports no online device.

Providers targeted (optimization-appropriate QPUs on Braket):
Rigetti, IonQ, IQM, QuEra (all atom/superconducting/trapped-ion/analog
QPU families) and AQT — each only "available" when AWS credentials are
present AND get_devices returns an ONLINE QPU for it.

Honesty contract mirrors origin.py: solve() never fakes a result, is
blocked while QUANTUM_LIVE_EXECUTION=false, and recomputes the objective
locally from the sampled bitstring. All costs are model estimates
(basis="model") until verified AWS pricing/benchmarks exist.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.core.config import settings
from app.solvers.base import Estimate, SolveResult, SolverAvailability, SolverSpec
from app.solvers.quantum.base import QuantumBackend
from app.x402.pricing import MODE_PRICE_USD

# Shots for every QPU run. Single constant so preflight logging and the
# submission call can never drift apart.
BRAKET_SHOTS = 1024

# Provider -> model figures. NONE of these are advertised as measured:
# they only feed relative cost-aware routing until live execution
# produces verified price-list / benchmark data. qubit cap is a SAFE
# floor; the real capacity comes from device discovery.
PROVIDERS: dict[str, dict[str, Any]] = {
    "rigetti": {"aws_name": "Rigetti", "price_usd": 0.75, "runtime_s": 60.0, "cap": 100},
    "ionq":    {"aws_name": "IonQ",    "price_usd": 3.40, "runtime_s": 90.0, "cap": 100},
    "iqm":     {"aws_name": "IQM",     "price_usd": 0.40, "runtime_s": 75.0, "cap": 100},
    "quera":   {"aws_name": "QuEra",   "price_usd": 0.25, "runtime_s": 120.0, "cap": 100},
    "aqt":     {"aws_name": "AQT",     "price_usd": 0.30, "runtime_s": 90.0, "cap": 100},
}

_DISCOVERY_TTL_S = 300.0  # ponytail: single TTL; per-region TTLs if a region flaps


def _new_client(region: str):
    """Braket API client for one region. Test seam — monkeypatched in
    tests; boto3 imports lazily so the app runs without it installed."""
    import boto3

    kw = {}
    if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
        kw.update(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
    return boto3.client("braket", region_name=region, **kw)


class BraketBackend(QuantumBackend):
    """One Braket provider (rigetti/ionq/iqm/quera/aqt) as a Solver."""

    def __init__(self, provider: str):
        if provider not in PROVIDERS:
            raise ValueError(f"unknown braket provider {provider!r}")
        cfg = PROVIDERS[provider]
        self._cfg = cfg
        self._devices: list[dict] | None = None
        self._error: str | None = None
        self._discovered_at = 0.0
        self._log = logging.getLogger(f"cortexcloud.solvers.braket.{provider}")
        super().__init__(
            SolverSpec(
                id=provider,
                name="quantum QPU",
                mode="quantum",
                description=(
                    "QAOA on real quantum hardware — 1024 shots per run."
                ),
                max_variables=cfg["cap"],
                requires_token=True,
            ),
            provider="aws_braket",
            algorithm="QAOA",
        )

    # -- capability --------------------------------------------------
    def _credentials_present(self) -> bool:
        if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
            return True
        import os

        return bool(os.environ.get("AWS_ACCESS_KEY_ID")) and bool(
            os.environ.get("AWS_SECRET_ACCESS_KEY")
        )

    def _regions(self) -> list[str]:
        return [r.strip() for r in settings.BRAKET_REGIONS.split(",") if r.strip()] or [
            "us-east-1"
        ]

    def _discover(self) -> tuple[list[dict] | None, str | None]:
        """(devices, error). Cached TTL_S; failures cached too so a
        flaky AWS call doesn't hammer per request."""
        if self._devices is not None and time.time() - self._discovered_at < _DISCOVERY_TTL_S:
            return self._devices, self._error
        try:
            devices: list[dict] = []
            for region in self._regions():
                client = _new_client(region)
                # SearchDevices only supports the deviceArn filter (and the
                # key itself is required) — pass empty filters, filter
                # provider/status client-side (matches the SDK's own pattern).
                resp = client.search_devices(filters=[])
                # ponytail: no nextToken pagination (Braket lists ~15 devices);
                # add a loop when device counts grow.
                for d in resp.get("devices", []):
                    if (
                        d.get("deviceType") == "QPU"
                        and d.get("deviceStatus") == "ONLINE"
                        and d.get("providerName") == self._cfg["aws_name"]
                    ):
                        # search_devices does NOT return deviceCapabilities,
                        # so fetch the full device record to check IR support.
                        # Excludes AHS-only devices (e.g. QuEra Aquila) that
                        # cannot run the QUBO/Ising IR. Failures skip the
                        # device, never the whole discovery.
                        caps = ""
                        try:
                            full = client.get_device(deviceArn=d["deviceArn"])
                            c = full.get("deviceCapabilities") or ""
                            caps = json.dumps(c) if isinstance(c, dict) else str(c)
                        except Exception:
                            caps = ""
                        if not any(k in caps for k in ("jaqcd", "annealing", "openqasm")):
                            continue
                        devices.append(d)
            self._devices, self._error = devices, None
        except ImportError as exc:
            self._devices, self._error = [], f"braket/boto3 SDK not installed ({exc})"
        except Exception as exc:
            self._log.warning("braket discovery failed: %s", exc)
            self._devices, self._error = [], str(exc)
        self._discovered_at = time.time()
        return self._devices, self._error

    def availability(self) -> SolverAvailability:
        if not self._credentials_present():
            return SolverAvailability(
                False, "quantum capability check failed"
            )
        devices, err = self._discover()
        if err is not None:
            return SolverAvailability(False, f"Braket capability check failed: {err}")
        if not devices:
            return SolverAvailability(False, "no quantum device online")
        # qubit count from the live discovery, not the static floor
        qc = (
            devices[0].get("quantumComputingDeviceData", {})
            .get("qpuSpecifications", {})
            .get("qubitCount")
        )
        if qc:
            self.spec.max_variables = int(qc)
        return SolverAvailability(
            True, f"capability check OK ({self.spec.max_variables} qubits)"
        )

    def estimate(self, qubo, n: int) -> Estimate:
        return Estimate(
            runtime_s=self._cfg["runtime_s"], price_usd=self._cfg["price_usd"], basis="model"
        )

    # -- preflight ---------------------------------------------------
    def _preflight_cost(self, qubo, n: int) -> str | None:
        """Refusal reason, or None when safe to submit. Called immediately
        before CreateQuantumTask: refuse unless the provider cost is known,
        positive, finite, and within QUANTUM_MAX_COST_USD."""
        est = self.estimate(qubo, n)
        try:
            cost = float(est.price_usd)
        except (TypeError, ValueError):
            return "quantum preflight failed: provider cost unavailable"
        if cost != cost or cost <= 0:  # NaN or non-positive => not confidently known
            return "quantum preflight failed: provider cost not confidently determined"
        if cost > settings.QUANTUM_MAX_COST_USD:
            return (
                f"quantum preflight failed: estimated provider cost ${cost:.2f} "
                f"> QUANTUM_MAX_COST_USD ${settings.QUANTUM_MAX_COST_USD:.2f}"
            )
        price = MODE_PRICE_USD.get("quantum", 0.0)
        if cost > price and not settings.QUANTUM_ALLOW_SUBSIDY:
            return (
                f"quantum preflight failed: est provider cost ${cost:.2f} > "
                f"cortexcloud price ${price:.2f} "
                f"(set QUANTUM_ALLOW_SUBSIDY=true to sell below cost)"
            )
        return None

    def _log_preflight(self, n: int, cost: float, device_arn: str) -> None:
        """One structured line per real submission attempt. Never logs
        credentials or request bodies — cost/billing fields only."""
        self._log.info(json.dumps({
            "event": "quantum.preflight",
            "provider": self.provider,
            "backend": self.spec.id,
            "device_arn": device_arn,
            "shots": BRAKET_SHOTS,
            "estimated_provider_cost_usd": round(cost, 4),
            "cortexcloud_price_usd": MODE_PRICE_USD.get("quantum"),
            "margin_usd": round(cost - MODE_PRICE_USD.get("quantum", 0.0), 4),
        }))

    # -- execution ---------------------------------------------------
    def solve(self, qubo, n: int, timeout_s: float = 300.0) -> SolveResult:
        t0 = time.time()
        gate = self.live_gate()
        if gate:
            return SolveResult(status="failed", error=gate.reason)
        av = self.availability()
        if not av.available:
            return SolveResult(status="failed", error=av.reason)
        if n > self.spec.max_variables:
            return SolveResult(
                status="failed",
                error=f"n={n} exceeds {self.spec.id} capacity ({self.spec.max_variables} qubits)",
            )
        # Live path — only reachable with QUANTUM_LIVE_EXECUTION=true.
        # QAOA p=1 gate model on the discovered device via braket-sdk
        # (same angles as the Origin template; objective recomputed
        # locally from the sampled bitstring either way).
        try:
            import boto3
            from braket.aws import AwsDevice, AwsSession
            from braket.circuits import Circuit

            arn = self._devices[0]["deviceArn"]
            # The SDK builds its own boto3 session — give it the device's
            # region + our creds explicitly (no ambient AWS_DEFAULT_REGION
            # on the server).
            region = arn.split(":")[3]
            _boto_kw = {"region_name": region}
            if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
                _boto_kw.update(
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                )
            dev = AwsDevice(arn, aws_session=AwsSession(boto_session=boto3.Session(**_boto_kw)))
            gamma, beta = -0.5, 0.5
            circ = Circuit().h(range(n))
            for key, c in (qubo.get("quadratic") or {}).items():
                i, j = (int(t) for t in key.split(","))
                circ.cnot(i, j).rz(j, 2.0 * float(c) * gamma).cnot(i, j)
            for i, h in enumerate(qubo.get("linear") or []):
                circ.rz(i, 2.0 * float(h) * gamma)
            circ.rx(range(n), 2.0 * beta)
            # Preflight cost gate: refuse submission unless the provider cost
            # is known, positive, and within QUANTUM_MAX_COST_USD — checked
            # HERE, immediately before CreateQuantumTask (defense in depth on
            # top of the runner-level cap). Log the billing facts first.
            est = self.estimate(qubo, n)
            preflight = self._preflight_cost(qubo, n)
            if preflight:
                self._log.warning("%s (device %s)", preflight, arn)
                return SolveResult(status="failed", error=preflight)
            self._log_preflight(n, float(est.price_usd), arn)
            task = dev.run(circ, shots=BRAKET_SHOTS)
            counts = task.result().measurement_counts
            bits = max(counts, key=counts.get) if counts else ("0" * n)
            x = [int(c) for c in bits]
            return SolveResult(
                status="succeeded",
                solution=x,
                objective=self.qubo_energy(x, qubo, n),
                backend=self.spec.id,
                runtime_s=round(time.time() - t0, 3),
                quality_note="hardware run — objective recomputed locally from sampled bitstring",
                meta={
                    "source": f"aws-braket-{self.spec.id}",
                    "device_arn": arn,
                    "task_arn": task.id,
                    "shots": BRAKET_SHOTS,
                    "counts": dict(counts),
                },
            )
        except Exception as exc:  # surface SDK/network errors honestly
            self._log.warning("braket solve failed: %s", exc)
            return SolveResult(status="failed", error=f"braket execution failed: {exc}")