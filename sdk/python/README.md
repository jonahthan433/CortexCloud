# cortexcloud

Pay-per-call **QUBO/Ising optimization** for AI agents. No API keys, no signup —
an agent estimates for free, pays USDC on Base per call via **x402**, and polls
for the solution.

```bash
pip install cortexcloud
```

## Quickstart

```python
from cortexcloud import CortexCloud

cc = CortexCloud()                          # free calls work with no key
est = cc.estimate({"problem_type": "qubo", "n": 6, "data": {...}})
print(est["recommendation"]["mode"], est["recommendation"]["cortexcloud_price_usd"])
```

**Paid solve** (needs a wallet with USDC on Base):

```python
cc = CortexCloud(private_key="0x...")       # from your secret store
job = cc.optimize({"problem_type": "qubo", "n": 6, "data": {...}})
print(cc.wait(job["job_id"]))
```

## Agent-friendly surface

- `estimate(problem)` — free exact quote (mode, backend, price, runtime)
- `simulate(problem)` — free dry-run: feasibility + confidence before paying
- `preset("portfolio" | "bin-packing" | "routing", constraints)` — plain-language
  constraints → ready-to-solve QUBO (free)
- `optimize(problem, mode="auto", webhook_url=...)` — pays, submits, returns job
- `job(id)` / `wait(id)` — poll with signed execution receipts on completion

## Budget guardrail

```python
rec = cc.estimate(problem)["recommendation"]
if rec["cortexcloud_price_usd"] > 0.25:
    raise SystemExit("over budget")
```

See `docs/AGENT_INTEGRATION_GUIDE.md` in the repo for CrewAI/LangGraph wiring,
error handling, and webhook setup.
