#!/usr/bin/env bun
/**
 * Reference x402 v2 buyer for CortexCloud — copy-paste, TypeScript mirror of
 * examples/paid_client.py.
 *
 *   bun add @x402/fetch @x402/evm viem
 *   bun add -d @types/bun            # only if you type-check with tsc
 *   CC_PRIVATE_KEY=0x... bun run examples/paid_client.ts
 *
 * Default target: POST /v1/data/token-price ($0.004). Override with
 * CC_URL / CC_PATH / CC_BODY.
 *
 * Why @x402/fetch and not x402-fetch: the npm package `x402-fetch` implements
 * x402 **v1** (deprecated) and sends the v1 `X-PAYMENT` header. This API
 * settles x402 v2 (`PAYMENT-SIGNATURE`), so the client uses the v2 successor
 * `@x402/fetch` + `@x402/evm`.
 */
import { wrapFetchWithPaymentFromConfig } from "@x402/fetch";
import { ExactEvmScheme } from "@x402/evm";
import { privateKeyToAccount } from "viem/accounts";

const BASE_URL = process.env.CC_URL ?? "https://api.cortexcloud.org";
const PATH = process.env.CC_PATH ?? "/v1/data/token-price";
const BODY: Record<string, unknown> = JSON.parse(
  process.env.CC_BODY ?? '{"id":"ethereum"}',
);
const NETWORK = "eip155:8453"; // Base mainnet, USDC

const privateKey = process.env.CC_PRIVATE_KEY;
if (!privateKey) {
  console.error("set CC_PRIVATE_KEY=0x... (Base wallet with USDC + a little ETH)");
  process.exit(1);
}

const account = privateKeyToAccount(privateKey as `0x${string}`);
console.log(`buyer: ${account.address}`);

const url = BASE_URL + PATH;
const init: RequestInit = {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(BODY),
};

// 1. Unpaid probe: show the exact 402 terms before signing anything.
const probe = await fetch(url, init);
if (probe.status !== 402) {
  console.error(`expected 402, got ${probe.status}: ${(await probe.text()).slice(0, 300)}`);
  process.exit(1);
}
const challenge = (await probe.json()) as {
  accepts?: Array<{ amount: string; payTo: string; network: string }>;
};
const accept = challenge.accepts?.[0];
if (!accept) {
  console.error("402 challenge carried no accepts[] entry");
  process.exit(1);
}
console.log(
  `challenge: $${(Number(accept.amount) / 1e6).toFixed(6)} -> ${accept.payTo.slice(0, 10)}... on ${accept.network}`,
);

// 2. Paid call: the wrapper answers the 402 and replays with PAYMENT-SIGNATURE.
const fetchWithPayment = wrapFetchWithPaymentFromConfig(fetch, {
  schemes: [{ network: NETWORK, client: new ExactEvmScheme(account) }],
});

const response = await fetchWithPayment(url, init);
console.log(`paid call: ${response.status}`);

if (response.status === 200) {
  const data = await response.json();
  console.log("RESULT:", JSON.stringify(data, null, 1).slice(0, 600));
  const receipt = response.headers.get("x-payment-response");
  if (receipt) console.log("SETTLED — receipt:", receipt.slice(0, 120));
} else {
  console.error("FAILED:", (await response.text()).slice(0, 400));
  process.exit(1);
}
