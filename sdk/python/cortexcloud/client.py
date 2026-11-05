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
                 private_key: Optional[str] = None, api_key: Optional[str] = None):
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
        self._c = httpx.Client(base_url=base_url, timeout=timeout, headers=headers)
        self.private_key = private_key
        self.api_key = api_key

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

    # ── generic paid call (x402 v2) ──────────────────────────────
    def pay(self, method: str, path: str, json: Optional[dict] = None,
            idempotency_key: Optional[str] = None) -> dict:
        """Use subscription credits first; if exhausted, sign x402 with private_key."""
        if not self.private_key and not self.api_key:
            raise CortexCloudError(0, "api_key or private_key required for paid calls")
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        r = self._c.request(method, path, json=json, headers=headers)
        if r.status_code == 402:
            if not self.private_key:
                raise CortexCloudError(402, "subscription credits exhausted; private_key required for x402 overage")
            sig = sign_payment(r.json(), self.private_key)
            r = self._c.request(method, path, json=json,
                                headers={**headers, "payment-signature": sig})
        self._raise(r)
        return r.json()

    # ── prepaid subscription / billing ───────────────────────────
    def billing_plans(self) -> dict:
        r = self._c.get("/v1/billing/plans")
        self._raise(r)
        return r.json()

    def subscribe(self, plan_id: str) -> dict:
        """Purchase/renew a prepaid plan with x402; returns an API key once."""
        if not self.private_key:
            raise CortexCloudError(0, "private_key required to pay for a subscription")
        return self.pay("POST", f"/v1/billing/subscribe/{plan_id}")

    def billing_account(self) -> dict:
        r = self._c.get("/v1/billing/account")
        self._raise(r)
        return r.json()

    def billing_usage(self) -> dict:
        r = self._c.get("/v1/billing/usage")
        self._raise(r)
        return r.json()

    def revoke_api_key(self, key_id: str) -> dict:
        r = self._c.post("/v1/billing/keys/revoke", json={"key_id": key_id})
        self._raise(r)
        return r.json()

    # ── Data ($0.004) ─────────────────────────────────────────────
    def token_price(self, symbol: str, currency: str = "usd", chain: str = "ethereum") -> dict:
        """Spot price; symbol must be a CoinGecko id (for example, 'ethereum')."""
        return self.pay("POST", "/v1/data/token-price", json={"id": symbol, "currency": currency, "chain": chain})

    def token_balances(self, address: str, chain: str = "ethereum",
                       tokens: list[str] | None = None, max_tokens: int = 50) -> dict:
        return self.pay("POST", "/v1/data/token-balances", json={
            "address": address, "chain": chain, "tokens": tokens, "max_tokens": max_tokens,
        })

    def wallet_intel(self, address: str, chain: str = "ethereum", limit: int = 25) -> dict:
        return self.pay("POST", "/v1/data/wallet-intel", json={"address": address, "chain": chain, "limit": limit})

    def token_risk(self, contract: str, chain: str = "ethereum", coin_id: str | None = None) -> dict:
        return self.pay("POST", "/v1/data/token-risk", json={"contract": contract, "chain": chain, "coin_id": coin_id})

    def token_intel(self, contract: str, chain: str = "ethereum", coin_id: str | None = None) -> dict:
        return self.pay("POST", "/v1/data/token-intel", json={"contract": contract, "chain": chain, "coin_id": coin_id})

    def whale_alerts(self, address: str, chain: str = "ethereum",
                     min_usd: float = 100000, limit: int = 50) -> dict:
        return self.pay("POST", "/v1/data/whale-alerts", json={
            "address": address, "chain": chain, "min_usd": min_usd, "limit": limit,
        })

    def cross_chain_compare(self, contract: str, chains: list[str],
                            solana_mint: str | None = None, coin_id: str | None = None) -> dict:
        return self.pay("POST", "/v1/data/cross-chain-compare", json={
            "contract": contract, "chains": chains,
            "solana_mint": solana_mint, "coin_id": coin_id,
        })

    def block(self, chain: str = "base", number: str = "latest") -> dict:
        return self.pay("GET", f"/v1/data/block?chain={chain}&block={number}")

    def gas_oracle(self, chain: str = "base") -> dict:
        return self.pay("GET", f"/v1/data/gas-oracle?chain={chain}")

    # ── Research ($0.006 / $0.012) ────────────────────────────────
    def research_search(self, query: str, top_k: int = 5) -> dict:
        return self.pay("POST", "/v1/research/search", json={"query": query, "top_k": top_k})

    def research_answer(self, query: str) -> dict:
        return self.pay("POST", "/v1/research/answer", json={"query": query})

    # ── Automation ($0.004–$0.020) ────────────────────────────────
    def http_request(self, url: str, method: str = "GET", headers: dict | None = None,
                     body: str | None = None) -> dict:
        return self.pay("POST", "/v1/automation/http-request",
                        json={"url": url, "method": method, "headers": headers or {}, "body": body})

    # ── AI ($0.004) ───────────────────────────────────────────────
    def chat(self, prompt: str, model: str = "auto") -> dict:
        return self.pay("POST", "/v1/ai/chat", json={"prompt": prompt, "model": model})

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

    @staticmethod
    def demo() -> None:
        """Free-path smoke check (no wallet, no spend). Fails if the API is down."""
        cc = CortexCloud()
        prob = {"problem_type": "qubo", "n": 4,
                "data": {"linear": [1, -2, 3, -4], "quadratic": {"0,1": -1.5}}}
        est = cc.estimate(prob)
        assert est.get("recommendation"), "estimate returned no recommendation"
        tr = cc.trial(prob)
        assert tr.get("status") in ("succeeded", "completed", "ok"), f"trial: {tr}"
        print("cortexcloud SDK demo OK — free endpoints reachable, no spend")


if __name__ == "__main__":
    CortexCloud.demo()
