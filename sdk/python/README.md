# cortexcloud

Agent-native, pay-per-call API platform settled by **x402** (USDC on Base). Six
categories: Optimization/Quantum, AI, Research, Data, Automation, MCP. No API
keys — free endpoints need no wallet; paid endpoints settle per call.

```bash
pip install cortexcloud
```

## Quickstart (free)

```python
from cortexcloud import CortexCloud

cc = CortexCloud()                       # free calls need no wallet
est = cc.estimate({"problem_type": "qubo", "n": 6, "data": {...}})
print(est["recommendation"]["mode"], est["recommendation"]["cortexcloud_price_usd"])
```

## Paid call (any category)

```python
cc = CortexCloud(private_key="0x...")   # Base wallet with USDC
price = cc.token_price("ETH")            # Data  $0.004
ans   = cc.research_answer("best L2 for USDC settlement?")  # Research $0.012
job   = cc.optimize({"problem_type": "qubo", "n": 6, "data": {...}})  # Opt $0.05
print(cc.wait(job["job_id"]))
```

Every paid method handles the x402 v2 flow automatically: 402 challenge →
EIP-712 sign → settle → JSON. You never touch the payment header.

## Surfaces

- `estimate / simulate / trial` — free quote, dry-run, no-wallet solve
- `optimize(problem, mode, webhook_url)` — Optimization/Quantum ($0.05+)
- `token_price / token_balances / block / gas_oracle` — Data ($0.004)
- `research_search / research_answer` — Research ($0.006 / $0.012)
- `http_request(url, method, ...)` — Automation ($0.004)
- `chat(prompt)` — AI ($0.004)
- `pay(method, path, json)` — generic escape hatch for any future paid route
- `job(id) / wait(id)` — poll with signed execution receipts

## Budget guardrail

```python
rec = cc.estimate(problem)["recommendation"]
if rec["cortexcloud_price_usd"] > 0.25:
    raise SystemExit("over budget")
```

`CortexCloud.demo()` runs the free path as a smoke check (no spend).
See `docs/AGENT_INTEGRATION_GUIDE.md` for CrewAI/LangGraph/MCP wiring.
