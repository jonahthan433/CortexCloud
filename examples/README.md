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
