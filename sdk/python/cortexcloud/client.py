"""CortexCloud API client — estimate / simulate / presets / optimize / jobs."""
from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from .signing import sign_payment

DEFAULT_BASE = "https://api.cortexcloud.org"


class CortexCloudError(RuntimeError):
    """Raised for API-level failures; carries status + body."""

    def __init__(self, status: int, detail: Any):
        self.status = status
        self.detail = detail
        super().__init__(f"cortexcloud {status}: {detail}")


class CortexCloud:
    def __init__(self, base_url: str = DEFAULT_BASE, timeout: float = 30.0,
                 private_key: Optional[str] = None):
        self._c = httpx.Client(base_url=base_url, timeout=timeout)
        self.private_key = private_key

    # ── free endpoints ────────────────────────────────────────────
    def estimate(self, problem: dict) -> dict:
        r = self._c.post("/v1/estimate", json=problem)
        self._raise(r)
        return r.json()

    def simulate(self, problem: dict) -> dict:
        r = self._c.post("/v1/simulate", json=problem)
        self._raise(r)
        return r.json()

    def preset(self, kind: str, constraints: dict) -> dict:
        r = self._c.post(f"/v1/solvers/{kind}", json=constraints)
        self._raise(r)
        return r.json()

    def trial(self, problem: dict, mode: str = "auto") -> dict:
        """Free no-wallet solve (n<=10). Mirrors POST /v1/trial server route."""
        r = self._c.post("/v1/trial", json={"problem": problem, "mode": mode})
        self._raise(r)
        return r.json()

    # ── paid path ─────────────────────────────────────────────────
    def optimize(self, problem: dict, mode: str = "auto",
                 webhook_url: Optional[str] = None) -> dict:
        """Full flow: 402 challenge -> sign -> settle -> job. Needs private_key."""
        if not self.private_key:
            raise CortexCloudError(0, "private_key required for paid calls")
        body = {"mode": mode, "problem": problem}
        if webhook_url:
            body["webhook_url"] = webhook_url
        r = self._c.post("/v1/optimize", json=body,
                         headers={"accept": "application/json"})
        if r.status_code == 402:
            sig = sign_payment(r.json(), self.private_key)
            r = self._c.post("/v1/optimize", json=body,
                             headers={"accept": "application/json",
                                      "payment-signature": sig})
        self._raise(r)
        return r.json()

    def job(self, job_id: str) -> dict:
        r = self._c.get(f"/v1/jobs/{job_id}")
        self._raise(r)
        return r.json()

    def wait(self, job_id: str, timeout_s: float = 180.0, poll_s: float = 2.0) -> dict:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            job = self.job(job_id)
            if job.get("status") in ("completed", "succeeded", "failed"):
                return job
            time.sleep(poll_s)
        raise TimeoutError(f"job {job_id} unfinished after {timeout_s}s")

    @staticmethod
    def _raise(r: httpx.Response) -> None:
        if r.status_code >= 400:
            try:
                detail = r.json()
            except Exception:
                detail = r.text[:200]
            raise CortexCloudError(r.status_code, detail)
