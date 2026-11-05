# CortexCloud Examples — real, runnable, free-to-try

Each script POSTs a real problem to the live API. `*_estimate.sh` scripts are
**free** (recommended mode/backend/price). `solve.py` shows the full paid
x402 flow (needs a wallet funded with USDC on Base).

## Scheduling — 4 jobs, pairwise conflicts
```bash
bash scheduling_estimate.sh
```
## Portfolio selection — pick 5 of 8 assets
```bash
bash portfolio_estimate.sh
```
## Delivery routing — 6 stops, pairwise travel costs
```bash
bash routing_estimate.sh
```
## Full paid flow (Python)
```bash
python3 solve.py          # estimate -> 402 challenge -> sign -> solve -> poll
```
Requires `python3`, `requests`, a Base wallet private key (env `WALLET_KEY`),
and USDC on Base. See the x402 docs: https://x402.org


## Monthly prepaid subscription
```bash
pip install cortexcloud
CC_PRIVATE_KEY=0x... CC_PLAN=trading-pro python3 subscription_client.py
```
The subscription is paid manually in USDC on Base. The script prints the API
key once; store it securely. Renewals are manual and never trigger automatic
wallet withdrawals.

## Trading-bot data access with credits
```bash
CORTEXCLOUD_API_KEY=cx_live_... TRADING_WALLET=0x... CHAIN=base \
  python3 trading_bot_data.py
```
Add CC_PRIVATE_KEY to allow x402 per-call overages when prepaid credits are
exhausted. Without it, exhausted credits return the normal 402 challenge.
