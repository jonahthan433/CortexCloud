# CortexCloud — Your first paid API call (in under 5 minutes)

Cheapest paid endpoints: **Data** and **Automation** at **$0.004 / call** (USDC on Base, no API key).
This guide takes you from zero to one successful paid call. No signup, no key — just a Base wallet with ~$0.01 USDC.

## What you need
- A Base wallet (any EVM wallet) with a little USDC (e.g. `$0.01`).
- Node.js installed.

## Install the x402 client
```bash
npm init -y && npm install x402-fetch viem dotenv
```

## Paid call #1 — Data: token price (Automation/Data, $0.004)
Create `.env`:
```
EVM_PRIVATE_KEY=0xYOUR_PRIVATE_KEY
```
Create `call.mjs`:
```js
import { config } from "dotenv";
config();
import { createWalletClient, http } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { wrapFetchWithPayment } from "x402-fetch";
import { base } from "viem/chains";

const account = privateKeyToAccount(process.env.EVM_PRIVATE_KEY);
const client = createWalletClient({ account, chain: base, transport: http() });
const fetch = wrapFetchWithPayment(globalThis.fetch, client);

// Data: spot token price — $0.004
const r = await fetch("https://api.cortexcloud.org/v1/data/token-price", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ chain: "ethereum", id: "ethereum" }),
});
console.log(await r.json());
```
Run: `node call.mjs`. x402-fetch auto-pays the 402 and returns the price. **That's your first paid call.**

## Paid call #2 — Automation: call any API safely ($0.004)
Replace the body with an outbound HTTP request (SSRF-guarded egress — no shell/fs):
```js
const r = await fetch("https://api.cortexcloud.org/v1/automation/http-request", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ method: "GET", url: "https://api.cortexcloud.org/v1/capabilities" }),
});
console.log(await r.json());
```

## Why these two?
- **Data** — instant, tangible value (token prices, balances, gas, tx history). Great for agents that need on-chain context.
- **Automation** — let an agent hit any external API through a paid, safe egress. No keys to manage; the call is the unit of payment.

## Free before you pay
- `GET /v1/capabilities` — payment terms, limits.
- `POST /v1/automation/estimate` / `POST /v1/data` probes — free price preview.
- `POST /v1/examples` — full request/response schemas.

## Settlement
Every paid endpoint returns an x402 v2 `402` with exact USDC terms on Base (eip155:8453), asset USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`. The client signs and resends; you're billed per call. Nothing else to configure.

Base URL: https://api.cortexcloud.org
