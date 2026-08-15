# CortexCloud x402 Integration Guide — Autonomous Agents (Python)

**CrewAI · LangGraph · plain `requests`**

CortexCloud sells QUBO/Ising optimization as a pay-per-call API. There are no
API keys, no signup, no billing portal: **the payment is the authentication.**
An agent discovers the API, gets a free exact quote, pays in USDC on Base via
an x402 challenge, and polls for the solution.

- Base URL: `https://api.cortexcloud.org`
- Settlement: USDC on Base (`eip155:8453`), contract
  `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`
- Protocol: x402 v2 (HTTP 402 + EIP-3009 `transferWithAuthorization`)

---

## 1. The payment flow, end to end

```
Agent                                  CortexCloud
  │ 1. GET  /.well-known/x402.json           │   discover (free, no auth)
  │ ----------------------------------------> │
  │ 2. POST /v1/estimate                      │   free exact quote
  │ ----------------------------------------> │
  │ <---------------------------------------- │  {recommendation: {mode,
  │                                          │   price_usd, runtime, ...}}
  │ 3. POST /v1/optimize (no payment)         │
  │ ----------------------------------------> │
  │ <------------------ 402 + challenge ----- │  {x402Version: 2, accepts:[
  │                                          │    {amount, payTo, ...}]}
  │ 4. Sign EIP-3009 transferWithAuthorization│   USDC → payTo (off-chain sign)
  │ 5. POST /v1/optimize + payment-signature  │
  │ ----------------------------------------> │   facilitator verifies on-chain
  │ <---------------------- 200 {job_id} ---- │
  │ 6. GET /v1/jobs/{job_id} (poll)           │
  │ <---------------- 200 {status, result} --- │
```

Only step 5 costs money, and only if the transfer verifies on-chain. A
request that fails validation (HTTP 422) or has no available backend (HTTP
409) is rejected **before** settlement — you are never charged for an
unrunnable problem.

---

## 2. Step 1 — Discovery (no API key)

Agents find CortexCloud the way humans find a website:

| URL | What it declares |
|---|---|
| `/.well-known/x402.json` | x402 discovery manifest |
| `/.well-known/bazaar` | AgentCash Bazaar listing (schemas + pricing) |
| `/openapi.json` | Full OpenAPI spec (16 routes) |
| `/llms.txt` | LLM-readable summary for zero-hop injection |
| `/mcp` | MCP server, 4 tools (for MCP-native harnesses) |

The OpenAPI spec marks `POST /v1/optimize` as the only paid route
(`x-payment-info`, dynamic $0.05–$1.503, protocols `[x402, mpp]`); every
other route is `security: []` — explicitly public.

---

## 3. Step 2 — Free estimate

`POST /v1/estimate` returns the recommended solver, backend, runtime and the
**exact price a paid call would charge**. Always call this first: it is your
budget gate.

```python
import requests

API = "https://api.cortexcloud.org"

def estimate(problem: dict) -> dict:
    r = requests.post(f"{API}/v1/estimate", json=problem, timeout=30)
    r.raise_for_status()
    return r.json()["recommendation"]

problem = {
    "problem_type": "qubo",
    "n": 6,
    "data": {
        "linear": [1, -2, 3, -4, 2, -1],
        "quadratic": {"0,1": -1.5, "1,2": 2.0, "2,3": -0.5, "3,4": 1.0, "4,5": -2.0},
    },
}

rec = estimate(problem)
print(rec["mode"], rec["solver_id"], rec["cortexcloud_price_usd"], rec["estimated_runtime_s"])
# classical brute-force 0.05 0.001
```

**Budget guardrail:** compare `rec["cortexcloud_price_usd"]` against the
agent's per-call budget before paying. If the recommended mode is quantum
($1.503) and the budget is $0.25, request `"mode": "classical"` explicitly —
the mode is a hint, the estimate endpoint does the math.

---

## 4. Step 3 — Get the payment challenge

`POST /v1/optimize` with no payment headers returns `HTTP 402` with a
x402-v2 challenge (also mirrored base64 in the `payment-required` header for
spec-compliant clients):

```python
def get_challenge(problem: dict, mode: str = "auto") -> dict:
    r = requests.post(
        f"{API}/v1/optimize",
        json={"mode": mode, "problem": problem},
        headers={"accept": "application/json"},
        timeout=30,
    )
    assert r.status_code == 402, f"expected 402, got {r.status_code}: {r.text[:200]}"
    return r.json()
```

Live example (n=4):

```json
{
  "x402Version": 2,
  "resource": {"url": "https://api.cortexcloud.org/v1/optimize", "mimeType": "application/json"},
  "accepts": [{
    "scheme": "exact",
    "network": "eip155:8453",
    "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "amount": "50000",
    "payTo": "0x5a0353bc9c75b893a9b5735d3e79f1bd988ea143",
    "maxTimeoutSeconds": 60,
    "extra": {"name": "USD Coin", "version": "2"}
  }],
  "extensions": {"bazaar": {"info": {"input": {...}, "output": {...}}, "schema": {...}}}
}
```

Read it like this:

- `accepts[0].scheme == "exact"` — pay exactly `amount`, no more.
- `amount` is **atomic units** (6 decimals): `50000 / 1e6 = $0.05`.
- `asset` is the USDC contract on Base; `network` is the CAIP-2 chain id.
- `payTo` is where the USDC goes.
- `extra` is the **EIP-712 domain** you must sign against:
  `{name: "USD Coin", version: "2"}` on chain `8453` with the asset contract
  as `verifyingContract`.
- `maxTimeoutSeconds: 60` — the authorization must be used within 60s.
- `extensions.bazaar.schema` is a machine-readable input/output schema.

---

## 5. Step 4 — Sign the payment (EIP-3009)

x402 v2 settles with USDC's `transferWithAuthorization` (EIP-3009): you sign
an authorization that lets the payee pull the exact amount, then submit the
signature. No approval transaction, no gas on the agent side.

```python
import base64, json, time, secrets
from eth_account import Account
from eth_account.messages import encode_typed_data

USDC_ON_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
CHAIN_ID = 8453

def sign_payment(challenge: dict, private_key: str) -> str:
    acc = challenge["accepts"][0]
    amount_atomic = int(acc["amount"])
    pay_to = acc["payTo"]
    domain = {
        "name": acc["extra"]["name"],          # "USD Coin"
        "version": acc["extra"]["version"],    # "2"
        "chainId": CHAIN_ID,
        "verifyingContract": acc["asset"],
    }
    # validAfter 0, validBefore now + maxTimeoutSeconds, random 32-byte nonce
    now = int(time.time())
    message = {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "TransferWithAuthorization": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce", "type": "bytes32"},
            ],
        },
        "primaryType": "TransferWithAuthorization",
        "domain": domain,
        "message": {
            "from": Account.from_key(private_key).address,
            "to": pay_to,
            "value": amount_atomic,
            "validAfter": 0,
            "validBefore": now + int(acc["maxTimeoutSeconds"]),
            "nonce": "0x" + secrets.token_hex(32),
        },
    }
    signed = Account.sign_typed_data(Account.from_key(private_key), encode_typed_data(message))

    # x402 v2 envelope: base64(JSON) -> payment-signature header.
    # The authorization object carries the EIP-3009 fields + the signature.
    authorization = {
        "from": message["message"]["from"],
        "to": pay_to,
        "value": str(amount_atomic),
        "validAfter": "0",
        "validBefore": str(message["message"]["validBefore"]),
        "nonce": message["message"]["nonce"],
        "r": hex(signed.r), "s": hex(signed.s), "v": signed.v,
    }
    payload = {"payload": {"authorization": authorization}}
    return base64.b64encode(json.dumps(payload).encode()).decode()
```

Security notes:

- **Never log the private key.** Load it from an env var / secret store
  (`EVM_PRIVATE_KEY`), keep it out of prompts, tool args and tracebacks.
- The nonce is single-use — a retried request with the same signature hits
  the server's nonce-dedup cache and is rejected; sign fresh per attempt.
- The server re-verifies everything on-chain via its facilitator before
  executing; a forged or expired signature simply gets a 402/401 back.

---

## 6. Step 5 — Pay and solve

Retry `POST /v1/optimize` with the same body plus the signed payload:

```python
def solve(problem: dict, challenge: dict, private_key: str) -> dict:
    signature = sign_payment(challenge, private_key)
    r = requests.post(
        f"{API}/v1/optimize",
        json={"mode": "auto", "problem": problem},
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "payment-signature": signature,
        },
        timeout=90,
    )
    if r.status_code == 402:
        raise PaymentChallengeExpired(r.json())   # re-run from step 3
    r.raise_for_status()
    return r.json()  # {"job_id": "...", "status": "queued|completed", ...}
```

Notes:

- Responses carry an `X-PAYMENT-RESPONSE` header (base64 of
  `{"success": true, ...}`) — the audit trail for the settled call.
- Identical proofs are cached for 60 s, so a network timeout + immediate
  retry with the same signature succeeds without double-charging (the
  EIP-3009 nonce also makes double-spend impossible).
- **Do not** put the private key or signature in the JSON body — the
  signature travels in the `payment-signature` header only.

---

## 7. Step 6 — Poll for the solution

```python
import time

def poll(job_id: str, timeout_s: int = 300) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        r = requests.get(f"{API}/v1/jobs/{job_id}", timeout=15)
        if r.status_code == 404:
            time.sleep(2); continue
        r.raise_for_status()
        job = r.json()
        if job.get("status") in ("completed", "failed"):
            return job
        time.sleep(2)
    raise TimeoutError(f"job {job_id} did not finish in {timeout_s}s")
```

---

## 8. Error handling matrix

| Code | Meaning | Agent action |
|---|---|---|
| `200` | Solved (or job queued with `job_id`) | Poll `/v1/jobs/{id}` |
| `402` | Challenge issued / payment rejected | Sign (or re-sign) and retry |
| `409` | No available backend for requested mode | Wait, or switch mode (classical is most reliable) |
| `422` | Problem invalid — **never charged** | Fix problem, no payment needed |
| `429` | Rate limited | Back off (exponential) |
| `5xx` | Upstream/quantum provider hiccup | Retry with backoff; no charge unless settled |

---

## 9. CrewAI — one tool, three steps

```python
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
import requests, time

class OptimizeInput(BaseModel):
    problem: dict = Field(description="QUBO/Ising problem: {problem_type, n, data:{linear, quadratic}}")
    max_price_usd: float = Field(default=0.25, description="Budget ceiling per call")

class CortexCloudOptimizeTool(BaseTool):
    name: str = "cortexcloud_optimize"
    description: str = "Solves a QUBO/Ising combinatorial optimization problem via the pay-per-call CortexCloud API (x402, USDC on Base). No API key needed; pays from the configured wallet."
    args_schema: type[BaseModel] = OptimizeInput
    private_key: str  # from env / secret store

    def _run(self, problem: dict, max_price_usd: float = 0.25) -> dict:
        rec = requests.post("https://api.cortexcloud.org/v1/estimate", json=problem, timeout=30).json()["recommendation"]
        if rec["cortexcloud_price_usd"] > max_price_usd:
            return {"error": "over_budget", "price_usd": rec["cortexcloud_price_usd"], "max_price_usd": max_price_usd}
        challenge = requests.post("https://api.cortexcloud.org/v1/optimize",
                                  json={"mode": "auto", "problem": problem},
                                  headers={"accept": "application/json"}, timeout=30)
        assert challenge.status_code == 402
        signature = self._sign(challenge.json())          # Section 5
        paid = requests.post("https://api.cortexcloud.org/v1/optimize",
                             json={"mode": "auto", "problem": problem},
                             headers={"accept": "application/json", "payment-signature": signature}, timeout=90)
        paid.raise_for_status()
        job = paid.json()
        while job.get("status") not in ("completed", "failed"):
            time.sleep(2)
            job = requests.get(f"https://api.cortexcloud.org/v1/jobs/{job['job_id']}", timeout=15).json()
        return job
```

Wire it into a Crew:

```python
from crewai import Agent, Task, Crew

optimizer = Agent(
    role="Optimization specialist",
    goal="Solve scheduling/portfolio/routing problems as QUBO and return the optimum",
    backstory="You pay per call from the team wallet; you always check the free estimate first and never exceed budget.",
    tools=[CortexCloudOptimizeTool(private_key=os.environ["EVM_PRIVATE_KEY"])],
    llm="gpt-4o",
)

task = Task(
    description="Minimize weighted portfolio variance for 10 assets with at most 4 selected. Use the optimization tool.",
    expected_output="The selected asset set and the objective value.",
    agent=optimizer,
)
```

---

## 10. LangGraph — a payment-aware state machine

```python
from typing import TypedDict, Literal
from langgraph.graph import StateGraph, START, END
import requests, time

class OptState(TypedDict):
    problem: dict
    estimate: dict
    challenge: dict
    signature: str
    job_id: str
    result: dict

def do_estimate(state: OptState) -> dict:
    r = requests.post("https://api.cortexcloud.org/v1/estimate", json=state["problem"], timeout=30)
    return {"estimate": r.json()["recommendation"]}

def get_challenge(state: OptState) -> dict:
    r = requests.post("https://api.cortexcloud.org/v1/optimize",
                      json={"mode": "auto", "problem": state["problem"]},
                      headers={"accept": "application/json"}, timeout=30)
    return {"challenge": r.json()}

def pay_and_submit(state: OptState) -> dict:
    sig = sign_payment(state["challenge"], os.environ["EVM_PRIVATE_KEY"])   # Section 5
    r = requests.post("https://api.cortexcloud.org/v1/optimize",
                      json={"mode": "auto", "problem": state["problem"]},
                      headers={"accept": "application/json", "payment-signature": sig}, timeout=90)
    if r.status_code == 402:
        return {"signature": None}            # route back to challenge
    r.raise_for_status()
    return {"job_id": r.json().get("job_id")}

def poll_job(state: OptState) -> dict:
    job = requests.get(f"https://api.cortexcloud.org/v1/jobs/{state['job_id']}", timeout=15).json()
    if job.get("status") == "completed":
        return {"result": job}
    time.sleep(2)
    return {}

def route(state: OptState) -> Literal["poll_job", "get_challenge"]:
    if state.get("result"): return END
    return "poll_job" if state.get("job_id") else "get_challenge"

g = StateGraph(OptState)
g.add_node("estimate", do_estimate); g.add_node("challenge", get_challenge)
g.add_node("pay", pay_and_submit); g.add_node("poll", poll_job)
g.add_edge(START, "estimate"); g.add_edge("estimate", "challenge")
g.add_edge("challenge", "pay")
g.add_conditional_edges("pay", lambda s: "poll" if s.get("job_id") else "challenge")
g.add_conditional_edges("poll", lambda s: "poll" if not s.get("result") else END)
app = g.compile()
```

The conditional edges make the graph **self-healing**: an expired or rejected
payment routes back to `get_challenge` and re-signs; an unfinished job keeps
polling. No human, no API key, no dead end.

---

## 11. MCP alternative (no code)

Harnesses with MCP support skip all of the above:

```
claude mcp add cortexcloud --transport http https://api.cortexcloud.org/mcp
```

The 4-tool MCP server wraps estimate/optimize/jobs/backends; the wallet
key lives in the server's environment, and the harness agent calls the tools
directly. Same payment flow underneath — the agent just never sees the
headers.

---

## 12. Production checklist

1. Load `EVM_PRIVATE_KEY` from a secret manager; never from code or logs.
2. Always call `/v1/estimate` first; refuse to pay above budget.
3. Treat `amount` as atomic (÷1e6) and `payTo` as untrusted data from the challenge — verify the challenge came from `api.cortexcloud.org` over TLS before signing.
4. Sign fresh per attempt (nonces are single-use; proofs cache for 60 s).
5. Handle 402/409/422 explicitly — 422 means your problem is wrong and costs nothing.
6. Keep the private key out of CrewAI tool args and LangGraph state.
7. For fleet operations, fund one wallet and share read-only usage via `GET /x402/v1/usage?address=...`.

Questions: `hello@cortexcloud.org` · Docs: `https://api.cortexcloud.org/docs` · Bazaar: `/.well-known/bazaar`
