# x402 Discoverability — Status Checklist

Ground truth as of 2026-08-03 (verified against repo on CT105 + live site).

## T1 Bazaar diagnosis — DONE
- payTo wallet kind: **CDP-key-derived** — 0xab55b97638b202059eec3104c334dfc588018008 derives from CDP_WALLET_SECRET (keccak-256 of pubkey, verified MATCH:True against systemd + .env). Not an external EOA.
- EXTENSION-RESPONSES header: **not applicable to merchant**. x402 SDK (v2.14.0) reads it only as an optional *response-side* header (facilitator→client, base64 JSON, allowlist fields status/rejectedReason/reason/code) — see x402/http/facilitator_client.py:98. Merchant discovery surface = inline extensions.bazaar block in the 402 body + `payment-required` base64 header; both present.
- Cloudflare edge intermittently returns 530/error 1033 on .well-known + paid routes (flaky since before changes; origin OK via localhost).

## T2 discoverable metadata — DONE (this session)
- `discoverable: True` added to 402 challenge extensions.bazaar (app/middleware/x402.py L466), verified live in challenge body via origin localhost.
- Per-route INPUT_SCHEMAS (middleware L121+) + INPUT_EXAMPLES/OUTPUT_EXAMPLES + bazaar schema/example blocks confirmed in challenge.
- Committed: 2a707f5 parent + "x402: mark endpoints discoverable in bazaar extension + status checklist".

## T3 /.well-known/x402.json — DONE
- Live 200, 8 top keys, 27 endpoints, merchant_wallet = CDP wallet 0xab55…8008, facilitator api.cdp.coinbase.com/platform/v2/x402.
- NOTE: no `discoverable` flag in the well-known manifest itself — that flag lives in per-route 402 challenges. Manifest is complete for discovery.

## T4 /llms.txt — DONE
- Live 200 text/plain; generated from model registry + ROUTE_PRICING.

## T5 dashboard zero-value finding — NOT started
- /v1/dashboard/analytics + /requests exist; zero-value question (hydration vs gap) never diagnosed.

## T6 catalog/registration payloads — NOT started
- No branches/PRs/registration payloads found.
