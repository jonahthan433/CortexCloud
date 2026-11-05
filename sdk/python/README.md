# cortexcloud

CortexCloud On-Chain Data API client for AI agents and trading systems.
Supports x402 pay-per-call in USDC on Base and optional monthly prepaid
subscriptions with wallet-linked API keys and weighted credits. Subscription
renewal is manual; there are no automatic wallet withdrawals.

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

## Pay per call with x402

```python
cc = CortexCloud(private_key="0x...")   # Base wallet with USDC
price = cc.token_price("ethereum")      # CoinGecko id, $0.004
wallet = cc.wallet_intel("0x...")
```

Every x402 method handles the 402 challenge → EIP-712 sign → settlement flow.

## Monthly prepaid credits

```python
# Purchase or renew manually; the response contains a one-time API key.
buyer = CortexCloud(private_key="0x...")
purchase = buyer.subscribe("trading-pro")
api_key = purchase["api_key"]  # save securely; shown only once

# Use credits; if credits run out, include private_key for x402 overages.
cc = CortexCloud(api_key=api_key, private_key="0x...")
account = cc.billing_account()
usage = cc.billing_usage()
data = cc.token_balances("0x...", chain="base")
```

Plans: Starter $19/19,000 credits; Trading Pro $49/49,000 credits;
Agent Fleet $99/99,000 credits. One credit equals $0.001 of advertised API
price. Requests deduct credits first; when exhausted, x402 per-call payment
remains available. Renewals are manual.

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
