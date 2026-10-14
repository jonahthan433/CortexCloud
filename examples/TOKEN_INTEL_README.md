# Token Intelligence integration examples

Copy-paste agent workflows for CortexCloud's on-chain intelligence surface.
Every example is ONE paid x402 call (USDC on Base) — no API keys, no signup.

```bash
pip install "x402" eth-account httpx
export TEST_BUYER_KEY=0x...        # Base wallet with USDC + a little ETH
python examples_token_intel.py risk     # screen an ERC-20 ($0.020)
python examples_token_intel.py wallet   # profile a counterparty ($0.006)
python examples_token_intel.py whale    # watch a whale wallet ($0.030)
python examples_token_intel.py cross    # one contract across chains ($0.040)
python examples_token_intel.py price    # spot price primitive ($0.004)
```

## Recurring agent workflows these plug into

- **Pre-trade screening loop** — `risk` before every buy signal, `whale` before
  every position change. Cache-friendly (60s TTL on risk), so a monitoring
  agent polling every minute pays once per minute, not once per token.
- **Counterparty trust check** — `wallet` before sending funds or trusting a
  signal provider; run on every new address an agent interacts with.
- **Cross-chain routing** — `cross` to pick the cheapest/most liquid chain for
  a bridge or swap, one call instead of five.

## Pricing (transparent, from the served spec)

| Endpoint | Price | Measured upstream cost | Margin |
|---|---|---|---|
| `/v1/data/token-price` | $0.004 | $0.000000 (CoinGecko free tier) | $0.004 |
| `/v1/data/token-risk` | $0.020 | $0.000045 (4 Alchemy calls) | $0.019955 |
| `/v1/data/wallet-intel` | $0.006 | $0.000045 (2 Alchemy calls) | $0.005955 |
| `/v1/data/whale-alerts` | $0.030 | $0.000034 (3 Alchemy calls) | $0.029966 |
| `/v1/data/cross-chain-compare` | $0.040 | $0.000068 (2 Alchemy calls/chain) | $0.039932 |

Every paid response carries `price_usd`, `provider_cost_usd`, and `margin_usd`
so the agent can verify the economics before it pays.

## Every claim carries evidence

`token-risk` returns a `verdict` (low/medium/high) plus an `evidence` array
where each entry names the check and its source
(`{"check": "contract_exists", "source": "alchemy eth_getCode", "result": true}`).
An agent can re-verify any claim independently — nothing is asserted without a
sourceable check.

## Full reference buyer

`examples/paid_client.py` in the repo root is the same flow with
`CC_PATH` / `CC_BODY` / `CC_URL` env overrides.
